
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .kubernetes import OperationError
from .launch_config import (
    LaunchConfigError,
    parse_labels,
    validate_dataset,
    validate_preprocessor,
)
from .models import (
    AnnotationRun,
    AnnotationSlot,
    DeletionRun,
    DjangoDataset,
    DjangoModel,
    ServingRun,
    TrainingRun,
)
from .prediction import predict as predict_text
from .serializers import DjangoDatasetSerializer, DjangoModelSerializer
from .serving import public_serving, start_serving, startup_result, stop_serving
from .task_results import retrieve
from .tasks import (
    new_dataset_task,
    new_delete_model_task,
    new_serve_task,
    new_train_task,
)
from .training import (
    public_run,
    start_training,
)


def check_launch(dataset, *, model=None, serving=False):
    """Reject unsafe persisted configurations before queueing API actions."""
    try:
        validate_dataset(dataset.to_dict())
        if model is not None:
            parse_labels(model.labels)
            if serving:
                validate_preprocessor(model.a_preprocess_fun)
    except LaunchConfigError as exc:
        raise ValidationError(exc.errors) from exc


class DatasetViewSet(viewsets.ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    queryset = DjangoDataset.objects.prefetch_related("annotation_runs").all()

    def get_queryset(self):
        return self.queryset.filter(retired_at__isnull=self.request.query_params.get("retired") != "true")
    serializer_class = DjangoDatasetSerializer

    def destroy(self, request, pk=None):
        from .deletion import public_deletion, request_deletion
        run, created = request_deletion("dataset", int(pk), request.data.get("preview_token"), request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "operation": public_deletion(run)}, status=202 if created else 200)

    @action(detail=True, methods=["get"])
    def deletion_preview(self, request, pk=None):
        from .deletion import preview
        return Response(preview("dataset", int(pk)))

    @action(detail=True, methods=["get", "post"])
    def retained_annotations(self, request, pk=None):
        from .deletion import preview, public_deletion, request_deletion
        if request.method == "GET":
            return Response(preview("annotations", int(pk)))
        run, created = request_deletion("annotations", int(pk), request.data.get("preview_token"), request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "operation": public_deletion(run)}, status=202 if created else 200)

    @action(detail=True, methods=["post"])
    def refresh_annotations(self, request, pk=None):
        dataset = self.get_object()
        DjangoDataset.objects.filter(pk=dataset.pk).update(annotation_refresh_requested=True)
        return Response({"status": "QUEUED"}, status=202)

    @action(detail=False, methods=["get"])
    def active_annotation(self, request):
        from django.conf import settings

        from .annotation import public_session
        slot = AnnotationSlot.objects.select_related("run").filter(pk=settings.KEDROGY_NAMESPACE).first()
        return Response(public_session(slot.run if slot else None))

    @action(detail=True, methods=["post"])
    def stop_annotation(self, request, pk=None):
        from .annotation import public_session, stop_annotation
        return Response(public_session(stop_annotation(self.get_object().pk)), status=202)

    @action(detail=True, methods=["post"])
    def label(self, request, pk=None):
        from .annotation import public_operation, start_annotation
        run, created = start_annotation(self.get_object().pk, request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "operation": public_operation(run)}, status=202 if created else 200)


class MLModelViewSet(viewsets.ModelViewSet):
    lookup_value_regex = r"[0-9]+"
    queryset = DjangoModel.objects.filter(retired_at__isnull=True).select_related("on_dataset", "published_run", "current_serving").prefetch_related("training_runs").all()
    serializer_class = DjangoModelSerializer

    @action(detail=True, methods=["get", "post"])
    def legacy_cleanup_review(self, request, pk=None):
        from .legacy_cleanup import confirm, preview
        model = self.get_object()
        if request.method == "GET":
            return Response(preview(model.pk))
        if not isinstance(request.data, dict):
            raise OperationError("INVALID_REVIEW", "Send the review token as a JSON object.")
        return Response(confirm(model.pk, request.data.get("review_token")))

    @action(detail=True, methods=["post"])
    def train(self, request, pk=None):
        model = self.get_object()
        run, created = start_training(model.id, request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "model_id": model.id, "run": public_run(run)},
                        status=202 if created else 200)

    @action(detail=True, methods=["post"])
    def serve(self, request, pk=None):
        model = self.get_object()
        run, created = start_serving(model.id, request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "model_id": model.id, "serving": public_serving(run)}, status=202 if created else 200)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        return Response(public_serving(stop_serving(self.get_object().id)), status=202)

    @action(detail=True, methods=["get"])
    def deletion_preview(self, request, pk=None):
        from .deletion import preview
        action_name = request.query_params.get("action", "model")
        if action_name not in {"model", "model_files"}:
            raise OperationError("INVALID_DELETE_ACTION", "Select model or model_files.")
        return Response(preview(action_name, int(pk)))

    @action(detail=True, methods=["post"])
    def delete_model(self, request, pk=None):
        from .deletion import public_deletion, request_deletion
        run, created = request_deletion("model_files", int(pk), request.data.get("preview_token"), request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "operation": public_deletion(run)}, status=202 if created else 200)

    @action(detail=True, methods=["post"])
    def predict(self, request, pk=None):
        model = self.get_object()
        if not isinstance(request.data, dict):
            raise OperationError("INVALID_TEXT", "Send a JSON object containing text_input.")
        text_input = request.data.get("text_input", "")
        prediction = predict_text(model.id, text_input)
        return Response({**prediction, "predicted_class": prediction["label"], "model_id": model.id})

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        model = self.get_object()
        return Response([public_run(run) | {"published": model.published_run_id == run.id,
            "served": model.current_serving is not None and model.current_serving.training_run_id == run.id}
            for run in model.training_runs.all()[:20]])

    def destroy(self, request, pk=None):
        from .deletion import public_deletion, request_deletion
        run, created = request_deletion("model", int(pk), request.data.get("preview_token"), request.headers.get("Idempotency-Key"))
        return Response({"result_id": str(run.id), "operation": public_deletion(run)}, status=202 if created else 200)


@api_view(["GET"])
def task_status(request, task_type, result_id):
    task_map = {
        "label": new_dataset_task,
        "train": new_train_task,
        "serve": new_serve_task,
        "delete": new_delete_model_task,
    }
    task_func = task_map.get(task_type)
    if not task_func:
        raise OperationError("INVALID_TASK_TYPE", "Unknown task type.")

    if task_type in ("label", "delete"):
        from .annotation import public_operation
        from .deletion import public_deletion
        try:
            run = (AnnotationRun if task_type == "label" else DeletionRun).objects.filter(pk=result_id).first()
        except (ValueError, DjangoValidationError):
            run = None
        if run is not None:
            return Response(public_operation(run) if task_type == "label" else public_deletion(run))

    if task_type in ("train", "serve"):
        run_class = TrainingRun if task_type == "train" else ServingRun
        try:
            run = run_class.objects.filter(pk=result_id).first()
        except (ValueError, DjangoValidationError):
            run = None
        if run is not None:
            return Response(public_run(run) if task_type == "train" else startup_result(run))
    return Response(retrieve(task_func, result_id))


@api_view(["POST"])
def retry_cleanup(request, result_id):
    from django.shortcuts import get_object_or_404

    from .deletion import public_deletion, retry_deletion
    get_object_or_404(DeletionRun, pk=result_id)
    return Response(public_deletion(retry_deletion(result_id)), status=202)
