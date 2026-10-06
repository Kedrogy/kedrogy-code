"""Regression checks for stable data identity, preflight, and serving revisions."""

import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from kedrogy_contracts import (
    ContractError,
    annotation_summary,
    normalize_labels,
    validate_prediction,
)

from .kubernetes import OperationError
from .models import DjangoDataset, DjangoModel, ServingRun, TrainingRun
from .serving import (
    _observe,
    advance_serving,
    public_serving,
    start_serving,
    startup_result,
    stop_serving,
)
from .tasks import request_resource_deletion
from .tests import choice_rows, dataset_values
from .training import _finish, _pods, start_training

ROWS = choice_rows()


class ContractTests(SimpleTestCase):
    def test_class_order_case_and_legacy_adapter(self):
        self.assertEqual(normalize_labels(" POS, NEG "), ("POS", "NEG"))
        self.assertEqual(normalize_labels(["N", "n"]), ("N", "n"))
        for value in [[], "", "P,", [1], ["P", " P "], ["OTHER"], ["P,N"], ["P\n"]]:
            with self.subTest(value=value), self.assertRaises(ContractError):
                normalize_labels(value)

    def test_exact_annotation_case_and_invalid_json_fail(self):
        for changed in [{"accept": ["p"]}, {"accept": [" P "]}, {"accept": None}, {"text": " "}, {"answer": []}, {"score": float("nan")}]:
            with self.subTest(changed=changed), self.assertRaises(ContractError):
                annotation_summary([ROWS[0] | changed, *ROWS[1:]], ["P", "N"], dataset_id=6)

    def test_fingerprint_preserves_multiset_and_identity(self):
        first = annotation_summary(ROWS, ["P", "N"], dataset_id=6)
        self.assertEqual(first, annotation_summary(list(reversed(ROWS)), ["P", "N"], dataset_id=6))
        for rows, identifier in [(ROWS + [ROWS[0]], 6), ([ROWS[0] | {"text": "Changed"}, *ROWS[1:]], 6), (ROWS, 7)]:
            self.assertNotEqual(first["fingerprint"], annotation_summary(rows, ["P", "N"], dataset_id=identifier)["fingerprint"])

    def test_zero_and_response_identity_are_validated(self):
        value = {"class_id": 0, "label": "OTHER", "contract_version": 1, "training_run_id": "train", "serving_run_id": "serve"}
        args = {"labels": ["P", "N"], "training_run_id": "train", "serving_run_id": "serve"}
        self.assertEqual(validate_prediction(value, **args)["label"], "OTHER")
        for change in [{"class_id": False}, {"class_id": 3}, {"label": "P"}, {"contract_version": True}, {"serving_run_id": "old"}]:
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_prediction(value | change, **args)


