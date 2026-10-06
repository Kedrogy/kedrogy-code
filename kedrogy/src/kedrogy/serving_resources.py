"""Immutable serving intents and UID-bound resources, including crash recovery."""

import copy
import hashlib
import json
import uuid

from .kubernetes import OperationError, command
from .training import _get

LAYOUT = "run-owned-v2"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def make_plan(run, documents):
    token = str(uuid.uuid4())
    labels = {"kedrogy/serving-id": str(run.id), "app.kubernetes.io/managed-by": "kedrogy"}
    resources = []
    for document in documents:
        document = copy.deepcopy(document)
        document["metadata"]["namespace"] = run.namespace
        document["metadata"].setdefault("labels", {}).update(labels)
        document["metadata"]["annotations"] = {"kedrogy/creation-intent": token}
        resources.append({"kind": document["kind"], "name": document["metadata"]["name"],
                          "uid": "", "document": document, "fingerprint": digest(document)})
    name = f"serve-owner-{run.id}"
    anchor = {"apiVersion": "v1", "kind": "ConfigMap", "immutable": True,
              "metadata": {"name": name, "namespace": run.namespace, "labels": labels},
              "data": {"intent": token, "spec": digest(resources), "run": str(run.id)}}
    return {"version": 2, "namespace_uid": "", "anchor": {"kind": "ConfigMap", "name": name,
            "uid": "", "document": anchor}, "resources": resources}


def service_name(run):
    if run.resource_layout == LAYOUT:
        return next(ref["name"] for ref in run.resource_plan["resources"] if ref["kind"] == "Service")
    return f"serve-svc-{run.model_id}"


def namespace_uid(namespace):
    value = _get("namespace", namespace, namespace)
    if value is None:
        raise OperationError("SERVING_NAMESPACE_LOST", "The serving namespace is unavailable.")
    return value["metadata"]["uid"]


def check_namespace(run):
    recorded = run.resource_plan.get("namespace_uid")
    if not recorded or namespace_uid(run.namespace) != recorded:
        raise OperationError("SERVING_CLUSTER_CHANGED", "The cluster or namespace identity changed. Review the serving resources.")


def desired(run, ref):
    document = copy.deepcopy(ref["document"])
    if ref["kind"] != "ConfigMap":
        anchor = run.resource_plan["anchor"]
        if not anchor["uid"]:
            raise OperationError("SERVING_IDENTITY_MISMATCH", "The serving ownership anchor is not established.")
        document["metadata"]["ownerReferences"] = [{"apiVersion": "v1", "kind": "ConfigMap",
            "name": anchor["name"], "uid": anchor["uid"]}]
    return document


def _contains(actual, expected):
    """Ignore API-defaulted map keys, but compare application-owned lists exactly."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _contains(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_contains(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def verify(run, ref, current):
    if ref["uid"] and current.get("metadata", {}).get("uid") != ref["uid"]:
        raise OperationError("SERVING_IDENTITY_MISMATCH", "A serving resource was replaced. It was not modified.")
    if not _contains(current, desired(run, ref)):
        raise OperationError("SERVING_IDENTITY_MISMATCH", "A serving resource conflicts with its saved ownership or specification. It was not modified.")
    if current["metadata"].get("deletionTimestamp"):
        raise OperationError("SERVING_LOST", "A serving resource is being deleted. Stop and launch a new version.")
    if ref.get("generation") is not None and current["metadata"].get("generation") != ref["generation"]:
        raise OperationError("SERVING_IDENTITY_MISMATCH", "The serving resource was changed outside its saved revision.")


def create_or_observe(run, ref, authorized):
    current = _get(ref["kind"], ref["name"], run.namespace)
    if current is None:
        if ref["uid"]:
            raise OperationError("SERVING_LOST", "A recorded serving resource was removed. Stop and launch a new version.")
        if not authorized():
            return None
        try:
            current = command(["create", "-f", "-", "-o", "json"], namespace=run.namespace,
                              document=desired(run, ref), json_output=True)
        except OperationError as error:
            if error.code != "RESOURCE_EXISTS":
                raise
            current = _get(ref["kind"], ref["name"], run.namespace)
            if current is None:
                raise
    verify(run, ref, current)
    return current


def inventory(run):
    """Return proven identities; never adopt a legacy Service using labels alone."""
    if run.resource_layout != LAYOUT:
        refs = [("Deployment", f"serve-{run.model_id}", run.deployment_uid),
                ("Service", f"serve-svc-{run.model_id}", "")]
        result = []
        for kind, name, uid in refs:
            value = _get(kind, name, run.namespace)
            if value is not None:
                if not uid or value["metadata"]["uid"] != uid:
                    raise OperationError("SERVING_OWNERSHIP_REVIEW", "Legacy serving ownership requires an explicit resource review.")
                result.append({"kind": kind, "name": name, "namespace": run.namespace, "uid": uid})
        return result
    if not run.resource_plan.get("namespace_uid"):
        return []  # No external create is authorized before this is persisted.
    check_namespace(run)
    result = []
    anchor = run.resource_plan["anchor"]
    for ref in [anchor, *run.resource_plan["resources"]]:
        value = _get(ref["kind"], ref["name"], run.namespace)
        if value is None:
            continue
        # Deleting a known UID remains safe even if its spec was subsequently edited.
        if ref["uid"]:
            if value["metadata"]["uid"] != ref["uid"]:
                raise OperationError("SERVING_IDENTITY_MISMATCH", "A serving resource was replaced and was not removed.")
        else:
            verify(run, ref, value)
            # A late anchor create may have completed after Stop invalidated its writer.
            if ref is anchor:
                anchor["uid"] = value["metadata"]["uid"]
        result.append({"kind": ref["kind"], "name": ref["name"], "namespace": run.namespace,
                       "uid": value["metadata"]["uid"]})
    return result
