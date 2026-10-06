"""Read-only and isolated reproductions for the Kedrogy audit."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Iterable
from unittest.mock import patch

ROOT = Path('/Users/millafedotova/work/kedrogy-code')
os.chdir(ROOT)
RESULTS = {}

def record(name, action):
    try:
        RESULTS[name] = action()
    except Exception as exc:
        RESULTS[name] = {'exception': type(exc).__name__, 'message': str(exc)}

def functions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace

syntax_files = [p for folder in ['kedrogy/src', 'mysite/src', 'predict/src', 'example/mykedro/src', 'example/myrecipes/src'] for p in (ROOT / folder).rglob('*.py')]
for path in syntax_files:
    ast.parse(path.read_text(), filename=str(path))
RESULTS['syntax'] = {'files': len(syntax_files), 'errors': 0}
test_files = list((ROOT / 'example/mykedro/tests').rglob('test*.py')) + [ROOT / 'kedrogy/src/kedrogy/tests.py']
RESULTS['test_definitions'] = sum(sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test') for n in ast.walk(ast.parse(p.read_text()))) for p in test_files)

ns = functions('example/mykedro/src/mykedro/pipelines/train/nodes.py', {'make_id2label_label2id', 'jsonl_to_fasttext'}, {'Iterable': Iterable, 'JSONInput': dict})
record('label_mismatch', lambda: ns['jsonl_to_fasttext']([{'answer': 'accept', 'label': 'N', 'text': 'sample'}], {'labels': ['p', ' n']}))
record('reject_means_other', lambda: ns['jsonl_to_fasttext']([{'answer': 'reject', 'label': 'positive', 'text': 'sample'}], {'labels': ['positive', 'negative']}))
record('reserved_other', lambda: ns['make_id2label_label2id'](['OTHER', 'positive']))
record('duplicate_labels', lambda: ns['make_id2label_label2id'](['positive', 'positive']))
record('mixed_label_types', lambda: [(r['label'], type(r['label']).__name__) for r in ns['jsonl_to_fasttext']([{'answer':'accept','label':'positive','text':'a'},{'answer':'reject','label':'positive','text':'b'}], {'labels':['positive','negative']})])

task_ns = functions('kedrogy/src/kedrogy/tasks.py', {'kubectl'}, {'subprocess': subprocess, 'time': time})
context = SimpleNamespace(metadata={'logs': ''}, save_metadata=lambda: None)
record('subprocess_exit_7', lambda: task_ns['kubectl'](context, [sys.executable, '-c', 'import sys; print("stdout diagnostic"); print("stderr diagnostic", file=sys.stderr); sys.exit(7)'], sleep=0))
RESULTS['captured_task_metadata'] = context.metadata

from jinja2 import Template
sys.path.append(str(ROOT / 'example/.venv/lib/python3.12/site-packages'))
import yaml
base = dict(model_id=9999, image='example/image:tag', workingDir='mykedro', pipeline='train', dataset_name='demo', labels='["POS","NEG"]')
template = Template((ROOT / 'kedrogy/src/kedrogy/templates_k8s/train.yaml.jinja').read_text())
injected = dict(base, image='example/image:tag\n        securityContext: {privileged: true}')
record('yaml_injection', lambda: list(yaml.safe_load_all(template.render(**injected)))[1]['spec']['template']['spec']['containers'][0]['securityContext'])
record('yaml_quoted_label', lambda: yaml.safe_load(list(yaml.safe_load_all(template.render(**dict(base, labels='["say"yes"]'))))[0]['data']['parameters_train.yml']))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
os.environ['PGOPTIONS'] = '-c default_transaction_read_only=on'
from kedrogy.apps import DatasetNewConfig
DatasetNewConfig.ready = lambda self: None
import django
django.setup()
from django.core.management import call_command
from django.core.checks import run_checks
from django.test import RequestFactory
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from kedrogy.serializers import DjangoDatasetSerializer
from kedrogy.api_views import DatasetViewSet, MLModelViewSet
from django.contrib.auth.models import AnonymousUser
from rest_framework.request import Request

def validate_dataset(data):
    serializer = DjangoDatasetSerializer(data=data)
    valid = serializer.is_valid()
    return {'valid': valid, 'errors': dict(serializer.errors), 'fields': list(serializer.validated_data)}
record('dataset_missing_configuration', lambda: validate_dataset({'dataset_name': 'demo'}))
record('dataset_blank_pipeline', lambda: validate_dataset({'dataset_name':'demo','image':'example/image:tag','workingDir':'mykedro','pipeline':'','recipe_options':'recipe','data_table_name':'all_data','id_field':'id'}))
record('dataset_injected_image_validation', lambda: validate_dataset({'dataset_name':'demo','image':injected['image']}))
record('dataset_path_name_validation', lambda: validate_dataset({'dataset_name':'x/../../audit-only'}))
request = Request(RequestFactory().post('/api/models/999/train/', data={}, content_type='application/json'))
request.user = AnonymousUser()
RESULTS['anonymous_permissions'] = {view.__name__: [permission.has_permission(request, view()) for permission in view().get_permissions()] for view in [DatasetViewSet, MLModelViewSet]}
RESULTS['django_deployment_checks'] = [{'id': x.id, 'message': str(x.msg)} for x in run_checks(include_deployment_checks=True)]

from django_tasks.base import TaskResult, TaskResultStatus
failed = SimpleNamespace(status=TaskResultStatus.FAILED)
RESULTS['failed_task_is_finished'] = TaskResult.is_finished.fget(failed)
record('failed_task_return_value', lambda: TaskResult.return_value.fget(failed))

def migration_plan():
    executor = MigrationExecutor(connection)
    return [f'{m.app_label}.{m.name}' for m, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes())]
record('unapplied_migrations', migration_plan)

def db_snapshot():
    with connection.cursor() as cur:
        cur.execute('SELECT id, dataset_name FROM kedrogy_djangodataset ORDER BY id')
        app_datasets = cur.fetchall()
        cur.execute('SELECT name FROM dataset ORDER BY name')
        prodigy_names = {r[0] for r in cur.fetchall()}
        cur.execute('SELECT id, on_dataset_id, labels, trained, served FROM kedrogy_djangomodel ORDER BY id')
        models = cur.fetchall()
        cur.execute('SELECT dataset_id FROM kedrogy_djangolastdataset')
        last = [r[0] for r in cur.fetchall()]
        cur.execute('SELECT status, count(*) FROM django_tasks_database_dbtaskresult GROUP BY status')
        tasks = cur.fetchall()
    return {'datasets': [{'id':i,'name':n,'has_matching_prodigy_dataset':n in prodigy_names} for i,n in app_datasets], 'models':models, 'last_dataset_ids':last, 'tasks_by_status':tasks}
record('database', db_snapshot)

from kedrogy import views
rf = RequestFactory()
record('legacy_new_dataset_get', lambda: views.new_dataset(rf.get('/new_dataset/')))
with patch.object(views, 'get_object_or_404', return_value=SimpleNamespace(id=999)), patch.object(views, 'predict_call', return_value='positive'), patch.dict(os.environ, {'KUBERNETES_SERVICE_HOST':'local-audit'}):
    record('legacy_predict_inside_cluster', lambda: views.predict_model(rf.post('/predict_model/999/', {'text_input':'sample'}), 999))

connection.close()
Path('/tmp/kedrogy-audit-probes.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))
print(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))
