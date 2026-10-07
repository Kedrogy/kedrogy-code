"""Run all SQL-dependent suites against separate disposable PostgreSQL 18 databases."""

import json
import os
import subprocess
import time
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/p1-tests'
REPORT = ROOT / 'reports/2026-09-26-p1-implementation'


def main():
    admin = json.loads((PRIVATE / 'admin-env.json').read_text())
    if admin.get('PGPORT') != '55440' or admin.get('PGDATABASE') != 'p1_runtime':
        raise ValueError('Disposable P1 fixture only.')
    env = dict(os.environ, **admin, KEDROGY_TEST_DATABASE='disposable')
    suffix = str(time.time_ns())
    sources_database, backend_database = 'p1_sources_' + suffix, 'p1_backend_' + suffix
    with psycopg.connect(host=admin['PGHOST'], port=admin['PGPORT'], dbname=admin['PGDATABASE'], user=admin['PGUSER'], password=admin['PGPASSWORD'], autocommit=True) as connection:
        for name in (sources_database, backend_database):
            if connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
                raise RuntimeError('Use a fresh test database; existing fixture results are retained.')
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    commands = [
        (sources_database, 'ml-postgres18-tests.log', [str(ROOT / 'example/.venv/bin/python'), '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        (backend_database, 'backend-postgres18-tests.log', [str(ROOT / 'mysite/.venv/bin/python'), '-m', 'django', 'test',
         'kedrogy.tests', 'kedrogy.test_training', 'kedrogy.test_revisions', 'kedrogy.test_lifecycle', 'kedrogy.test_operations',
         'kedrogy.test_deployment', 'kedrogy.test_serving_ownership', 'kedrogy.test_training_concurrency',
         'kedrogy.test_annotation_identity', 'kedrogy.test_p1_migrations', '--settings=mysite.test_postgres_settings', '--noinput']),
    ]
    for database, filename, command in commands:
        with (REPORT / filename).open('w') as log:
            subprocess.run(command, env=env | {'PGDATABASE': database}, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f'{filename}: passed', flush=True)


if __name__ == '__main__':
    main()
