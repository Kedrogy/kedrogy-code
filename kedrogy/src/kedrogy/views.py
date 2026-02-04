from django.http import HttpResponse

# from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django_tasks import default_task_backend, TaskResultStatus, TaskResult

from .models import DjangoDataset, DjangoModel, DjangoLastDataset
from .tasks import new_dataset_task


# @login_required # use LoginRequiredMiddleware instead
def index(request):
    dataset_list = (
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
        recipe = request.POST.get("recipe")
        recipe_options = request.POST.get("recipe_options")
    print(dataset_name, image, workingDir, pipeline, recipe, recipe_options)
    # redirect?
    this_dataset = DjangoDataset(
        dataset_name=dataset_name,
        image=image,
        workingDir=workingDir,
        pipeline=pipeline,
        recipe=recipe,
        recipe_options=recipe_options,
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
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    print("new model on dataset", dataset, "using labels", labels, flush=True)
    that_model = DjangoModel.objects.create(on_dataset=dataset, labels=labels)
    return redirect("kedrogy:detail_model", model_id=that_model.id)


def detail_model(request, model_id):
    model = get_object_or_404(DjangoModel, pk=model_id)
    print(model)
    return render(request, "kedrogy/detail_model.html", {"model": model})


def train_model(request, model_id):
    print("train model with id", model_id)
    model = get_object_or_404(DjangoModel, pk=model_id)
    return render(request, "kedrogy/training.html", {"model": model})


def delete_model(request, model_id):
    model = get_object_or_404(DjangoModel, pk=model_id)
    model.delete()
    return redirect("kedrogy:index")
