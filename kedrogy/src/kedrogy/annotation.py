"""One durable annotation slot per namespace with independent health observation."""

import os
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import manifests
from .dataset_bindings import record_created_binding, verify_binding
from .kubernetes import OperationError, command, service_tunnel
from .launch_config import LaunchConfigError, validate_dataset
from .models import AnnotationRun, AnnotationSlot, DjangoDataset
from .operation_control import (
    acquire,
    delete_exact,
    owned,
    release,
    request_key,
    require_dataset,
    resource_ref,
)
from .training import _ensure, _get

LIVE = ("STARTING", "READY", "UNAVAILABLE", "STOPPING")
OBSERVABLE = ("STARTING", "READY", "UNAVAILABLE")


def start_annotation(dataset_id, key=None):
    from .tasks import new_dataset_task

    key = request_key(key)
    with transaction.atomic():
        slot, _ = AnnotationSlot.objects.get_or_create(namespace=settings.KEDROGY_NAMESPACE)
        slot = AnnotationSlot.objects.select_for_update().get(pk=slot.pk)
        dataset = DjangoDataset.objects.select_for_update().get(pk=dataset_id)
        previous = dataset.annotation_runs.filter(idempotency_key=key).first()
        if previous:
            return previous, False
        require_dataset(dataset)
        if slot.run_id:
            error = OperationError("ANNOTATION_ACTIVE", "Stop the current annotation session before starting another one.")
            error.run_id = str(slot.run_id)
            raise error
        try:
            cfg = validate_dataset(dataset.to_dict())
        except LaunchConfigError as error:
            raise OperationError("INVALID_CONFIGURATION", str(error)) from error
        if dataset.source_config is None:
            dataset.source_config = settings.KEDROGY_SOURCES[cfg.table_name]
            dataset.save(update_fields=["source_config"])
        run = AnnotationRun.objects.create(dataset=dataset, namespace=slot.namespace, idempotency_key=key,
            snapshot={"dataset": dataset.to_dict(), "image": cfg.image})
        slot.run = run
        slot.save(update_fields=["run"])
        result = new_dataset_task.enqueue(str(run.id))
        run.task_id = str(result.id)
        run.save(update_fields=["task_id"])
        return run, True


def stop_annotation(dataset_id):
    with transaction.atomic():
        slot = AnnotationSlot.objects.select_for_update().filter(pk=settings.KEDROGY_NAMESPACE).first()
        DjangoDataset.objects.select_for_update().get(pk=dataset_id)
        if not slot or not slot.run_id:
            return None
        run = AnnotationRun.objects.select_for_update().get(pk=slot.run_id)
        if run.dataset_id != dataset_id:
            return None
        run.status = "STOPPING"
        if run.startup_status == "RUNNING":
            run.startup_status = "FAILED"
            run.startup_error = {"code": "ANNOTATION_STOPPED", "message": "Annotation was stopped before startup completed."}
        run.save(update_fields=["status", "startup_status", "startup_error"])
        return run


def public_session(run):
    if run is None:
        return {"id": None, "dataset_id": None, "status": "UNVERIFIED", "observed_at": None, "url": None, "error": None}
    status, error = run.status, run.error or None
    if status == "READY" and (run.observed_at is None or timezone.now() - run.observed_at > timedelta(seconds=settings.KEDROGY_ANNOTATION_FRESHNESS)):
        status = "UNAVAILABLE"
        error = {"code": "OBSERVATION_STALE", "message": "Annotation health has not been checked recently."}
    return {"id": str(run.pk), "dataset_id": run.dataset_id, "status": status,
            "observed_at": run.observed_at.isoformat() if run.observed_at else None,
            "url": settings.KEDROGY_ANNOTATION_URL if status == "READY" else None, "error": error}


def public_operation(run):
    return {"id": str(run.pk), "kind": "label", "status": run.startup_status,
            "is_finished": run.startup_status != "RUNNING", "logs": "", "error": run.startup_error or None,
            "step": "Annotation startup", "can_retry": False, "session": public_session(run),
            "return_value": {"dataset_id": run.dataset_id} if run.startup_status == "SUCCEEDED" else None}


