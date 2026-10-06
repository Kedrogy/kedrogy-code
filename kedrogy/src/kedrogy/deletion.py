"""Reviewed cleanup plans, exact-resource deletion and resumable tombstones."""

import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from . import manifests
from .annotation import advance_annotation, stop_annotation
from .dataset_bindings import reader
from .kubernetes import OperationError, command
from .launch_config import LaunchConfig
from .models import (
    AnnotationSlot,
    DeletionRun,
    DjangoDataset,
    DjangoModel,
    TrainingRun,
)
from .operation_control import (
    acquire,
    delete_exact,
    owned,
    release,
    request_key,
    resource_ref,
)
from .serving import advance_serving, stop_serving
from .training import ACTIVE, _conditions, _ensure, _get

ACTIONS = {"model_files", "model", "dataset", "annotations"}
SALT = "kedrogy.deletion-preview.v1"


def _stamp(dataset, models):
    value = {"dataset": dataset.to_dict(), "retired": bool(dataset.retired_at),
             "annotations_deleted": dataset.annotations_deleted,
             "annotation_runs": list(dataset.annotation_runs.values_list("id", "status")),
             "models": [{"id": m.id, "retired": bool(m.retired_at), "published": m.published_run_id,
                         "legacy_cleanup_review": m.legacy_cleanup_review,
                         "serving": m.current_serving_id, "labels": m.label_schema,
                         "serving_runs": list(m.serving_runs.values_list("id", "status", "resource_plan")),
                         "runs": list(m.training_runs.values_list("id", "status"))} for m in models]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def annotation_receipt(dataset):
    if dataset.binding_state != "BOUND" or dataset.annotations_deleted:
        raise OperationError("DATASET_UNRESOLVED", "Only an established, retained annotation binding can be deleted.")
    with reader() as connection:
        found = connection.execute("SELECT id,meta FROM public.dataset WHERE name=%s AND session IS NOT TRUE", (dataset.prodigy_dataset_name,)).fetchall()
        if len(found) != 1 or found[0][0] != dataset.prodigy_dataset_id:
            raise OperationError("DATASET_REPLACED", "The annotation identity changed. Review its binding.")
        try:
            meta = json.loads(bytes(found[0][1])) if found[0][1] is not None else {}
            if not isinstance(meta, dict) or meta.get("structured", False):
                raise ValueError
        except (ValueError, TypeError):
            raise OperationError("INVALID_ANNOTATIONS", "Only unstructured annotation datasets with valid metadata can use this cleanup adapter.") from None
        rows = connection.execute("SELECT e.id,e.content FROM public.link l JOIN public.example e ON e.id=l.example_id WHERE l.dataset_id=%s ORDER BY e.id LIMIT %s", (dataset.prodigy_dataset_id, settings.KEDROGY_MAX_ANNOTATIONS + 1)).fetchall()
    if len(rows) > settings.KEDROGY_MAX_ANNOTATIONS:
        raise OperationError("INVALID_ANNOTATIONS", "The annotation cleanup exceeds the configured limit.")
    h = hashlib.sha256()
    for identifier, content in rows:
        h.update(str(identifier).encode() + b":" + hashlib.sha256(bytes(content)).digest())
    return {"name": dataset.prodigy_dataset_name, "id": dataset.prodigy_dataset_id, "fingerprint": h.hexdigest(), "count": len(rows)}


def _inventory(models):
    resources, issues = [], []
    for model in models:
        from .legacy_cleanup import reviewed_resources
        try:
            reviewed = reviewed_resources(model)
        except OperationError as error:
            issues.append(str(error))
            reviewed = []
        resources.extend(reviewed)
        reviewed_keys = {(ref["kind"], ref["name"]) for ref in reviewed}
        candidates = [("PersistentVolumeClaim", f"pvc-model-{model.pk}", None, {"kedrogy/model-id": str(model.pk), "app.kubernetes.io/managed-by": "kedrogy"})]
        for run in model.training_runs.all():
            candidates += [("Job", run.job_name, run.job_uid or None, {"kedrogy/run-id": str(run.id)}),
                           ("Job", f"verify-{run.id}", None, {"kedrogy/run-id": str(run.id)}),
                           ("ConfigMap", f"parameters-{run.id}", None, {"kedrogy/run-id": str(run.id)})]
        from .serving_resources import inventory
        for serving in model.serving_runs.all():
            try:
                resources.extend(inventory(serving))
            except OperationError as error:
                issues.append(str(error))
        if not model.serving_runs.exists():
            candidates += [("Deployment", f"serve-{model.id}", None, {}),
                           ("Service", f"serve-svc-{model.id}", None, {})]
        candidates += [("Job", f"train-{model.id}", None, {}),
                       ("ConfigMap", f"parameters-train-{model.id}", None, {})]
        for kind, name, uid, labels in candidates:
            if (kind, name) in reviewed_keys:
                continue
            current = _get(kind, name, settings.KEDROGY_NAMESPACE)
            if current is None:
                continue
            actual = current["metadata"]
            proven = actual["uid"] == uid if uid else bool(labels) and all(actual.get("labels", {}).get(k) == v for k, v in labels.items())
            if not proven:
                issues.append(f"Ownership is unresolved for {kind}/{name}.")
                continue
            resources.append(resource_ref(current, settings.KEDROGY_NAMESPACE))
    unique = {r["namespace"] + ":" + r["kind"] + ":" + r["name"]: r for r in resources}
    return list(unique.values()), issues


def preview(action, identifier):
    if action not in ACTIONS:
        raise OperationError("INVALID_DELETE_ACTION", "Select a supported cleanup action.")
    if action in {"model", "model_files"}:
        model = get_object_or_404(DjangoModel.objects.select_related("on_dataset", "current_serving"), pk=identifier)
        dataset, models, target = model.on_dataset, [model], f"model:{model.pk}"
    else:
        dataset = get_object_or_404(DjangoDataset, pk=identifier)
        models = list(dataset.djangomodel_set.filter(retired_at__isnull=True).select_related("current_serving").order_by("pk"))
        target = f"dataset:{dataset.pk}"
    if action == "annotations":
        resources, issues = [], []
    else:
        resources, issues = _inventory(models)
    if dataset.deletion_pending or any(m.resources_deleting for m in models):
        issues.append("Cleanup is already reserved. Open its existing operation.")
    if TrainingRun.objects.filter(model__in=models, status__in=ACTIVE).exists():
        issues.append("Wait for active training before cleanup.")
    if action == "annotations" and any(m.current_serving and m.current_serving.status != "STOPPED" for m in models):
        issues.append("Stop serving dependent models before deleting annotations.")
    plan = {"action": action, "target": target, "dataset_id": dataset.pk, "model_ids": [m.pk for m in models],
            "namespace": settings.KEDROGY_NAMESPACE, "resources": resources, "issues": issues,
            "stamp": _stamp(dataset, models), "dataset_snapshot": dataset.to_dict(),
            "annotations": annotation_receipt(dataset) if action == "annotations" else None,
            "cleanup_image": settings.KEDROGY_ML_IMAGE if action == "annotations" else None,
            "legacy_review_model_ids": [m.pk for m in models if action != "annotations"
                                        and not m.training_runs.exists() and not m.serving_runs.exists()],
            "retains_annotations": action != "annotations", "retains_source_rows": True}
    return plan | {"preview_token": signing.dumps(plan, salt=SALT, compress=True)}


def request_deletion(action, identifier, token, key=None):
    from .tasks import new_delete_model_task

    key = request_key(key)
    target = f"{'model' if action in {'model','model_files'} else 'dataset'}:{identifier}"
    previous = DeletionRun.objects.filter(target=target, idempotency_key=key).first()
    if previous:
        if previous.action != action:
            raise OperationError("DELETE_CONFLICT", "This request key belongs to another cleanup action.")
        return previous, False
    try:
        plan = signing.loads(token, salt=SALT, max_age=600)
    except (signing.BadSignature, TypeError):
        raise OperationError("PREVIEW_CHANGED", "The deletion preview is missing or expired. Review a fresh preview.") from None
    if plan.get("action") != action or plan.get("target") != target or plan.get("namespace") != settings.KEDROGY_NAMESPACE or plan.get("issues"):
        raise OperationError("PREVIEW_CHANGED", "Resolve the preview conflicts before deleting anything.")
    with transaction.atomic():
        AnnotationSlot.objects.get_or_create(namespace=settings.KEDROGY_NAMESPACE)
        AnnotationSlot.objects.select_for_update().get(pk=settings.KEDROGY_NAMESPACE)
        dataset = DjangoDataset.objects.select_for_update().get(pk=plan["dataset_id"])
        models = list(DjangoModel.objects.select_for_update().filter(pk__in=plan["model_ids"]).order_by("pk"))
        previous = DeletionRun.objects.filter(target=target, idempotency_key=key).first()
        if previous:
            return previous, False
        actual_ids = list(dataset.djangomodel_set.filter(retired_at__isnull=True).order_by("pk").values_list("pk", flat=True))
        if (dataset.deletion_pending or any(m.resources_deleting for m in models)
                or _stamp(dataset, models) != plan["stamp"]
                or (action in {"dataset", "annotations"} and actual_ids != plan["model_ids"])):
            raise OperationError("PREVIEW_CHANGED", "The target changed. Review a fresh deletion preview.")
        if TrainingRun.objects.filter(model__in=models, status__in=ACTIVE).exists():
            raise OperationError("MODEL_BUSY", "Wait for active training before cleanup.")
        run = DeletionRun.objects.create(dataset=dataset, model=models[0] if action in {"model", "model_files"} else None,
            action=action, target=target, idempotency_key=key, plan=plan)
        if action in {"dataset", "annotations"}:
            dataset.deletion_pending = True
            dataset.save(update_fields=["deletion_pending"])
        DjangoModel.objects.filter(pk__in=plan["model_ids"]).update(resources_deleting=True)
        result = new_delete_model_task.enqueue(str(run.id))
        run.task_id = str(result.id)
        run.save(update_fields=["task_id"])
        return run, True


def public_deletion(run):
    complete = run.status == "SUCCEEDED"
    return {"id": str(run.pk), "kind": "delete", "status": run.status, "is_finished": complete or run.status == "NEEDS_REVIEW",
            "logs": "", "error": run.error or None, "step": run.step, "can_retry": run.status == "NEEDS_REVIEW",
            "progress": {"completed": len(run.completed), "total": len(run.plan["resources"]) + (3 if run.action == "annotations" else 2)},
            "return_value": {"target": run.target} if complete else None}


def retry_deletion(identifier):
    with transaction.atomic():
        run = DeletionRun.objects.select_for_update().get(pk=identifier)
        if run.status == "NEEDS_REVIEW":
            run.status, run.error, run.next_attempt_at, run.attempts = "QUEUED", {}, None, 0
            run.plan["attempt_started_at"] = timezone.now().isoformat()
            run.save(update_fields=["status", "error", "next_attempt_at", "attempts", "plan"])
        return run


def _annotation_cleanup(run, owner):
    receipt = run.plan["annotations"]
    image = run.plan["cleanup_image"]
    if image not in settings.KEDROGY_ML_IMAGE_ALIASES | {settings.KEDROGY_ML_IMAGE}:
        raise OperationError("IMAGE_NO_LONGER_APPROVED", "The pinned cleanup image is no longer approved.")
    # Cleanup only needs a verified binding and the operator-approved adapter.
    # A retired source/recipe configuration must not prevent retained-data cleanup.
    cfg = LaunchConfig(image=image, working_dir="/app/mykedro", pipeline="", dataset_name=receipt["name"],
                       table_name="", id_field="", recipe_args=())
    name = f"annotation-delete-{run.id}"
    container = manifests.container("delete-annotations", cfg, ["-m", "myrecipes.delete_annotations", "--", receipt["name"], str(receipt["id"]), receipt["fingerprint"]])
    container["env"] = manifests.db_env("kedrogy-db-annotator")
    spec = manifests.pod_spec() | {"restartPolicy": "Never", "containers": [container]}
    document = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": name, "labels": {"kedrogy/deletion-id": str(run.id)}},
                "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 120, "template": {"spec": spec}}}
    if run.plan.get("annotation_committed"):
        return delete_exact(run.plan["annotation_job"])
    known = run.plan.get("annotation_job")
    if not owned(DeletionRun, run.pk, owner, ("RUNNING",)):
        return False
    job = _get("Job", name, run.plan["namespace"]) if known else _ensure(document, run.plan["namespace"])
    if job is None:
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "The recorded annotation cleanup Job disappeared before its outcome was recorded.")
    if job["metadata"].get("labels", {}).get("kedrogy/deletion-id") != str(run.id):
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "The annotation cleanup Job has another owner.")
    ref = resource_ref(job, run.plan["namespace"])
    if known and known["uid"] != ref["uid"]:
        raise OperationError("RESOURCE_IDENTITY_CHANGED", "The annotation cleanup Job was replaced.")
    if not known:
        run.plan["annotation_job"] = ref
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(plan=run.plan)
    if "Failed" in _conditions(job):
        raise OperationError("ANNOTATION_DELETE_FAILED", "Annotation cleanup failed. Review the binding and job before retrying.")
    if "Complete" not in _conditions(job):
        return False
    run.plan["annotation_committed"] = True
    DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(plan=run.plan)
    return delete_exact(ref)


