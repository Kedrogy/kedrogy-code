"""Dependency-free contracts shared by the API, training and inference runtimes."""

import hashlib
import json
import unicodedata
from collections import Counter

LEGACY_POLICY = "reject-other-v1"
CONVERSION_VERSION = "single-label-choice-v2"
ARTIFACT_VERSION = 2
CONTRACT_VERSION = 1


class ContractError(ValueError):
    """A safe validation failure without annotation text or credentials."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def normalize_labels(value: str | list[str] | tuple[str, ...], *, policy=LEGACY_POLICY) -> tuple[str, ...]:
    """Preserve class order and case; support the legacy comma-separated input."""
    if policy not in (LEGACY_POLICY, CONVERSION_VERSION):
        raise ContractError("UNSUPPORTED_POLICY", "The annotation policy is not supported.")
    parts = value.split(",") if isinstance(value, str) else value
    if not isinstance(parts, (list, tuple)) or not (2 if policy == CONVERSION_VERSION else 1) <= len(parts) <= 100:
        raise ContractError("INVALID_LABELS", "Provide between 2 and 100 explicit classes for single-label classification.")
    labels = []
    for part in parts:
        if not isinstance(part, str):
            raise ContractError("INVALID_LABELS", "Every label must be a string.")
        label = part.strip()
        if (not label or len(label) > 100 or label.startswith("-") or "," in label
                or any(unicodedata.category(c).startswith("C") for c in part)):
            raise ContractError("INVALID_LABELS", "Labels must be nonempty, at most 100 characters, without commas, controls or a leading '-'.")
        if label == "OTHER" and policy == LEGACY_POLICY:
            raise ContractError("INVALID_LABELS", "OTHER is reserved for the current rejected-example conversion policy.")
        labels.append(label)
    if len(set(labels)) != len(labels):
        raise ContractError("INVALID_LABELS", "Labels must be distinct after trimming outer whitespace.")
    return tuple(labels)


def class_mapping(labels, *, artifact_version=1):
    """Artifact versions define class IDs independently of the HTTP envelope."""
    if type(artifact_version) is not int or artifact_version not in (1, 2):
        raise ContractError("UNSUPPORTED_ARTIFACT", "The artifact class-schema version is unsupported.")
    normalized = normalize_labels(labels, policy=LEGACY_POLICY if artifact_version == 1 else CONVERSION_VERSION)
    return ["OTHER", *normalized] if artifact_version == 1 else list(normalized)


def artifact_mapping(artifact):
    version = artifact.get("version")
    mapping = class_mapping(artifact.get("labels"), artifact_version=version)
    if type(artifact.get("class_schema_version", 1)) is not int:
        raise ContractError("UNSUPPORTED_ARTIFACT", "The artifact class schema must be an integer.")
    if version == 1 and (artifact.get("conversion_policy", LEGACY_POLICY) != LEGACY_POLICY
                         or artifact.get("class_schema_version", 1) != 1):
        raise ContractError("UNSUPPORTED_ARTIFACT", "The legacy artifact policy and class schema are incompatible.")
    if version == 2 and (artifact.get("conversion_policy") != CONVERSION_VERSION
                        or artifact.get("class_schema_version") != 2):
        raise ContractError("UNSUPPORTED_ARTIFACT", "The artifact policy and class schema are incompatible.")
    return mapping


def training_examples(rows: list[dict], labels, *, dataset_id: int, policy=CONVERSION_VERSION):
    """One conversion for preflight and training; rejects never imply a class."""
    if policy != CONVERSION_VERSION:
        raise ContractError("ANNOTATION_POLICY_REVIEW", "Legacy binary answers require review. Create a dataset using explicit class choices; rejected suggestions cannot determine a target.")
    labels = normalize_labels(labels, policy=policy)
    counts, class_counts = Counter(), Counter()
    hashes, examples, identities, failures = [], [], {}, []
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("INVALID_ANNOTATIONS", "An annotation is not a JSON object.")
        try:
            encoded = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        except (TypeError, ValueError):
            raise ContractError("INVALID_ANNOTATIONS", "An annotation contains invalid JSON values.") from None
        hashes.append(hashlib.sha256(encoded).hexdigest())
        answer = row.get("answer")
        if not isinstance(answer, str) or answer not in {"accept", "reject", "ignore"}:
            counts["invalid"] += 1
            failures.append("INVALID_ANNOTATIONS")
            continue
        counts[answer] += 1
        meta = row.get("meta")
        if not isinstance(meta, dict) or meta.get("_annotation_policy") != policy:
            counts["invalid"] += 1
            failures.append("ANNOTATION_POLICY_REVIEW")
            continue
        if answer != "accept":
            continue
        choices = row.get("accept")
        schema = meta.get("_class_schema")
        if (not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], str)
                or choices[0] not in labels or not isinstance(schema, list)
                or any(not isinstance(label, str) for label in schema)
                or len(schema) != len(labels) or set(schema) != set(labels)):
            counts["invalid"] += 1
            failures.append("INVALID_ANNOTATION_LABELS")
            continue
        text = row.get("text")
        identity = (meta.get("_source_id"), meta.get("_record_id"))
        digest = meta.get("_content_digest")
        if (not isinstance(text, str) or not text.strip()
                or any(not isinstance(part, str) or not part or len(part) > 512 for part in identity)
                or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            counts["invalid"] += 1
            failures.append("INVALID_ANNOTATIONS")
            continue
        label = choices[0]
        content = (text, label, digest)
        if identity in identities:
            if identities[identity] != content:
                counts["conflicting"] += 1
                failures.append("CONFLICTING_ANNOTATIONS")
            else:
                counts["duplicate_accepted"] += 1
            continue
        identities[identity] = content
        class_counts[label] += 1
        examples.append({"label": labels.index(label), "text": text})
    if failures:
        code = "ANNOTATION_POLICY_REVIEW" if "ANNOTATION_POLICY_REVIEW" in failures else failures[0]
        raise ContractError(code, f"Annotation validation failed: {counts['invalid']} invalid and {counts['conflicting']} conflicting records. Review policy, source identity and explicit choices.")
    if len(examples) < 4 or any(class_counts[label] < 2 for label in labels):
        raise ContractError("INSUFFICIENT_CLASS_SUPPORT", "At least two distinct accepted records per configured class and four in total are required. Reject and skip do not supply training targets.")
    digest = hashlib.sha256(json.dumps({"dataset_id": dataset_id, "policy": policy,
        "class_schema": labels, "rows": sorted(hashes)}, sort_keys=True).encode()).hexdigest()
    summary = {"fingerprint": digest, "dataset_id": dataset_id, "policy": policy,
        "class_schema_version": 2, "artifact_version": 2, "labels": list(labels),
        "total": len(rows), "usable": len(examples), "accepted": counts["accept"],
        "rejected": counts["reject"], "ignored": counts["ignore"], "invalid": 0, "conflicting": 0,
        "needs_review": counts["reject"], "duplicate_accepted": counts["duplicate_accepted"],
        "label_counts": {label: class_counts[label] for label in labels}}
    return examples, summary


def annotation_summary(rows: list[dict], labels, *, dataset_id: int, policy=CONVERSION_VERSION):
    return training_examples(rows, labels, dataset_id=dataset_id, policy=policy)[1]


def legacy_annotation_preview(rows, labels):
    """Counts only; never infer the opposite class or alter stored answers."""
    labels = normalize_labels(labels, policy=CONVERSION_VERSION)
    counts = Counter()
    for row in rows:
        if not isinstance(row, dict):
            counts["invalid"] += 1
        elif row.get("answer") == "accept" and row.get("label") in labels:
            counts["accepted_exact_label"] += 1
        elif row.get("answer") == "reject":
            counts["requires_reannotation"] += 1
        elif row.get("answer") == "ignore":
            counts["skipped"] += 1
        else:
            counts["unresolved"] += 1
    return {"total": len(rows), "target_policy": CONVERSION_VERSION, "counts": dict(counts),
            "applied": False, "historical_answers_modified": False}


def validate_prediction(value, *, labels, training_run_id: str, serving_run_id: str, artifact_version=1) -> dict:
    """Bind an inference result to the exact loaded version and checkpoint mapping."""
    mapping = class_mapping(labels, artifact_version=artifact_version)
    if not isinstance(value, dict):
        raise ContractError("INVALID_INFERENCE_RESPONSE", "The inference response is invalid.")
    class_id = value.get("class_id")
    if (type(class_id) is not int or not 0 <= class_id < len(mapping)
            or value.get("label") != mapping[class_id]
            or type(value.get("contract_version")) is not int
            or value.get("contract_version") != CONTRACT_VERSION
            or value.get("training_run_id") != training_run_id
            or value.get("serving_run_id") != serving_run_id
            or (artifact_version == 1 and (type(value.get("class_schema_version", 1)) is not int
                                          or value.get("class_schema_version", 1) != 1))
            or (artifact_version == 2 and (type(value.get("class_schema_version")) is not int
                                          or value["class_schema_version"] != 2))):
        raise ContractError("INVALID_INFERENCE_RESPONSE", "The inference response does not match the requested model version.")
    keys = ["class_id", "label", "contract_version", "training_run_id", "serving_run_id"]
    if artifact_version == 2:
        keys.append("class_schema_version")
    return {key: value[key] for key in keys}
