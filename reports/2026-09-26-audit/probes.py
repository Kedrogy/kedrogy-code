"""Audit-only reproductions: passing assertions confirm current defects.

Run with the in-memory test database and mocked external systems:
PYTHONPATH=reports/2026-09-26-audit DJANGO_SETTINGS_MODULE=mysite.test_settings \
  mysite/.venv/bin/python -m django test probes --noinput
"""

import copy
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from urllib3.exceptions import ReadTimeoutError

from kedrogy import annotation, deletion, prediction, serving
from kedrogy.kubernetes import OperationError
from kedrogy.models import AnnotationRun, AnnotationSlot, DeletionRun, DjangoDataset, DjangoModel, ServingRun, TrainingRun
from kedrogy.operation_control import acquire
from kedrogy.tests import dataset_values


class RemainingDefects(TestCase):
    """These deliberately assert buggy outcomes, not desired product behavior."""

    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values(), binding_state="BOUND", prodigy_dataset_id=11)
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, labels="positive,negative", label_schema=["positive", "negative"], a_preprocess_fun="")
        self.training = TrainingRun.objects.create(model=self.model, idempotency_key="audit", namespace="default", job_name=f"train-{uuid.uuid4()}", status="SUCCEEDED")

    def run_record(self, **extra):
        run = ServingRun.objects.create(model=self.model, training_run=self.training, namespace="default", idempotency_key=str(uuid.uuid4()),
            snapshot={"labels": ["positive", "negative"], "image": settings.KEDROGY_ML_IMAGE,
                      "dataset": self.dataset.to_dict(), "preprocessor": "", "artifact": {"path": "synthetic/artifact"}}, **extra)
        DjangoModel.objects.filter(pk=self.model.pk).update(current_serving=run)
        return run

    def test_serving_replaces_a_foreign_deployment(self):
        foreign = {"kind": "Deployment", "metadata": {"name": "serve-1", "uid": "foreign-uid", "resourceVersion": "8", "labels": {"owner": "another-application"}},
                   "spec": {"selector": {"matchLabels": {"owner": "another-application"}}}}
        desired = {"kind": "Deployment", "metadata": {"name": "serve-1", "labels": {"kedrogy/serving-id": "new-run"}},
                   "spec": {"selector": {"matchLabels": {"app": "model"}}, "template": {"metadata": {"labels": {}}}}}
        with patch("kedrogy.serving._get", return_value=foreign), patch("kedrogy.serving.command") as command:
            serving._put(desired, "default")
        self.assertEqual(command.call_args.args[0][0], "replace")
        self.assertEqual(command.call_args.kwargs["document"]["metadata"]["uid"], "foreign-uid")

    def test_expired_serving_lease_still_authorizes_writes(self):
        owner = uuid.uuid4()
        run = self.run_record(lease_owner=owner, lease_until=timezone.now()-timedelta(seconds=1))
        self.assertTrue(serving._owned(run, owner))

    def test_delayed_serving_worker_writes_after_new_revision_takes_over(self):
        owner = uuid.uuid4()
        old = self.run_record(lease_owner=owner, lease_until=timezone.now()+timedelta(seconds=360))
        from kedrogy.launch_config import validate_dataset
        cfg = validate_dataset(old.snapshot["dataset"])
        replacement = []

        def resume_after_takeover(_):
            # Deterministic barrier: old worker passed _owned, then was paused.
            ServingRun.objects.filter(pk=old.pk).update(status="STOPPED", lease_owner=None, lease_until=None)
            replacement.append(self.run_record(status="READY", startup_status="SUCCEEDED"))
            return cfg

        deployment = {"metadata": {"uid": "new-uid", "generation": 1, "labels": {"kedrogy/serving-id": str(old.pk)}}, "status": {}}
        with patch("kedrogy.serving._get", return_value=None), patch("kedrogy.serving.validate_dataset", side_effect=resume_after_takeover), patch("kedrogy.serving._put", return_value=deployment) as put:
            serving._advance(old, owner)
        self.assertEqual(put.call_count, 2)
        self.assertEqual(put.call_args_list[0].args[0]["metadata"]["labels"]["kedrogy/serving-id"], str(old.pk))
        self.model.refresh_from_db()
        self.assertEqual(self.model.current_serving_id, replacement[0].pk)

    def test_annotation_can_create_a_deployment_after_stop_completed(self):
        run, _ = annotation.start_annotation(self.dataset.pk, "audit-annotation")
        run, owner = acquire(AnnotationRun, run.pk, ("STARTING",))
        created_after_stop = []

        def create(document, namespace):
            result = copy.deepcopy(document)
            result["metadata"].update(uid=str(uuid.uuid4()), generation=1)
            if result["kind"] == "Deployment":
                # Pause after the ownership check; a new owner finishes Stop.
                AnnotationRun.objects.filter(pk=run.pk).update(status="STOPPED", lease_owner=None, lease_until=None)
                AnnotationSlot.objects.filter(run=run).update(run=None)
                created_after_stop.append(result)
            return result

        with patch("kedrogy.annotation._get", return_value=None), patch("kedrogy.annotation._ensure", side_effect=create):
            annotation._advance(run, owner)
        run.refresh_from_db()
        self.assertEqual(run.status, "STOPPED")
        self.assertEqual(len(created_after_stop), 1)
        self.assertIsNone(AnnotationSlot.objects.get().run_id)

    def test_successful_http_check_can_publish_ready_after_annotation_deadline(self):
        run, _ = annotation.start_annotation(self.dataset.pk, "late")
        run, owner = acquire(AnnotationRun, run.pk, ("STARTING",))
        AnnotationRun.objects.filter(pk=run.pk).update(created_at=timezone.now()-timedelta(hours=1))
        run.refresh_from_db()
        annotation._observe(run, owner, "READY")
        run.refresh_from_db()
        self.assertEqual((run.status, run.startup_status), ("READY", "SUCCEEDED"))

    def test_busy_prediction_probe_demotes_a_healthy_service(self):
        run = self.run_record(status="READY", startup_status="SUCCEEDED", deployment_uid="uid", generation=1, observed_at=timezone.now())
        deployment = {"metadata": {"uid": "uid", "generation": 1, "labels": {"kedrogy/serving-id": str(run.pk)}},
                      "status": {"observedGeneration": 1, "updatedReplicas": 1, "readyReplicas": 1, "availableReplicas": 1, "replicas": 1}}
        with patch("kedrogy.serving._get", return_value=deployment), patch("kedrogy.prediction.check_service", side_effect=OperationError("PREDICTION_BUSY", "The model is busy. Retry shortly.")):
            serving.advance_serving(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.status, "UNAVAILABLE")

    def test_low_level_response_timeout_escapes_public_error_boundary(self):
        response = MagicMock(status_code=200)
        response.raw.read.side_effect = ReadTimeoutError(None, "/predict", "synthetic timeout")
        response.__enter__.return_value = response
        run = SimpleNamespace(snapshot={"labels": ["positive"]}, training_run_id=uuid.uuid4(), id=uuid.uuid4())
        with patch("kedrogy.prediction.requests.post", return_value=response), self.assertRaises(ReadTimeoutError):
            prediction.call("Synthetic", "http://synthetic.invalid/predict", run=run)

    def test_cleanup_non_object_json_becomes_500(self):
        self.client.raise_request_exception = False
        response = self.client.post(f"/api/models/{self.model.pk}/delete_model/", "[]", content_type="application/json")
        self.assertEqual(response.status_code, 500)

    def test_serving_history_calls_a_stopped_revision_served(self):
        self.run_record(status="STOPPED", startup_status="SUCCEEDED")
        data = self.client.get(f"/api/models/{self.model.pk}/runs/").json()
        self.assertTrue(data[0]["served"])

    def test_model_list_query_count_grows_with_each_model(self):
        with CaptureQueriesContext(connection) as first:
            response = self.client.get("/api/models/")
            self.assertEqual(response.status_code, 200)
        for _ in range(10):
            DjangoModel.objects.create(on_dataset=self.dataset, label_schema=["positive"], a_preprocess_fun="")
        with CaptureQueriesContext(connection) as second:
            response = self.client.get("/api/models/")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(second)-len(first), 10)
        print(f"AUDIT model-list queries: {len(first)} for one model, {len(second)} for eleven")

    def test_annotation_cleanup_retry_reuses_failed_job_without_recovery(self):
        owner = uuid.uuid4()
        run = DeletionRun.objects.create(dataset=self.dataset, action="annotations", target=f"dataset:{self.dataset.pk}", idempotency_key="purge",
            status="RUNNING", lease_owner=owner, lease_until=timezone.now()+timedelta(seconds=360),
            plan={"annotations": {"name": "synthetic", "id": 11, "fingerprint": "0"*64}, "cleanup_image": settings.KEDROGY_ML_IMAGE, "namespace": "default", "resources": []})
        failed = {"kind": "Job", "metadata": {"name": f"annotation-delete-{run.id}", "uid": "failed-job", "labels": {"kedrogy/deletion-id": str(run.id)}},
                  "status": {"conditions": [{"type": "Failed", "status": "True"}]}}
        run.plan["annotation_job"] = {"kind": "Job", "name": failed["metadata"]["name"], "namespace": "default", "uid": "failed-job"}
        run.save(update_fields=["plan"])
        with patch("kedrogy.deletion._get", return_value=failed), patch("kedrogy.deletion._ensure") as create:
            for _ in range(2):
                with self.assertRaisesRegex(OperationError, "Annotation cleanup failed"):
                    deletion._annotation_cleanup(run, owner)
                DeletionRun.objects.filter(pk=run.pk).update(status="NEEDS_REVIEW")
                deletion.retry_deletion(run.pk)
                DeletionRun.objects.filter(pk=run.pk).update(status="RUNNING")
                run.refresh_from_db()
            create.assert_not_called()

    def test_bound_dataset_accepts_source_switch_with_existing_annotations(self):
        self.dataset.annotation_data = {"status": "PRESENT", "counts": {"total": 4}}
        self.dataset.save(update_fields=["annotation_data"])
        sources = settings.KEDROGY_SOURCES | {"second_source": {"schema": "public", "table": "second_source", "id_fields": ["id"]}}
        with self.settings(KEDROGY_SOURCES=sources):
            response = self.client.patch(f"/api/datasets/{self.dataset.pk}/", '{"data_table_name":"second_source"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.prodigy_dataset_id, 11)
        self.assertEqual(self.dataset.data_table_name, "second_source")

    def test_logout_does_not_end_a_django_session(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="synthetic-audit-user")
        self.client.force_login(user)
        response = self.client.get("/logout/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "logged out")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
