"""Bounded inference transport with strict checkpoint/revision response validation."""

import os
from contextlib import contextmanager

import requests
from kedrogy_contracts import CONTRACT_VERSION, ContractError, validate_prediction

from .kubernetes import OperationError, service_tunnel
from .models import DjangoModel


@contextmanager
def service_url(run):
    from .serving_resources import service_name
    name = service_name(run)
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        yield f"http://{name}.{run.namespace}.svc.cluster.local:8888/predict"
    else:
        with service_tunnel(f"service/{name}", 8888, path="/predict", namespace=run.namespace) as url:
            yield url


def check_text(text):
    if not isinstance(text, str) or not text.strip():
        raise OperationError("INVALID_TEXT", "Enter nonempty text to classify.")
    if len(text) > 20000 or len(text.encode()) > 60000:
        raise OperationError("INVALID_TEXT", "Text exceeds the request size limit.")


def call(text: str, url: str, *, run) -> dict:
    check_text(text)
    try:
        with requests.post(url, json={"text": text}, timeout=(5, 30), stream=True) as response:
            if response.status_code in (400, 413, 422):
                raise OperationError("INVALID_TEXT", "The text is invalid or exceeds this model's token limit.")
            if response.status_code == 429:
                raise OperationError("PREDICTION_BUSY", "The model is busy. Retry shortly.")
            response.raise_for_status()
            content = response.raw.read(16385, decode_content=True)
            if len(content) > 16384:
                raise ValueError
            import json
            result = json.loads(content)
        return validate_prediction(result, labels=run.snapshot["labels"],
                                   training_run_id=str(run.training_run_id), serving_run_id=str(run.id),
                                   artifact_version=run.snapshot["artifact"].get("version", 1))
    except requests.Timeout:
        raise OperationError("PREDICTION_TIMEOUT", "The prediction request timed out.") from None
    except ContractError as error:
        raise OperationError(error.code, str(error)) from error
    except (requests.RequestException, ValueError, KeyError, TypeError):
        raise OperationError("PREDICTION_UNAVAILABLE", "The model could not return a compatible prediction. Check its serving status.") from None


def check_service(run):
    """Check the Service identity and one actual forward pass before publishing READY."""
    try:
        with service_url(run) as url:
            response = requests.get(url.removesuffix("/predict") + "/readyz", timeout=(5, 5))
            response.raise_for_status()
            data = response.json()
            if (not isinstance(data, dict) or data.get("ready") is not True
                    or type(data.get("contract_version")) is not int or data["contract_version"] != CONTRACT_VERSION
                    or data.get("training_run_id") != str(run.training_run_id) or data.get("serving_run_id") != str(run.id)):
                raise OperationError("INFERENCE_INCOMPATIBLE", "The Service reports a different model version or an incompatible protocol.")
            call("Model readiness check.", url, run=run)
    except (requests.RequestException, ValueError, TypeError):
        raise OperationError("PREDICTION_UNAVAILABLE", "The inference Service is not ready.") from None


def predict(model_id: int, text: str) -> dict:
    from .serving import public_serving

    check_text(text)
    model = DjangoModel.objects.select_related("current_serving").get(pk=model_id)
    run = model.current_serving
    if model.resources_deleting or model.retired_at or public_serving(run)["status"] != "READY":
        raise OperationError("MODEL_UNAVAILABLE", "Serve a verified model and wait for a fresh Ready status before predicting.")
    try:
        with service_url(run) as url:
            result = call(text, url, run=run)
    except OperationError as error:
        if error.code not in ("INVALID_TEXT", "PREDICTION_BUSY"):
            # A failed request can invalidate readiness, but cannot complete a startup task.
            from django.utils import timezone

            from .models import ServingRun
            ServingRun.objects.filter(pk=run.pk, status="READY", model__current_serving_id=run.pk).update(
                status="UNAVAILABLE", error=error.public(), observed_at=timezone.now())
        raise
    if not DjangoModel.objects.filter(pk=model_id, current_serving_id=run.pk, current_serving__status="READY", resources_deleting=False,
            retired_at__isnull=True, on_dataset__deletion_pending=False, on_dataset__retired_at__isnull=True).exists():
        raise OperationError("SERVING_CHANGED", "The serving version changed during prediction. Retry after it becomes ready.")
    return result
