"""Durable serving revisions with leased observations and immutable startup results."""

import re
import uuid
from dataclasses import replace
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone

from . import manifests
from .kubernetes import OperationError, command
from .launch_config import LaunchConfigError, validate_dataset, validate_preprocessor
from .models import DjangoDataset, DjangoModel, ServingRun
from .training import published_artifact
from . import serving_resources as resources

LIVE = ("STARTING", "READY", "UNAVAILABLE", "STOPPING")


def public_serving(run: ServingRun | None) -> dict:
    """A GET reports stale observations conservatively without mutating records."""
    if run is None:
        return {"id": None, "status": "UNVERIFIED", "training_run_id": None,
                "labels": [], "class_schema_version": None, "conversion_policy": None, "observed_at": None, "error": None}
    status = run.status
    error = run.error or None
    if status == "READY" and (run.observed_at is None or timezone.now() - run.observed_at > timedelta(seconds=settings.KEDROGY_SERVE_FRESHNESS)):
        status = "UNAVAILABLE"
        error = {"code": "OBSERVATION_STALE", "message": "Serving health has not been checked recently."}
    return {"id": str(run.id), "status": status, "training_run_id": str(run.training_run_id),
            "labels": run.snapshot["labels"],
            "class_schema_version": run.snapshot["artifact"].get("version", 1),
            "conversion_policy": run.snapshot["artifact"].get("conversion_policy", "reject-other-v1"), "observed_at": run.observed_at.isoformat() if run.observed_at else None,
            "error": error}


def startup_result(run: ServingRun) -> dict:
    return {"id": str(run.id), "status": run.startup_status, "is_finished": run.startup_status != "RUNNING",
            "logs": "", "error": run.startup_error or None,
            "return_value": {"model_id": run.model_id, "serving_run_id": str(run.id)} if run.startup_status == "SUCCEEDED" else None}


def start_serving(model_id: int, key: str | None = None) -> tuple[ServingRun, bool]:
    from .tasks import new_serve_task

    key = key or str(uuid.uuid4())
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        raise OperationError("INVALID_REQUEST_KEY", "Use a request key of at most 128 ASCII letters, digits, or ._:-.")
    with transaction.atomic():
        from .operation_control import require_dataset
        parent_id = DjangoModel.objects.values_list("on_dataset_id", flat=True).get(pk=model_id)
        dataset = DjangoDataset.objects.select_for_update().get(pk=parent_id)
        model = DjangoModel.objects.select_for_update(of=("self",)).select_related("published_run").get(pk=model_id)
        previous = model.serving_runs.filter(idempotency_key=key).first()
        if previous:
            return previous, False
        require_dataset(dataset)
        if model.resources_deleting or model.retired_at:
            raise OperationError("MODEL_BUSY", "Model resources are being deleted.")
        artifact = published_artifact(model)
        training = model.published_run
        try:
            # Serving uses the trained draft, never the current editable labels or title.
            preprocessor = validate_preprocessor(training.snapshot.get("preprocessor", ""))
            cfg = validate_dataset(training.snapshot["dataset"])
        except LaunchConfigError as error:
            raise OperationError("INVALID_CONFIGURATION", str(error)) from error
        active = model.serving_runs.filter(status__in=LIVE).first()
        if active:
            raise OperationError("SERVING_ACTIVE", "Stop the current serving version before launching another one.")
        run = ServingRun.objects.create(model=model, training_run=training, idempotency_key=key,
            namespace=settings.KEDROGY_NAMESPACE, snapshot={"artifact": artifact, "labels": training.snapshot["labels"],
                "dataset": training.snapshot["dataset"], "image": cfg.image, "preprocessor": preprocessor})
        run.resource_layout = resources.LAYOUT
        cfg = replace(cfg, image=run.snapshot["image"])
        run.resource_plan = resources.make_plan(run, manifests.serving(cfg, run.model_id, preprocessor,
            artifact_path=artifact["path"], serving_run_id=str(run.id), training_run_id=str(training.id), artifact=artifact))
        run.save(update_fields=["resource_layout", "resource_plan"])
        model.current_serving = run
        model.served = False
        model.save(update_fields=["current_serving", "served"])
        new_serve_task.enqueue(str(run.id))
        return run, True


