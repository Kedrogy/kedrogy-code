"""Small shared guards for durable operations; external calls stay outside locks."""

import re
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .kubernetes import OperationError, command
from .training import _get

LEASE_SECONDS = 360


def request_key(value=None):
    value = value or str(uuid.uuid4())
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise OperationError("INVALID_REQUEST_KEY", "Use at most 128 ASCII letters, digits, or ._:-.")
    return value


def require_dataset(dataset, *, allow_retired=False):
    if dataset.deletion_pending or (dataset.retired_at and not allow_retired):
        raise OperationError("DATASET_BUSY", "The dataset is being deleted or has been retired.")
    if dataset.annotations_deleted:
        raise OperationError("DATASET_UNRESOLVED", "These annotations were deleted. Create a new dataset to annotate again.")


def acquire(model, identifier, statuses):
    with transaction.atomic():
        run = model.objects.select_for_update().get(pk=identifier)
        now = timezone.now()
        if run.status not in statuses or (run.lease_until and run.lease_until > now):
            return run, None
        owner = uuid.uuid4()
        run.lease_owner = owner
        run.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        run.save(update_fields=["lease_owner", "lease_until"])
        return run, owner


def release(model, identifier, owner):
    model.objects.filter(pk=identifier, lease_owner=owner).update(lease_owner=None, lease_until=None)


def owned(model, identifier, owner, statuses):
    return model.objects.filter(pk=identifier, lease_owner=owner, lease_until__gt=timezone.now(), status__in=statuses).exists()


def resource_ref(document, namespace):
    return {"kind": document["kind"], "name": document["metadata"]["name"],
            "namespace": namespace, "uid": document["metadata"]["uid"]}


def delete_exact(ref):
    """Delete a recorded UID, then observe absence; never remove finalizers."""
    if "namespace_uid" in ref:
        from .serving_resources import namespace_uid
        if namespace_uid(ref["namespace"]) != ref["namespace_uid"]:
            raise OperationError("RESOURCE_IDENTITY_CHANGED", "The reviewed resource namespace changed.")
    current = _get(ref["kind"], ref["name"], ref["namespace"])
    if current is None:
        return True
    if current["metadata"]["uid"] != ref["uid"]:
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "A planned resource was replaced. Review the cleanup inventory.")
    if "spec_digest" in ref:
        from .legacy_cleanup import resource_digest
        if resource_digest(current) != ref["spec_digest"]:
            raise OperationError("RESOURCE_IDENTITY_CHANGED", "A reviewed legacy resource was modified. Review it again before cleanup.")
    kind = ref["kind"].lower()
    endpoint = {"deployment": "apis/apps/v1", "job": "apis/batch/v1"}.get(kind, "api/v1")
    plural = {"persistentvolumeclaim": "persistentvolumeclaims"}.get(kind, kind + "s")
    if not current["metadata"].get("deletionTimestamp"):
        preconditions = {"uid": ref["uid"]}
        if "spec_digest" in ref:
            preconditions["resourceVersion"] = current["metadata"]["resourceVersion"]
        command(["delete", "--raw", f'/{endpoint}/namespaces/{ref["namespace"]}/{plural}/{ref["name"]}', "-f", "-"],
                namespace=ref["namespace"], document={"apiVersion": "v1", "kind": "DeleteOptions",
                "preconditions": preconditions, "propagationPolicy": "Foreground"})
    return _get(ref["kind"], ref["name"], ref["namespace"]) is None