def _advance(run, owner):
    def active():
        return owned(DeletionRun, run.pk, owner, ("RUNNING",))

    if not active():
        return
    from datetime import datetime
    started = datetime.fromisoformat(run.plan["attempt_started_at"]) if run.plan.get("attempt_started_at") else run.created_at
    if timezone.now() - started > timedelta(seconds=settings.KEDROGY_CLEANUP_TIMEOUT):
        raise OperationError("CLEANUP_TIMEOUT", "Cleanup reached its deadline. Review blocked resources, then retry this same operation.")
    if "stopped" not in run.completed:
        from .legacy_cleanup import preview as legacy_preview
        legacy_models = DjangoModel.objects.filter(pk__in=run.plan["model_ids"]).exclude(legacy_cleanup_review={}) if run.action != "annotations" else []
        for model in legacy_models:
            current = legacy_preview(model.pk, for_cleanup=True)
            planned = [ref for ref in run.plan["resources"] if ref in model.legacy_cleanup_review["resources"]]
            if current["issues"] or current["resources"] != planned:
                raise OperationError("RESOURCE_IDENTITY_CHANGED", "Legacy resources or dependencies changed after review. No resources were deleted; review ownership again.")
        if run.action in {"dataset", "annotations"}:
            session = stop_annotation(run.dataset_id)
            if session and advance_annotation(session.id).status != "STOPPED":
                return
        for identifier in run.plan["model_ids"]:
            session = stop_serving(identifier)
            if session and advance_serving(session.id).status != "STOPPED":
                return
        run.completed.append("stopped")
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(completed=run.completed)
    for ref in sorted(run.plan["resources"], key=lambda r: r["kind"] == "PersistentVolumeClaim"):
        name = ref["kind"] + "/" + ref["name"]
        if name in run.completed:
            # A later object under the same name is never silently removed.
            current = _get(ref["kind"], ref["name"], ref["namespace"])
            if current:
                raise OperationError("RESOURCE_IDENTITY_CHANGED", "A resource appeared after its cleanup step completed.")
            continue
        if not active():
            return
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(step=f"Removing {name}")
        if ref["kind"] == "PersistentVolumeClaim":
            pods = command(["get", "pods", "-o", "json"], namespace=ref["namespace"], json_output=True)
            if any(v.get("persistentVolumeClaim", {}).get("claimName") == ref["name"] for p in pods.get("items", []) for v in p.get("spec", {}).get("volumes", [])):
                raise OperationError("VOLUME_IN_USE", "A Pod still references this model volume. Wait for owned workloads to stop; review unrelated consumers.")
        if not delete_exact(ref):
            return
        run.completed.append(name)
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(completed=run.completed)
    if run.action == "annotations" and "annotations" not in run.completed:
        if not active() or not _annotation_cleanup(run, owner):
            return
        run.completed.append("annotations")
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(completed=run.completed)
    with transaction.atomic():
        dataset = DjangoDataset.objects.select_for_update().get(pk=run.dataset_id)
        list(DjangoModel.objects.select_for_update().filter(pk__in=run.plan["model_ids"]).order_by("pk"))
        current = DeletionRun.objects.select_for_update().get(pk=run.pk)
        if current.lease_owner != owner or current.status != "RUNNING":
            return
        now = timezone.now()
        models = DjangoModel.objects.filter(pk__in=run.plan["model_ids"])
        if run.action != "annotations":
            models.update(trained=False, served=False, published_run=None, artifact_status="MISSING",
                          resources_deleting=False, legacy_cleanup_review={})
            TrainingRun.objects.filter(model__in=models, artifact_removed_at__isnull=True).update(artifact_removed_at=now)
        else:
            models.update(resources_deleting=False)
            dataset.annotations_deleted = True
            dataset.annotation_refresh_requested = True
        if run.action in {"model", "dataset"}:
            models.update(retired_at=now)
        if run.action == "dataset":
            dataset.retired_at = now
        dataset.deletion_pending = False
        dataset.save(update_fields=["retired_at", "deletion_pending", "annotations_deleted", "annotation_refresh_requested"])
        current.completed = run.completed + ["finalized"]
        current.status, current.step, current.finished_at, current.error = "SUCCEEDED", "Cleanup completed", now, {}
        current.save(update_fields=["completed", "status", "step", "finished_at", "error"])


def advance_deletion(identifier):
    run, owner = acquire(DeletionRun, identifier, ("QUEUED", "RUNNING", "RETRY_WAIT"))
    if owner is None:
        return run
    try:
        if run.next_attempt_at and run.next_attempt_at > timezone.now():
            return run
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(status="RUNNING")
        run.status = "RUNNING"
        _advance(run, owner)
    except OperationError as error:
        transient = error.code in {"CLUSTER_UNAVAILABLE", "OPERATION_TIMEOUT", "VOLUME_IN_USE", "COMMAND_FAILED"}
        attempts = run.attempts + 1
        retry = transient and attempts < 6
        DeletionRun.objects.filter(pk=run.pk, lease_owner=owner).update(
            status="RETRY_WAIT" if retry else "NEEDS_REVIEW", error=error.public(), attempts=attempts,
            next_attempt_at=timezone.now() + timedelta(seconds=min(60, 2 ** attempts)), step="Cleanup needs attention")
    finally:
        release(DeletionRun, run.pk, owner)
    return DeletionRun.objects.get(pk=run.pk)
