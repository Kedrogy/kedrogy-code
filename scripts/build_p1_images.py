"""Build the P1 repair release on verified cached layers; push only to the local registry."""

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/2026-09-26-p1-implementation'
BASE = ROOT / 'reports/2026-09-26-implementation/release-images.json'


def main():
    config = ROOT / '.local/p1-tests/docker'
    config.mkdir(parents=True, exist_ok=True)
    (config / 'config.json').write_text(json.dumps({'cliPluginsExtraDirs': [str(Path.home() / '.docker/cli-plugins')]}))
    env = dict(os.environ, DOCKER_CONFIG=str(config), DOCKER_HOST='unix://' + str(Path.home() / '.docker/run/docker.sock'))
    base = json.loads(BASE.read_text())
    web_context = ROOT / '.local/p1-tests/web-context'
    web_context.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'app/dist', web_context / 'dist', dirs_exist_ok=True)
    for name in ('nginx.conf', 'nginx-proxy.conf'):
        shutil.copyfile(ROOT / 'infra' / name, web_context / name)
    layers = {
        'ml': 'COPY example/myrecipes /app/myrecipes\nCOPY example/mykedro/src /app/mykedro/src\nCOPY example/mykedro/conf/base /app/mykedro/conf/base\nCOPY predict/src /predict/src\nCOPY contracts /contracts\nRUN uv pip install --offline --no-deps --no-build-isolation --python /app/.venv/bin/python -e /app/myrecipes\n',
        'backend': 'COPY kedrogy/src /app/kedrogy/src\nCOPY mysite/src /app/mysite/src\nCOPY contracts /app/contracts\n',
        'web': 'COPY dist /usr/share/nginx/html\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nCOPY nginx-proxy.conf /etc/nginx/proxy_params_kedrogy\n',
    }
    images = {}
    for kind, repository in [('ml', 'mykedro'), ('backend', 'mysite'), ('web', 'web')]:
        cached = f'kedrogy-registry.localhost:5500/{repository}:lifecycle-20260926'
        actual = subprocess.check_output(['docker', 'image', 'inspect', cached, '--format', '{{.Id}}'], env=env, text=True).strip()
        if actual != base[kind].split('@')[1]:
            raise RuntimeError('Cached base image does not match the verified release.')
        tag = f'kedrogy-registry.localhost:5500/{repository}:p1-20260926'
        context = web_context if kind == 'web' else ROOT
        with (REPORT / f'build-{kind}.log').open('w') as log:
            subprocess.run(['docker', 'build', '--network=none', '--pull=false', '--progress=plain', '-f', '-', '-t', tag, str(context)],
                input='FROM ' + cached + '\n' + layers[kind], text=True, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run(['docker', 'push', tag], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        digest = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], env=env, text=True).strip()
        images[kind] = f'kedrogy-registry:5000/{repository}@{digest}'
        print(f'{kind}: {digest}', flush=True)
    (REPORT / 'release-images.json').write_text(json.dumps(images, indent=2) + '\n')


if __name__ == '__main__':
    main()
