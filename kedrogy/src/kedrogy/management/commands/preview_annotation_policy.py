"""Preview legacy label review without exporting text or changing annotations."""

import json

from django.core.management.base import BaseCommand
from kedrogy_contracts import legacy_annotation_preview

from kedrogy.dataset_bindings import read_bound_annotations
from kedrogy.models import DjangoDataset


class Command(BaseCommand):
    help = "Show safe counts for migrating legacy binary annotations to explicit choices."

    def add_arguments(self, parser):
        parser.add_argument("dataset_id", type=int)
        parser.add_argument("--labels", required=True, help="Exact target classes as a JSON array; no automatic aliases.")

    def handle(self, *args, **options):
        dataset = DjangoDataset.objects.get(pk=options["dataset_id"])
        _, rows = read_bound_annotations(dataset)
        self.stdout.write(json.dumps(legacy_annotation_preview(rows, json.loads(options["labels"])), sort_keys=True))
