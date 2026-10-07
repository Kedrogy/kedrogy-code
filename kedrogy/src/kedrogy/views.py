import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .kubernetes import OperationError
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


# @login_required # use LoginRequiredMiddleware instead
def index(request):
    dataset_list = (
        # XXX ignore those for now , https://github.com/astral-sh/ty/issues/1018
        DjangoDataset.objects.filter(retired_at__isnull=True)
    )  # has no calss attribute objects: https://pyrefly.org/en/docs/django/
    model_list = DjangoModel.objects.filter(retired_at__isnull=True)
    latest = get_latest_dataset()
    if latest:
        print("latest", latest, "dataset_name", latest.dataset.dataset_name)
    context = {
        "dataset_list": dataset_list,
        "model_list": model_list,
        "latest_dataset": latest,
    }
    return render(request, "kedrogy/index.html", context)


def detail(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    from .annotation import public_session
    from .annotation_data import public_data
    return render(request, "kedrogy/detail.html", {"dataset": dataset,
        "annotation_data": public_data(dataset), "annotation_session": public_session(dataset.annotation_runs.first()),
        "request_key": str(uuid.uuid4())})


@require_POST
def new_dataset(request):
    serializer = DjangoDatasetSerializer(data=request.POST.dict())
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=400)
    dataset = serializer.save()
    return redirect("kedrogy:detail", dataset_id=dataset.id)


@require_POST
def label_dataset(request, dataset_id):
    from .annotation import start_annotation
    get_object_or_404(DjangoDataset, pk=dataset_id)
    try:
        run, _ = start_annotation(dataset_id, request.POST.get("request_key"))
    except OperationError as error:
        return JsonResponse({"error": error.public()}, status=409)
    return render(request, "kedrogy/detail_task.html", {"dataset_name": run.dataset.dataset_name, "result_id": run.id})


@require_POST
def delete_dataset(request, dataset_id):
    return cleanup(request, "dataset", dataset_id)


def new_dataset_poll(request, dataset_name, result_id):
    context = {"dataset_name": dataset_name, "result_id": result_id}
    return render(request, "kedrogy/detail_task.html", context)


def get_latest_dataset():
    from django.conf import settings

    from .annotation import public_session
    slot = AnnotationSlot.objects.select_related("run__dataset").filter(pk=settings.KEDROGY_NAMESPACE).first()
    run = slot.run if slot else None
    return run if public_session(run)["status"] == "READY" else None


def task_result_view(request, result_id, task_function, template, *, training=False, redirect_success=False):
    """Render terminal failures without reading a failed task return value."""
    result = None
    if task_function in (new_dataset_task, new_delete_model_task):
        from .annotation import public_operation
        from .deletion import public_deletion
        try:
            run = (AnnotationRun if task_function == new_dataset_task else DeletionRun).objects.filter(pk=result_id).first()
        except (ValueError, DjangoValidationError):
            run = None
        if run:
            result = public_operation(run) if task_function == new_dataset_task else public_deletion(run)
    if training or task_function == new_serve_task:
        try:
            run = (TrainingRun if training else ServingRun).objects.filter(pk=result_id).first()
        except (ValueError, DjangoValidationError):
            run = None
        if run is not None:
            result = public_run(run) if training else startup_result(run)
    result = result or retrieve(task_function, result_id)
    if result["is_finished"]:
        if result["status"] == "SUCCEEDED" and redirect_success:
            return redirect("kedrogy:index")
        return render(request, "kedrogy/task_terminal.html", {"task": result})
    return render(request, template + "#task_result", {
        "result_id": result_id, "result": result["status"], "logs": result["logs"],
    })


def new_dataset_result(request, result_id):
    return task_result_view(request, result_id, new_dataset_task, "kedrogy/detail_task.html", redirect_success=False)


