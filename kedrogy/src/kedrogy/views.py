from spacy.util import find_available_port
import json
import os
import socket
from contextlib import closing
import subprocess
import time

import requests

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django_tasks import default_task_backend, TaskResultStatus, TaskResult

from .models import DjangoDataset, DjangoModel, DjangoLastDataset
from .tasks import (
    new_dataset_task,
    new_train_task,
    new_serve_task,
    new_delete_model_task,
)


# @login_required # use LoginRequiredMiddleware instead
def index(request):
    dataset_list = (
        # XXX ignore those for now , https://github.com/astral-sh/ty/issues/1018
        DjangoDataset.objects.all()
    )  # has no calss attribute objects: https://pyrefly.org/en/docs/django/
    model_list = DjangoModel.objects.all()
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
    print(dataset)
    return render(request, "kedrogy/detail.html", {"dataset": dataset})


def new_dataset(request):  # , dataset_name):
    if request.method == "POST":
        dataset_name = request.POST.get("dataset_name")
        image = request.POST.get("image")
        workingDir = request.POST.get("workingDir")
        pipeline = request.POST.get("pipeline")
        # recipe = request.POST.get("recipe")
        recipe_options = request.POST.get("recipe_options")
        # parameters for load_examples
        data_table_name = request.POST.get("data_table_name")
        id_field = request.POST.get("id_field")
    print(
        dataset_name,
        image,
        workingDir,
        pipeline,
        # recipe,
        recipe_options,
    )
    # redirect?
    this_dataset = DjangoDataset(
        dataset_name=dataset_name,
        image=image,
        workingDir=workingDir,
        pipeline=pipeline,
        # recipe=recipe,
        recipe_options=recipe_options,
        # parameters for load_examples
        data_table_name=data_table_name,
        id_field=id_field,
    )
    this_dataset.save()
    return redirect("kedrogy:detail", dataset_id=this_dataset.id)


