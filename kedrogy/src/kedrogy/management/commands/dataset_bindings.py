"""Inspect annotation identity evidence or establish an explicit historical binding."""

import json
import shlex

from django.core.management.base import BaseCommand, CommandError
from kedrogy.dataset_bindings import bind_dataset, inventory
from kedrogy.kubernetes import OperationError
from kedrogy.models import DjangoDataset


class Command(BaseCommand):
    help = "Read binding evidence; use --bind APP_ID --name EXACT_NAME --prodigy-id ID for an explicit mapping."

    def add_arguments(self, parser):
        parser.add_argument("--bind", type=int)
        parser.add_argument("--name")
        parser.add_argument("--prodigy-id", type=int)
        parser.add_argument("--apply-unambiguous", action="store_true")

    def handle(self, *args, **options):
        try:
            if options["bind"] is not None:
                if not options["name"] or options["prodigy_id"] is None:
                    raise CommandError("Explicit binding requires both --name and --prodigy-id.")
                bind_dataset(options["bind"], options["name"], options["prodigy_id"], allow_existing=True)
            source = inventory()
            datasets = list(DjangoDataset.objects.all())
            result = []
            for dataset in datasets:
                # A persisted full recipe is evidence of the original technical name.
                # A short recipe or mutable display name alone is insufficient.
                try:
                    recipe = shlex.split(dataset.recipe_options)
                except ValueError:
                    recipe = []
                name = (recipe[1] if len(recipe) == 5 and recipe[0] == "myrecipes.textcat.custom-model"
                        and recipe[2] == "./data/00_examples/examples.jsonl" and recipe[3] in ("-l", "--label") else None)
                matches = [item for item in source if item["name"] == name and not item.get("session")]
                claims = sum(1 for other in datasets if other.prodigy_dataset_name == name or name and other.recipe_options == dataset.recipe_options)
                candidate = matches[0] if len(matches) == 1 and claims <= 1 else None
                if options["apply_unambiguous"] and dataset.binding_state == "UNRESOLVED" and candidate:
                    bind_dataset(dataset.pk, candidate["name"], candidate["id"], allow_existing=True)
                    dataset.refresh_from_db()
                result.append({"app_id": dataset.pk, "display_name": dataset.dataset_name,
                    "state": dataset.binding_state, "key": dataset.prodigy_dataset_name,
                    "prodigy_id": dataset.prodigy_dataset_id, "verified_recipe_candidate": candidate,
                    "diagnostic": "Explicit mapping is required." if dataset.binding_state == "UNRESOLVED" and not candidate else None})
            self.stdout.write(json.dumps({"application": result, "annotation_sets": source}, indent=2))
        except OperationError as error:
            raise CommandError(f"{error.code}: {error}") from None
