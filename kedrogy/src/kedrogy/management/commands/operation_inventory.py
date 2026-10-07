"""Read-only inventory; legacy queue rows are never replayed automatically."""

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django_tasks.backends.database.models import DBTaskResult
from kedrogy.models import (
    AnnotationRun,
    DeletionRun,
    DjangoDataset,
    DjangoModel,
    TrainingRun,
)


class Command(BaseCommand):
    help = "List operation identities and historical queue deliveries without changing them."

    def add_arguments(self, parser):
        parser.add_argument("--resources", action="store_true", help="Read resource identities and ownership without cleanup.")

    def handle(self, *args, **options):
        links = {}
        for model in (TrainingRun, AnnotationRun, DeletionRun):
            links.update({row.task_id: {"operation_id": str(row.pk), "state": row.status}
                          for row in model.objects.exclude(task_id="")})
        report = {"deliveries": [{"id": str(row.id), "status": row.status,
            "operation": links.get(str(row.id)),
            "disposition": "Observe domain operation" if str(row.id) in links else "Review worker liveness and intent; do not replay automatically"}
            for row in DBTaskResult.objects.filter(status__in=["READY", "RUNNING"])[:200]],
            "retained_annotations": list(DjangoDataset.objects.filter(retired_at__isnull=False, annotations_deleted=False).values(
                "id", "prodigy_dataset_name", "prodigy_dataset_id", "binding_state"))}
        report["pending_cleanup"] = list(DeletionRun.objects.exclude(status="SUCCEEDED").values("id", "target", "status", "step"))
        if options["resources"]:
            from kedrogy.deletion import _inventory
            from kedrogy.kubernetes import command
            proven, issues = _inventory(DjangoModel.objects.select_related("current_serving").all())
            report["verified_model_resources"], report["ownership_issues"] = proven, issues
            found = command(["get", "deployments,jobs,services,configmaps,persistentvolumeclaims", "-o", "json"],
                            namespace=settings.KEDROGY_NAMESPACE, json_output=True)
            report["resource_identities"] = [{"kind": row["kind"], "name": row["metadata"]["name"],
                "uid": row["metadata"]["uid"], "namespace": settings.KEDROGY_NAMESPACE,
                "disposition": "Inventory only; names and labels alone do not authorize historical cleanup"}
                for row in found.get("items", [])]
        self.stdout.write(json.dumps(report, indent=2, default=str))