def stop_serving(model_id: int) -> ServingRun | None:
    with transaction.atomic():
        model = DjangoModel.objects.select_for_update().get(pk=model_id)
        if model.current_serving_id is None:
            return None
        run = ServingRun.objects.select_for_update().get(pk=model.current_serving_id)
        if run.status not in ("STOPPING", "STOPPED"):
            run.status = "STOPPING"
            run.lease_epoch += 1
            run.lease_owner = None
            run.lease_until = None
            if run.startup_status == "RUNNING":
                run.startup_status = "FAILED"
                run.startup_error = {"code": "SERVING_STOPPED", "message": "Serving was stopped before startup completed."}
            run.save(update_fields=["status", "startup_status", "startup_error", "lease_epoch", "lease_owner", "lease_until"])
        model.served = False
        model.save(update_fields=["served"])
        return run


def _fenced(run, owner):
    return ServingRun.objects.filter(pk=run.pk, lease_owner=owner,
        lease_epoch=run.lease_epoch, lease_until__gt=Now())


def _active(run, owner):
    return _fenced(run, owner).filter(status__in=("STARTING", "READY", "UNAVAILABLE"),
        model__current_serving_id=run.pk, model__resources_deleting=False,
        model__retired_at__isnull=True, model__on_dataset__deletion_pending=False,
        model__on_dataset__retired_at__isnull=True, model__on_dataset__annotations_deleted=False)


def _owned(run, owner):
    return _active(run, owner).exists()


def _observe(run, owner, status, error=None):
    """A lease generation and ordered domain locks fence every publication."""
    with transaction.atomic():
        parent = DjangoModel.objects.values_list("on_dataset_id", flat=True).get(pk=run.model_id)
        DjangoDataset.objects.select_for_update().get(pk=parent)
        DjangoModel.objects.select_for_update().get(pk=run.model_id)
        current = ServingRun.objects.select_for_update().get(pk=run.pk)
        if not _owned(run, owner) or current.observed_at != run.observed_at:
            return
        current.status = status
        current.error = error or {}
        current.observed_at = timezone.now()
        if current.startup_status == "RUNNING" and status in ("READY", "FAILED"):
            current.startup_status = "SUCCEEDED" if status == "READY" else "FAILED"
            current.startup_error = error or {}
        if status == "READY" and current.activated_at is None:
            current.activated_at = timezone.now()
        current.save(update_fields=["status", "error", "observed_at", "startup_status", "startup_error", "activated_at"])
        DjangoModel.objects.filter(pk=run.model_id, current_serving_id=run.pk).update(served=status == "READY")


def _stop(run, owner):
    from .operation_control import delete_exact

    # Terminal tombstones keep collecting late creates without becoming current again.
    for ref in sorted(resources.inventory(run), key=lambda item: item["kind"] == "ConfigMap"):
        if not _fenced(run, owner).filter(status__in=("STOPPING", "STOPPED", "FAILED")).exists():
            return
        if not delete_exact(ref):
            return
    # Foreground deletion normally waits for descendants; explicitly check Pod absence too.
    pods = command(["get", "pods", "-l", f"kedrogy/serving-id={run.id}", "-o", "json"],
                   namespace=run.namespace, json_output=True)
    if pods.get("items"):
        return
    values = {"cleanup_observed_at": timezone.now(), "error": {}}
    if run.status == "STOPPING":
        values |= {"status": "STOPPED", "stopped_at": timezone.now(), "observed_at": timezone.now()}
    _fenced(run, owner).filter(status=run.status).update(**values)


