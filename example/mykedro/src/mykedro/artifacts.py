"""Publish and validate locally loadable, immutable training artifacts."""

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path

from kedrogy_contracts import CONVERSION_VERSION, artifact_mapping, class_mapping

MANIFEST_NAME = "kedrogy-manifest.json"


def checksum(path: Path) -> str:
    """Hash a file without reading all weights into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_checkpoint(path: Path, labels: list[str], *, artifact_version: int = 1) -> dict:
    """Load the complete checkpoint offline and check a real forward pass."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if not path.is_dir() or path.is_symlink():
        raise ValueError("Checkpoint directory is missing or invalid.")
    files = sorted(p for p in path.rglob("*") if p.is_file())
    if any(p.is_symlink() for p in path.rglob("*")) or not files:
        raise ValueError("Checkpoint files are missing or invalid.")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        path, local_files_only=True, trust_remote_code=False, use_safetensors=True,
    )
    expected = dict(enumerate(class_mapping(labels, artifact_version=artifact_version)))
    if model.config.num_labels != len(expected) or model.config.id2label != expected:
        raise ValueError("Checkpoint labels do not match the training configuration.")
    if {str(key): int(value) for key, value in model.config.label2id.items()} != {
        label: index for index, label in expected.items()
    }:
        raise ValueError("Checkpoint label mappings are inconsistent.")
    model.eval()
    with torch.inference_mode():
        logits = model(**tokenizer("Artifact verification.", return_tensors="pt")).logits
    if tuple(logits.shape) != (1, len(expected)) or not torch.isfinite(logits).all().item():
        raise ValueError("Checkpoint failed the inference check.")
    return {str(p.relative_to(path)): checksum(p) for p in files if p.name != MANIFEST_NAME}


def emit_receipt(manifest: dict) -> None:
    """Write a bounded structured receipt to the Kubernetes termination message."""
    payload = json.dumps(manifest, sort_keys=True)
    if len(payload.encode()) > 3500:
        raise ValueError("Artifact manifest exceeds the receipt limit.")
    destination = Path(os.environ.get("KEDROGY_TERMINATION_LOG", "/dev/termination-log"))
    destination.write_text(payload, encoding="utf-8")


def publish_checkpoint(trainer, tokenizer, *, root: Path, run_id: str, attempt_id: str,
                       labels: list[str], image: str, artifact_version: int = 2, quality: dict | None = None) -> dict:
    """Save, reload, hash and atomically publish one attempt's checkpoint."""
    uuid.UUID(run_id)
    uuid.UUID(attempt_id)
    parent = root / "runs" / run_id / attempt_id
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".pending-{uuid.uuid4()}"
    target = parent / "artifact"
    trainer.save_model(str(staging))
    tokenizer.save_pretrained(staging)
    if quality is not None:
        (staging / "quality.json").write_text(json.dumps(quality, sort_keys=True, allow_nan=False))
    hashes = validate_checkpoint(staging, labels, artifact_version=artifact_version)
    manifest = {
        "version": artifact_version, "verified": True, "run_id": run_id, "attempt_id": attempt_id,
        "path": str(target.relative_to(root)), "labels": labels, "image": image,
        "files": hashes,
    }
    if quality is not None:
        # Keep the receipt bounded even for a large class schema.
        manifest["quality"] = {key: quality[key] for key in (
            "version", "split", "samples", "train_samples", "training_steps",
            "accuracy", "macro_f1", "majority_baseline", "warnings")}
    if artifact_version == 2:
        manifest |= {"conversion_policy": CONVERSION_VERSION, "class_schema_version": 2}
    if len(json.dumps(manifest, sort_keys=True).encode()) > 3500:
        raise ValueError("Artifact manifest exceeds the receipt limit before publication.")
    (staging / MANIFEST_NAME).write_text(json.dumps(manifest, sort_keys=True))
    # The run/attempt namespace prevents stale checkpoints from satisfying a new run.
    if target.exists():
        raise ValueError("This attempt already published a checkpoint.")
    staging.rename(target)
    emit_receipt(manifest)
    return manifest


def verify_artifact(path: Path, *, run_id: str, attempt_id: str, labels: list[str],
                    image: str, legacy: bool = False, artifact_version: int | None = None) -> dict:
    """Recheck saved files and identity; legacy import must be requested explicitly."""
    saved = {} if legacy else json.loads((path / MANIFEST_NAME).read_text())
    version = 1 if legacy else saved.get("version")
    if artifact_version is not None and artifact_version != version:
        raise ValueError("The artifact version does not match the saved training snapshot.")
    if not legacy:
        artifact_mapping(saved)
    hashes = validate_checkpoint(path, labels, artifact_version=version)
    if legacy:
        manifest = {"version": 1, "verified": True, "run_id": run_id,
                    "attempt_id": attempt_id, "path": "best", "labels": labels,
                    "image": image, "files": hashes, "legacy": True}
    else:
        manifest = saved
        expected_path = f"runs/{run_id}/{attempt_id}/artifact"
        for key, value in {"run_id": run_id, "attempt_id": attempt_id, "labels": labels,
                           "image": image, "path": expected_path, "files": hashes}.items():
            if manifest.get(key) != value:
                raise ValueError("Artifact identity or file checksums do not match.")
    emit_receipt(manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--artifact-version", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    verify_artifact(args.path, run_id=args.run_id, attempt_id=args.attempt_id,
                    labels=json.loads(args.labels), image=args.image, legacy=args.legacy, artifact_version=args.artifact_version)
