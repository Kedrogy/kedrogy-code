"""Regression tests for foreign ownership, stale leases and delayed creates."""

import copy
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from . import serving_resources as resources
from .models import DjangoDataset, DjangoModel, ServingRun, TrainingRun
from .serving import _advance, _observe, advance_serving, start_serving, stop_serving
from .tests import dataset_values


class ServingOwnershipTests(TestCase):
    def setUp(self):
        dataset = DjangoDataset.objects.create(**dataset_values())
        self.model = DjangoModel.objects.create(on_dataset=dataset, labels="P,N")
        training = TrainingRun.objects.create(model=self.model, namespace="default", idempotency_key="training",
            job_name="test-training", status="SUCCEEDED", snapshot={"dataset": dataset.to_dict(), "labels": ["P", "N"], "preprocessor": ""},
            artifact={"path": "runs/synthetic/attempt/artifact", "labels": ["P", "N"]})
        self.model.published_run = training
        self.model.artifact_status = "VERIFIED"
        self.model.save()
        self.objects = {}
        self.created = []
        for target, side_effect in [("kedrogy.serving_resources._get", self.get),
                                    ("kedrogy.operation_control._get", self.get),
                                    ("kedrogy.serving_resources.command", self.command),
                                    ("kedrogy.operation_control.command", self.command),
                                    ("kedrogy.serving.command", self.command)]:
            context = patch(target, side_effect=side_effect)
            context.start()
            self.addCleanup(context.stop)
        context = patch("kedrogy.prediction.check_service")
        context.start()
        self.addCleanup(context.stop)

    def get(self, kind, name, namespace):
        if kind.lower() == "namespace":
            return {"metadata": {"uid": "cluster-namespace-uid"}}
        return copy.deepcopy(self.objects.get((kind.lower(), name)))

    def command(self, args, *, namespace, document=None, json_output=False):
        if args[0] == "create":
            result = copy.deepcopy(document)
            result["metadata"] |= {"uid": str(uuid.uuid4()), "generation": 1}
            result["status"] = {"observedGeneration": 1, "updatedReplicas": 1, "readyReplicas": 1, "availableReplicas": 1, "replicas": 1}
            self.objects[(result["kind"].lower(), result["metadata"]["name"])] = result
            self.created.append(result)
            return copy.deepcopy(result)
        if args[0] == "delete":
            for key, value in list(self.objects.items()):
                if value["metadata"]["uid"] == document["preconditions"]["uid"]:
                    del self.objects[key]
            return ""
        if args[:2] == ["get", "pods"]:
            return {"items": []}
        self.fail(f"Unexpected Kubernetes operation: {args}")

    def start(self):
        return start_serving(self.model.pk)[0]

    def test_foreign_deployment_and_service_are_never_replaced(self):
        for kind in ["Deployment", "Service", "ConfigMap"]:
            with self.subTest(kind=kind):
                run = self.start()
                ref = next(ref for ref in [run.resource_plan["anchor"], *run.resource_plan["resources"]] if ref["kind"] == kind)
                foreign = {"kind": kind, "metadata": {"uid": "foreign", "name": ref["name"]}, "spec": {"sentinel": True}}
                key = kind.lower(), ref["name"]
                self.objects[key] = copy.deepcopy(foreign)
                run = advance_serving(run.pk)
                self.assertEqual(run.error["code"], "SERVING_IDENTITY_MISMATCH")
                self.assertEqual(self.objects[key], foreign)
                ServingRun.objects.filter(pk=run.pk).update(status="FAILED")

    def test_lost_acknowledgment_recovers_same_resource(self):
        run = advance_serving(self.start().pk)
        uid = run.deployment_uid
        run.resource_plan["resources"][0]["uid"] = ""
        run.resource_plan["resources"][0].pop("generation", None)
        run.save()
        before = len(self.created)
        recovered = advance_serving(run.pk)
        self.assertEqual(recovered.status, "READY")
        self.assertEqual(recovered.deployment_uid, uid)
        self.assertEqual(len(self.created), before)

    def test_missing_or_replaced_uid_is_not_adopted(self):
        run = advance_serving(self.start().pk)
        key = "deployment", run.resource_plan["resources"][0]["name"]
        previous = self.objects.pop(key)
        self.assertEqual(advance_serving(run.pk).error["code"], "SERVING_LOST")
        previous["metadata"]["uid"] = "replacement"
        self.objects[key] = previous
        self.assertEqual(advance_serving(run.pk).error["code"], "SERVING_IDENTITY_MISMATCH")

    def test_expired_owner_cannot_publish_and_old_release_cannot_clear_new_lease(self):
        run = self.start()
        owner = uuid.uuid4()
        ServingRun.objects.filter(pk=run.pk).update(lease_owner=owner, lease_epoch=1,
            lease_until=timezone.now() - timedelta(seconds=1))
        run.refresh_from_db()
        _observe(run, owner, "READY")
        run.refresh_from_db()
        self.assertEqual(run.status, "STARTING")
        from .serving import _fenced
        replacement = uuid.uuid4()
        ServingRun.objects.filter(pk=run.pk).update(lease_owner=replacement, lease_epoch=2,
            lease_until=timezone.now() + timedelta(minutes=1))
        self.assertEqual(_fenced(run, owner).update(lease_owner=None, lease_until=None), 0)
        run.refresh_from_db()
        self.assertEqual(run.lease_owner, replacement)

    def test_delayed_create_after_stop_does_not_change_new_run_and_is_collected(self):
        old = self.start()
        owner = uuid.uuid4()
        ServingRun.objects.filter(pk=old.pk).update(lease_owner=owner, lease_epoch=1,
            lease_until=timezone.now() + timedelta(minutes=1))
        old.refresh_from_db()
        newer = []
        def delayed(args, **kwargs):
            if args[0] == "create" and kwargs["document"]["kind"] == "Deployment" and not newer:
                stop_serving(self.model.pk)
                stopped = advance_serving(old.pk)
                self.assertEqual(stopped.status, "STOPPED")
                newer.append(self.start())
                newer[0] = advance_serving(newer[0].pk)
                self.assertEqual(newer[0].status, "READY")
            return self.command(args, **kwargs)
        with patch("kedrogy.serving_resources.command", side_effect=delayed):
            _advance(old, owner)
        current = copy.deepcopy(self.objects)
        self.model.refresh_from_db()
        self.assertEqual(self.model.current_serving_id, newer[0].id)
        old.refresh_from_db()
        self.assertEqual(old.status, "STOPPED")
        self.assertNotIn(("service", resources.service_name(old)), self.objects)
        advance_serving(old.id)
        self.assertNotIn(("deployment", old.resource_plan["resources"][0]["name"]), self.objects)
        for key, value in current.items():
            if value["metadata"].get("labels", {}).get("kedrogy/serving-id") == str(newer[0].id):
                self.assertEqual(value, self.objects[key])

    def test_namespace_replacement_blocks_cleanup(self):
        run = advance_serving(self.start().pk)
        stop_serving(self.model.pk)
        before = copy.deepcopy(self.objects)
        with patch("kedrogy.serving_resources.namespace_uid", return_value="other-cluster"):
            stopped = advance_serving(run.id)
        self.assertEqual(stopped.error["code"], "SERVING_CLUSTER_CHANGED")
        self.assertEqual(before, self.objects)
