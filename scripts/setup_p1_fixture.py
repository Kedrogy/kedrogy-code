"""Create a disposable P1 acceptance fixture; never copy working data."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/p1-tests'
NAMESPACE = 'kedrogy-p1-20260926'
CONTAINER = 'kedrogy-p1-pg'


def main():
    path = PRIVATE / 'runtime-env.json'
    if path.exists():
        raise RuntimeError('Inspect the existing P1 fixture before reuse.')
    images = json.loads((ROOT / 'reports/2026-09-26-p1-implementation/release-images.json').read_text())
    admin = {'PGHOST': '127.0.0.1', 'PGPORT': '55440', 'PGDATABASE': 'p1_runtime',
             'PGUSER': 'fixture_admin', 'PGPASSWORD': secrets.token_urlsafe(40)}
    saved = PRIVATE / 'admin-env.json'
    saved.write_text(json.dumps(admin)); saved.chmod(0o600)
    child = dict(os.environ, **admin, POSTGRES_PASSWORD=admin['PGPASSWORD'])
    subprocess.run(['docker', 'run', '-d', '--name', CONTAINER, '--network', 'k3d-kedrogy', '-p', '127.0.0.1:55440:5432',
                    '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_USER=fixture_admin', '-e', 'POSTGRES_DB=p1_runtime', 'postgres:18'], env=child, check=True)
    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg.connect(**{k.removeprefix('PG').lower() if k != 'PGDATABASE' else 'dbname': v for k,v in admin.items()}, connect_timeout=2):
                break
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)
    # Initialize the installed Prodigy schema using its actual ORM, in the fixture only.
    code = """import os
from prodigy.components.db import Database
from peewee import PostgresqlDatabase
Database(PostgresqlDatabase(os.environ['PGDATABASE'],user=os.environ['PGUSER'],password=os.environ['PGPASSWORD'],host=os.environ['PGHOST'],port=int(os.environ['PGPORT'])), 'postgresql', 'P1 synthetic fixture')
"""
    subprocess.run([str(ROOT / 'example/.venv/bin/python'), '-c', code], env=child, check=True, timeout=120)
    env = admin | {'DJANGO_SETTINGS_MODULE': 'p1_runtime_settings', 'KEDROGY_TEST_DATABASE': 'disposable',
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(50), 'KEDROGY_NAMESPACE': NAMESPACE, 'KEDROGY_ML_IMAGE': images['ml'],
        'PYTHONPATH': str(PRIVATE), 'KUBECONFIG': str(Path.home() / '.kube/config')}
    (PRIVATE / 'p1_runtime_settings.py').write_text('''import json
import os
from mysite.test_postgres_settings import *
KEDROGY_NAMESPACE = os.environ['KEDROGY_NAMESPACE']
KEDROGY_ML_IMAGE = os.environ['KEDROGY_ML_IMAGE']
KEDROGY_ML_IMAGE_ALIASES = {'approved:1', KEDROGY_ML_IMAGE}
KEDROGY_TRAIN_OPTIONS = {'base_model': 'data/06_models/tiny-base', 'max_steps': 1}
KEDROGY_TRAIN_TIMEOUT = 600
KEDROGY_SERVE_TIMEOUT = 600
KEDROGY_SOURCES = json.loads(os.environ.get('KEDROGY_SOURCES', '{}'))
''')
    subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), '-m', 'django', 'migrate', '--noinput'], env=os.environ | env, check=True)
    credentials = PRIVATE / 'credentials'
    subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), 'scripts/configure_database.py', '--output-dir', str(credentials)], env=child, check=True)
    from configure_sources import create_source
    with psycopg.connect(**{'host': admin['PGHOST'], 'port': admin['PGPORT'], 'dbname': admin['PGDATABASE'], 'user': admin['PGUSER'], 'password': admin['PGPASSWORD']}) as connection:
        source_id = create_source(connection, 'synthetic-p1-v1', 'upstream-id-v1')
    sources = {'managed_reviews': {'schema': 'kedrogy_source', 'table': 'record', 'id_fields': ['id'], 'source_id': str(source_id)}}
    roles = {kind: dict(dotenv_values(credentials / f'{kind}.env')) for kind in ('app', 'migrator', 'reader', 'annotator', 'ingest')}
    env |= roles['app'] | {'READER_' + key: value for key, value in roles['reader'].items()}
    env['KEDROGY_SOURCES'] = json.dumps(sources)
    subprocess.run(['kubectl', 'create', 'namespace', NAMESPACE], check=True)
    subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), 'scripts/render_infrastructure.py', '--namespace', NAMESPACE,
                    '--output-dir', str(PRIVATE / 'rendered')], check=True)
    subprocess.run(['kubectl', '-n', NAMESPACE, 'apply', '-f', str(PRIVATE / 'rendered/infra/rbac.json')], check=True)
    route = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'prodigy-svc', 'namespace': NAMESPACE},
             'spec': {'selector': {'app.kubernetes.io/name': 'prodigy', 'kedrogy/annotation-id': 'stopped'}, 'ports': [{'port': 8080}]}}
    subprocess.run(['kubectl', '-n', NAMESPACE, 'create', '-f', '-'], input=json.dumps(route), text=True, check=True)
    from publish_local_secrets import apply_secret
    ip = subprocess.check_output(['docker', 'inspect', CONTAINER, '--format', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'], text=True).strip()
    for kind, values in roles.items():
        apply_secret('kedrogy-db-' + kind, values | {'PGHOST': ip, 'PGPORT': '5432'}, NAMESPACE)
    # This fixture contains only generated records with explicit upstream IDs.
    rows = [{'id': f'{i:03d}', 'text': ('A good synthetic product.' if i % 2 else 'A bad synthetic product.'),
             'source': 'p1-acceptance'} for i in range(12)]
    source_file = PRIVATE / 'source.jsonl'
    source_file.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    import_env = os.environ | roles['ingest']
    import_command = [str(ROOT / 'example/.venv/bin/python'), '-m', 'mykedro.sources', str(source_file),
                      '--source', 'synthetic-p1-v1', '--request-key', 'first-import', '--apply']
    subprocess.run(import_command, env=import_env, check=True)
    source_file.write_text(''.join(json.dumps(row) + '\n' for row in reversed(rows)))
    subprocess.run(import_command, env=import_env, check=True)
    path.write_text(json.dumps(env)); path.chmod(0o600)
    print('P1 fixture ready; private credentials withheld and no working data copied.', flush=True)


if __name__ == '__main__':
    main()
