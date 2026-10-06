"""Observable invariants for annotation and resumable cleanup."""

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from .annotation import (
    _observe,
    _route,
    advance_annotation,
    public_operation,
    public_session,
    start_annotation,
    stop_annotation,
)
from .annotation_data import observe_data, public_data
from .deletion import advance_deletion, preview, request_deletion, retry_deletion
from .kubernetes import OperationError
from .models import (
    AnnotationRun,
    AnnotationSlot,
    DeletionRun,
    DjangoDataset,
    DjangoLastDataset,
    DjangoModel,
)
from .operation_control import acquire, delete_exact
from .tests import dataset_values


class LifecycleTests(TestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values(), binding_state="BOUND", prodigy_dataset_id=6)
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, labels="P,N", label_schema=["P", "N"], a_preprocess_fun="")

    def plan(self, action="model_files", resources=None):
        with patch("kedrogy.deletion._inventory", return_value=(resources or [], [])):
            return preview(action, self.dataset.pk if action == "dataset" else self.model.pk)

    def delete(self, action="model_files", resources=None, key="delete-once"):
        plan = self.plan(action, resources)
        return request_deletion(action, self.dataset.pk if action == "dataset" else self.model.pk, plan["preview_token"], key)[0]

    def test_two_datasets_keep_independent_annotation_data(self):
        other = DjangoDataset.objects.create(**(dataset_values() | {"dataset_name": "Other"}), binding_state="BOUND", prodigy_dataset_id=7)
        DjangoLastDataset.objects.create(dataset=other)
        with patch("kedrogy.annotation_data.read_bound_annotations", return_value=(6, [{"answer": "accept", "accept": ["P"], "text": "synthetic", "meta": {"_annotation_policy": "single-label-choice-v2", "_class_schema": ["P", "N"]}}])):
            observe_data(self.dataset.pk)
            observe_data(other.pk)
        data = self.client.get("/api/datasets/").json()
        self.assertEqual([d["annotation_data"]["status"] for d in data], ["PRESENT", "PRESENT"])
        self.assertTrue(all(d["labelled"] for d in data))

    def test_invalid_unavailable_empty_and_stale_are_distinct(self):
        for rows, status in [([], "EMPTY"), ([{"answer": []}], "INVALID")]:
            with patch("kedrogy.annotation_data.read_bound_annotations", return_value=(6, rows)):
                self.assertEqual(observe_data(self.dataset.pk)["status"], status)
        with patch("kedrogy.annotation_data.read_bound_annotations", side_effect=OperationError("ANNOTATIONS_UNAVAILABLE", "Unavailable.")):
            self.assertEqual(observe_data(self.dataset.pk)["status"], "UNKNOWN")
        self.dataset.refresh_from_db()
        self.dataset.annotation_observed_at = timezone.now() - timedelta(hours=1)
        self.assertEqual(public_data(self.dataset)["status"], "UNKNOWN")

    def test_annotation_request_replay_and_namespace_slot(self):
        first, created = start_annotation(self.dataset.pk, "once")
        repeated, replay = start_annotation(self.dataset.pk, "once")
        self.assertTrue(created)
        self.assertFalse(replay)
        self.assertEqual(first.pk, repeated.pk)
        with self.assertRaises(OperationError):
            start_annotation(self.dataset.pk, "another")
        self.assertEqual(AnnotationRun.objects.count(), 1)
        self.assertEqual(AnnotationSlot.objects.get().run_id, first.pk)

    def test_launch_configuration_is_snapshotted_and_rename_is_allowed(self):
        run, _ = start_annotation(self.dataset.pk)
        old_title = run.snapshot["dataset"]["display_name"]
        response = self.client.patch(f"/api/datasets/{self.dataset.pk}/", json.dumps({"display_name": "New title"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.snapshot["dataset"]["display_name"], old_title)
        response = self.client.patch(f"/api/datasets/{self.dataset.pk}/", json.dumps({"recipe_options": "-l X,Y"}), content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_stop_wins_over_delayed_annotation_observation(self):
        run, _ = start_annotation(self.dataset.pk)
        run, owner = acquire(AnnotationRun, run.pk, ["STARTING"])
        stop_annotation(self.dataset.pk)
        _observe(run, owner, "READY")
        run.refresh_from_db()
        self.assertEqual((run.status, run.startup_status), ("STOPPING", "FAILED"))

    def test_lost_lease_cannot_change_shared_annotation_route(self):
        run, _ = start_annotation(self.dataset.pk)
        run, owner = acquire(AnnotationRun, run.pk, ["STARTING"])
        route = {"metadata": {"uid": "route", "resourceVersion": "1"}, "spec": {}}
        def lose_owner(*args):
            AnnotationRun.objects.filter(pk=run.pk).update(lease_owner=uuid.uuid4())
            return route
        with patch("kedrogy.annotation._get", side_effect=lose_owner), patch("kedrogy.annotation.command") as command:
            self.assertFalse(_route(run, owner))
            command.assert_not_called()

    def test_annotation_deadline_retains_slot_and_does_not_report_ready(self):
        run, _ = start_annotation(self.dataset.pk)
        AnnotationRun.objects.filter(pk=run.pk).update(created_at=timezone.now()-timedelta(hours=1))
        with patch("kedrogy.annotation._advance", side_effect=OperationError("ANNOTATION_UNAVAILABLE", "Unavailable.")):
            run = advance_annotation(run.pk)
        self.assertEqual((run.status, run.startup_status), ("UNAVAILABLE", "FAILED"))
        self.assertIsNotNone(AnnotationSlot.objects.get().run_id)

    def test_runtime_health_does_not_rewrite_startup_result(self):
        run, _ = start_annotation(self.dataset.pk)
        run.status, run.startup_status = "READY", "SUCCEEDED"
        run.observed_at = timezone.now()-timedelta(hours=1)
        self.assertEqual(public_session(run)["status"], "UNAVAILABLE")
        self.assertEqual(public_operation(run)["status"], "SUCCEEDED")

    def test_bare_delete_requires_review_and_preserves_records(self):
        response = self.client.delete(f"/api/models/{self.model.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(DjangoModel.objects.filter(pk=self.model.pk).exists())
        self.assertFalse(DeletionRun.objects.exists())

    def test_changed_preview_cannot_delete_new_child_model(self):
        plan = self.plan("dataset")
        DjangoModel.objects.create(on_dataset=self.dataset)
        with self.assertRaises(OperationError):
            request_deletion("dataset", self.dataset.pk, plan["preview_token"])
        self.assertFalse(DeletionRun.objects.exists())

    def test_duplicate_cleanup_reserves_once_and_prevents_mutation(self):
        run = self.delete()
        repeated, created = request_deletion("model_files", self.model.pk, None, "delete-once")
        self.assertEqual(repeated.pk, run.pk)
        self.assertFalse(created)
        self.model.refresh_from_db()
        self.assertTrue(self.model.resources_deleting)
        response = self.client.patch(f"/api/models/{self.model.pk}/", json.dumps({"model_name": "racing"}), content_type="application/json")
        self.assertEqual(response.status_code, 409)

    def test_dataset_reservation_blocks_new_child_and_label(self):
        self.delete("dataset")
        response = self.client.post("/api/models/", json.dumps({"on_dataset": self.dataset.pk, "labels": ["P", "N"], "a_preprocess_fun": ""}), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        with self.assertRaises(OperationError):
            start_annotation(self.dataset.pk)

    def test_partial_cleanup_retry_preserves_completed_steps(self):
        refs = [{"kind": "ConfigMap", "name": name, "namespace": settings.KEDROGY_NAMESPACE, "uid": name} for name in ["a", "b"]]
        run = self.delete(resources=refs)
        with patch("kedrogy.deletion.stop_serving", return_value=None), patch("kedrogy.deletion.delete_exact", side_effect=[True, OperationError("RESOURCE_IDENTITY_CHANGED", "Changed.")]):
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "NEEDS_REVIEW")
        self.assertIn("ConfigMap/a", run.completed)
        self.model.refresh_from_db()
        self.assertTrue(self.model.resources_deleting)
        retry_deletion(run.pk)
        with patch("kedrogy.deletion._get", return_value=None), patch("kedrogy.deletion.delete_exact", return_value=True) as remove:
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "SUCCEEDED")
        self.assertEqual(remove.call_args.args[0]["name"], "b")

    def test_external_crash_before_progress_record_is_recoverable(self):
        ref = {"kind": "ConfigMap", "name": "a", "namespace": settings.KEDROGY_NAMESPACE, "uid": "a"}
        run = self.delete(resources=[ref])
        with patch("kedrogy.deletion.stop_serving", return_value=None), patch("kedrogy.deletion.delete_exact", side_effect=RuntimeError("simulated crash")), self.assertRaises(RuntimeError):
            advance_deletion(run.pk)
        run.refresh_from_db()
        self.assertEqual(run.completed, ["stopped"])
        with patch("kedrogy.deletion.delete_exact", return_value=True):
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "SUCCEEDED")

    def test_replaced_resource_uid_is_never_deleted(self):
        ref = {"kind": "Service", "name": "example", "namespace": "test", "uid": "old"}
        with patch("kedrogy.operation_control._get", return_value={"metadata": {"uid": "new"}}), patch("kedrogy.operation_control.command") as command:
            with self.assertRaises(OperationError):
                delete_exact(ref)
            command.assert_not_called()

    def test_terminating_resource_is_not_treated_as_gone(self):
        ref = {"kind": "Service", "name": "example", "namespace": "test", "uid": "old"}
        with patch("kedrogy.operation_control._get", return_value={"metadata": {"uid": "old", "deletionTimestamp": "now"}}), patch("kedrogy.operation_control.command") as command:
            self.assertFalse(delete_exact(ref))
            command.assert_not_called()

    def test_pvc_consumer_prevents_deletion(self):
        ref = {"kind": "PersistentVolumeClaim", "name": "pvc", "namespace": "test", "uid": "pvc"}
        run = self.delete(resources=[ref])
        pods = {"items": [{"spec": {"volumes": [{"persistentVolumeClaim": {"claimName": "pvc"}}]}}]}
        with patch("kedrogy.deletion.stop_serving", return_value=None), patch("kedrogy.deletion.command", return_value=pods), patch("kedrogy.deletion.delete_exact") as remove:
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "RETRY_WAIT")
        remove.assert_not_called()

    def test_model_retirement_keeps_operation_and_binding(self):
        run = self.delete("model")
        with patch("kedrogy.deletion.stop_serving", return_value=None):
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "SUCCEEDED")
        self.assertEqual(self.client.get(f"/api/models/{self.model.pk}/").status_code, 404)
        self.assertTrue(DjangoDataset.objects.filter(pk=self.dataset.pk).exists())
        self.assertIsNotNone(DjangoModel.objects.get(pk=self.model.pk).retired_at)
        self.assertEqual(self.client.get(f"/api/tasks/delete/{run.pk}/status/").json()["status"], "SUCCEEDED")
        same, created = request_deletion("model", self.model.pk, None, "delete-once")
        self.assertEqual(same.pk, run.pk)
        self.assertFalse(created)

    def test_orm_cascade_cannot_bypass_model_cleanup(self):
        with self.assertRaises(ProtectedError):
            self.dataset.delete()

    def test_domain_result_overrides_queue_delivery(self):
        run = self.delete()
        DeletionRun.objects.filter(pk=run.pk).update(status="NEEDS_REVIEW", error={"code": "X", "message": "Review ownership."})
        with patch("kedrogy.api_views.retrieve", side_effect=AssertionError("Queue status must not override domain state")):
            response = self.client.get(f"/api/tasks/delete/{run.pk}/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "NEEDS_REVIEW")
        self.assertTrue(response.json()["can_retry"])

    def test_get_and_head_do_not_enqueue_observers(self):
        with patch("kedrogy.annotation_data.observe_data") as observe:
            for method in (self.client.get, self.client.head):
                self.assertEqual(method(f"/api/datasets/{self.dataset.pk}/").status_code, 200)
            observe.assert_not_called()

    def test_cleanup_deadline_keeps_reservation_and_can_resume_same_id(self):
        run = self.delete()
        DeletionRun.objects.filter(pk=run.pk).update(created_at=timezone.now()-timedelta(hours=1))
        result = advance_deletion(run.pk)
        self.assertEqual(result.status, 'NEEDS_REVIEW')
        self.assertEqual(result.error['code'], 'CLEANUP_TIMEOUT')
        self.model.refresh_from_db()
        self.assertTrue(self.model.resources_deleting)
        self.assertEqual(retry_deletion(run.pk).pk, run.pk)
        with patch('kedrogy.deletion.stop_serving', return_value=None):
            self.assertEqual(advance_deletion(run.pk).status, 'SUCCEEDED')

    def test_stop_changes_route_resource_version_even_before_first_route_ownership(self):
        run, _ = start_annotation(self.dataset.pk, 'fence')
        stop_annotation(self.dataset.pk)
        run, owner = acquire(AnnotationRun, run.pk, ['STOPPING'])
        route = {'metadata': {'name': 'prodigy-svc', 'resourceVersion': '1'}, 'spec': {'selector': {'legacy': 'yes'}}}
        with patch('kedrogy.annotation._get', return_value=route), patch('kedrogy.annotation.command') as command:
            self.assertTrue(_route(run, owner, stop=True))
            updated = command.call_args.kwargs['document']
            self.assertTrue(updated['metadata']['annotations']['kedrogy/annotation-fence'])
            self.assertEqual(updated['spec']['selector'], {'legacy': 'yes'})

    def test_unfinished_cleanup_is_recoverable_from_model_and_dataset_views(self):
        run = self.delete()
        self.assertEqual(self.client.get(f'/api/models/{self.model.pk}/').json()['pending_cleanup'], str(run.id))
        self.assertEqual(self.client.get(f'/api/datasets/{self.dataset.pk}/').json()['pending_cleanup'], str(run.id))

    def test_legacy_model_creation_reports_parent_cleanup_conflict(self):
        self.delete('dataset')
        response = self.client.post(f'/new_model/{self.dataset.pk}', {'labels': 'P,N'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error']['code'], 'DATASET_BUSY')

    def test_retained_annotation_cleanup_does_not_depend_on_retired_source_configuration(self):
        self.dataset.image = 'retired-image'
        self.dataset.data_table_name = 'retired-source'
        self.dataset.retired_at = timezone.now()
        self.dataset.save()
        with patch('kedrogy.deletion.annotation_receipt', return_value={'name': self.dataset.prodigy_dataset_name, 'id': 6, 'fingerprint': 'checked', 'count': 1}):
            plan = preview('annotations', self.dataset.pk)
        self.assertEqual(plan['cleanup_image'], settings.KEDROGY_ML_IMAGE)
        self.assertTrue(plan['retains_source_rows'])
