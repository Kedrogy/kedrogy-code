"""Persisted training runs, leased reconciliation, and artifact publication."""

import json
import math
import re
import time
import uuid
from dataclasses import replace
from datetime import timedelta

from kedrogy_contracts.training import training_options

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import manifests
from .kubernetes import OperationError, command, redact
from .launch_config import LaunchConfigError, validate_dataset, validate_preprocessor
from .models import DjangoDataset, DjangoModel, TrainingRun
from .training_preflight import model_labels, preflight

ACTIVE = ("QUEUED", "RUNNING", "VERIFYING")
TRANSIENT = {"CLUSTER_UNAVAILABLE", "CLUSTER_ACCESS_DENIED", "OPERATION_TIMEOUT"}
LOG_LIMIT = 16000


class TrainingConflict(OperationError):
    """Another run already owns this model's training slot."""

    def __init__(self, run_id):
        self.run_id = str(run_id)
        super().__init__("TRAINING_ACTIVE", "This model already has an active training run.")


def start_training(model_id: int, key: str | None = None) -> tuple[TrainingRun, bool]:
    """Atomically create the run and its database-backed queue entry."""
    from .tasks import new_train_task

    key = key or str(uuid.uuid4())
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        raise OperationError("INVALID_REQUEST_KEY", "Use a request key of at most 128 ASCII letters, digits, or ._:-.")
    model = DjangoModel.objects.select_related("on_dataset").get(pk=model_id)
    previous = model.training_runs.filter(idempotency_key=key).first()
    if previous:
        return previous, False
    active = model.training_runs.filter(status__in=ACTIVE).first()
    if active:
        raise TrainingConflict(active.id)
    from .operation_control import require_dataset
    require_dataset(model.on_dataset)
    if model.resources_deleting or model.retired_at:
        raise OperationError("MODEL_BUSY", "Model resources are being deleted.")
    try:
        config = validate_dataset(model.on_dataset.to_dict())
        labels = list(model_labels(model))
        preprocessor = validate_preprocessor(model.a_preprocess_fun)
    except LaunchConfigError as error:
        raise OperationError("INVALID_CONFIGURATION", str(error)) from error
    try:
        options = training_options(getattr(settings, "KEDROGY_TRAIN_OPTIONS", {}))
    except ValueError as error:
        raise OperationError("INVALID_CONFIGURATION", str(error)) from error
    summary = preflight(model)
    dataset_snapshot = model.on_dataset.to_dict()
    with transaction.atomic():
        # Keep slow annotation reads outside the lock, then reject a changed draft.
        dataset = DjangoDataset.objects.select_for_update().get(pk=model.on_dataset_id)
        current = DjangoModel.objects.select_for_update().get(pk=model_id)
        previous = current.training_runs.filter(idempotency_key=key).first()
        if previous:
            return previous, False
        active = current.training_runs.filter(status__in=ACTIVE).first()
        if active:
            raise TrainingConflict(active.id)
        require_dataset(dataset)
        if current.resources_deleting or current.retired_at:
            raise OperationError("MODEL_BUSY", "Model resources are being deleted.")
        compare = lambda data: {k: v for k, v in data.items() if k != "display_name"}
        if (current.on_dataset_id != dataset.pk or compare(dataset.to_dict()) != compare(dataset_snapshot)
                or list(model_labels(current)) != labels or current.a_preprocess_fun != preprocessor):
            raise OperationError("DRAFT_CHANGED", "The draft changed during validation. Review it and retry training.")
        identifier = uuid.uuid4()
        snapshot = {
            "dataset": dataset_snapshot, "image": config.image, "labels": labels,
            "preprocessor": preprocessor, "annotations": summary,
            "artifact_version": 2, "class_schema_version": 2, "conversion_policy": summary["policy"],
            "options": {**options,
                        "annotation_fingerprint": summary["fingerprint"],
                        "prodigy_dataset_id": summary["dataset_id"],
                        "conversion_policy": summary["policy"],
                        "max_annotations": settings.KEDROGY_MAX_ANNOTATIONS, "artifact_version": 2},
        }
        run = TrainingRun.objects.create(
            id=identifier, model=current, idempotency_key=key, snapshot=snapshot,
            namespace=settings.KEDROGY_NAMESPACE, job_name=f"train-{identifier}",
        )
        result = new_train_task.enqueue(str(run.id))
        run.task_id = str(result.id)
        run.save(update_fields=["task_id"])
        return run, True


