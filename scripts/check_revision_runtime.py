"""Run a real synthetic training and serving lifecycle in an isolated namespace."""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = json.loads((ROOT / '.local/revisions-env.json').read_text())
    if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env.get('KEDROGY_NAMESPACE') != 'kedrogy-check-20260925':
        raise RuntimeError('Only the isolated revision fixture is allowed.')
    os.environ.update(env)
    import django
    django.setup()
    from datetime import timedelta

    from django.conf import settings
    from django.test import Client
    from django.utils import timezone
    from kedrogy.launch_config import validate_dataset
    from kedrogy.models import DjangoDataset, DjangoModel, ServingRun
    from kedrogy.serving import advance_serving, startup_result
    from kedrogy.training import ACTIVE, _conditions, _ensure, _get, advance_run

    from kedrogy import manifests
    settings.KEDROGY_ML_IMAGE = env['KEDROGY_ML_IMAGE']
    settings.KEDROGY_ML_IMAGE_ALIASES = {'approved:1', env['KEDROGY_ML_IMAGE']}
    settings.KEDROGY_NAMESPACE = env['KEDROGY_NAMESPACE']
    settings.KEDROGY_TRAIN_OPTIONS = {'base_model': 'data/06_models/tiny-base', 'max_steps': 1}
    settings.KEDROGY_TRAIN_TIMEOUT = 300
    client = Client()
    response = client.post('/api/datasets/', json.dumps({'display_name': 'Synthetic revision lifecycle',
        'image': 'approved:1', 'workingDir': 'mykedro', 'pipeline': 'load_examples', 'recipe_options': '-l positive,negative',
        'data_table_name': 'all_data', 'id_field': 'id'}), content_type='application/json')
    if response.status_code != 201:
        raise RuntimeError(f'Dataset API failed: {response.status_code} {response.json()}')
    dataset = DjangoDataset.objects.get(pk=response.json()['id'])
    from kedrogy.dataset_bindings import bind_dataset
    bind_dataset(dataset.pk, 'revision-fixture', 1, allow_existing=True)
    dataset.refresh_from_db()
    response = client.post('/api/models/', json.dumps({'on_dataset': dataset.pk, 'labels': ['positive', 'negative'], 'a_preprocess_fun': ''}), content_type='application/json')
    if response.status_code != 201:
        raise RuntimeError(f'Model API failed: {response.status_code}')
    model = DjangoModel.objects.get(pk=response.json()['id'])
    cfg = validate_dataset(dataset.to_dict())
    _ensure(manifests.pvc(model.pk), settings.KEDROGY_NAMESPACE)
    code = '''from pathlib import Path
from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
p=Path('data/06_models/tiny-base');p.mkdir(parents=True,exist_ok=True)
v=['[PAD]','[UNK]','[CLS]','[SEP]','[MASK]','good','bad','product','.']
(p/'vocab.txt').write_text('\\n'.join(v))
t=BertTokenizerFast(vocab_file=str(p/'vocab.txt'));t.save_pretrained(p)
m={0:'OTHER',1:'positive',2:'negative'}
BertForSequenceClassification(BertConfig(vocab_size=len(v),hidden_size=16,num_hidden_layers=1,num_attention_heads=2,intermediate_size=32,id2label=m,label2id={v:k for k,v in m.items()})).save_pretrained(p)
'''
    fixture = manifests.verification(cfg, model.pk, name=f'fixture-{uuid.uuid4()}', run_id=str(uuid.uuid4()), attempt_id=str(uuid.uuid4()), path='tiny-base', labels=['positive','negative'])
    container = fixture['spec']['template']['spec']['containers'][0]
    container['args'] = ['-c', code]
    container['volumeMounts'][0]['readOnly'] = False
    _ensure(fixture, settings.KEDROGY_NAMESPACE)

    def until(function, predicate, description, timeout=400):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = function()
            if predicate(value):
                print(description, flush=True)
                return value
            time.sleep(2)
        raise TimeoutError(description)

    def fixture_complete():
        value = _get('job', fixture['metadata']['name'], settings.KEDROGY_NAMESPACE)
        if 'Failed' in _conditions(value):
            raise RuntimeError('Tiny fixture failed.')
        return value
    until(fixture_complete, lambda item: 'Complete' in _conditions(item), 'Tiny checkpoint prepared.')

    def train(key):
        response = client.post(f'/api/models/{model.pk}/train/', HTTP_IDEMPOTENCY_KEY=key)
        if response.status_code != 202:
            raise RuntimeError(f'Train request failed: {response.status_code} {response.json()}')
        identifier = response.json()['result_id']
        repeated = client.post(f'/api/models/{model.pk}/train/', HTTP_IDEMPOTENCY_KEY=key)
        if repeated.status_code != 200 or repeated.json()['result_id'] != identifier:
            raise AssertionError('Train replay created another run.')
        run = until(lambda: advance_run(identifier), lambda value: value.status not in ACTIVE, 'Training reached a terminal state.', 650)
        if run.status != 'SUCCEEDED':
            raise RuntimeError(f'Training failed: {run.error}')
        return run

    first = train('first-real-run')
    renamed = client.patch(f'/api/datasets/{dataset.pk}/', json.dumps({'display_name': 'Renamed during lifecycle'}), content_type='application/json')
    if renamed.status_code != 200 or renamed.json()['prodigy_dataset_name'] != 'revision-fixture':
        raise AssertionError('Rename changed the binding.')
    client.patch(f'/api/models/{model.pk}/', json.dumps({'labels': ['negative', 'positive']}), content_type='application/json')
    second = train('second-real-run')
    if first.job_uid == second.job_uid or first.artifact['path'] == second.artifact['path'] or first.snapshot['labels'] == second.snapshot['labels']:
        raise AssertionError('Independent retraining did not preserve separate versions.')
    response = client.post(f'/api/models/{model.pk}/serve/', HTTP_IDEMPOTENCY_KEY='real-serve')
    if response.status_code != 202:
        raise RuntimeError(f'Serve failed: {response.status_code} {response.json()}')
    serving_id = response.json()['result_id']
    repeated = client.post(f'/api/models/{model.pk}/serve/', HTTP_IDEMPOTENCY_KEY='real-serve')
    if repeated.status_code != 200 or repeated.json()['result_id'] != serving_id:
        raise AssertionError('Serve replay created another revision.')
    def observe():
        run = advance_serving(serving_id)
        if run.status == 'FAILED':
            raise RuntimeError(f'Serving failed: {run.error}')
        return run
    serving = until(observe, lambda value: value.status == 'READY', 'Serving is ready through its Service.')
    client.patch(f'/api/models/{model.pk}/', json.dumps({'labels': ['future', 'draft']}), content_type='application/json')
    predicted = client.post(f'/api/models/{model.pk}/predict/', {'text_input': 'good product'})
    if predicted.status_code != 200 or predicted.json()['training_run_id'] != str(second.id) or predicted.json()['label'] not in ['OTHER','negative','positive']:
        raise AssertionError(f'Checked Django prediction failed: {predicted.status_code} {predicted.json()}')
    ServingRun.objects.filter(pk=serving.id).update(observed_at=timezone.now()-timedelta(minutes=2))
    stale = client.post(f'/api/models/{model.pk}/predict/', {'text_input': 'good product'})
    if stale.status_code != 503 or startup_result(ServingRun.objects.get(pk=serving.pk))['status'] != 'SUCCEEDED':
        raise AssertionError('Stale health changed startup history or permitted inference.')
    observe()
    subprocess.run(['kubectl', '--kubeconfig', str(Path.home()/'.kube/config'), '-n', settings.KEDROGY_NAMESPACE,
                    'delete', 'pod', '-l', f'kedrogy/serving-id={serving_id}', '--wait=false'], check=True)
    until(observe, lambda value: value.status == 'UNAVAILABLE', 'Pod removal makes serving unavailable.')
    until(observe, lambda value: value.status == 'READY', 'Replacement Pod recovered the same serving revision.')
    subprocess.run(['kubectl', '--kubeconfig', str(Path.home()/'.kube/config'), '-n', settings.KEDROGY_NAMESPACE,
                    'scale', f'deployment/serve-{model.pk}', '--replicas=0'], check=True)
    unavailable = observe()
    if unavailable.status != 'UNAVAILABLE':
        raise AssertionError('External deployment change was not rejected.')
    stopped = client.post(f'/api/models/{model.pk}/stop/')
    if stopped.status_code != 202:
        raise AssertionError('Stop request failed.')
    until(lambda: advance_serving(serving_id), lambda value: value.status == 'STOPPED', 'Serving stopped without resurrection.')
    # A deliberate new serving request starts a separate revision after Stop.
    response = client.post(f'/api/models/{model.pk}/serve/', HTTP_IDEMPOTENCY_KEY='restart-after-stop')
    serving_id = response.json()['result_id']
    serving = until(observe, lambda value: value.status == 'READY', 'Serving restart is ready for browser acceptance.')
    report = {'namespace': settings.KEDROGY_NAMESPACE, 'dataset_id': dataset.pk, 'model_id': model.pk,
        'runs': [{'id': str(run.id), 'job_uid': run.job_uid, 'artifact_path': run.artifact['path'], 'labels': run.snapshot['labels']} for run in [first,second]],
        'serving_id': str(serving.id), 'prediction': predicted.json(), 'checks': ['real tiny BERT training twice', 'annotation preflight',
        'idempotent Train and Serve', 'rename preserves binding', 'distinct training classes and artifacts', 'draft edit cannot relabel inference',
        'fresh readiness required', 'replacement Pod recovery', 'external deployment change invalidates health', 'Stop followed by explicit restart']}
    directory = ROOT / 'reports/2026-09-25-implementation'
    directory.mkdir(exist_ok=True)
    (directory / 'revision-runtime.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
