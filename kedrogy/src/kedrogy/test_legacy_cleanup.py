"""Legacy ownership is an explicit, identity-bound review, never a name bypass."""

import copy
import json
from unittest.mock import patch

from django.core import signing
from django.test import TestCase, override_settings

from . import legacy_cleanup
from .deletion import _inventory, advance_deletion, preview, request_deletion
from .kubernetes import OperationError
from .models import DeletionRun, DjangoDataset, DjangoModel
from .operation_control import delete_exact


@override_settings(KEDROGY_NAMESPACE="test", KEDROGY_ML_IMAGE="approved:1", KEDROGY_ML_IMAGE_ALIASES=frozenset({"approved:1"}))
class LegacyCleanupTests(TestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(dataset_name="Historical", prodigy_dataset_name="original", image="approved:1")
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, artifact_status="INVALID")
        mid = self.model.pk
        def resource(kind, name, spec=None):
            return {"kind": kind, "metadata": {"name": name, "uid": kind + "-uid", "resourceVersion": "1"}, "spec": spec or {}}
        selector = {"app.kubernetes.io/name": f"serve-{mid}"}
        volume = {"name": "models", "persistentVolumeClaim": {"claimName": f"pvc-model-{mid}"}}
        container = {"name": "model", "image": "approved:1", "volumeMounts": [{"name": "models", "mountPath": "/app/mykedro/data/06_models/"}]}
        deployment = resource("Deployment", f"serve-{mid}", {"selector": {"matchLabels": selector}, "template": {
            "metadata": {"labels": selector}, "spec": {"volumes": [volume], "containers": [container | {"args": ["-m", "ysz.predict", "data/06_models/best/"]}]}}})
        job = resource("Job", f"train-{mid}", {"template": {"spec": {"volumes": [volume,
            {"name": "params", "configMap": {"name": f"parameters-train-{mid}"}}],
            "containers": [container | {"args": ["-m", "kedro", "run", "--pipeline=train"]}]}}})
        config = resource("ConfigMap", f"parameters-train-{mid}")
        config["data"] = {"parameters_train.yml": "model_options:\n  dataset_name: original\n"}
        self.docs = {row["kind"]: row for row in [deployment, job, config,
            resource("PersistentVolumeClaim", f"pvc-model-{mid}"), resource("Service", f"serve-svc-{mid}", {"selector": selector})]}
        self.graph = [deployment, job, self.docs["Service"]]
        self.getter = self.enterContext(patch("kedrogy.legacy_cleanup._get", side_effect=lambda kind, name, namespace: self.docs.get(kind)))
        self.enterContext(patch("kedrogy.legacy_cleanup.namespace_uid", return_value="namespace-uid"))
        self.command = self.enterContext(patch("kedrogy.legacy_cleanup.command", side_effect=lambda *args, **kwargs: {"items": self.graph}))

    def approve(self):
        review = legacy_cleanup.preview(self.model.pk)
        self.assertEqual(review["issues"], [])
        return legacy_cleanup.confirm(self.model.pk, review["review_token"])

    def test_preview_is_read_only_and_confirmation_preserves_every_resource(self):
        before = copy.deepcopy(self.docs)
        response = self.client.get(f"/api/models/{self.model.pk}/legacy_cleanup_review/")
        self.assertEqual(response.status_code, 200)
        self.model.refresh_from_db()
        self.assertEqual(self.model.legacy_cleanup_review, {})
        response = self.client.post(f"/api/models/{self.model.pk}/legacy_cleanup_review/",
            json.dumps({"review_token": response.json()["review_token"]}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], False)
        self.assertEqual(response.json()["resource_count"], 5)
        self.assertEqual(before, self.docs)
        self.model.refresh_from_db()
        self.assertEqual(self.model.artifact_status, "INVALID")
        self.assertIsNone(self.model.retired_at)
        self.assertEqual(DeletionRun.objects.count(), 0)
        self.assertTrue(all(call.args[0][0] == "get" for call in self.command.call_args_list))

    def test_cleanup_inventory_includes_reviewed_configuration_and_exact_identities(self):
        self.approve(); self.model.refresh_from_db()
        with patch("kedrogy.deletion._get", side_effect=AssertionError("Reviewed resources must not be adopted by name.")):
            resources, issues = _inventory([self.model])
        self.assertEqual(issues, [])
        self.assertEqual(len(resources), 5)
        self.assertIn("ConfigMap", {row["kind"] for row in resources})
        self.assertTrue(all(row["namespace_uid"] == "namespace-uid" and row["spec_digest"] for row in resources))

    def test_wrong_selector_binding_image_and_existing_owner_cannot_be_approved(self):
        cases = [("Service", lambda row: row["spec"].update(selector={"app": "unrelated"})),
                 ("ConfigMap", lambda row: row["data"].update({"parameters_train.yml": "model_options:\n  dataset_name: other"})),
                 ("Deployment", lambda row: row["spec"]["template"]["spec"]["containers"][0].update(image="unapproved:1")),
                 ("Deployment", lambda row: row["spec"]["template"]["spec"]["containers"][0].update(command=["sh", "-c", "unrelated"])),
                 ("PersistentVolumeClaim", lambda row: row["metadata"].update(ownerReferences=[{"uid": "other-owner"}]))]
        for kind, mutate in cases:
            with self.subTest(kind=kind):
                original = copy.deepcopy(self.docs[kind]); mutate(self.docs[kind])
                review = legacy_cleanup.preview(self.model.pk)
                self.assertTrue(review["issues"])
                with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk, review["review_token"])
                self.docs[kind] = original

    def test_missing_resource_does_not_turn_names_into_ownership(self):
        self.docs.pop("Job")
        self.assertTrue(legacy_cleanup.preview(self.model.pk)["issues"])

    def test_shared_storage_configuration_and_route_block_confirmation(self):
        for kind, spec, labels in [
            ("StatefulSet", {"volumes": [{"persistentVolumeClaim": {"claimName": f"pvc-model-{self.model.pk}"}}]}, {}),
            ("Job", {"containers": [{"envFrom": [{"configMapRef": {"name": f"parameters-train-{self.model.pk}"}}]}]}, {}),
            ("Pod", {}, {"app.kubernetes.io/name": f"serve-{self.model.pk}"})]:
            with self.subTest(kind=kind):
                row = {"kind": kind, "metadata": {"name": "foreign", "uid": "foreign", "labels": labels},
                       "spec": spec if kind == "Pod" else {"template": {"spec": spec}}}
                self.graph.append(row)
                self.assertTrue(legacy_cleanup.preview(self.model.pk)["issues"])
                self.graph.pop()

    def test_resource_or_namespace_replacement_after_preview_rejects_confirmation(self):
        token = legacy_cleanup.preview(self.model.pk)["review_token"]
        self.docs["Service"]["metadata"]["uid"] = "replacement"
        with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk, token)
        self.model.refresh_from_db(); self.assertEqual(self.model.legacy_cleanup_review, {})
        token = legacy_cleanup.preview(self.model.pk)["review_token"]
        with patch("kedrogy.legacy_cleanup.namespace_uid", return_value="another-namespace"), self.assertRaises(OperationError):
            legacy_cleanup.confirm(self.model.pk, token)

    def test_changed_spec_or_model_invalidates_signed_review(self):
        token = legacy_cleanup.preview(self.model.pk)["review_token"]
        self.docs["Deployment"]["spec"]["replicas"] = 4
        with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk, token)
        token = legacy_cleanup.preview(self.model.pk)["review_token"]
        self.dataset.prodigy_dataset_name = "changed"; self.dataset.save()
        with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk, token)

    def test_recorded_uid_is_never_replaced_by_matching_names(self):
        self.approve(); self.model.refresh_from_db()
        self.docs["Deployment"]["metadata"]["uid"] = "same-name-new-resource"
        with self.assertRaises(OperationError): legacy_cleanup.reviewed_resources(self.model)

    def test_edited_review_and_cross_model_tokens_are_rejected(self):
        token = legacy_cleanup.preview(self.model.pk)["review_token"]
        with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk, token + "tampered")
        with self.assertRaises(OperationError): legacy_cleanup.confirm(self.model.pk + 1, token)
        with patch("django.core.signing.loads", side_effect=signing.SignatureExpired), self.assertRaises(OperationError):
            legacy_cleanup.confirm(self.model.pk, token)

    def test_delete_uses_uid_and_resource_version_and_rechecks_spec(self):
        review = legacy_cleanup.preview(self.model.pk)
        ref = next(row for row in review["resources"] if row["kind"] == "Service")
        with patch("kedrogy.serving_resources.namespace_uid", return_value="namespace-uid"), patch("kedrogy.operation_control._get", side_effect=[self.docs["Service"], None]), patch("kedrogy.operation_control.command") as delete:
            self.assertTrue(delete_exact(ref))
            self.assertEqual(delete.call_args.kwargs["document"]["preconditions"], {"uid": ref["uid"], "resourceVersion": "1"})
        self.docs["Service"]["spec"]["selector"] = {"app": "other"}
        with patch("kedrogy.serving_resources.namespace_uid", return_value="namespace-uid"), patch("kedrogy.operation_control._get", return_value=self.docs["Service"]), patch("kedrogy.operation_control.command") as delete:
            with self.assertRaises(OperationError): delete_exact(ref)
            delete.assert_not_called()

    def test_successful_cleanup_remains_a_separate_request(self):
        self.approve()
        with patch("kedrogy.deletion._get", return_value=None):
            plan = preview("model", self.model.pk)
        self.assertEqual(plan["issues"], [])
        with patch("kedrogy.tasks.new_delete_model_task") as task:
            task.enqueue.return_value.id = "test-delete-task"
            run, _ = request_deletion("model", self.model.pk, plan["preview_token"], "delete-test")
        self.assertEqual(run.status, "QUEUED")
        self.model.refresh_from_db(); self.assertIsNone(self.model.retired_at)
        with patch("kedrogy.deletion.delete_exact", return_value=True), patch("kedrogy.deletion.command", return_value={"items": []}):
            run = advance_deletion(run.pk)
        self.assertEqual(run.status, "SUCCEEDED")
        self.model.refresh_from_db(); self.assertIsNotNone(self.model.retired_at)
        self.assertEqual(self.model.legacy_cleanup_review, {})
        self.assertEqual(len(run.plan["resources"]), 5)

    def test_unreviewed_training_config_is_not_silently_orphaned(self):
        with patch("kedrogy.deletion._get", side_effect=lambda kind, name, namespace: self.docs.get(kind) if kind == "ConfigMap" else None):
            resources, issues = _inventory([self.model])
        self.assertEqual(resources, [])
        self.assertEqual(issues, [f"Ownership is unresolved for ConfigMap/parameters-train-{self.model.pk}."])

    def test_new_dependency_after_recording_blocks_deletion_without_side_effects(self):
        self.approve()
        with patch("kedrogy.deletion._get", return_value=None): plan = preview("model", self.model.pk)
        with patch("kedrogy.tasks.new_delete_model_task") as task:
            task.enqueue.return_value.id = "test-stale-delete-task"
            run, _ = request_deletion("model", self.model.pk, plan["preview_token"], "stale-delete")
        self.graph.append({"kind": "Service", "metadata": {"name": "foreign", "uid": "foreign"},
                           "spec": {"selector": self.docs["Service"]["spec"]["selector"]}})
        with patch("kedrogy.deletion.delete_exact") as delete:
            run = advance_deletion(run.pk)
            self.assertEqual(run.status, "NEEDS_REVIEW"); delete.assert_not_called()
