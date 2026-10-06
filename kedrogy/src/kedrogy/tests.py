"""Regression tests for SQL-independent launch and HTTP safety boundaries."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.middleware.csrf import get_token
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
)
from django_tasks import TaskContext, TaskResultStatus
from .kubernetes import OperationError

from . import manifests, tasks
from .launch_config import LaunchConfigError, validate_dataset
from .models import DjangoDataset, DjangoLastDataset, DjangoModel
from .serializers import DjangoDatasetSerializer


def dataset_values():
    return {"dataset_name": "reviews", "image": "approved:1", "workingDir": "mykedro",
            "pipeline": "load_examples", "recipe_options": "-l positive,negative",
            "data_table_name": "all_data", "id_field": "id"}


def choice_rows(labels=("P", "N")):
    """Four distinct source records with balanced explicit class answers."""
    return [{"text": f"Synthetic example {i}", "answer": "accept", "accept": [label],
             "meta": {"_annotation_policy": "single-label-choice-v2", "_class_schema": list(labels),
                      "_source_id": "synthetic-source", "_record_id": str(i), "_content_digest": "a" * 64}}
            for i, label in enumerate([*labels, *labels])]


class LaunchSafetyTests(SimpleTestCase):
    def test_rejected_values(self):
        cases = [("image", "approved:1\nsecurityContext: {privileged: true}"),
                 ("image", "unapproved:1"), ("workingDir", "../outside"),
                 ("pipeline", "ingest"), ("data_table_name", "auth_user"),
                 ("id_field", 'id; SELECT 1'), ("dataset_name", "-x"),
                 ("recipe_options", "db-drop reviews"),
                 ("recipe_options", "-l positive,negative --extra"),
                 ("recipe_options", 'myrecipes.textcat.custom-model other ./data/00_examples/examples.jsonl -l P,N')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                serializer = DjangoDatasetSerializer(data=dataset_values() | {key: value})
                self.assertFalse(serializer.is_valid())
                self.assertIn(key, serializer.errors)

    def test_nested_document_and_argv_preserve_values(self):
        name = 'O\'Reilly: отзывы, x=y "quoted"'
        cfg = validate_dataset(dataset_values() | {"dataset_name": name})
        docs = json.loads(json.dumps(manifests.annotation(cfg, 9)))
        params = json.loads(docs[0]["data"]["parameters_load_examples.yml"])
        self.assertEqual(params["load_examples_options"]["dataset_name"], name)
        spec = docs[1]["spec"]["template"]["spec"]
        self.assertEqual(spec["containers"][0]["args"][3], name)
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertNotIn("hostPath", json.dumps(spec))
        self.assertTrue(all(c["image"] == cfg.image for c in spec["initContainers"] + spec["containers"]))
        for container in spec["initContainers"]:
            for entry in container["env"]:
                if entry["name"] == "PGPASSWORD":
                    self.assertIn("secretKeyRef", entry["valueFrom"])
                    self.assertNotIn("value", entry)

    def test_training_labels_are_nested_data(self):
        cfg = validate_dataset(dataset_values())
        labels = ('good: "yes"', 'bad\\no')
        docs = manifests.training(cfg, 1, labels, run_id="00000000-0000-0000-0000-000000000001")
        params = json.loads(docs[0]["data"]["parameters_train.yml"])
        self.assertEqual(params["model_options"]["labels"], list(labels))
        serving = manifests.serving(cfg, 1, "", artifact_path="best", serving_run_id="00000000-0000-0000-0000-000000000001", training_run_id="00000000-0000-0000-0000-000000000002", artifact={})
        self.assertNotIn("PGPASSWORD", json.dumps(serving))

    def test_failed_kubectl_does_not_leak_payload(self):
        ctx = Mock(spec=TaskContext)
        ctx.metadata = {}
        with (
            patch("kedrogy.tasks.command", side_effect=OperationError("COMMAND_FAILED", "Kubernetes operation failed (exit 1).")),
            self.assertRaisesRegex(RuntimeError, 'exit 1') as error,
        ):
            tasks.kubectl(ctx, ['apply', '-f', '-'], document={"private": "private-password"})
        self.assertNotIn('private-password', str(error.exception))
        self.assertEqual(ctx.metadata, {})
        ctx.save_metadata.assert_not_called()


class HTTPMethodTests(TestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values())
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, labels="positive,negative", a_preprocess_fun="")

    def test_get_head_never_mutate(self):
        routes = ["new_dataset/", f"new_model/{self.dataset.id}", f"label_dataset/{self.dataset.id}",
                  f"delete_dataset/{self.dataset.id}", f"train_model/{self.model.id}/",
                  f"serve_model/{self.model.id}/", f"delete_model/{self.model.id}", f"predict_model/{self.model.id}/"]
        with patch("kedrogy.kubernetes.subprocess.Popen") as process:
            for prefix in ('/', '/en/', '/ru/'):
                for route in routes:
                    for method in ('get', 'head'):
                        with self.subTest(prefix=prefix, route=route, method=method):
                            self.assertEqual(getattr(self.client, method)(prefix + route).status_code, 405)
            process.assert_not_called()
        self.assertEqual(DjangoDataset.objects.count(), 1)
        self.assertEqual(DjangoModel.objects.count(), 1)

    def test_csrf_protected_post_enqueues_once(self):
        client = Client(enforce_csrf_checks=True)
        url = f'/label_dataset/{self.dataset.id}'
        with patch('kedrogy.tasks.new_dataset_task') as task:
            self.assertEqual(client.post(url).status_code, 403)
            task.enqueue.assert_not_called()
            request = RequestFactory().get('/')
            token = get_token(request)
            client.cookies['csrftoken'] = request.META['CSRF_COOKIE']
            task.enqueue.return_value = SimpleNamespace(id='test-task')
            self.assertEqual(client.post(url, {'csrfmiddlewaretoken': token}).status_code, 200)
            task.enqueue.assert_called_once()

    def test_poll_is_read_only_and_task_records_once(self):
        other = DjangoDataset.objects.create(**(dataset_values() | {'dataset_name': 'other'}))
        DjangoLastDataset.objects.create(dataset=other)
        before = list(DjangoLastDataset.objects.values_list('id', 'dataset_id'))
        with patch('kedrogy.views.new_dataset_task') as task:
            task.get_result.return_value = SimpleNamespace(status=TaskResultStatus.SUCCEEDED, metadata={}, return_value={'dataset_id': self.dataset.id})
            for _ in range(2):
                self.assertEqual(self.client.get('/new_dataset_result/test-task/').status_code, 200)
        self.assertEqual(list(DjangoLastDataset.objects.values_list('id', 'dataset_id')), before)
        # Result pages never write the legacy pointer or invent data readiness.
        self.assertEqual(list(DjangoLastDataset.objects.values_list('dataset_id', flat=True)), [other.id])

    def test_api_and_worker_recheck_persisted_configuration(self):
        self.dataset.image = 'unapproved:1'
        self.dataset.save(update_fields=['image'])
        with patch('kedrogy.api_views.new_dataset_task') as queued:
            response = self.client.post(f'/api/datasets/{self.dataset.id}/label/')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['error']['code'], 'INVALID_CONFIGURATION')
            queued.enqueue.assert_not_called()
        with patch('kedrogy.tasks.apply_documents') as apply:
            context = Mock(spec=TaskContext)
            context.metadata = {}
            with self.assertRaises(OperationError):
                tasks.new_dataset_task.func(context, {'dataset_id': self.dataset.id, 'image': 'approved:1'})
            apply.assert_not_called()

    def test_failed_rollout_does_not_record_annotation(self):
        ctx = Mock(spec=TaskContext)
        ctx.metadata = {}
        with (
            patch('kedrogy.tasks.apply_documents'),
            patch('kedrogy.tasks.kubectl', side_effect=RuntimeError('rollout failed')),
            self.assertRaises(RuntimeError),
        ):
            tasks.new_dataset_task.func(ctx, {'dataset_id': self.dataset.id})
        self.assertFalse(DjangoLastDataset.objects.exists())

    def test_partial_update_cannot_bypass_validation(self):
        response = self.client.patch(f'/api/datasets/{self.dataset.id}/', json.dumps({'image': 'evil:1'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.dataset.refresh_from_db()
        self.assertEqual(self.dataset.image, 'approved:1')
