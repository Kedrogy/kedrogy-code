"""Behavioral subprocess and task-result regression tests."""

import os
import sys
import time
from typing import ClassVar
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django_tasks import TaskResultStatus

from . import prediction
from .kubernetes import OperationError, execute, redact
from .task_results import present


class ProcessTests(SimpleTestCase):
    def test_real_nonzero_exit_is_public_failure(self):
        with self.assertRaises(OperationError) as caught:
            execute([sys.executable, '-c', 'import sys; print("private-value", file=sys.stderr); sys.exit(7)'])
        self.assertEqual(caught.exception.returncode, 7)
        self.assertNotIn('private-value', str(caught.exception))

    def test_both_pipes_are_drained_and_bounded(self):
        result = execute([sys.executable, '-c', 'import os; os.write(1,b"a"*2000000); os.write(2,b"b"*2000000)'], limit=1024)
        self.assertEqual(len(result.stdout), 1024)
        self.assertEqual(len(result.stderr), 1024)
        self.assertTrue(result.truncated)
        self.assertEqual(result.returncode, 0)

    def test_structured_output_is_not_silently_truncated(self):
        with self.assertRaises(OperationError) as caught:
            execute([sys.executable, '-c', 'print("x"*10000)'], limit=128, strict_output=True)
        self.assertEqual(caught.exception.code, 'OUTPUT_LIMIT')

    def test_timeout_reaps_process_and_inherited_pipes(self):
        before = time.monotonic()
        with self.assertRaises(OperationError) as caught:
            execute([sys.executable, '-c', 'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import signal; signal.pause()"]); import signal; signal.pause()'], timeout=0.2)
        self.assertEqual(caught.exception.code, 'OPERATION_TIMEOUT')
        self.assertLess(time.monotonic() - before, 3)

    def test_missing_executable_is_controlled(self):
        with self.assertRaises(OperationError) as caught:
            execute(['/nonexistent/kedrogy-executable'])
        self.assertEqual(caught.exception.code, 'PROCESS_START_FAILED')

    def test_stderr_warning_does_not_fail_success(self):
        result = execute([sys.executable, '-c', 'import sys; print("warning",file=sys.stderr); print("result")'])
        self.assertEqual(result.stdout.strip(), 'result')
        self.assertEqual(result.stderr.strip(), 'warning')

    def test_known_secrets_and_dsns_are_filtered(self):
        with patch.dict(os.environ, {'TEST_PASSWORD': 'synthetic-private-password'}):
            value = redact('synthetic-private-password postgresql://account:other-secret@host/db token=another-secret')
        for secret in ('synthetic-private-password', 'other-secret', 'another-secret'):
            self.assertNotIn(secret, value)

    def test_prediction_tunnel_exits_on_http_error(self):
        with patch('kedrogy.prediction.service_tunnel') as tunnel, patch('kedrogy.prediction.call', side_effect=OperationError('PREDICTION_TIMEOUT', 'Timed out.')):
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(OperationError):
                with prediction.service_url(SimpleNamespace(model_id=1, namespace='test', resource_layout='legacy-fixed-v1')) as url:
                    prediction.call('test', url, run=None)
            tunnel.return_value.__exit__.assert_called_once()


class FailedResult:
    status = TaskResultStatus.FAILED
    metadata: ClassVar[dict] = {'logs': 'legacy-secret-value'}

    @property
    def return_value(self):
        raise AssertionError('A failed return value must never be read.')


class TaskResultTests(TestCase):
    def test_failed_result_never_reads_return_value_or_legacy_logs(self):
        value = present(FailedResult())
        self.assertEqual(value['status'], 'FAILED')
        self.assertTrue(value['is_finished'])
        self.assertIsNone(value['return_value'])
        self.assertNotIn('legacy-secret-value', str(value))

    def test_failed_poll_is_200_and_read_only(self):
        with patch('kedrogy.api_views.new_serve_task') as task:
            task.get_result.return_value = FailedResult()
            with self.assertNumQueries(0):
                response = self.client.get('/api/tasks/serve/old-task/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'FAILED')

    def test_failed_legacy_poll_is_terminal_html(self):
        with patch('kedrogy.views.new_dataset_task') as task:
            task.get_result.return_value = FailedResult()
            response = self.client.get('/new_dataset_result/old-task/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'hx-trigger')
        self.assertNotContains(response, 'successfully')

    def test_status_for_unknown_task_is_json_404(self):
        response = self.client.get('/api/tasks/serve/not-present/status/')
        self.assertEqual(response.status_code, 404)
        self.assertIn('error', response.json())