def _owned(run, owner, statuses=OBSERVABLE):
    return owned(AnnotationRun, run.pk, owner, statuses) and AnnotationSlot.objects.filter(pk=run.namespace, run=run).exists()


def _observe(run, owner, status, error=None):
    updates = {"status": status, "error": error or {}, "observed_at": timezone.now()}
    if run.startup_status == "RUNNING":
        if status == "READY":
            updates.update(startup_status="SUCCEEDED", startup_error={})
        elif timezone.now() > run.created_at + timedelta(seconds=settings.KEDROGY_ANNOTATION_TIMEOUT):
            updates.update(status="UNAVAILABLE", startup_status="FAILED", startup_error=error or {"code": "ANNOTATION_TIMEOUT", "message": "Annotation startup timed out. Stop the session before retrying."})
    AnnotationRun.objects.filter(pk=run.pk, lease_owner=owner, status__in=OBSERVABLE).update(**updates)


@contextmanager
def health_url(run):
    name = f"annotation-{run.id}"
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        yield f"http://{name}.{run.namespace}.svc.cluster.local:8081/readyz"
    else:
        with service_tunnel(f"service/{name}", 8081, path="/readyz", namespace=run.namespace) as url:
            yield url


def _check_http(run):
    try:
        with health_url(run) as url:
            response = requests.get(url, timeout=(5, 5))
            response.raise_for_status()
            value = response.json()
        if (not isinstance(value, dict) or value.get("ready") is not True
                or value.get("annotation_run_id") != str(run.pk)
                or value.get("dataset_key") != run.snapshot["dataset"]["dataset_name"]):
            raise ValueError
    except (requests.RequestException, ValueError):
        raise OperationError("ANNOTATION_UNAVAILABLE", "The annotation application has not reported the expected ready identity.") from None


def _route(run, owner, *, stop=False):
    # Read the Kubernetes version before the ownership check. Stop advances it,
    # fencing any delayed write prepared by an older observation.
    current = _get("service", "prodigy-svc", run.namespace)
    if current is None:
        if stop:
            return _owned(run, owner, ("STOPPING",))
        raise OperationError("ANNOTATION_ROUTE_MISSING", "Install the configured annotation Service before starting a session.")
    if not _owned(run, owner, ("STOPPING",) if stop else OBSERVABLE):
        return False
    identity = current["metadata"].get("labels", {}).get("kedrogy/annotation-id")
    if identity not in (None, "stopped", str(run.pk)):
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "The annotation route belongs to another session. Review it before continuing.")
    if stop:
        current["metadata"].setdefault("annotations", {})["kedrogy/annotation-fence"] = str(uuid.uuid4())
    if stop and identity is None:
        # Advance the version to fence a prepared old write without disconnecting
        # a legacy route this operation has never owned.
        command(["replace", "-f", "-"], namespace=run.namespace, document=current)
        return True
    desired = "stopped" if stop else str(run.pk)
    current["metadata"].setdefault("labels", {})["kedrogy/annotation-id"] = desired
    current["spec"]["selector"] = {"app.kubernetes.io/name": "prodigy", "kedrogy/annotation-id": desired}
    command(["replace", "-f", "-"], namespace=run.namespace, document=current)
    return True


def _stop(run, owner):
    if not _route(run, owner, stop=True):
        return
    # Include resources created immediately before a crashed worker recorded them.
    refs = {r["name"] + r["kind"]: r for r in run.resources}
    for kind in ("Deployment", "Service", "ConfigMap"):
        name = f"annotation-{run.pk}"
        current = _get(kind, name, run.namespace)
        if current:
            if current["metadata"].get("labels", {}).get("kedrogy/annotation-id") != str(run.pk):
                raise OperationError("RESOURCE_IDENTITY_CHANGED", "An annotation resource has another owner.")
            refs.setdefault(name + kind, resource_ref(current, run.namespace))
    for ref in sorted(refs.values(), key=lambda r: {"Deployment": 0, "Service": 1, "ConfigMap": 2}[r["kind"]]):
        if not _owned(run, owner, ("STOPPING",)) or not delete_exact(ref):
            return
    pods = command(["get", "pods", "-l", f"kedrogy/annotation-id={run.id}", "-o", "json"], namespace=run.namespace, json_output=True)
    if pods.get("items"):
        return
    with transaction.atomic():
        slot = AnnotationSlot.objects.select_for_update().get(pk=run.namespace)
        current = AnnotationRun.objects.select_for_update().get(pk=run.pk)
        if slot.run_id == run.id and current.lease_owner == owner and current.status == "STOPPING":
            current.status = "STOPPED"
            current.stopped_at = timezone.now()
            current.error = {}
            current.save(update_fields=["status", "stopped_at", "error"])
            slot.run = None
            slot.save(update_fields=["run"])


