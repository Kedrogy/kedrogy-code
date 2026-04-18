import json
import os
import subprocess
import time

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import DjangoDataset, DjangoModel
from .serializers import DjangoDatasetSerializer, DjangoModelSerializer
from .tasks import (
    new_dataset_task,
    new_train_task,
    new_serve_task,
    new_delete_model_task,
)
from .views import predict_call, find_free_port


class DatasetViewSet(viewsets.ModelViewSet):
    queryset = DjangoDataset.objects.all()
    serializer_class = DjangoDatasetSerializer

    @action(detail=True, methods=["post"])
    def label(self, request, pk=None):
        dataset = self.get_object()
        result = new_dataset_task.enqueue(dataset.to_dict())
        return Response({"result_id": str(result.id), "dataset_name": dataset.dataset_name})


class MLModelViewSet(viewsets.ModelViewSet):
    queryset = DjangoModel.objects.select_related("on_dataset").all()
    serializer_class = DjangoModelSerializer

    @action(detail=True, methods=["post"])
    def train(self, request, pk=None):
        model = self.get_object()
        result = new_train_task.enqueue(model.id)
        return Response({"result_id": str(result.id), "model_id": model.id})

    @action(detail=True, methods=["post"])
    def serve(self, request, pk=None):
        model = self.get_object()
        result = new_serve_task.enqueue(model.id)
        return Response({"result_id": str(result.id), "model_id": model.id})

    @action(detail=True, methods=["post"])
    def delete_model(self, request, pk=None):
        model = self.get_object()
        result = new_delete_model_task.enqueue(model.id)
        return Response({"result_id": str(result.id), "model_id": model.id})

    @action(detail=True, methods=["post"])
    def predict(self, request, pk=None):
        model = self.get_object()
        text_input = request.data.get("text_input", "")
        process = None

        if os.getenv("KUBERNETES_SERVICE_HOST", "NOT_FOUND") != "NOT_FOUND":
            url = f"http://serve-svc-{model.id}.default.svc.cluster.local:8888/predict"
        else:
            try_port = find_free_port()
            process = subprocess.Popen(
                ["kubectl", "port-forward", f"svc/serve-svc-{model.id}", f"{try_port}:8888"],
                stdout=subprocess.PIPE,
                text=True,
            )
            for line in process.stdout:
                if "Forwarding from" in line:
                    break
                time.sleep(0.3)
            url = f"http://0.0.0.0:{try_port}/predict"

        predicted_class = predict_call(text_input, url)
        if process:
            process.kill()

        return Response({
            "predicted_class": predicted_class,
            "text_input": text_input,
            "model_id": model.id,
        })


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
        return Response({"error": "Unknown task type"}, status=status.HTTP_400_BAD_REQUEST)

    task_result = task_func.get_result(result_id)
    return Response({
        "status": str(task_result.status),
        "is_finished": task_result.is_finished,
        "logs": task_result.metadata.get("logs", ""),
        "return_value": task_result.return_value if task_result.is_finished else None,
    })
