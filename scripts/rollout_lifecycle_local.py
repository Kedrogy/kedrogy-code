"""Apply the additive lifecycle migration and inspect local ownership without deleting data."""
import json
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT=Path(__file__).resolve().parents[1]
images=json.loads((ROOT/'reports/2026-09-26-implementation/release-images.json').read_text())
env={k:v for k,v in dotenv_values(ROOT/'.env').items() if v is not None}
if env.get('PGDATABASE')!='mysite' or env.get('KEDROGY_NAMESPACE','default')!='default':
    raise RuntimeError('Inspect the local database and namespace before migration.')
old_image=env['KEDROGY_ML_IMAGE']
aliases=set(json.loads(env.get('KEDROGY_ML_IMAGE_ALIASES','[]')))|{old_image,images['ml']}
env.update(DJANGO_SETTINGS_MODULE='mysite.settings_local',KUBECONFIG=str(ROOT/'.local/kubeconfig.json'))
subprocess.run([str(ROOT/'mysite/.venv/bin/python'),'scripts/refresh_kubeconfig.py'],check=True)
admin=dict(env);admin.update({k:v for k,v in dotenv_values(ROOT/'.local/credentials/migrator.env').items() if v is not None})
subprocess.run([str(ROOT/'mysite/.venv/bin/python'),'-m','django','migrate','--noinput'],env=dict(os.environ,**admin),check=True)
for key,value in {'KEDROGY_ML_IMAGE':images['ml'],'KEDROGY_ML_IMAGE_ALIASES':json.dumps(sorted(aliases)),
                  'KEDROGY_ANNOTATION_URL':'http://label.localhost:8081'}.items():
    set_key(ROOT/'.env',key,value)
env.update(KEDROGY_ML_IMAGE=images['ml'],KEDROGY_ML_IMAGE_ALIASES=json.dumps(sorted(aliases)))
with (ROOT/'reports/2026-09-26-implementation/local-inventory.json').open('w') as report:
    subprocess.run([str(ROOT/'mysite/.venv/bin/python'),'-m','django','operation_inventory','--resources'],
                   env=dict(os.environ,**env),stdout=report,check=True)
print('Local additive migration and read-only resource/task inventory completed. Historical data and workloads retained.')
