"""Fault-inject only synthetic cleanup, preserving UID and volume safety."""
import json
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
env=json.loads((ROOT/'.local/lifecycle-env.json').read_text())
if env.get('KEDROGY_TEST_DATABASE')!='disposable' or env['KEDROGY_NAMESPACE']!='kedrogy-check-20260926':
    raise RuntimeError('Disposable lifecycle fixture required.')
os.environ.update(env);sys.path.insert(0,str(ROOT/'.local'))
import django;django.setup()
from django.conf import settings
from django.utils import timezone
from kedrogy.deletion import preview,request_deletion,advance_deletion,retry_deletion
from kedrogy.models import DeletionRun,DjangoModel
from kedrogy.training import _ensure,_get
from kedrogy.operation_control import resource_ref,delete_exact
from kedrogy.kubernetes import command
state=json.loads((ROOT/'.local/lifecycle-state.json').read_text());model_id=state['model_id']
if '--resume-after-consumer' not in sys.argv:
    name='synthetic-volume-consumer'
    job=_ensure({'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name},'spec':{'backoffLimit':0,'template':{'spec':{
        'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[{'name':'consumer','image':settings.KEDROGY_ML_IMAGE,
        'command':['/app/.venv/bin/python','-c',"from pathlib import Path;import time;p=Path('/models/fixture-version');p.mkdir(exist_ok=True);(p/'synthetic-checkpoint.txt').write_text('Synthetic checkpoint fixture');time.sleep(1200)"],
        'volumeMounts':[{'name':'models','mountPath':'/models'}]}], 'volumes':[{'name':'models','persistentVolumeClaim':{'claimName':f'pvc-model-{model_id}'}}]}}}},settings.KEDROGY_NAMESPACE)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        pods=command(['get','pods','-l',f'job-name={name}','-o','json'],json_output=True)
        if any(p.get('status',{}).get('phase')=='Running' for p in pods['items']):break
        time.sleep(2)
    else:raise TimeoutError('Volume consumer did not start.')
    plan=preview('model_files',model_id)
    run,_=request_deletion('model_files',model_id,plan['preview_token'],'recovery-fixture')
    for _ in range(6):
        DeletionRun.objects.filter(pk=run.pk).update(next_attempt_at=None)
        run=advance_deletion(run.pk)
    assert run.status=='NEEDS_REVIEW' and run.error['code']=='VOLUME_IN_USE',run.error
    assert _get('pvc',f'pvc-model-{model_id}',settings.KEDROGY_NAMESPACE)
    assert DjangoModel.objects.get(pk=model_id).resources_deleting
    (ROOT/'.local/recovery-operation.txt').write_text(str(run.id))
    print('Volume consumer prevented cleanup; reservation and completed steps retained.',flush=True)
    # The temporary Job is a test fixture, not a user-owned historical workload.
    ref=resource_ref(job,settings.KEDROGY_NAMESPACE)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if delete_exact(ref):break
        time.sleep(2)
    else:raise TimeoutError('Fixture consumer did not stop.')
else:
    run=DeletionRun.objects.get(pk=(ROOT/'.local/recovery-operation.txt').read_text())
retry_deletion(run.pk)
marker=ROOT/'.local/cleanup-crash-marker'
child_code='''import os,json,sys,time
from pathlib import Path
os.environ.update(json.load(open('.local/lifecycle-env.json')));sys.path.insert(0,'.local')
import django;django.setup()
from kedrogy import deletion
actual=deletion.delete_exact
def interrupted(ref):
 done=actual(ref)
 if done:
  Path('.local/cleanup-crash-marker').write_text('External UID is gone; progress has not been committed.')
  time.sleep(120)
 return done
deletion.delete_exact=interrupted
while True:
 deletion.advance_deletion(Path('.local/recovery-operation.txt').read_text())
 time.sleep(1)
'''
with (ROOT/'.local/cleanup-crash.log').open('w') as log:
    child=subprocess.Popen([sys.executable,'-c',child_code],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        deadline=time.monotonic()+120
        while time.monotonic()<deadline and not marker.exists():
            if child.poll() is not None:raise RuntimeError('Crash target exited before the intended boundary.')
            time.sleep(.2)
        if not marker.exists():raise TimeoutError('Crash boundary not reached.')
        os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
run.refresh_from_db();assert run.status=='RUNNING' and 'stopped' in run.completed
# Inject lease expiry instead of waiting six minutes; the former owner was killed above.
DeletionRun.objects.filter(pk=run.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
run=advance_deletion(run.pk)
assert run.status=='SUCCEEDED',run.error
assert not DjangoModel.objects.get(pk=model_id).resources_deleting
state['recovery_cleanup']=str(run.id)
state['checks'].extend(['A live Pod prevents volume deletion and leaves visible NEEDS_REVIEW progress',
                       'After removing the synthetic consumer, the process was killed after external deletion but before progress commit; an independent observer completed the same operation'])
(ROOT/'.local/lifecycle-state.json').write_text(json.dumps(state,indent=2)+'\n')
print('Killed cleanup process recovered the same operation without recreating or deleting a replacement resource.',flush=True)
