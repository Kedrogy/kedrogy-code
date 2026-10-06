"""A read-only, public representation of background task results."""

from django.http import Http404
from django_tasks import TaskResultStatus
from django_tasks.exceptions import TaskResultDoesNotExist, TaskResultMismatch


def present(result) -> dict:
    """Never read return_value for failed or incomplete tasks."""
    status = result.status
    succeeded = status == TaskResultStatus.SUCCEEDED
    failed = status == TaskResultStatus.FAILED
    # Metadata is written only with public summaries by the operation boundary.
    error = result.metadata.get("error") if failed else None
    if failed and not error:
        error = {"code": "TASK_FAILED", "message": "The operation failed. Check the task or model status."}
    return {
        "status": str(status), "is_finished": succeeded or failed,
        "logs": result.metadata.get("public_logs", "")[-16000:],
        "return_value": result.return_value if succeeded else None,
        "error": error,
    }


def retrieve(task, result_id: str) -> dict:
    """Turn a missing or mismatched queue result into an ordinary 404."""
    try:
        return present(task.get_result(result_id))
    except (TaskResultDoesNotExist, TaskResultMismatch, ValueError):
        raise Http404("Task not found.") from None
