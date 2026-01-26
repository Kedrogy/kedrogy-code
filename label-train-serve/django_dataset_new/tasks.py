import logging
import time
import subprocess

from django_tasks import TaskContext, task
from pathlib import Path
from jinja2 import Template

from .models import DjangoDataset


logger = logging.getLogger(__name__)


@task(takes_context=True)
def new_dataset_task(context: TaskContext, dataset_name):
    def kubectl(args):
        # args = ["bash", "-c", 'for i in {1..10}; do echo "log line $i" ; sleep 1 ; done']
        process = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
        for line in process.stdout:
            context.metadata["logs"] = context.metadata["logs"] + line
            context.save_metadata()

            time.sleep(1)

    def render_print(jinja_filename, ingress_data):
        template_ingress = Template(
            (
                Path(__file__).resolve().parent / "k8s_templates" / jinja_filename
            ).read_text()
        )
        render_ingress = template_ingress.render(**ingress_data)
        print(render_ingress)
        return render_ingress

    logger.warning(
        f"Attempt {context.attempt} to create dataset {dataset_name}. Task result id: {context.task_result.id}."
    )
    context.metadata["logs"] = ""

    render_prodigy = render_print(
        "prodigy-deployment-svc.yaml.jinja",
        {"dataset_name": dataset_name},
    )
    yaml_filename = f"prodigy-{dataset_name}.yaml"
    Path(yaml_filename).write_text(render_prodigy)
    kubectl(["kubectl", "apply", "-f", yaml_filename])

    kubectl(
        [
            "kubectl",
            "rollout",
            "status",
            "-n",
            "annotate",
            f"deployment/prodigy-{dataset_name}",
        ]
    )
    # example output 
    # > kubectl rollout status -n annotate deployment/prodigy-ysz-textcat-teach-multi
    # Waiting for deployment "prodigy-ysz-textcat-teach-multi" rollout to finish: 0 of 1 updated replicas are available...
    # deployment "prodigy-ysz-textcat-teach-multi" successfully rolled out

    this_dataset = DjangoDataset(dataset_name=dataset_name)

    # first ensure service above , otherwise: <error: services "prodigy-bar" not found>
    render_ingress = render_print(
        "ingress.yaml.jinja",
        {"datasets": list(DjangoDataset.objects.all()) + [this_dataset]},
    )
    Path("ingress.yaml").write_text(render_ingress)
    kubectl(["kubectl", "apply", "-f", "ingress.yaml"])
    logger.warning(f"Done create dataset {dataset_name}")
    this_dataset.save()
    return f"{dataset_name} has been created"
