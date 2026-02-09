import logging
import time
import subprocess
from typing import TypedDict

from django_tasks import TaskContext, task
from django.shortcuts import get_object_or_404
from pathlib import Path
from jinja2 import Template

from .models import DjangoDataset, DjangoModel


logger = logging.getLogger(__name__)


def kubectl(context, args, sleep: float = 1) -> str:
    """Runs kubectl with args, appends stdout line by line to context["logs"]
    and returns kubectl logs ."""
    # args = ["bash", "-c", 'for i in {1..10}; do echo "log line $i" ; sleep 1 ; done']
    process = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    lines = ""
    for line in process.stdout:
        context.metadata["logs"] = context.metadata["logs"] + line
        context.save_metadata()
        lines = lines + line
        time.sleep(sleep)
    # TODO return process. returncode
    return lines


def render_print(jinja_filename, ingress_data):
    template_ingress = Template(
        (Path(__file__).resolve().parent / "templates_k8s" / jinja_filename).read_text()
    )
    render_ingress = template_ingress.render(**ingress_data)
    print(render_ingress)
    return render_ingress


class NewDatasetTask(TypedDict):
    dataset_id: str
    # DjangoDataset:
    image: str
    workingDir: str
    pipeline: str
    # recipe: str
    recipe_options: str
    # computed:
    recipe_options_split: str
    # parameters for load_examples
    data_table_name: str
    id_field: str


@task(takes_context=True)
def new_dataset_task(context: TaskContext, task_parameters: NewDatasetTask):
    # update this dataset
    this_dataset = get_object_or_404(DjangoDataset, pk=task_parameters["dataset_id"])
    print(this_dataset, flush=True)
    dataset_name = this_dataset.dataset_name
    logger.warning(
        f"Attempt {context.attempt} to create dataset {dataset_name}. Task result id: {context.task_result.id}."
    )
    context.metadata["logs"] = ""

    # TODO create configmap /volume for parameters_load_examples.yml for dataset
    # and mount to prodigy

    # maybe?
    # kubectl(
    #     context,
    #     [
    #         "kubectl",
    #         "delete",
    #         "deployment",
    #         "prodigy",
    #     ],
    # )

    # XXX or jinja split etc
    task_parameters["recipe_options_split"] = (
        '"' + '", "'.join(task_parameters["recipe_options"].split(" ")) + '"'
    )
    render_prodigy = render_print(
        "prodigy.yaml.jinja",
        {
            **task_parameters,
            **{
                "params": f"load_examples_options.data_table_name={task_parameters["data_table_name"]},load_examples_options.dataset_name={dataset_name},load_examples_options.id_field={task_parameters["id_field"]}"
            },
        },
    )
    yaml_filename = f"prodigy-{dataset_name}.yaml"
    Path(yaml_filename).write_text(render_prodigy)
    kubectl(context, ["kubectl", "apply", "-f", yaml_filename])

    kubectl(
        context,
        [
            "kubectl",
            "rollout",
            "status",
            # "-n",
            # "annotate",
            "deployment/prodigy",
        ],
    )
    # example output
    # > kubectl rollout status deployment/prodigy-ysz-textcat-teach-multi
    # Waiting for deployment "prodigy-ysz-textcat-teach-multi" rollout to finish: 0 of 1 updated replicas are available...
    # deployment "prodigy-ysz-textcat-teach-multi" successfully rolled out

    # # first ensure service above , otherwise: <error: services "prodigy-bar" not found>
    # render_ingress = render_print(
    #     "ingress.yaml.jinja",
    #     {"datasets": list(DjangoDataset.objects.all()) + [this_dataset]},
    # )
    # Path("ingress.yaml").write_text(render_ingress)
    # kubectl(context, ["kubectl", "apply", "-f", "ingress.yaml"])
    logger.warning(f"Done label dataset {dataset_name}")
    return {"dataset_id": this_dataset.id}


