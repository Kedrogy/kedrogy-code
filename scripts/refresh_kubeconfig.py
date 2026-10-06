"""Create a scoped local kubeconfig without changing the user's kubectl context."""
import argparse
import json
import os
import subprocess
from pathlib import Path


def refresh(*, admin_config: Path, output: Path, namespace: str = 'default') -> None:
    """Issue a bounded controller token; never print or embed admin credentials."""
    base = ['kubectl', '--kubeconfig', str(admin_config)]
    raw = json.loads(subprocess.check_output(base + ['config', 'view', '--raw', '--minify', '-o', 'json'], text=True))
    token = subprocess.check_output(base + ['-n', namespace, 'create', 'token', 'kedrogy-controller', '--duration=24h'], text=True).strip()
    cluster = raw['clusters'][0]
    cluster_settings = cluster['cluster']
    ca_file = cluster_settings.pop('certificate-authority', None)
    if ca_file:
        import base64
        certificate = Path(ca_file)
        if not certificate.is_absolute():
            certificate = admin_config.parent / certificate
        cluster_settings['certificate-authority-data'] = base64.b64encode(certificate.read_bytes()).decode()
    config = {'apiVersion': 'v1', 'kind': 'Config', 'clusters': [cluster],
              'users': [{'name': 'kedrogy-controller', 'user': {'token': token}}],
              'contexts': [{'name': 'kedrogy-local', 'context': {'cluster': cluster['name'], 'user': 'kedrogy-controller', 'namespace': namespace}}],
              'current-context': 'kedrogy-local'}
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(output, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        json.dump(config, file)
    print('Scoped kubeconfig refreshed (token requested for 24h); credential values withheld.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-config', type=Path, default=Path.home() / '.kube/config')
    parser.add_argument('--output', type=Path, default=Path('.local/kubeconfig.json'))
    parser.add_argument('--namespace', default='default')
    args = parser.parse_args()
    refresh(admin_config=args.admin_config, output=args.output, namespace=args.namespace)
