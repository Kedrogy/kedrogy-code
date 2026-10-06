"""Create disposable lifecycle acceptance data without reading working records."""
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.local/lifecycle-env.json'
NAME = 'kedrogy-lifecycle-pg'
NAMESPACE = 'kedrogy-check-20260926'


def main():
    import psycopg
    if ENV_FILE.exists():
        raise RuntimeError('Inspect the existing lifecycle fixture before reuse.')
    env = {'PGHOST': '127.0.0.1', 'PGPORT': '55433', 'PGDATABASE': 'lifecycle', 'PGUSER': 'fixture',
           'PGPASSWORD': secrets.token_urlsafe(40), 'DJANGO_SECRET_KEY': secrets.token_urlsafe(60),
           'KEDROGY_TEST_DATABASE': 'disposable', 'DJANGO_SETTINGS_MODULE': 'mysite.test_postgres_settings',
           'KEDROGY_NAMESPACE': NAMESPACE, 'KEDROGY_ML_IMAGE': 'approved:1'}
    ENV_FILE.write_text(json.dumps(env)); ENV_FILE.chmod(0o600)
    os.environ.update(env)
    subprocess.run(['docker','run','-d','--name',NAME,'--network','k3d-kedrogy','-p','127.0.0.1:55433:5432',
                    '-e','POSTGRES_PASSWORD','-e','POSTGRES_USER=fixture','-e','POSTGRES_DB=lifecycle','postgres:18'],
                   check=True, env=dict(os.environ, POSTGRES_PASSWORD=env['PGPASSWORD']))
    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg.connect(connect_timeout=2) as conn:
                conn.execute('SELECT 1')
            break
        except psycopg.Error:
            if time.monotonic() > deadline:
                raise TimeoutError('Fixture database did not start.') from None
            time.sleep(1)
    env |= {'READER_'+k:v for k,v in env.items() if k.startswith('PG')}
    ENV_FILE.write_text(json.dumps(env))
    print('Disposable lifecycle database created. No working data copied.')


if __name__ == '__main__':
    main()
