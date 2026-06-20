import logging
import time
import subprocess

from django_tasks import TaskContext, task
from django.shortcuts import get_object_or_404
from pathlib import Path
from jinja2 import Template

from .models import DjangoDataset


logger = logging.getLogger(__name__)


def kubectl(context, args):
    # args = ["bash", "-c", 'for i in {1..10}; do echo "log line $i" ; sleep 1 ; done']
    process = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    for line in process.stdout:
        context.metadata["logs"] = context.metadata["logs"] + line
        context.save_metadata()

        time.sleep(1)


def render_print(jinja_filename, ingress_data):
    template_ingress = Template(
        (Path(__file__).resolve().parent / "templates_k8s" / jinja_filename).read_text()
    )
    render_ingress = template_ingress.render(**ingress_data)
    print(render_ingress)
    return render_ingress


@task(takes_context=True)
def new_dataset_task(context: TaskContext, task_parameters: dict):
    # update this dataset
    this_dataset = get_object_or_404(DjangoDataset, pk=task_parameters["dataset_id"])
    print(this_dataset, flush=True)
    dataset_name = this_dataset.dataset_name
    logger.warning(
        f"Attempt {context.attempt} to create dataset {dataset_name}. Task result id: {context.task_result.id}."
    )
    context.metadata["logs"] = ""

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
        task_parameters,
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
    return f"Prodigy for {dataset_name} has been started"
