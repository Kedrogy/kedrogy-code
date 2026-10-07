"""Safe HTTP error boundaries, trusted proxy handling, and credential filtering."""

import ipaddress
import logging
import uuid

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpResponse, JsonResponse
from kedrogy.kubernetes import OperationError, redact
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

MESSAGES = {
    400: "The request is invalid.", 403: "The request is not permitted.",
    404: "The requested resource was not found.", 405: "This HTTP method is not allowed.",
    409: "The operation conflicts with the current state.", 500: "An internal error occurred.",
    503: "The service is temporarily unavailable.",
}


def payload(request, status: int, *, code: str | None = None, message: str | None = None) -> dict:
    """Build a public error without exception details or request input."""
    return {"error": {"code": code or f"HTTP_{status}", "message": message or MESSAGES.get(status, "The request failed.")},
            "request_id": getattr(request, "request_id", "")}


def api_exception_handler(exc, context):
    """Keep expected task errors separate from unexpected application failures."""
    request = context["request"]
    if isinstance(exc, OperationError):
        from rest_framework.response import Response
        status = (409 if exc.code in {"LEGACY_REVIEW_BLOCKED", "ANNOTATION_IDENTITY_FROZEN", "ANNOTATION_POLICY_REVIEW", "CONFLICTING_ANNOTATIONS", "ANNOTATION_ACTIVE", "DATASET_BUSY", "DELETE_CONFLICT", "PREVIEW_CHANGED", "RESOURCE_IDENTITY_CHANGED", "LEGACY_ANNOTATION_ACTIVE", "TRAINING_ACTIVE", "MODEL_NOT_VERIFIED", "SERVING_ACTIVE", "MODEL_BUSY", "DRAFT_CHANGED", "DATASET_CONFLICT", "DATASET_REPLACED", "DATASET_UNRESOLVED", "SERVING_CHANGED"}
                  else 504 if exc.code == "PREDICTION_TIMEOUT" else 429 if exc.code == "PREDICTION_BUSY"
                  else 502 if exc.code == "INVALID_INFERENCE_RESPONSE" else 400 if exc.code.startswith("INVALID") or exc.code in {"CLASS_SCHEMA_TOO_LARGE", "INSUFFICIENT_CLASS_SUPPORT"} else 503)
        data = payload(request, status, code=exc.code, message=str(exc))
        if hasattr(exc, "run_id"):
            data["active_run_id"] = exc.run_id
        return Response(data, status=status)
    response = exception_handler(exc, context)
    if response is not None:
        data = payload(request, response.status_code)
        if isinstance(exc, ValidationError):
            data["fields"] = response.data
        response.data = data
    return response


class APIBoundaryMiddleware:
    """Normalize routing/middleware failures as well as DRF failures."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        try:
            request.get_host()
        except DisallowedHost:
            response = JsonResponse(payload(request, 400), status=400)
        else:
            response = self.get_response(request)
        if (request.path.startswith("/api/") and response.status_code >= 400
                and not response.get("Content-Type", "").startswith("application/json")):
            original = response
            response = JsonResponse(payload(request, original.status_code), status=original.status_code)
            for header in ("Allow", "Retry-After"):
                if header in original:
                    response[header] = original[header]
        response["X-Request-ID"] = request.request_id
        return response


class TrustedProxyMiddleware:
    """Ignore forwarding claims from peers outside the configured proxy networks."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ipaddress.ip_network(value) for value in settings.TRUSTED_PROXY_CIDRS]

    def __call__(self, request):
        try:
            address = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
            trusted = any(address in network for network in self.networks)
        except ValueError:
            trusted = False
        if not trusted:
            request.META.pop("HTTP_X_FORWARDED_PROTO", None)
        return self.get_response(request)


class RedactFilter(logging.Filter):
    """Remove known credentials from message text and exception chains."""

    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def error_response(request, status: int):
    """Return the same safe error policy for HTML and JSON callers."""
    if request.path.startswith("/api/"):
        return JsonResponse(payload(request, status), status=status)
    return HttpResponse(MESSAGES.get(status, "The request failed."), status=status)


def error_400(request, exception=None):
    return error_response(request, 400)


def error_403(request, exception=None):
    return error_response(request, 403)


def error_404(request, exception=None):
    return error_response(request, 404)


def error_500(request):
    return error_response(request, 500)


def csrf_failure(request, reason=""):
    return error_response(request, 403)


def health(request):
    """Expose only process availability; no configuration or cluster diagnostics."""
    return JsonResponse({"status": "ok"})