def public_run(run: TrainingRun) -> dict:
    """Expose domain state without private queue tracebacks or launch credentials."""
    finished = run.status not in ACTIVE
    return {
        "id": str(run.id), "model_id": run.model_id, "status": run.status,
        "is_finished": finished, "logs": run.public_logs[-16000:],
        "labels": run.snapshot.get("labels", []), "attempts": run.attempts,
        "annotations": run.snapshot.get("annotations"),
        "quality": run.artifact.get("quality"),
        "artifact_verified": bool(run.artifact) and run.status == "SUCCEEDED" and run.artifact_removed_at is None,
        "error": run.error or None, "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "return_value": {"model_id": run.model_id, "run_id": str(run.id)} if run.status == "SUCCEEDED" else None,
    }


def config_for(run: TrainingRun):
    """Revalidate the saved launch profile and preserve its pinned image."""
    config = validate_dataset(run.snapshot["dataset"])
    if run.snapshot["image"] not in (settings.KEDROGY_ML_IMAGE_ALIASES | {settings.KEDROGY_ML_IMAGE}):
        raise OperationError("IMAGE_NO_LONGER_APPROVED", "The saved training image is no longer approved.")
    return replace(config, image=run.snapshot["image"])


def _get(kind: str, name: str, namespace: str) -> dict | None:
    try:
        return command(["get", kind, name, "-o", "json"], namespace=namespace, json_output=True)
    except OperationError as error:
        if error.code == "RESOURCE_NOT_FOUND":
            return None
        raise


def _ensure(document: dict, namespace: str) -> dict:
    """Create once; a retry reads the existing object instead of changing a Job."""
    document = document | {"metadata": document["metadata"] | {"namespace": namespace}}
    try:
        return command(["create", "-f", "-", "-o", "json"], document=document,
                       namespace=namespace, json_output=True)
    except OperationError as error:
        if error.code != "RESOURCE_EXISTS":
            raise
        existing = _get(document["kind"], document["metadata"]["name"], namespace)
        if existing is None:
            raise OperationError("RESOURCE_LOST", "The resource disappeared while being created.") from None
        return existing


def _pods(job: dict, namespace: str) -> list[dict]:
    uid = job["metadata"]["uid"]
    result = command(["get", "pods", "-l", f"controller-uid={uid}", "-o", "json"],
                     namespace=namespace, json_output=True)
    return [pod for pod in result.get("items", []) if any(
        owner.get("uid") == uid for owner in pod["metadata"].get("ownerReferences", [])
    )]


def _conditions(job: dict) -> set[str]:
    return {c["type"] for c in job.get("status", {}).get("conditions", []) if c.get("status") == "True"}


def training_log_snapshot(pods: list[dict], namespace: str, *, previous: str = "") -> str:
    """Read a bounded tail from already verified training Job children.

    Callers must verify the Job identity and obtain its children through _pods.
    Log access failures are diagnostic only and must not fail a training run.
    """
    if not pods:
        return "Waiting for the training Pod to be scheduled."
    sections = []
    unavailable = False
    received_output = False
    recent = sorted(pods, key=lambda pod: (pod["metadata"].get("creationTimestamp", ""), pod["metadata"]["name"]))[-2:]
    for pod in recent:
        name = pod["metadata"]["name"]
        status = pod.get("status", {})
        lines = [f"--- {name} | {status.get('phase', 'Pending')} ---"]
        conditions = status.get("conditions", [])
        for condition in conditions:
            if condition.get("type") == "PodScheduled" and condition.get("status") == "False":
                lines.append(f"Scheduling: {condition.get('reason', 'Pending')} — {condition.get('message', '')}")
        container = next((value for value in status.get("containerStatuses", []) if value["name"] == "train"), None)
        state = container.get("state", {}) if container else {}
        waiting = state.get("waiting")
        if waiting:
            lines.append(f"Container waiting: {waiting.get('reason', 'Pending')} — {waiting.get('message', '')}")
        elif not container:
            lines.append("Waiting for the training container to start.")
        else:
            ended = state.get("terminated")
            if ended:
                lines.append(f"Container exited: {ended.get('reason', 'Terminated')} (exit code {ended.get('exitCode', 'unknown')}).")
            try:
                output = command(["logs", name, "--container=train", "--timestamps=true", "--tail=100"],
                                 namespace=namespace, timeout=3)
            except OperationError as error:
                unavailable = True
                lines.append(f"Container output is temporarily unavailable ({error.code}).")
            else:
                received_output = received_output or bool(output)
                # Keep the actual tail: kubectl --limit-bytes can discard its newest lines.
                lines.append(redact(output)[-7000:] or "The training container has not written output yet.")
        sections.append("\n".join(lines))
    text = "\n\n".join(sections)
    if unavailable and previous and not received_output:
        marker = "\n\n--- Log collection warning ---\n"
        text = previous.split(marker, 1)[0] + marker + text
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return redact(text)[-LOG_LIMIT:]


