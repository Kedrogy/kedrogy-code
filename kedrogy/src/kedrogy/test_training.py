"""Training state, publication, idempotency, and recovery invariants."""

import json
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .kubernetes import OperationError
from .models import DjangoDataset, DjangoModel, TrainingRun
from .tests import choice_rows, dataset_values
from .training import TrainingConflict, _record_training_logs, advance_run, published_artifact, start_training, training_log_snapshot


class TrainingTests(TestCase):
    def setUp(self):
        self.dataset = DjangoDataset.objects.create(**dataset_values())
        self.model = DjangoModel.objects.create(on_dataset=self.dataset, labels='P,N', a_preprocess_fun='')
        reader = patch("kedrogy.training_preflight.read_bound_annotations", return_value=(1, choice_rows()))
        reader.start()
        self.addCleanup(reader.stop)
        self.run, _ = start_training(self.model.id, 'initial-request')
        self.uid = str(uuid.uuid4())
        self.attempt = str(uuid.uuid4())
        self.job = {'metadata': {'uid': self.uid, 'labels': {'kedrogy/run-id': str(self.run.id)}}, 'status': {'conditions': []}}
        self.cluster = self.enterContext(patch('kedrogy.training.command', return_value=''))

    def receipt(self):
        return {'version': 2, 'class_schema_version': 2, 'conversion_policy': 'single-label-choice-v2', 'verified': True, 'run_id': str(self.run.id), 'attempt_id': self.attempt,
                'path': f'runs/{self.run.id}/{self.attempt}/artifact', 'image': self.run.snapshot['image'],
                'labels': ['P','N'], 'files': {'config.json': 'a'*64, 'model.safetensors': 'b'*64, 'tokenizer.json': 'c'*64}}

    def pod(self, container, message):
        return {'metadata': {'uid': self.attempt, 'name': 'training-attempt'},
                'status': {'phase': 'Succeeded', 'containerStatuses': [{'name': container, 'state': {
                    'terminated': {'exitCode': 0, 'message': message}}}]}}

    def test_repeated_request_is_same_run_and_new_request_conflicts(self):
        repeated, created = start_training(self.model.id, 'initial-request')
        self.assertFalse(created)
        self.assertEqual(repeated.pk, self.run.pk)
        with self.assertRaises(TrainingConflict):
            start_training(self.model.id, 'second-request')
        self.assertEqual(TrainingRun.objects.count(), 1)

    def test_effective_training_defaults_are_frozen_in_the_snapshot(self):
        self.assertEqual(self.run.snapshot["options"]["num_train_epochs"], 8)
        self.assertEqual(self.run.snapshot["options"]["train_batch_size"], 8)
        self.assertEqual(self.run.snapshot["options"]["max_steps"], -1)
        self.assertEqual(self.run.snapshot["options"]["seed"], 123)

    def test_database_constraint_enforces_single_active_run(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TrainingRun.objects.create(model=self.model, idempotency_key='other', namespace='default', job_name='other')

    def test_complete_job_waits_for_independent_verification(self):
        self.job['status']['conditions'] = [{'type':'Complete','status':'True'}]
        verifier = {'metadata': {'uid': str(uuid.uuid4())}, 'status': {}}
        with patch('kedrogy.training._get', side_effect=[self.job, verifier]), patch('kedrogy.training._pods', return_value=[self.pod('train', json.dumps(self.receipt()))]):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'VERIFYING')
        self.model.refresh_from_db()
        self.assertFalse(self.model.trained)

    def test_verified_job_publishes_only_matching_checkpoint(self):
        self.job['status']['conditions'] = [{'type':'Complete','status':'True'}]
        verifier = {'metadata': {'uid': str(uuid.uuid4())}, 'status': {'conditions':[{'type':'Complete','status':'True'}]}}
        receipt = json.dumps(self.receipt())
        with patch('kedrogy.training._get', side_effect=[self.job, verifier]), patch('kedrogy.training._pods', side_effect=[[self.pod('train', receipt)], [self.pod('verify',receipt)]]):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'SUCCEEDED')
        self.model.refresh_from_db()
        self.assertEqual(published_artifact(self.model)['path'], self.receipt()['path'])
        next_run, _ = start_training(self.model.id, 'next-run')
        self.assertNotEqual(next_run.job_name, run.job_name)

    def test_wrong_run_receipt_never_publishes(self):
        self.job['status']['conditions'] = [{'type':'Complete','status':'True'}]
        receipt = self.receipt() | {'run_id': str(uuid.uuid4())}
        with patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[self.pod('train',json.dumps(receipt))]):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.error['code'], 'ARTIFACT_INVALID')

    def test_quality_receipt_requires_hashed_report_and_valid_metrics(self):
        from .training import validate_receipt
        quality = {"version":1,"split":"validation","samples":44,"train_samples":132,
                   "training_steps":136,"accuracy":.9,"macro_f1":.8,
                   "majority_baseline":.77,"warnings":[]}
        receipt = self.receipt() | {"quality": quality}
        with self.assertRaises(OperationError):
            validate_receipt(json.dumps(receipt), self.run, self.attempt)
        receipt["files"]["quality.json"] = "d" * 64
        self.assertEqual(validate_receipt(json.dumps(receipt), self.run, self.attempt)["quality"], quality)
        for changes in [{"version":True},{"accuracy":float("nan")},{"macro_f1":1.5},{"training_steps":True},{"warnings":[42]}]:
            with self.subTest(changes=changes), self.assertRaises(OperationError):
                validate_receipt(json.dumps(receipt | {"quality":quality | changes}), self.run, self.attempt)

    def test_failed_verifier_rejects_empty_or_corrupt_checkpoint(self):
        self.job['status']['conditions'] = [{'type':'Complete','status':'True'}]
        verifier = {'status': {'conditions':[{'type':'Failed','status':'True'}]}}
        with patch('kedrogy.training._get', side_effect=[self.job,verifier]), patch('kedrogy.training._pods', return_value=[self.pod('train','')]):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.error['code'], 'ARTIFACT_INVALID')

    def test_failed_retraining_preserves_previous_version(self):
        previous = TrainingRun.objects.create(model=self.model, idempotency_key='previous', status='SUCCEEDED', job_name='previous', namespace='default', artifact={'path':'previous/artifact'})
        self.model.published_run = previous
        self.model.artifact_status = 'VERIFIED'
        self.model.trained = True
        self.model.save()
        self.job['status']['conditions'] = [{'type':'Failed','status':'True'}]
        with patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[]):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'FAILED')
        self.model.refresh_from_db()
        self.assertEqual(self.model.published_run_id, previous.id)
        self.assertTrue(self.model.trained)

    def test_restart_observes_existing_job_without_recreating_it(self):
        self.run.job_uid = self.uid
        self.run.status = 'RUNNING'
        self.run.lease_until = timezone.now()-timedelta(minutes=1)
        self.run.save()
        with patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[]), patch('kedrogy.training._ensure') as create:
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'RUNNING')
        create.assert_not_called()
        self.assertIsNone(run.lease_owner)

    def test_unexpired_lease_prevents_duplicate_observer(self):
        self.run.lease_until = timezone.now()+timedelta(minutes=1)
        self.run.save()
        with patch('kedrogy.training._get') as get:
            advance_run(self.run.id)
        get.assert_not_called()

    def test_replaced_job_does_not_satisfy_old_run(self):
        self.run.job_uid = 'old-uid'
        self.run.save()
        with patch('kedrogy.training._get', return_value=self.job):
            run = advance_run(self.run.id)
        self.assertEqual(run.error['code'], 'JOB_IDENTITY_MISMATCH')

    def test_expired_run_cannot_later_be_promoted(self):
        TrainingRun.objects.filter(pk=self.run.pk).update(created_at=timezone.now()-timedelta(hours=4))
        with patch('kedrogy.training._get', return_value=None):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'TIMED_OUT')
        with patch('kedrogy.training._get') as get:
            advance_run(run.id)
        get.assert_not_called()

    def test_unavailable_cluster_is_not_reported_as_training_success(self):
        with patch('kedrogy.training._get', side_effect=OperationError('CLUSTER_UNAVAILABLE','Unavailable.')):
            run = advance_run(self.run.id)
        self.assertEqual(run.status, 'QUEUED')
        self.assertIn('CLUSTER_UNAVAILABLE', run.public_logs)

    def test_old_boolean_does_not_enable_serve(self):
        self.model.trained = True
        self.model.save()
        response = self.client.get(f'/api/models/{self.model.pk}/')
        self.assertFalse(response.json()['trained'])
        with patch('kedrogy.api_views.new_serve_task') as task:
            response = self.client.post(f'/api/models/{self.model.pk}/serve/')
            self.assertEqual(response.status_code, 409)
            task.enqueue.assert_not_called()

    def test_train_status_is_read_only_and_snapshot_does_not_follow_edits(self):
        self.model.labels='changed,labels'
        self.model.save()
        before = list(TrainingRun.objects.values())
        with patch('kedrogy.training.command') as cluster:
            response = self.client.get(f'/api/tasks/train/{self.run.pk}/status/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(before,list(TrainingRun.objects.values()))
        self.assertEqual(self.run.snapshot['labels'],['P','N'])
        cluster.assert_not_called()

    def test_active_training_blocks_model_and_dataset_record_deletion(self):
        for url in [f'/api/models/{self.model.pk}/', f'/api/datasets/{self.dataset.pk}/']:
            self.assertEqual(self.client.delete(url).status_code, 409)
        with patch('kedrogy.deletion._get', return_value=None):
            self.assertEqual(self.client.post(f'/delete_dataset/{self.dataset.pk}').status_code, 409)
        self.assertTrue(TrainingRun.objects.filter(pk=self.run.pk).exists())

    def test_running_output_is_cached_redacted_and_exposed_by_read_only_status(self):
        output = '\x1b[32mepoch=1 loss=0.4\x1b[0m\rpassword=synthetic-secret\npostgresql://account:dsn-secret@host/db'
        self.cluster.return_value = output
        with patch.dict(os.environ, {'TEST_PASSWORD': 'synthetic-secret'}), patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[self.pod('train', '')]):
            run = advance_run(self.run.pk)
        self.assertEqual(run.status, 'RUNNING')
        self.assertIn('epoch=1 loss=0.4', run.public_logs)
        for value in ('synthetic-secret', 'dsn-secret', '\x1b', '\r'):
            self.assertNotIn(value, run.public_logs)
        self.cluster.reset_mock()
        response = self.client.get(f'/api/tasks/train/{run.pk}/status/')
        self.assertEqual(response.json()['logs'], run.public_logs)
        self.cluster.assert_not_called()

    def test_log_failure_preserves_last_output_without_failing_training(self):
        self.run.public_logs = 'epoch=1 loss=0.4'
        self.run.save(update_fields=['public_logs'])
        self.cluster.side_effect = OperationError('OPERATION_TIMEOUT', 'Private error detail')
        with patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[self.pod('train', '')]):
            run = advance_run(self.run.pk)
            run = advance_run(run.pk)
        self.assertEqual(run.status, 'RUNNING')
        self.assertIsNone(run.lease_owner)
        self.assertIn('epoch=1 loss=0.4', run.public_logs)
        self.assertEqual(run.public_logs.count('Log collection warning'), 1)
        self.assertIn('OPERATION_TIMEOUT', run.public_logs)
        self.assertNotIn('Private error detail', run.public_logs)

    def test_pending_container_explains_wait_without_requesting_unavailable_logs(self):
        pod = self.pod('train', '')
        pod['status'] = {'phase': 'Pending', 'containerStatuses': [{'name': 'train', 'state': {'waiting': {'reason': 'ImagePullBackOff', 'message': 'Retrying image pull'}}}]}
        logs = training_log_snapshot([pod], 'test')
        self.assertIn('ImagePullBackOff', logs)
        self.cluster.assert_not_called()
        self.assertIn('scheduled', training_log_snapshot([], 'test'))

    def test_log_reading_is_bounded_and_only_uses_two_latest_attempts(self):
        pods = [self.pod('train', '') for _ in range(4)]
        for index, pod in enumerate(pods):
            pod['metadata'] = {'name': f'attempt-{index}', 'uid': str(index), 'creationTimestamp': f'2026-10-01T10:00:0{index}Z'}
        self.cluster.return_value = 'x' * 10000 + '\nLatest training result'
        logs = training_log_snapshot(pods, 'test')
        self.assertLessEqual(len(logs), 16000)
        self.assertTrue(logs.endswith('Latest training result'))
        self.assertEqual(self.cluster.call_count, 2)
        self.assertEqual([call.args[0][1] for call in self.cluster.call_args_list], ['attempt-2', 'attempt-3'])
        for call in self.cluster.call_args_list:
            self.assertIn('--tail=100', call.args[0])
            self.assertFalse(any(arg.startswith('--limit-bytes') for arg in call.args[0]))
            self.assertIn('--container=train', call.args[0])
            self.assertEqual(call.kwargs['timeout'], 3)

    def test_stale_observer_cannot_overwrite_saved_logs(self):
        self.run.lease_owner = uuid.uuid4()
        self.run.lease_until = timezone.now() + timedelta(minutes=1)
        self.run.public_logs = 'Newer observer output'
        self.run.save()
        _record_training_logs(self.run, uuid.uuid4(), [])
        self.run.refresh_from_db()
        self.assertEqual(self.run.public_logs, 'Newer observer output')

    def test_terminal_failure_keeps_the_container_output(self):
        self.job['status']['conditions'] = [{'type': 'Failed', 'status': 'True'}]
        self.cluster.return_value = 'RuntimeError: training failed in a node'
        with patch('kedrogy.training._get', return_value=self.job), patch('kedrogy.training._pods', return_value=[self.pod('train', '')]):
            run = advance_run(self.run.pk)
        self.assertEqual(run.status, 'FAILED')
        self.assertIn('RuntimeError: training failed in a node', run.public_logs)
        self.assertIn('Training failed.', run.public_logs)
