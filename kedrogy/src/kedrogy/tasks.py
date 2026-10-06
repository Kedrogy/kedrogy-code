"""Execute validated operations and persist only safe public task diagnostics."""

import logging
from functools import wraps

from django.db import DatabaseError
from django_tasks import TaskContext, task

from .kubernetes import OperationError, command

logger = logging.getLogger(__name__)


def public_errors(function):
    """Record a safe error without allowing metadata failures to hide the cause."""
    @wraps(function)
    def wrapped(context, *args, **kwargs):
        try:
            return function(context, *args, **kwargs)
        except OperationError as error:
            context.metadata['error'] = error.public()
            try:
                context.save_metadata()
            except DatabaseError:
                logger.warning('Could not persist task error metadata.')
            raise
    return wrapped


def kubectl(context: TaskContext, args: list[str], *, document: dict | None = None,
            timeout: int = 180) -> str:
    """Run an operation without exposing cluster output in the unauthenticated API."""
    result = command(args, document=document, timeout=timeout)
    summary = f'Kubernetes {args[0]} completed.'
    context.metadata['public_logs'] = (context.metadata.get('public_logs', '') + '\n' + summary)[-16000:]
    context.save_metadata()
    return result


def apply_documents(context: TaskContext, documents: list[dict]) -> None:
    """Send structured documents over stdin without writing manifest files."""
    kubectl(context, ['apply', '-f', '-'], document={'apiVersion': 'v1', 'kind': 'List', 'items': documents})


@task(takes_context=True)
@public_errors
def new_dataset_task(context: TaskContext, run_id: str):
    """Deliver a durable annotation intent; reconciliation survives this worker."""
    import uuid

    from .annotation import advance_annotation
    try:
        identifier = uuid.UUID(str(run_id))
    except (ValueError, TypeError):
        raise OperationError("LEGACY_TASK", "This annotation request has no durable identity. Review it and submit a new request.") from None
    advance_annotation(identifier)
    return {"operation_id": str(identifier)}


@task(takes_context=True)
@public_errors
def new_train_task(context: TaskContext, run_id: str):
    """Observe one durable training run until its verified terminal result."""
    import uuid

    from .training import wait_for_run
    try:
        uuid.UUID(str(run_id))
    except ValueError:
        raise OperationError('LEGACY_TASK', 'This queued training request predates training runs. Submit a new Train request.') from None
    run = wait_for_run(run_id)
    if run.status != 'SUCCEEDED':
        raise OperationError(run.error.get('code', 'TRAINING_FAILED'), run.error.get('message', 'Training failed.'))
    return {'model_id': run.model_id, 'run_id': str(run.id)}


@task(takes_context=True)
@public_errors
def new_serve_task(context: TaskContext, run_id: str):
    """A queue task observes startup; the separate reconciler continues health checks."""
    import time
    import uuid

    from .serving import advance_serving
    try:
        uuid.UUID(str(run_id))
    except ValueError:
        raise OperationError("LEGACY_TASK", "Submit a new Serve request for a verified model.") from None
    while True:
        run = advance_serving(run_id)
        if run.startup_status != "RUNNING":
            if run.startup_status != "SUCCEEDED":
                raise OperationError(run.startup_error.get("code", "SERVING_FAILED"), run.startup_error.get("message", "Serving startup failed."))
            return {"model_id": run.model_id, "serving_run_id": str(run.id)}
        time.sleep(3)


@task(takes_context=True)
@public_errors
def new_delete_model_task(context: TaskContext, run_id: str):
    """A delivery starts one cleanup step; its durable result is authoritative."""
    import uuid

    from .deletion import advance_deletion
    try:
        identifier = uuid.UUID(str(run_id))
    except (ValueError, TypeError):
        raise OperationError("LEGACY_TASK", "This deletion request has no reviewed durable identity. Create a new cleanup preview.") from None
    advance_deletion(identifier)
    return {"operation_id": str(identifier)}


def request_resource_deletion(model_id: int, *, preview_token=None, key=None):
    from .deletion import request_deletion
    return request_deletion("model_files", model_id, preview_token, key)[0]
