"""Apply the verified P1 release locally without relabeling history or rotating passwords."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import psycopg
from dotenv import dotenv_values, set_key

from configure_sources import install

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/2026-09-26-p1-implementation'


def environment(path):
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def connect(env):
    return psycopg.connect(host=env['PGHOST'], port=env['PGPORT'], dbname=env['PGDATABASE'],
                           user=env['PGUSER'], password=env['PGPASSWORD'], connect_timeout=5)


def source_signature(connection):
    # Aggregate only: source text is never exported into the release report.
    return connection.execute("""SELECT count(*), coalesce(sum(
        ('x' || substr(md5(row_to_json(row)::text),1,15))::bit(60)::bigint),0)::text
        FROM public.all_data AS row""").fetchone()


def resource_signatures():
    result = subprocess.check_output(['kubectl', '-n', 'default', 'get',
        'deployments,jobs,services,configmaps,persistentvolumeclaims', '-o', 'json'], text=True)
    return {row['kind'] + '/' + row['metadata']['name']: {
        'uid': row['metadata']['uid'],
        'spec_hash': hashlib.sha256(json.dumps(row.get('spec', row.get('data', {})), sort_keys=True).encode()).hexdigest()
    } for row in json.loads(result)['items']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    env = environment(ROOT / '.env')
    if (env.get('PGDATABASE') != 'mysite' or env.get('PGHOST') not in ('localhost', '127.0.0.1')
            or env.get('PGPORT') != '30001' or env.get('KEDROGY_NAMESPACE', 'default') != 'default'):
        raise RuntimeError('This release script is restricted to the verified local database and namespace.')
    context = subprocess.check_output(['kubectl', 'config', 'current-context'], text=True).strip()
    if context != 'k3d-kedrogy':
        raise RuntimeError('Select the verified local k3d-kedrogy context before rollout.')
    processes = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True).splitlines()
    markers = ('scripts/run_local.py', '-m django db_worker', '-m django reconcile_', 'uvicorn mysite.')
    if any(any(marker in line for marker in markers) for line in processes):
        raise RuntimeError('Stop existing project API/worker/reconciler processes before controller cutover.')
    images = json.loads((REPORT / 'release-images.json').read_text())
    aliases = set(json.loads(env.get('KEDROGY_ML_IMAGE_ALIASES', '[]'))) | {env['KEDROGY_ML_IMAGE'], images['ml']}
    admin = env | environment(ROOT / '.local/credentials/admin.env')
    with connect(admin) as connection:
        before_source = source_signature(connection)
    before_resources = resource_signatures()
    if not args.apply:
        print(json.dumps({'dry_run': True, 'database': 'mysite', 'namespace': 'default',
            'legacy_source_rows': before_source[0], 'images': images, 'password_changes': False}, indent=2))
        return
    runtime = env | {'DJANGO_SETTINGS_MODULE': 'mysite.settings_local',
                     'KUBECONFIG': str(ROOT / '.local/kubeconfig.json')}
    migrator = runtime | environment(ROOT / '.local/credentials/migrator.env')
    subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), '-m', 'django', 'migrate', '--noinput'],
                   env=dict(os.environ, **migrator), check=True)
    with connect(admin) as connection:
        install(connection)
        after_source = source_signature(connection)
        if before_source != after_source:
            raise RuntimeError('Legacy source contents changed; the source setup transaction was rolled back.')
        privileges = connection.execute("""SELECT
            has_table_privilege('kedrogy_ingest','kedrogy_source.record','INSERT'),
            has_table_privilege('kedrogy_ingest','kedrogy_source.record','UPDATE'),
            has_table_privilege('kedrogy_ingest','public.all_data','DELETE'),
            pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.all_data'::regclass""").fetchone()
    rbac = json.loads((ROOT / 'infra/rbac.json').read_text())
    rbac['items'] = [row for row in rbac['items'] if row['kind'] in ('ClusterRole', 'ClusterRoleBinding')]
    subprocess.run(['kubectl', 'apply', '-f', '-'], input=json.dumps(rbac), text=True, check=True)
    subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), 'scripts/refresh_kubeconfig.py'], cwd=ROOT, check=True)
    for key, value in {'KEDROGY_ML_IMAGE': images['ml'], 'KEDROGY_ML_IMAGE_ALIASES': json.dumps(sorted(aliases))}.items():
        set_key(ROOT / '.env', key, value)
        runtime[key] = value
    with (REPORT / 'local-inventory.json').open('w') as output:
        subprocess.run([str(ROOT / 'mysite/.venv/bin/python'), '-m', 'django', 'operation_inventory', '--resources'],
                       env=dict(os.environ, **runtime), stdout=output, check=True)
    after_resources = resource_signatures()
    result = {'database': 'mysite', 'namespace': 'default', 'password_changes': False,
              'source_before': before_source, 'source_after': after_source,
              'legacy_resources_unchanged': before_resources == after_resources,
              'legacy_resources': before_resources, 'ingest_can_insert_managed': privileges[0],
              'ingest_can_update_managed': privileges[1], 'ingest_can_delete_legacy': privileges[2],
              'legacy_source_owner': privileges[3], 'images': images,
              'controllers_started': False, 'historical_annotations_converted': False}
    (REPORT / 'local-rollout.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['legacy_resources_unchanged']:
        raise RuntimeError('Resource inventory changed during cutover; inspect before starting controllers.')
    print('Additive local rollout completed. Source contents and existing workload specifications are unchanged.')


if __name__ == '__main__':
    main()