def _advance(run, owner):
    if run.status == "STOPPING":
        return _stop(run, owner)
    if run.startup_status == "FAILED":
        return
    legacy = _get("deployment", "prodigy", run.namespace)
    if legacy and legacy.get("spec", {}).get("replicas", 1):
        raise OperationError("LEGACY_ANNOTATION_ACTIVE", "An unmanaged annotation Deployment exists. Review and stop it explicitly before starting a managed session.")
    if run.snapshot["image"] not in settings.KEDROGY_ML_IMAGE_ALIASES | {settings.KEDROGY_ML_IMAGE}:
        raise OperationError("IMAGE_NO_LONGER_APPROVED", "The pinned annotation image is no longer approved.")
    cfg = replace(validate_dataset(run.snapshot["dataset"]), image=run.snapshot["image"])
    documents = manifests.annotation_revision(cfg, run.dataset_id, str(run.id))
    for document in documents:
        if not _owned(run, owner):
            return
        known = next((r for r in run.resources if r["kind"] == document["kind"]), None)
        current = _get(document["kind"], document["metadata"]["name"], run.namespace) if known else _ensure(document, run.namespace)
        if (not current or current["metadata"].get("labels", {}).get("kedrogy/annotation-id") != str(run.pk)
                or (known and current["metadata"]["uid"] != known["uid"])):
            raise OperationError("RESOURCE_IDENTITY_CHANGED", "An annotation resource disappeared or was replaced. Stop and review this session.")
        if not known:
            ref = resource_ref(current, run.namespace)
            ref["generation"] = current["metadata"].get("generation", 0)
            run.resources.append(ref)
            AnnotationRun.objects.filter(pk=run.pk, lease_owner=owner).update(resources=run.resources)
        if document["kind"] == "Deployment":
            ref = next(r for r in run.resources if r["kind"] == "Deployment")
            status = current.get("status", {})
            if current["metadata"].get("generation") != ref["generation"]:
                raise OperationError("RESOURCE_IDENTITY_CHANGED", "The annotation Deployment was modified outside this session.")
            if (status.get("observedGeneration", 0) < ref["generation"] or status.get("readyReplicas") != 1
                    or status.get("updatedReplicas") != 1 or status.get("replicas") != 1):
                _observe(run, owner, "STARTING" if run.startup_status == "RUNNING" else "UNAVAILABLE")
                return
    _check_http(run)
    if not _owned(run, owner):
        return
    dataset = DjangoDataset.objects.get(pk=run.dataset_id)
    if dataset.binding_state != "BOUND":
        record_created_binding(dataset)
        dataset.refresh_from_db()
    verify_binding(dataset)
    if not _route(run, owner):
        return
    _observe(run, owner, "READY")


def advance_annotation(identifier):
    run, owner = acquire(AnnotationRun, identifier, LIVE)
    if owner is None:
        return run
    try:
        _advance(run, owner)
    except (OperationError, LaunchConfigError) as error:
        public = error.public() if isinstance(error, OperationError) else {"code": "INVALID_CONFIGURATION", "message": str(error)}
        if run.status == "STOPPING":
            AnnotationRun.objects.filter(pk=run.pk, lease_owner=owner).update(error=public)
        else:
            _observe(run, owner, "UNAVAILABLE", public)
    finally:
        release(AnnotationRun, run.pk, owner)
    return AnnotationRun.objects.get(pk=run.pk)