def label_dataset(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    myresult = new_dataset_task.enqueue(dataset.to_dict())
    # return HttpResponse("You're creating a dataset %s , result id %s" % (dataset_name, myresult.id))
    context = {"dataset_name": dataset.dataset_name, "result_id": myresult.id}
    # return render(request, "kedrogy/new_dataset.html", context)#You're creating a dataset
    return render(request, "kedrogy/detail_task.html", context)
    # return redirect("kedrogy:index")


def delete_dataset(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    dataset.delete()
    return redirect("kedrogy:index")


def new_dataset_poll(request, dataset_name, result_id):
    context = {"dataset_name": dataset_name, "result_id": result_id}
    return render(request, "kedrogy/detail_task.html", context)


def update_latest_dataset(dataset_id):
    found = list(DjangoLastDataset.objects.all())
    if len(found) > 0:
        DjangoLastDataset.objects.all().delete()
    latest = DjangoLastDataset(dataset_id=dataset_id).save()
    return latest


def get_latest_dataset():
    x = list(DjangoLastDataset.objects.all())
    if len(x) > 0:
        return x[0]
    return None


def new_dataset_result(request, result_id):
    taskResult: TaskResult = new_dataset_task.get_result(result_id)
    if not taskResult.is_finished:
        result = f"status: {taskResult.status}"
    else:
        result = taskResult.return_value
        # dataset = get_object_or_404(DjangoDataset, pk=result["dataset_id"])
        # dataset.running = True
        # dataset.save()
        update_latest_dataset(result["dataset_id"])
        return redirect("kedrogy:index")
    logs = taskResult.metadata.get("logs", "")
    # TODO if is_finished return non-HTMX to stop polling
    return render(
        request,
        "kedrogy/detail_task.html#task_result",
        {"result_id": result_id, "result": result, "logs": logs},
    )


def new_model(request, dataset_id):
    labels = request.POST.get("labels")
    a_preprocess_fun = request.POST.get("a_preprocess_fun")
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    print("new model on dataset", dataset, "using labels", labels, flush=True)
    that_model = DjangoModel.objects.create(
        on_dataset=dataset,
        labels=labels,
        a_preprocess_fun=a_preprocess_fun,
    )
    return redirect("kedrogy:detail_model", model_id=that_model.id)


def detail_model(request, model_id):
    model = get_object_or_404(DjangoModel, pk=model_id)
    print(model)
    return render(
        request, "kedrogy/detail_model.html", {"model": model, "predicted_class": None}
    )


def train_model(request, model_id):
    print("train model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    myresult = new_train_task.enqueue(model_id)
    return render(
        request, "kedrogy/training.html", {"model": model, "result_id": myresult.id}
    )


def delete_model(request, model_id):
    print("delete model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    myresult = new_delete_model_task.enqueue(model_id)
    return render(
        request, "kedrogy/deleting.html", {"model": model, "result_id": myresult.id}
    )


#     model = get_object_or_404(DjangoModel, pk=model_id)
#     if model.trained:
#         None
#     if model.served:
#         None
# delete job train-{ model.id }
#     model.delete()
#     return redirect("kedrogy:index")


def new_delete_model_result(request, result_id):
    taskResult: TaskResult = new_delete_model_task.get_result(result_id)
    if not taskResult.is_finished:
        result = f"status: {taskResult.status}"
    else:
        result = taskResult.return_value
        # dataset = get_object_or_404(DjangoDataset, pk=result["dataset_id"])
        # dataset.running = True
        # dataset.save()
        # update_latest_dataset(result["dataset_id"])
        return render(request, "kedrogy/done.html")
    logs = taskResult.metadata.get("logs", "")
    # TODO if is_finished return non-HTMX to stop polling
    return render(
        request,
        "kedrogy/deleting.html#task_result",
        {"result_id": result_id, "result": result, "logs": logs},
    )


def new_train_result(request, result_id):
    taskResult: TaskResult = new_train_task.get_result(result_id)
    if not taskResult.is_finished:
        result = f"status: {taskResult.status}"
    else:
        result = taskResult.return_value
        # dataset = get_object_or_404(DjangoDataset, pk=result["dataset_id"])
        # dataset.running = True
        # dataset.save()
        # update_latest_dataset(result["dataset_id"])
        return render(request, "kedrogy/done.html")
    logs = taskResult.metadata.get("logs", "")
    # TODO if is_finished return non-HTMX to stop polling
    return render(
        request,
        "kedrogy/training.html#task_result",
        {"result_id": result_id, "result": result, "logs": logs},
    )


def serve_model(request, model_id):
    print("serving model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    myresult = new_serve_task.enqueue(model_id)
    return render(
        request, "kedrogy/serving.html", {"model": model, "result_id": myresult.id}
    )


def new_serve_result(request, result_id):
    taskResult: TaskResult = new_serve_task.get_result(result_id)
    if not taskResult.is_finished:
        result = f"status: {taskResult.status}"
    else:
        result = taskResult.return_value
        # dataset = get_object_or_404(DjangoDataset, pk=result["dataset_id"])
        # dataset.running = True
        # dataset.save()
        # update_latest_dataset(result["dataset_id"])
        return render(request, "kedrogy/done.html")
    logs = taskResult.metadata.get("logs", "")
    # TODO if is_finished return non-HTMX to stop polling
    return render(
        request,
        "kedrogy/serving.html#task_result",
        {"result_id": result_id, "result": result, "logs": logs},
    )


def predict_call(text_input, url="http://0.0.0.0:8888/predict"):
    # curl -H "Content-Type: application/json" http://0.0.0.0:8888/predict -d '{"text":"Hello, world"}'

    # url = "http://0.0.0.0:8888/predict"

    resp = requests.post(
        url=url,
        data=json.dumps(
            {
                "text": text_input,  # "Hello, world",
            }
        ),
    )
    predicted_class_id = resp.json()["predicted_class_id"]

    return predicted_class_id


# h/t: https://stackoverflow.com/a/45690594
# or spacy.find_available_port
def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def predict_model(request, model_id):
    if request.method == "POST":
        text_input = request.POST.get("text_input")
    model = get_object_or_404(DjangoModel, pk=model_id)
    # XXX or task? async?
    if os.getenv("KUBERNETES_SERVICE_HOST", "NOT_FOUND") != "NOT_FOUND":
        # kubernetes pod
        url = f"http://serve-svc-{model.id}.default.svc.cluster.local:8888/predict"
    else:
        try_port = find_free_port()

        # XXX tasks.py kubectl
        process = subprocess.Popen(
            [
                "kubectl",
                "port-forward",
                f"svc/serve-svc-{model.id}",
                f"{try_port}:8888",
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        sleep = 0.3
        for line in process.stdout:
            if "Forwarding from" in line:
                break
            time.sleep(sleep)
        url = f"http://0.0.0.0:{try_port}/predict"

    predicted_class = predict_call(text_input, url)
    if process:
        process.kill()
    print("predict_model", model.id, "predicted_class", predicted_class)
    return render(
        request,
        "kedrogy/detail_model.html",
        {
            "model": model,
            "predicted_class": predicted_class,
            "given_text_input": text_input,
        },
    )