class RevisionTests(TestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values(), binding_state="BOUND", prodigy_dataset_id=6)
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, labels="P,N", label_schema=["P", "N"], a_preprocess_fun="")
        reader = patch("kedrogy.training_preflight.read_bound_annotations", return_value=(6, copy.deepcopy(ROWS)))
        self.reader = reader.start()
        self.addCleanup(reader.stop)

    def publish(self, key="train"):
        run, _ = start_training(self.model.pk, key)
        run.status = "SUCCEEDED"
        run.artifact = {"path": f"runs/{run.id}/attempt/artifact", "labels": run.snapshot["labels"]}
        run.save()
        self.model.published_run = run
        self.model.artifact_status = "VERIFIED"
        self.model.trained = True
        self.model.save()
        return run

    def test_rename_keeps_binding_and_snapshot_even_with_invalid_launch_config(self):
        run = self.publish()
        snapshot = copy.deepcopy(run.snapshot)
        self.dataset.image = "obsolete"
        self.dataset.save()
        response = self.client.patch(f"/api/datasets/{self.dataset.pk}/", json.dumps({"display_name": "Renamed title"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.prodigy_dataset_id, 6)
        self.assertEqual(self.dataset.prodigy_dataset_name, snapshot["dataset"]["dataset_name"])
        run.refresh_from_db()
        self.assertEqual(run.snapshot, snapshot)
        repeated, created = start_training(self.model.pk, "train")
        self.assertFalse(created)
        self.assertEqual(repeated.pk, run.pk)

    def test_label_api_shape_and_rejections(self):
        url = f"/api/models/{self.model.pk}/"
        response = self.client.patch(url, json.dumps({"labels": " POS, NEG "}), content_type="application/json")
        self.assertEqual(response.json()["labels"], ["POS", "NEG"])
        for labels in [["P", " P "], ["OTHER"], [3], [""]]:
            self.assertEqual(self.client.patch(url, json.dumps({"labels": labels}), content_type="application/json").status_code, 400)

    def test_incompatible_annotations_never_enqueue_a_run(self):
        self.reader.return_value = (6, [ROWS[0] | {"accept": ["positive"]}, *ROWS[1:]])
        with patch("kedrogy.tasks.new_train_task") as queue:
            response = self.client.post(f"/api/models/{self.model.pk}/train/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_ANNOTATION_LABELS")
        self.assertFalse(TrainingRun.objects.exists())
        queue.enqueue.assert_not_called()

    def test_changed_draft_during_preflight_is_conflict(self):
        def changed(_):
            DjangoModel.objects.filter(pk=self.model.pk).update(label_schema=["N", "P"])
            return 6, ROWS
        self.reader.side_effect = changed
        with self.assertRaises(OperationError) as caught:
            start_training(self.model.pk, "changed")
        self.assertEqual(caught.exception.code, "DRAFT_CHANGED")
        self.assertFalse(TrainingRun.objects.exists())

    def test_success_and_failed_retraining_have_independent_snapshots(self):
        first = self.publish()
        self.model.label_schema = ["N", "P"]
        self.model.save()
        second, _ = start_training(self.model.pk, "second")
        self.assertNotEqual(first.job_name, second.job_name)
        self.assertEqual(first.snapshot["labels"], ["P", "N"])
        self.assertEqual(second.snapshot["labels"], ["N", "P"])
        owner = uuid.uuid4()
        TrainingRun.objects.filter(pk=second.pk).update(lease_owner=owner)
        _finish(second, owner, "FAILED", {"code": "SYNTHETIC", "message": "Synthetic failure."})
        _finish(first, owner, "SUCCEEDED", artifact={"path": "stale"})
        self.model.refresh_from_db()
        self.assertEqual(self.model.published_run_id, first.pk)
        second.refresh_from_db()
        self.assertEqual(second.status, "FAILED")

    def test_foreign_pod_label_does_not_establish_ownership(self):
        job = {"metadata": {"uid": "real-job"}}
        pods = [{"metadata": {"uid": "foreign", "ownerReferences": [{"uid": "other-job"}]}},
                {"metadata": {"uid": "owned", "ownerReferences": [{"uid": "real-job"}]}}]
        with patch("kedrogy.training.command", return_value={"items": pods}):
            self.assertEqual([p["metadata"]["uid"] for p in _pods(job, "test")], ["owned"])

    def test_serving_pins_trained_classes_and_duplicate_requests(self):
        trained = self.publish()
        self.model.label_schema = ["future", "draft"]
        self.model.a_preprocess_fun = "invalid-draft"
        self.model.save()
        run, created = start_serving(self.model.pk, "serve")
        self.assertTrue(created)
        self.assertEqual(run.training_run_id, trained.pk)
        self.assertEqual(run.snapshot["labels"], ["P", "N"])
        for key in ["serve"]:
            repeated, created = start_serving(self.model.pk, key)
            self.assertFalse(created)
            self.assertEqual(repeated.pk, run.pk)
        with self.assertRaises(OperationError) as caught:
            start_serving(self.model.pk, "different-key")
        self.assertEqual(caught.exception.code, "SERVING_ACTIVE")

    def test_stale_get_and_failed_request_do_not_rewrite_startup_success(self):
        self.publish()
        run, _ = start_serving(self.model.pk)
        ServingRun.objects.filter(pk=run.pk).update(status="READY", startup_status="SUCCEEDED", observed_at=timezone.now() - timedelta(minutes=1))
        run.refresh_from_db()
        self.assertEqual(public_serving(run)["status"], "UNAVAILABLE")
        self.assertEqual(startup_result(run)["status"], "SUCCEEDED")
        response = self.client.post(f"/api/models/{self.model.pk}/predict/", {"text_input": "Synthetic"})
        self.assertEqual(response.status_code, 503)
        run.refresh_from_db()
        self.assertEqual(run.status, "READY")

    def test_stop_wins_over_delayed_readiness(self):
        self.publish()
        run, _ = start_serving(self.model.pk)
        owner = uuid.uuid4()
        ServingRun.objects.filter(pk=run.pk).update(lease_owner=owner)
        stop_serving(self.model.pk)
        _observe(run, owner, "READY")
        run.refresh_from_db()
        self.assertEqual(run.status, "STOPPING")
        self.assertEqual(run.startup_status, "FAILED")
        self.assertEqual(self.client.post(f"/api/models/{self.model.pk}/serve/").status_code, 409)

    def test_deleted_deployment_is_not_recreated(self):
        self.publish()
        run, _ = start_serving(self.model.pk)
        run.resource_plan["namespace_uid"] = "namespace-uid"
        run.resource_plan["anchor"]["uid"] = "observed-anchor"
        run.deployment_uid = "observed-uid"
        run.generation = 1
        run.startup_status = "SUCCEEDED"
        run.status = "READY"
        run.save()
        with patch("kedrogy.serving_resources._get", return_value=None), patch("kedrogy.serving_resources.check_namespace"), patch("kedrogy.serving_resources.command") as create:
            run = advance_serving(run.pk)
        self.assertEqual(run.status, "UNAVAILABLE")
        self.assertEqual(run.error["code"], "SERVING_LOST")
        self.assertEqual(run.startup_status, "SUCCEEDED")
        create.assert_not_called()

    def test_startup_deadline_is_terminal(self):
        self.publish()
        run, _ = start_serving(self.model.pk)
        ServingRun.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(hours=1))
        run = advance_serving(run.pk)
        self.assertEqual((run.status, run.startup_status), ("FAILED", "FAILED"))

    def test_resource_deletion_reserves_model_before_queueing(self):
        self.publish()
        from .deletion import preview
        with patch("kedrogy.deletion._inventory", return_value=([], [])):
            plan = preview("model_files", self.model.pk)
        request_resource_deletion(self.model.pk, preview_token=plan["preview_token"])
        with self.assertRaises(OperationError):
            start_serving(self.model.pk)
        with self.assertRaises(OperationError):
            start_training(self.model.pk)

    def test_unique_binding_and_live_serving_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            DjangoDataset.objects.create(**dataset_values(), binding_state="BOUND", prodigy_dataset_id=6)
        self.publish()
        run, _ = start_serving(self.model.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ServingRun.objects.create(model=self.model, training_run=run.training_run, idempotency_key="other", namespace="test")

    def test_newer_failed_observation_wins_over_delayed_ready_response(self):
        self.publish()
        run, _ = start_serving(self.model.pk)
        owner = uuid.uuid4()
        ServingRun.objects.filter(pk=run.pk).update(lease_owner=owner, status="UNAVAILABLE", observed_at=timezone.now(),
            error={"code": "PREDICTION_UNAVAILABLE", "message": "The model failed."})
        _observe(run, owner, "READY")
        run.refresh_from_db()
        self.assertEqual(run.status, "UNAVAILABLE")
        self.assertEqual(run.error["code"], "PREDICTION_UNAVAILABLE")
