"""Install and check the built images only in the disposable lifecycle namespace."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from scripts.publish_local_secrets import apply_secret

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'kedrogy-check-20260926'
REPORT = ROOT / 'reports/2026-09-26-implementation'


def kubectl(*args, document=None):
    return subprocess.check_output(['kubectl', '-n', NAMESPACE, *args],
        input=json.dumps(document) if document is not None else None, text=True, timeout=65)


def main():
    env = json.loads((ROOT/'.local/lifecycle-env.json').read_text())
    if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env['KEDROGY_NAMESPACE'] != NAMESPACE:
        raise RuntimeError('Only the disposable fixture is permitted.')
    images = json.loads((REPORT/'release-images.json').read_text())
    os.environ['KUBECONFIG'] = str(Path.home()/'.kube/config')
    apply_secret('kedrogy-app-config', {'DJANGO_SECRET_KEY': env['DJANGO_SECRET_KEY'], 'KEDROGY_ML_IMAGE': images['ml'],
        'KEDROGY_ML_IMAGE_ALIASES': json.dumps(['approved:1', images['ml']])}, NAMESPACE)
    directory = ROOT/'.local/lifecycle-manifests'
    subprocess.run(['python3', 'scripts/render_infrastructure.py', '--profile', 'local', '--backend-image', images['backend'],
        '--web-image', images['web'], '--output-dir', str(directory)], check=True)
    for path in [directory/'mysite.yaml', directory/'infra/web.json']:
        doc = json.loads(path.read_text())
        # The fixture is reached by local port-forward only, without adding project ingress routes.
        doc['items'] = [item for item in doc['items'] if item['kind'] != 'Ingress']
        print(kubectl('apply', '-f', '-', document=doc).strip(), flush=True)
    for name in ['mysite', 'kedrogy-web']:
        deadline = time.monotonic()+300
        while time.monotonic() < deadline:
            doc=json.loads(kubectl('get', 'deployment', name, '-o', 'json'))
            if doc.get('status',{}).get('availableReplicas') == 1:
                break
            time.sleep(3)
        else:
            raise TimeoutError(f'{name} did not become ready.')
    for name, selector, port, allowed in [
        ('mysite-ingress', {'app.kubernetes.io/name':'mysite'}, 8000, [{'podSelector':{'matchLabels':{'app.kubernetes.io/name':'kedrogy-web'}}}]),
        ('web-ingress', {'app.kubernetes.io/name':'kedrogy-web'}, 8080, [{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'app.kubernetes.io/name':'traefik'}}}]),
    ]:
        kubectl('apply','-f','-',document={'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':name},
            'spec':{'podSelector':{'matchLabels':selector},'policyTypes':['Ingress'],'ingress':[{'from':allowed,'ports':[{'protocol':'TCP','port':port}]}]}})
    backend=json.loads(kubectl('get','service/mysite-svc','-o','json'))
    web=json.loads(kubectl('get','service/kedrogy-web','-o','json'))
    pods=json.loads(kubectl('get','pods','-l','app.kubernetes.io/name=mysite','-o','json'))['items']
    ready=[p for p in pods if not p['metadata'].get('deletionTimestamp') and any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[]))]
    if len(ready)!=1:raise RuntimeError('Expected one healthy fixture backend.')
    targets=[(backend['spec']['clusterIP'],8000),(ready[0]['status']['podIP'],8000),(web['spec']['clusterIP'],8080)]
    code='''import json,socket,time
results=[]
time.sleep(10)
for host,port in TARGETS:
 try:
  connection=socket.create_connection((host,port),timeout=4)
 except OSError:
  results.append({'host':host,'port':port,'blocked':True})
 else:
  connection.close();results.append({'host':host,'port':port,'blocked':False})
print(json.dumps(results),flush=True)
raise SystemExit(0 if all(r['blocked'] for r in results) else 1)
'''.replace('TARGETS',repr(targets))
    name='network-check-'+uuid.uuid4().hex[:8]
    kubectl('create','-f','-',document={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name},'spec':{'backoffLimit':0,'activeDeadlineSeconds':90,
        'template':{'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[{'name':'probe','image':images['backend'],'command':['/app/.venv/bin/python','-c',code]}]}}}})
    kubectl('wait','--for=condition=complete',f'job/{name}','--timeout=60s')
    results=json.loads(kubectl('logs',f'job/{name}'))
    if not all(item['blocked'] for item in results):raise RuntimeError('Network policy enforcement failed.')
    (REPORT/'deployment-network.json').write_text(json.dumps({'namespace':NAMESPACE,'checks':results},indent=2)+'\n')
    print('Fixture images are ready; real network-denial checks passed.',flush=True)


if __name__ == '__main__':
    main()
