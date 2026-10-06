"""Verify independent observers survive a disposable PostgreSQL outage."""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='kedrogy-check-20260926'
env=json.loads((ROOT/'.local/lifecycle-env.json').read_text())
if env.get('KEDROGY_TEST_DATABASE')!='disposable' or env['KEDROGY_NAMESPACE']!=NAMESPACE:
    raise RuntimeError('Disposable fixture required.')
base=['kubectl','--kubeconfig',str(Path.home()/'.kube/config'),'-n',NAMESPACE]
def pod():
    return json.loads(subprocess.check_output(base+['get','pods','-l','app.kubernetes.io/name=mysite','-o','json'],text=True))['items'][0]
before=pod(); stopped=time.time()
subprocess.run(['docker','stop','-t','2','kedrogy-lifecycle-pg'],check=True,stdout=subprocess.DEVNULL)
try:
    time.sleep(15)
finally:
    subprocess.run(['docker','start','kedrogy-lifecycle-pg'],check=True,stdout=subprocess.DEVNULL)
import psycopg
reader={key[7:].lower():value for key,value in env.items() if key.startswith('READER_PG')}
options={k:env[v] for k,v in [('host','PGHOST'),('port','PGPORT'),('dbname','PGDATABASE'),('user','PGUSER'),('password','PGPASSWORD')]}
deadline=time.monotonic()+90
while time.monotonic()<deadline:
    try:
        with psycopg.connect(**options,connect_timeout=2) as c:
            c.execute('UPDATE kedrogy_djangodataset SET annotation_refresh_requested=true WHERE id=4')
        break
    except psycopg.Error:time.sleep(1)
else:raise TimeoutError('Fixture database did not recover.')
while time.monotonic()<deadline:
    with psycopg.connect(**options,connect_timeout=2) as c:
        observed=c.execute('SELECT annotation_observed_at,annotation_refresh_requested FROM kedrogy_djangodataset WHERE id=4').fetchone()
    if observed and observed[0] and observed[0].timestamp()>stopped and not observed[1]:break
    time.sleep(2)
else:raise TimeoutError('Deployed observer did not resume data observation.')
after=pod()
checks=[]
for name in ['training-reconciler','serving-reconciler','operation-reconciler']:
    a=next(s for s in before['status']['initContainerStatuses'] if s['name']==name)
    b=next(s for s in after['status']['initContainerStatuses'] if s['name']==name)
    assert a['state']['running']['startedAt']==b['state']['running']['startedAt'],name
    checks.append({'name':name,'same_process_survived':True})
(ROOT/'reports/2026-09-26-implementation/database-recovery.json').write_text(json.dumps({'outage_seconds':15,'reconcilers':checks,'data_observer_resumed':True},indent=2)+'\n')
print('All three deployed reconcilers survived the database outage; independent observation resumed.')