def _record_training_logs(run: TrainingRun, owner: uuid.UUID, pods: list[dict]) -> None:
    """Cache logs outside row locks; a stale observer cannot overwrite them."""
    logs = training_log_snapshot(pods, run.namespace, previous=run.public_logs)
    TrainingRun.objects.filter(pk=run.pk, lease_owner=owner, lease_until__gt=timezone.now(), status__in=ACTIVE).update(public_logs=logs)


def _winner(pods: list[dict], container_name: str) -> tuple[dict, dict] | None:
    for pod in pods:
        if pod.get("status", {}).get("phase") != "Succeeded":
            continue
        for container in pod["status"].get("containerStatuses", []):
            terminated = container.get("state", {}).get("terminated", {})
            if container["name"] == container_name and terminated.get("exitCode") == 0:
                return pod, terminated
    return None


def validate_receipt(payload: str, run: TrainingRun, attempt_id: str, *, legacy: bool = False) -> dict:
    """Bind a bounded verification receipt to this run and successful Pod attempt."""
    try:
        if len(payload.encode()) > 3500:
            raise ValueError
        receipt = json.loads(payload)
        path = "best" if legacy else f"runs/{run.id}/{attempt_id}/artifact"
        expected = {
            "version": run.snapshot.get("artifact_version", 1), "verified": True, "run_id": str(run.id),
            "attempt_id": attempt_id, "path": path, "labels": run.snapshot["labels"],
            "image": run.snapshot["image"],
        }
        if expected["version"] == 2:
            expected |= {"conversion_policy": "single-label-choice-v2", "class_schema_version": 2}
        if type(receipt.get("version")) is not int or any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError
        files = receipt["files"]
        if not isinstance(files, dict) or "config.json" not in files or not files:
            raise ValueError
        for name, digest in files.items():
            if (not isinstance(name, str) or name.startswith("/") or ".." in name.split("/")
                    or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                raise ValueError
        if not any(name.endswith(".safetensors") for name in files):
            raise ValueError
        quality = receipt.get("quality")
        if quality is not None:
            if (not isinstance(quality, dict) or type(quality.get("version")) is not int or quality.get("version") != 1
                    or quality.get("split") != "validation" or "quality.json" not in files):
                raise ValueError
            for key in ("samples", "train_samples", "training_steps"):
                if type(quality.get(key)) is not int or quality[key] <= 0:
                    raise ValueError
            for key in ("accuracy", "macro_f1", "majority_baseline"):
                value = quality.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError
            warnings = quality.get("warnings")
            allowed = {"missing_predicted_classes", "not_above_majority_baseline", "small_validation_sample", "few_training_steps"}
            if not isinstance(warnings, list) or any(not isinstance(value, str) or value not in allowed for value in warnings):
                raise ValueError
        if legacy and receipt.get("legacy") is not True:
            raise ValueError
        return receipt | {"pvc": f"pvc-model-{run.model_id}"}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise OperationError("ARTIFACT_INVALID", "The checkpoint verification receipt is missing or invalid.") from None


def _finish(run: TrainingRun, owner: uuid.UUID, status: str, error: dict | None = None,
            artifact: dict | None = None) -> None:
    """Publish only while this reconciler still owns a nonterminal run."""
    with transaction.atomic():
        current = TrainingRun.objects.select_for_update().get(pk=run.pk)
        if current.lease_owner != owner or current.status not in ACTIVE:
            return
        current.status = status
        current.error = error or {}
        current.artifact = artifact or {}
        current.finished_at = timezone.now()
        current.public_logs = (current.public_logs + f"\nTraining {status.lower()}.")[-16000:]
        current.save(update_fields=["status", "error", "artifact", "finished_at", "public_logs"])
        if status == "SUCCEEDED":
            DjangoModel.objects.filter(pk=run.model_id).update(
                published_run=current, trained=True, artifact_status="VERIFIED",
            )


def _advance(run: TrainingRun, owner: uuid.UUID) -> None:
    cfg = config_for(run)
    deadline = run.created_at + timedelta(seconds=getattr(settings, "KEDROGY_TRAIN_TIMEOUT", 3600) + 360)
    job = _get("job", run.job_name, run.namespace)
    if timezone.now() > deadline:
        if job is not None and run.job_uid and job["metadata"]["uid"] == run.job_uid:
            command(["delete", "--raw", f"/apis/batch/v1/namespaces/{run.namespace}/jobs/{run.job_name}", "-f", "-"],
                    namespace=run.namespace, document={"apiVersion": "v1", "kind": "DeleteOptions",
                        "preconditions": {"uid": run.job_uid}, "propagationPolicy": "Background"})
        _finish(run, owner, "TIMED_OUT", {"code": "TRAINING_TIMEOUT", "message": "Training exceeded its deadline."})
        return
    if job is None:
        if run.job_uid:
            _finish(run, owner, "INTERRUPTED", {"code": "JOB_LOST", "message": "The training Job was removed before verification."})
            return
        _ensure(manifests.pvc(run.model_id), run.namespace)
        config, document = manifests.training(
            cfg, run.model_id, tuple(run.snapshot["labels"]), run_id=str(run.id),
            options=run.snapshot["options"],
        )
        _ensure(config, run.namespace)
        job = _ensure(document, run.namespace)
    if job["metadata"].get("labels", {}).get("kedrogy/run-id") != str(run.id):
        raise OperationError("JOB_IDENTITY_MISMATCH", "The Job does not belong to this training run.")
    uid = job["metadata"]["uid"]
    if run.job_uid and run.job_uid != uid:
        raise OperationError("JOB_IDENTITY_MISMATCH", "The training Job was replaced unexpectedly.")
    TrainingRun.objects.filter(pk=run.pk, lease_owner=owner, status__in=ACTIVE).update(
        job_uid=uid, started_at=run.started_at or timezone.now(), status="VERIFYING" if run.status == "VERIFYING" else "RUNNING",
    )
    pods = _pods(job, run.namespace)
    attempts = []
    for pod in pods:
        for container in pod.get("status", {}).get("containerStatuses", []):
            ended = container.get("state", {}).get("terminated", {})
            attempts.append({"pod": pod["metadata"]["name"], "uid": pod["metadata"]["uid"],
                             "phase": pod.get("status", {}).get("phase"),
                             "exit_code": ended.get("exitCode"), "reason": ended.get("reason", "")})
    TrainingRun.objects.filter(pk=run.pk, lease_owner=owner).update(attempts=attempts)
    _record_training_logs(run, owner, pods)
    conditions = _conditions(job)
    if "Failed" in conditions:
        timed_out = any(c.get("reason") == "DeadlineExceeded" for c in job["status"].get("conditions", []))
        reason = "Training exceeded its deadline." if timed_out else "The training Job failed. Check annotation labels and available resources."
        if any(a["reason"] == "OOMKilled" for a in attempts):
            reason = "The training container ran out of memory."
        error = {"code": "TRAINING_TIMEOUT" if timed_out else "TRAINING_FAILED", "message": reason}
        for pod in pods:
            for container in pod.get("status", {}).get("containerStatuses", []):
                message = container.get("state", {}).get("terminated", {}).get("message", "")
                if len(message) > 3500:
                    continue
                try:
                    code = json.loads(message).get("error", {}).get("code")
                except (ValueError, AttributeError):
                    continue
                if code == "ANNOTATIONS_CHANGED":
                    error = {"code": code, "message": "Annotations changed after preflight. Start a new training run."}
        _finish(run, owner, "TIMED_OUT" if timed_out else "FAILED", error)
        return
    if "Complete" not in conditions:
        return
    winner = _winner(pods, "train")
    if winner is None:
        raise OperationError("TRAINING_EXIT_INVALID", "No successful training container was found.")
    pod, ended = winner
    attempt_id = pod["metadata"]["uid"]
    TrainingRun.objects.filter(pk=run.pk, lease_owner=owner).update(status="VERIFYING")
    # Check the receipt if present, then independently reload the read-only checkpoint.
    if ended.get("message"):
        validate_receipt(ended["message"], run, attempt_id)
    name = f"verify-{run.id}"
    verify_job = _get("job", name, run.namespace)
    if verify_job is None:
        verify_job = _ensure(manifests.verification(
            cfg, run.model_id, name=name, run_id=str(run.id), attempt_id=attempt_id,
            path=f"runs/{run.id}/{attempt_id}/artifact", labels=run.snapshot["labels"],
            artifact_version=run.snapshot.get("artifact_version", 1),
        ), run.namespace)
    if "Failed" in _conditions(verify_job):
        raise OperationError("ARTIFACT_INVALID", "The saved model or tokenizer failed offline verification.")
    if "Complete" not in _conditions(verify_job):
        return
    checked = _winner(_pods(verify_job, run.namespace), "verify")
    if checked is None:
        raise OperationError("ARTIFACT_INVALID", "No successful checkpoint verifier was found.")
    artifact = validate_receipt(checked[1].get("message", ""), run, attempt_id)
    _finish(run, owner, "SUCCEEDED", artifact=artifact)


def advance_run(run_id) -> TrainingRun:
    """Perform one leased reconciliation step; safe across worker restarts."""
    owner = uuid.uuid4()
    now = timezone.now()
    with transaction.atomic():
        run = TrainingRun.objects.select_for_update().get(pk=run_id)
        if run.status not in ACTIVE or (run.lease_until and run.lease_until > now):
            return run
        run.lease_owner = owner
        run.lease_until = now + timedelta(seconds=360)
        run.heartbeat_at = now
        run.save(update_fields=["lease_owner", "lease_until", "heartbeat_at"])
    try:
        _advance(run, owner)
    except OperationError as error:
        if error.code in TRANSIENT:
            TrainingRun.objects.filter(pk=run.pk, lease_owner=owner).update(
                public_logs=f"Waiting for cluster access: {error.code}.",
            )
            limit = run.created_at + timedelta(seconds=getattr(settings, "KEDROGY_TRAIN_TIMEOUT", 3600) + 600)
            if timezone.now() > limit:
                _finish(run, owner, "INTERRUPTED", error.public())
        else:
            _finish(run, owner, "FAILED", error.public())
    except Exception:
        # Preserve a public terminal record even for unexpected adapter/validation bugs.
        _finish(run, owner, "FAILED", {"code": "TRAINING_ERROR", "message": "Training could not be reconciled. Review its configuration."})
        raise
    finally:
        TrainingRun.objects.filter(pk=run.pk, lease_owner=owner).update(lease_owner=None, lease_until=None)
    return TrainingRun.objects.get(pk=run.pk)


def wait_for_run(run_id, *, poll_seconds: float = 3) -> TrainingRun:
    """Observe a run until terminal; reconciliation can also proceed independently."""
    while True:
        run = advance_run(run_id)
        if run.status not in ACTIVE:
            return run
        time.sleep(poll_seconds)


def published_artifact(model: DjangoModel) -> dict:
    """Refuse inference unless a verified successful run is explicitly published."""
    run = model.published_run
    if model.artifact_status != "VERIFIED" or run is None or run.status != "SUCCEEDED" or run.artifact_removed_at is not None or not run.artifact:
        raise OperationError("MODEL_NOT_VERIFIED", "Train and verify a model before serving it.")
    return run.artifact


def delete_model_record(model_id: int, *, preview_token=None, key=None):
    """All record deletion goes through reviewed, durable cleanup."""
    from .deletion import request_deletion
    return request_deletion("model", model_id, preview_token, key)[0]


def delete_dataset_record(dataset_id: int, *, preview_token=None, key=None):
    from .deletion import request_deletion
    return request_deletion("dataset", dataset_id, preview_token, key)[0]
