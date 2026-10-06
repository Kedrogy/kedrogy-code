"""Install existing private credential files into the project's namespace."""
import argparse
import json
import os
import subprocess
from pathlib import Path


def apply_secret(name: str, values: dict, namespace: str) -> None:
    """Send secrets via stdin and avoid kubectl's last-applied annotation."""
    document = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': namespace}, 'type': 'Opaque', 'stringData': values}
    result = subprocess.run(['kubectl', 'apply', '--server-side', '--field-manager=kedrogy-security', '-f', '-'], input=json.dumps(document), text=True, capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError(f'Could not install {name}. Credential values and server response withheld.')


if __name__ == '__main__':
    # uv run --with python-dotenv ... or use the existing development environment.
    from dotenv import dotenv_values
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--namespace', default='default')
    args = parser.parse_args()
    for kind in ('app', 'reader', 'annotator', 'ingest', 'migrator', 'admin'):
        values = dict(dotenv_values(args.credentials / f'{kind}.env'))
        if any(not values.get(key) for key in ('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')):
            raise ValueError(f'Incomplete {kind} configuration; values withheld.')
        apply_secret('kedrogy-db-' + kind, values | {'PGHOST': 'postgres-svc'}, args.namespace)
    apply_secret('kedrogy-app-config', {key: os.environ[key] for key in ('DJANGO_SECRET_KEY', 'KEDROGY_ML_IMAGE')} | {
        'KEDROGY_ML_IMAGE_ALIASES': os.environ.get('KEDROGY_ML_IMAGE_ALIASES', '["kedrogy-registry:5000/mykedro:latest"]')}, args.namespace)
    print('Installed service secrets; values withheld.')