@require_POST
def new_model(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    serializer = DjangoModelSerializer(data={**request.POST.dict(), "on_dataset": dataset.id})
    if not serializer.is_valid():
        return JsonResponse(serializer.errors, status=400)
    try:
        model = serializer.save()
    except OperationError as error:
        return JsonResponse({"error": error.public()}, status=409)
    return redirect("kedrogy:detail_model", model_id=model.id)


def detail_model(request, model_id):
    model = get_object_or_404(DjangoModel, pk=model_id)
    print(model)
    return render(
        request, "kedrogy/detail_model.html", model_context(model)
    )


@require_POST
def train_model(request, model_id):
    print("train model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    try:
        run, _ = start_training(model_id, request.POST.get("request_key") or request.headers.get("Idempotency-Key"))
    except OperationError as error:
        return JsonResponse({"error": error.public()}, status=409 if error.code in {"TRAINING_ACTIVE", "DRAFT_CHANGED", "MODEL_BUSY"} else 400)
    return render(
        request, "kedrogy/training.html", {"model": model, "result_id": str(run.id)}
    )


@require_POST
def delete_model(request, model_id):
    return cleanup(request, "model_files", model_id)


def new_delete_model_result(request, result_id):
    return task_result_view(request, result_id, new_delete_model_task, "kedrogy/deleting.html", training=False)


@require_POST
def retry_cleanup_view(request, identifier):
    from .deletion import retry_deletion
    get_object_or_404(DeletionRun, pk=identifier)
    retry_deletion(identifier)
    return redirect("kedrogy:new-delete-model-result", result_id=str(identifier))


def new_train_result(request, result_id):
    return task_result_view(request, result_id, new_train_task, "kedrogy/training.html", training=True)


@require_POST
def serve_model(request, model_id):
    print("serving model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    try:
        run, _ = start_serving(model_id, request.POST.get("request_key") or request.headers.get("Idempotency-Key"))
    except OperationError as error:
        return JsonResponse({"error": error.public()}, status=409)
    return render(request, "kedrogy/serving.html", {"model": model, "result_id": str(run.id)})


@require_POST
def stop_model(request, model_id):
    get_object_or_404(DjangoModel, pk=model_id)
    stop_serving(model_id)
    return redirect("kedrogy:detail_model", model_id=model_id)


def new_serve_result(request, result_id):
    return task_result_view(request, result_id, new_serve_task, "kedrogy/serving.html", training=False)


@require_POST
def predict_model(request, model_id):
    model = get_object_or_404(DjangoModel, pk=model_id)
    text_input = request.POST.get("text_input", "")
    context = model_context(model) | {"given_text_input": text_input}
    try:
        context["predicted_class"] = predict_text(model.id, text_input)["label"]
    except OperationError as error:
        context["prediction_error"] = str(error)
        model.refresh_from_db()
        context["serving"] = public_serving(model.current_serving)
        return render(request, "kedrogy/detail_model.html", context,
                      status=400 if error.code == "INVALID_TEXT" else 504 if error.code == "PREDICTION_TIMEOUT" else 503)
    return render(request, "kedrogy/detail_model.html", context)


def model_context(model):
    return {"model": model, "predicted_class": None, "serving": public_serving(model.current_serving),
            "draft_labels": DjangoModelSerializer(model).data["labels"], "request_key": str(uuid.uuid4())}



def cleanup(request, action, identifier):
    from django.views.decorators.http import require_http_methods

    from .deletion import preview, request_deletion

    @require_http_methods(["GET", "POST"])
    def response(request):
        try:
            if request.method == "POST" and request.POST.get("preview_token"):
                run, _ = request_deletion(action, identifier, request.POST["preview_token"], request.POST.get("request_key"))
                return render(request, "kedrogy/deleting.html", {"result_id": run.id})
            plan = preview(action, identifier)
            status = 409 if request.method == "POST" and plan["issues"] else 200
            return render(request, "kedrogy/cleanup_preview.html", {"plan": plan, "request_key": str(uuid.uuid4())}, status=status)
        except OperationError as error:
            return JsonResponse({"error": error.public()}, status=409)
    return response(request)


@require_POST
def stop_annotation_view(request, dataset_id):
    from .annotation import stop_annotation
    get_object_or_404(DjangoDataset, pk=dataset_id)
    stop_annotation(dataset_id)
    return redirect("kedrogy:detail", dataset_id=dataset_id)


@require_POST
def refresh_annotations_view(request, dataset_id):
    get_object_or_404(DjangoDataset, pk=dataset_id)
    DjangoDataset.objects.filter(pk=dataset_id).update(annotation_refresh_requested=True)
    return redirect("kedrogy:detail", dataset_id=dataset_id)
