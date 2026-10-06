"""Compare critical installed image modules with the verified source files."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/2026-09-26-p1-implementation'


def main():
    images = json.loads((REPORT / 'release-images.json').read_text())
    checks = {
        'ml': {'example/mykedro/src/mykedro/sources.py': '/app/mykedro/src/mykedro/sources.py',
               'example/mykedro/src/mykedro/pipelines/train/nodes.py': '/app/mykedro/src/mykedro/pipelines/train/nodes.py',
               'example/myrecipes/src/myrecipes/textcat_choice.py': '/app/myrecipes/src/myrecipes/textcat_choice.py',
               'contracts/src/kedrogy_contracts/__init__.py': '/contracts/src/kedrogy_contracts/__init__.py',
               'predict/src/ysz/predict/serve.py': '/predict/src/ysz/predict/serve.py'},
        'backend': {path: '/app/' + path for path in (
            'kedrogy/src/kedrogy/serving_resources.py', 'kedrogy/src/kedrogy/serving.py',
            'kedrogy/src/kedrogy/training_preflight.py', 'kedrogy/src/kedrogy/views.py',
            'kedrogy/src/kedrogy/serializers.py', 'contracts/src/kedrogy_contracts/__init__.py')},
        'web': {'app/dist/index.html': '/usr/share/nginx/html/index.html'},
    }
    checks['web'].update({str(path.relative_to(ROOT)): '/usr/share/nginx/html/assets/' + path.name
                          for path in (ROOT / 'app/dist/assets').glob('*.js')})
    report = {}
    for kind, paths in checks.items():
        repository = {'ml': 'mykedro', 'backend': 'mysite', 'web': 'web'}[kind]
        tag = f'kedrogy-registry.localhost:5500/{repository}:p1-20260926'
        digest = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
        if images[kind].split('@')[1] != digest:
            raise RuntimeError('The local image tag changed after release verification.')
        hashes = {}
        for source, installed in paths.items():
            data = subprocess.check_output(['docker', 'run', '--rm', '--network=none', '--entrypoint', 'cat', tag, installed])
            expected = (ROOT / source).read_bytes()
            if data != expected:
                raise AssertionError(f'{kind}: {source} does not match the installed image.')
            hashes[source] = hashlib.sha256(data).hexdigest()
        report[kind] = {'digest': digest, 'files': hashes, 'verified': True}
    (REPORT / 'image-module-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Critical backend, ML, inference, annotation and frontend modules match the pinned images.')


if __name__ == '__main__':
    main()
