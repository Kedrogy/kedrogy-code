"""Exercise training serialization using real independent PostgreSQL transactions."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django_tasks.backends.database.models import DBTaskResult

from .models import DjangoDataset, DjangoModel, TrainingRun
from .tests import choice_rows, dataset_values
from .training import TrainingConflict, start_training


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ConcurrentTrainingTests(TransactionTestCase):
    def setUp(self):
        dataset = DjangoDataset.objects.create(**dataset_values())
        self.model = DjangoModel.objects.create(on_dataset=dataset, labels="positive,negative", a_preprocess_fun="")

        reader = patch("kedrogy.training_preflight.read_bound_annotations", return_value=(1, choice_rows(("positive", "negative"))))
        reader.start()
        self.addCleanup(reader.stop)

    def submit_pair(self, keys):
        barrier = threading.Barrier(2)
        def submit(key):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    run, created = start_training(self.model.pk, key)
                    return (str(run.pk), created)
                except TrainingConflict as exc:
                    return (exc.run_id, "conflict")
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(submit, keys))

    def test_same_key_creates_one_run_and_one_queue_entry(self):
        results = self.submit_pair(["same-key", "same-key"])
        self.assertEqual(len({result[0] for result in results}), 1)
        self.assertCountEqual([result[1] for result in results], [True, False])
        self.assertEqual(TrainingRun.objects.count(), 1)
        self.assertEqual(DBTaskResult.objects.count(), 1)

    def test_different_keys_share_one_active_slot(self):
        results = self.submit_pair(["first-key", "second-key"])
        self.assertEqual(len({result[0] for result in results}), 1)
        self.assertCountEqual([result[1] for result in results], [True, "conflict"])
        self.assertEqual(DBTaskResult.objects.count(), 1)

    def test_queue_failure_rolls_back_domain_record(self):
        with patch("kedrogy.tasks.new_train_task") as task:
            task.enqueue.side_effect = RuntimeError("Synthetic queue failure")
            with self.assertRaises(RuntimeError):
                start_training(self.model.pk, "queue-failure")
        self.assertFalse(TrainingRun.objects.exists())
        self.assertFalse(DBTaskResult.objects.exists())

    def test_serve_requests_share_one_revision_and_queue_entry(self):
        from .models import ServingRun
        from .serving import start_serving
        run, _ = start_training(self.model.pk, "training")
        run.status = "SUCCEEDED"
        run.artifact = {"path": "synthetic/artifact", "labels": ["positive", "negative"]}
        run.save()
        self.model.published_run = run
        self.model.artifact_status = "VERIFIED"
        self.model.save()
        barrier = threading.Barrier(2)
        def submit(key):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                serving, created = start_serving(self.model.pk, key)
                return str(serving.pk), created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, ["serve-a", "serve-a"]))
        self.assertEqual(len({item[0] for item in results}), 1)
        self.assertCountEqual([item[1] for item in results], [True, False])
        self.assertEqual(ServingRun.objects.count(), 1)
        self.assertEqual(DBTaskResult.objects.count(), 2)

    def test_train_and_resource_delete_cannot_both_own_model(self):
        from .kubernetes import OperationError
        from .tasks import request_resource_deletion
        from .deletion import preview
        with patch("kedrogy.deletion._inventory", return_value=([], [])):
            token = preview("model_files", self.model.pk)["preview_token"]
        barrier = threading.Barrier(2)
        def operation(name):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    if name == "train":
                        start_training(self.model.pk, "racing-training")
                    else:
                        request_resource_deletion(self.model.pk, preview_token=token)
                    return name
                except OperationError:
                    return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(operation, ["train", "delete"]))
        self.assertEqual(results.count("conflict"), 1)
        self.model.refresh_from_db()
        self.assertNotEqual(self.model.resources_deleting, TrainingRun.objects.exists())
        self.assertEqual(DBTaskResult.objects.count(), 1)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class ConcurrentLifecycleTests(TransactionTestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values())
        self.other = DjangoDataset.objects.create(**(dataset_values() | {"dataset_name": "Other"}))

    def race(self, functions):
        barrier = threading.Barrier(len(functions))
        def run(fn):
            from .kubernetes import OperationError
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    return fn()
                except OperationError:
                    return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            return list(executor.map(run, functions))

    def test_duplicate_annotation_submission_commits_one_intent(self):
        from .annotation import start_annotation
        from .models import AnnotationRun
        results = self.race([lambda: str(start_annotation(self.dataset.pk, "same")[0].pk)] * 2)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(AnnotationRun.objects.count(), 1)
        self.assertEqual(DBTaskResult.objects.count(), 1)

    def test_two_datasets_cannot_replace_each_others_session(self):
        from .annotation import start_annotation
        from .models import AnnotationSlot
        results = self.race([lambda: str(start_annotation(self.dataset.pk, "a")[0].pk),
                             lambda: str(start_annotation(self.other.pk, "b")[0].pk)])
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(AnnotationSlot.objects.exclude(run=None).count(), 1)

    def test_duplicate_deletion_commits_one_intent(self):
        from .deletion import preview, request_deletion
        from .models import DeletionRun
        with patch("kedrogy.deletion._inventory", return_value=([], [])):
            token = preview("dataset", self.dataset.pk)["preview_token"]
        results = self.race([lambda: str(request_deletion("dataset", self.dataset.pk, token, "same")[0].pk)] * 2)
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(DeletionRun.objects.count(), 1)
        self.assertEqual(DBTaskResult.objects.count(), 1)

    def test_dataset_cleanup_cannot_miss_a_concurrent_child(self):
        from .deletion import preview, request_deletion
        from .serializers import DjangoModelSerializer
        with patch("kedrogy.deletion._inventory", return_value=([], [])):
            token = preview("dataset", self.dataset.pk)["preview_token"]
        def create():
            serializer = DjangoModelSerializer(data={"on_dataset": self.dataset.pk, "labels": ["P", "N"]})
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return "child"
        result = self.race([create, lambda: str(request_deletion("dataset", self.dataset.pk, token, "delete")[0].pk)])
        self.assertEqual(result.count("conflict"), 1)
        self.dataset.refresh_from_db()
        self.assertNotEqual(self.dataset.deletion_pending, self.dataset.djangomodel_set.exists())

    def test_annotation_queue_failure_rolls_back_slot(self):
        from .annotation import start_annotation
        from .models import AnnotationRun, AnnotationSlot
        with patch("kedrogy.tasks.new_dataset_task") as task:
            task.enqueue.side_effect = RuntimeError("Synthetic queue failure")
            with self.assertRaises(RuntimeError):
                start_annotation(self.dataset.pk, "failed")
        self.assertFalse(AnnotationRun.objects.exists())
        self.assertFalse(AnnotationSlot.objects.exclude(run=None).exists())
