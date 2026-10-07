"""Provision the disposable namespace, restricted database roles and runtime settings."""
import json
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from scripts.configure_database import provision
from scripts.publish_local_secrets import apply_secret
from scripts.refresh_kubeconfig import refresh

root = Path(__file__).resolve().parents[1]
path = root/'.local/lifecycle-env.json'
env = json.loads(path.read_text())
if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env['KEDROGY_NAMESPACE'] != 'kedrogy-check-20260926':
    raise RuntimeError('Disposable lifecycle fixture required.')
os.environ.update(env)
ns = env['KEDROGY_NAMESPACE']
os.environ['KUBECONFIG'] = str(Path.home()/'.kube/config')
credentials = root/'.local/lifecycle-credentials'
if not credentials.exists():
    provision(credentials)
subprocess.run(['kubectl','create','namespace',ns],check=True)
subprocess.run(['python3','scripts/render_infrastructure.py','--output-dir','.local/lifecycle-manifests'],check=True)
app = json.loads((root/'.local/lifecycle-manifests/mysite.yaml').read_text())
app['items'] = [x for x in app['items'] if x['kind'] in ['ServiceAccount','Role','RoleBinding']]
subprocess.run(['kubectl','-n',ns,'apply','-f','-'],input=json.dumps(app),text=True,check=True)
web = json.loads((root/'.local/lifecycle-manifests/infra/web.json').read_text())
service = next(x for x in web['items'] if x['kind']=='Service' and x['metadata']['name']=='prodigy-svc')
subprocess.run(['kubectl','-n',ns,'apply','-f','-'],input=json.dumps(service),text=True,check=True)
for kind in ['app','reader','annotator','ingest','migrator']:
    values=dict(dotenv_values(credentials/f'{kind}.env'))
    apply_secret('kedrogy-db-'+kind,values|{'PGHOST':'kedrogy-lifecycle-pg','PGPORT':'5432'},ns)
    if kind=='reader':
        env.update({'READER_'+k:v for k,v in values.items()})
    if kind=='app':
        env.update(values)
images=json.loads((root/'reports/2026-09-26-implementation/release-images.json').read_text())
env.update(KEDROGY_ML_IMAGE=images['ml'],KUBECONFIG=str(root/'.local/lifecycle-kubeconfig.json'),
           DJANGO_SETTINGS_MODULE='lifecycle_runtime_settings',PYTHONPATH=str(root/'.local'))
refresh(admin_config=Path.home()/'.kube/config',output=Path(env['KUBECONFIG']),namespace=ns)
(root/'.local/lifecycle_runtime_settings.py').write_text('''import os
from mysite.test_postgres_settings import *
KEDROGY_ML_IMAGE=os.environ['KEDROGY_ML_IMAGE']
KEDROGY_ML_IMAGE_ALIASES={'approved:1',KEDROGY_ML_IMAGE}
KEDROGY_NAMESPACE=os.environ['KEDROGY_NAMESPACE']
KEDROGY_ANNOTATION_URL='http://127.0.0.1:18081'
ALLOWED_HOSTS=['testserver','localhost','127.0.0.1']
''')
path.write_text(json.dumps(env)); path.chmod(0o600)
print('Disposable runtime configured with restricted roles; credential values withheld.')
