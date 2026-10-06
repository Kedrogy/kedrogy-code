"""API guards for immutable annotation meaning and source bindings."""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from .launch_config import LaunchConfigError, validate_dataset
from .models import DjangoDataset, DjangoModel
from .tests import choice_rows, dataset_values
from .training import start_training
from .kubernetes import OperationError


class AnnotationIdentityTests(TestCase):
    def test_existing_binding_cannot_change_source_or_class_objective(self):
        dataset = DjangoDataset.objects.create(**dataset_values(), binding_state="BOUND", prodigy_dataset_id=7)
        for change in [{"recipe_options": "-l P,N"}, {"data_table_name": "other"}]:
            with override_settings(KEDROGY_SOURCES={"all_data": {"schema": "public", "table": "all_data", "id_fields": ["id"]},
                                                   "other": {"schema": "public", "table": "other", "id_fields": ["id"]}}):
                response = self.client.patch(f"/api/datasets/{dataset.pk}/", json.dumps(change), content_type="application/json")
            self.assertEqual(response.status_code, 409)
        dataset.refresh_from_db()
        self.assertEqual(dataset.recipe_options, "-l positive,negative")

    def test_legacy_training_has_a_specific_review_error(self):
        dataset = DjangoDataset.objects.create(**dataset_values(), annotation_policy="reject-other-v1")
        model = DjangoModel.objects.create(on_dataset=dataset, labels="positive,negative", a_preprocess_fun="")
        with patch("kedrogy.training_preflight.read_bound_annotations") as read, self.assertRaises(OperationError) as error:
            start_training(model.id)
        self.assertEqual(error.exception.code, "ANNOTATION_POLICY_REVIEW")
        read.assert_not_called()
        self.assertFalse(model.training_runs.exists())

    def test_server_registry_changes_cannot_rebind_a_pinned_source(self):
        values = dataset_values() | {"source_config": {"schema": "public", "table": "different", "id_fields": ["id"]}}
        with self.assertRaises(LaunchConfigError):
            validate_dataset(values)

    def test_new_annotation_uses_exclusive_choice_recipe(self):
        dataset = DjangoDataset.objects.create(**dataset_values())
        cfg = validate_dataset(dataset.to_dict())
        self.assertEqual(cfg.recipe_args[0], "myrecipes.textcat.choice")
