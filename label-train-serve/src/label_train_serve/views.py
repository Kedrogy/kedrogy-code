from django.http import HttpResponse

# from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django_tasks import default_task_backend, TaskResultStatus, TaskResult

from .models import DjangoDataset
from .tasks import new_dataset_task


# @login_required # use LoginRequiredMiddleware instead
def index(request):
    dataset_list = (
        DjangoDataset.objects.all()
    )  # has no calss attribute objects: https://pyrefly.org/en/docs/django/
    context = {"dataset_list": dataset_list}
    return render(request, "label_train_serve/index.html", context)


def detail(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    print(dataset)
    return render(request, "label_train_serve/detail.html", {"dataset": dataset})


def new_dataset(request):  # , dataset_name):
    if request.method == "POST":
        dataset_name = request.POST.get("dataset_name")
        image = request.POST.get("image")
        workingDir = request.POST.get("workingDir")
        pipeline = request.POST.get("pipeline")
        recipe = request.POST.get("recipe")
        recipe_options = request.POST.get("recipe_options")
    print(dataset_name, image, workingDir, pipeline, recipe, recipe_options)
    dataset = {
        "dataset_name": dataset_name,
        "image": image,
        "workingDir": workingDir,
        "pipeline": pipeline,
        "recipe": recipe,
        "recipe_options": recipe_options,
    }
    # myresult = new_dataset_task.enqueue(dataset)
    # # return HttpResponse("You're creating a dataset %s , result id %s" % (dataset_name, myresult.id))
    # context = {"dataset_name": dataset_name, "result_id": myresult.id}
    # # return render(request, "label_train_serve/new_dataset.html", context)#You're creating a dataset
    # return render(request, "label_train_serve/detail_task.html", context)

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
    return redirect("label_train_serve:detail", dataset_id=this_dataset.id)


def delete_dataset(request, dataset_id):
    dataset = get_object_or_404(DjangoDataset, pk=dataset_id)
    dataset.delete()
    return redirect("label_train_serve:index")


def new_dataset_poll(request, dataset_name, result_id):
    context = {"dataset_name": dataset_name, "result_id": result_id}
    return render(request, "label_train_serve/detail_task.html", context)


def new_dataset_result(request, result_id):
    taskResult: TaskResult = new_dataset_task.get_result(result_id)
    if not taskResult.is_finished:
        result = f"status: {taskResult.status}"
    else:
        result = taskResult.return_value
    logs = taskResult.metadata.get("logs", "")
    # TODO if is_finished return non-HTMX to stop polling
    return render(
        request,
        "label_train_serve/detail_task.html#task_result",
        {"result_id": result_id, "result": result, "logs": logs},
    )
