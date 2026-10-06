"""Deployment boundary checks without a live server or production database."""

import os
import subprocess
import sys

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override


class DeploymentTests(SimpleTestCase):
    def test_unknown_host_and_routes_have_safe_json(self):
        response = self.client.get('/api/unknown/', HTTP_HOST='unapproved.invalid')
        self.assertEqual(response.status_code,400)
        self.assertIn('error',response.json())
        response = self.client.get('/api/unknown/')
        self.assertEqual(response.status_code,404)
        self.assertNotIn('Traceback',response.content.decode())
        self.assertIn('X-Request-ID',response)

    def test_api_500_does_not_expose_exception(self):
        from unittest.mock import patch
        client=Client(raise_request_exception=False)
        with patch('kedrogy.api_views.new_serve_task') as task:
            task.get_result.side_effect = RuntimeError('private-internal-path')
            response=client.get('/api/tasks/serve/id/status/')
        self.assertEqual(response.status_code,500)
        self.assertIn('error',response.json())
        self.assertNotIn('private-internal-path',response.content.decode())

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https'), TRUSTED_PROXY_CIDRS=['10.42.0.0/16'])
    def test_only_trusted_proxy_can_claim_https(self):
        response=Client().get('/health/',REMOTE_ADDR='192.0.2.1',HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code,301)
        response=Client().get('/health/',REMOTE_ADDR='10.42.1.8',HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code,200)

    def test_local_http_and_legacy_reverse_are_compatible(self):
        self.assertEqual(self.client.get('/health/').status_code,200)
        self.assertEqual(reverse('kedrogy:train_model',args=[1]),'/train_model/1/')
        with override('ru'):
            self.assertEqual(reverse('kedrogy_i18n:train_model',args=[1]),'/ru/train_model/1/')

    def test_deploy_profile_rejects_debug_and_missing_hosts(self):
        env=os.environ | {'DJANGO_SETTINGS_MODULE':'mysite.settings_deploy', 'DJANGO_SECRET_KEY':'s'*64,
            'KEDROGY_ML_IMAGE':'approved:1', 'DJANGO_ALLOWED_HOSTS':'app.kedrogy.test',
            'DJANGO_CORS_ORIGINS':'https://app.kedrogy.test', 'DJANGO_CSRF_ORIGINS':'https://app.kedrogy.test',
            'DJANGO_TRUSTED_PROXY_CIDRS':'10.42.0.0/16', 'DJANGO_DEBUG':'false'}
        command=[sys.executable,'-c','import django; django.setup()']
        result=subprocess.run(command,env=env,capture_output=True,timeout=15,check=False)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        for bad in [{'DJANGO_DEBUG':'true'},{'DJANGO_ALLOWED_HOSTS':''},{'DJANGO_ALLOWED_HOSTS':'*'},{'DJANGO_TRUSTED_PROXY_CIDRS':'0.0.0.0/0'}]:
            with self.subTest(bad=bad):
                result=subprocess.run(command,env=env|bad,capture_output=True,timeout=15,check=False)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('s'*64,result.stderr.decode())