@task(takes_context=True)
def new_train_task(context: TaskContext, model_id):
    # update this dataset
    this_model: DjangoModel = get_object_or_404(DjangoModel, pk=model_id)
    dataset_name = this_model.on_dataset.dataset_name
    print("training", this_model, "on dataset", dataset_name, flush=True)

    context.metadata["logs"] = ""
    render_manifest = render_print(
        "pvc.yaml.jinja",
        {"model_id": this_model.id},
    )
    yaml_filename = f"pvc-model-{this_model.id}.yaml"
    Path(yaml_filename).write_text(render_manifest)
    kubectl(context, ["kubectl", "apply", "-f", yaml_filename])

    # train.yaml.jinja
    render_manifest = render_print(
        "train.yaml.jinja",
        {
            "model_id": this_model.id,
            "image": this_model.on_dataset.image,
            "workingDir": this_model.on_dataset.workingDir,
            "pipeline": "train",
            # parameters_train.yml
            "dataset_name": dataset_name,
            "labels": f'["{'","'.join(this_model.labels.split(","))}"]',
        },
    )
    yaml_filename = f"pvc-model-{this_model.id}.yaml"
    Path(yaml_filename).write_text(render_manifest)
    kubectl(context, ["kubectl", "apply", "-f", yaml_filename])

    # get pod of the job h/t: https://blog.alexellis.io/fixing-the-ux-for-one-time-tasks-on-kubernetes/
    # kubectl get job train-1 -o "jsonpath={.metadata.labels.controller-uid}"
    # output: 46887afa-18f3-4cfb-ba1a-f3da7dc4c35b
    controller_uid = kubectl(
        context,
        [
            "kubectl",
            "get",
            "job",
            f"train-{this_model.id}",
            "-o",
            "jsonpath={.metadata.labels.controller-uid}",
        ],
    )

    # kubectl get po -l controller-uid=46887afa-18f3-4cfb-ba1a-f3da7dc4c35b -o name
    # output: pod/train-1-v4hck

    pod = kubectl(
        context,
        [
            "kubectl",
            "get",
            "po",
            "-l",
            f"controller-uid={controller_uid}",
            "-o",
            "name",
        ],
    )
    pod = pod[:-1]  # trailing \n

    kubectl(
        context,
        ["kubectl", "wait", "--for=condition=Ready", pod, "--timeout=120s"],
    )

    kubectl(context, ["kubectl", "logs", "-f", pod], sleep=0.3)

    this_model.trained = True
    this_model.save()

    return {"model_id": this_model.id}


@task(takes_context=True)
def new_serve_task(context: TaskContext, model_id):
    this_model: DjangoModel = get_object_or_404(DjangoModel, pk=model_id)
    dataset_name = this_model.on_dataset.dataset_name
    print("serving", this_model, "on dataset", dataset_name, flush=True)

    context.metadata["logs"] = ""
    render_manifest = render_print(
        "serve.yaml.jinja",
        {
            "model_id": this_model.id,
            "image": this_model.on_dataset.image,
            "workingDir": this_model.on_dataset.workingDir,
            "a_preprocess_fun": this_model.a_preprocess_fun,
        },
    )
    yaml_filename = f"serve-{this_model.id}.yaml"
    Path(yaml_filename).write_text(render_manifest)
    kubectl(context, ["kubectl", "apply", "-f", yaml_filename])

    this_model.served = True
    this_model.save()

    return {"model_id": this_model.id}


@task(takes_context=True)
def new_delete_model_task(context: TaskContext, model_id):
    this_model: DjangoModel = get_object_or_404(DjangoModel, pk=model_id)
    dataset_name = this_model.on_dataset.dataset_name
    print("deleting", this_model, "on dataset", dataset_name, flush=True)

    context.metadata["logs"] = ""

    kubectl(
        context,
        ["kubectl", "delete", "deployment", f"serve-{this_model.id}"],
        sleep=0.3,
    )

    this_model.served = False
    this_model.save()

    kubectl(context, ["kubectl", "delete", "job", f"train-{this_model.id}"], sleep=0.3)

    this_model.trained = False
    this_model.save()

    kubectl(
        context, ["kubectl", "delete", "pvc", f"pvc-model-{this_model.id}"], sleep=0.3
    )

    return {"model_id": this_model.id}