def _advance(run, owner):
    from .prediction import check_service

    if run.status in ("STOPPING", "STOPPED", "FAILED"):
        _stop(run, owner)
        return
    if not _owned(run, owner):
        return
    if run.startup_status == "RUNNING" and timezone.now() > run.created_at + timedelta(seconds=settings.KEDROGY_SERVE_TIMEOUT):
        _observe(run, owner, "FAILED", {"code": "SERVING_TIMEOUT", "message": "The model did not become ready before the startup deadline."})
        return
    if run.resource_layout != resources.LAYOUT:
        raise OperationError("LEGACY_SERVING_REVIEW", "Stop and review the legacy fixed-name resources before launching a new serving version.")
    if run.snapshot["image"] not in settings.KEDROGY_ML_IMAGE_ALIASES | {settings.KEDROGY_ML_IMAGE}:
        raise OperationError("IMAGE_NO_LONGER_APPROVED", "The pinned serving image is no longer approved.")
    plan = run.resource_plan
    if not plan["namespace_uid"]:
        plan["namespace_uid"] = resources.namespace_uid(run.namespace)
        if not _active(run, owner).update(resource_plan=plan):
            return
    resources.check_namespace(run)
    deployment = None
    for ref in [plan["anchor"], *plan["resources"]]:
        if not _owned(run, owner):
            return
        current = resources.create_or_observe(run, ref, lambda: _owned(run, owner))
        if current is None:
            return
        if not ref["uid"]:
            ref["uid"] = current["metadata"]["uid"]
            if "generation" in current["metadata"]:
                ref["generation"] = current["metadata"]["generation"]
            if not _active(run, owner).update(resource_plan=plan):
                return
        if ref["kind"] == "Deployment":
            deployment = current
            run.deployment_uid = ref["uid"]
            run.generation = ref["generation"]
            if not _active(run, owner).update(deployment_uid=run.deployment_uid, generation=run.generation):
                return
    status = deployment.get("status", {})
    if (status.get("observedGeneration", 0) < run.generation or status.get("updatedReplicas", 0) != 1
            or status.get("readyReplicas", 0) != 1 or status.get("availableReplicas", 0) != 1
            or status.get("replicas", 0) != 1):
        _observe(run, owner, "STARTING" if run.startup_status == "RUNNING" else "UNAVAILABLE",
                 {"code": "MODEL_LOADING", "message": "The serving Pod is loading or recovering."})
        return
    if not _owned(run, owner):
        return
    check_service(run)
    _observe(run, owner, "READY")


def advance_serving(run_id) -> ServingRun:
    owner = uuid.uuid4()
    with transaction.atomic():
        run = ServingRun.objects.select_for_update().get(pk=run_id)
        now = ServingRun.objects.annotate(db_now=Now()).values_list("db_now", flat=True).get(pk=run_id)
        eligible = run.status in LIVE or (run.resource_layout == resources.LAYOUT and run.status in ("STOPPED", "FAILED"))
        if not eligible or (run.lease_until and run.lease_until > now):
            return run
        run.lease_epoch += 1
        run.lease_owner = owner
        run.lease_until = now + timedelta(seconds=360)
        run.save(update_fields=["lease_owner", "lease_until", "lease_epoch"])
    try:
        _advance(run, owner)
    except OperationError as error:
        if run.status in ("STOPPING", "STOPPED", "FAILED"):
            _fenced(run, owner).filter(status=run.status).update(error=error.public(), cleanup_observed_at=timezone.now())
        else:
            expired = run.startup_status == "RUNNING" and timezone.now() > run.created_at + timedelta(seconds=settings.KEDROGY_SERVE_TIMEOUT)
            _observe(run, owner, "FAILED" if expired else "UNAVAILABLE", error.public())
    except Exception:
        _observe(run, owner, "UNAVAILABLE", {"code": "SERVING_ERROR", "message": "Serving health could not be checked."})
        raise
    finally:
        _fenced(run, owner).update(lease_owner=None, lease_until=None)
    return ServingRun.objects.get(pk=run.pk)
