"""Rebuild changed sources on the previously verified local dependency layers."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/2026-09-26-implementation'
REPORT.mkdir(exist_ok=True)
config = ROOT / '.local/docker-lifecycle'
config.mkdir(exist_ok=True)
(config/'config.json').write_text(json.dumps({'cliPluginsExtraDirs': [str(Path.home()/'.docker/cli-plugins')]}))
env = dict(os.environ, DOCKER_CONFIG=str(config), DOCKER_HOST='unix://' + str(Path.home()/'.docker/run/docker.sock'))
base = json.loads((ROOT/'reports/2026-09-25-implementation/release-images.json').read_text())
copy = {
 'ml': 'COPY example/myrecipes/src /app/myrecipes/src\nCOPY example/mykedro/src /app/mykedro/src\nCOPY predict/src /predict/src\nCOPY contracts /contracts\n',
 'backend': 'COPY kedrogy/src /app/kedrogy/src\nCOPY mysite/src /app/mysite/src\nCOPY contracts /app/contracts\n',
 'web': 'COPY .local/lifecycle-web-dist /usr/share/nginx/html\nCOPY infra/nginx.conf /etc/nginx/conf.d/default.conf\nCOPY infra/nginx-proxy.conf /etc/nginx/proxy_params_kedrogy\n'}
images = {}
for kind, repository in [('ml','mykedro'),('backend','mysite'),('web','web')]:
    tag = f'kedrogy-registry.localhost:5500/{repository}:lifecycle-20260926'
    cached = f'kedrogy-registry.localhost:5500/{repository}:revisions-20260925'
    expected = base[kind].split('@')[1]
    actual = subprocess.check_output(['docker','image','inspect',cached,'--format','{{.Id}}'],env=env,text=True).strip()
    if actual != expected:
        raise RuntimeError('Cached base differs from the recorded release identity.')
    recipe = 'FROM '+cached+'\n'+copy[kind]
    # The web build context contains only its compiled public assets and proxy files.
    context = str(ROOT/'.local/lifecycle-web-context') if kind == 'web' else str(ROOT)
    with (ROOT/f'.local/build-{kind}-1316-cached.log').open('w') as log:
        subprocess.run(['docker','build','--pull=false','--progress=plain','-f','-','-t',tag,context],
                       input=recipe,text=True,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run(['docker','push',tag],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    digest = subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],env=env,text=True).strip()
    images[kind] = f'kedrogy-registry:5000/{repository}@{digest}'
    print(f'{kind}: {digest}',flush=True)
(REPORT/'release-images.json').write_text(json.dumps(images,indent=2)+'\n')
