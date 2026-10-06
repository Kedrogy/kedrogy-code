"""Real isolated P1 workflow and deterministic delayed-worker acceptance."""

import argparse
import copy
import json
import os
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/p1-tests'
REPORT = ROOT / 'reports/2026-09-26-p1-implementation'
NAMESPACE = 'kedrogy-p1-20260926'


def until(function, predicate, description, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = function()
        if predicate(value):
            print(description, flush=True)
            return value
        time.sleep(2)
    raise TimeoutError(description)


def initialize():
    env = json.loads((PRIVATE / 'runtime-env.json').read_text())
    if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env.get('KEDROGY_NAMESPACE') != NAMESPACE or env.get('PGDATABASE') != 'p1_runtime':
        raise RuntimeError('Only the isolated P1 fixture is permitted.')
    os.environ.update(env)
    sys.path.insert(0, str(PRIVATE))
    import django
    django.setup()


def annotation_stage():
    from django.test import Client
    from kedrogy.models import DjangoDataset, DjangoModel
    from kedrogy.annotation import start_annotation, advance_annotation
    from kedrogy.launch_config import validate_dataset
    from kedrogy.training import _ensure, _get, _conditions
    from kedrogy import manifests

    path = PRIVATE / 'workflow.json'
    if path.exists():
        raise RuntimeError('The fixture workflow already exists. Resume its existing stage.')
    client = Client()
    response = client.post('/api/datasets/', json.dumps({'display_name': 'Synthetic P1 acceptance', 'image': 'approved:1',
        'workingDir': 'mykedro', 'pipeline': 'load_examples', 'recipe_options': '-l positive,negative',
        'data_table_name': 'managed_reviews', 'id_field': 'id'}), content_type='application/json')
    if response.status_code != 201:
        raise RuntimeError(response.json())
    dataset = DjangoDataset.objects.get(pk=response.json()['id'])
    model = DjangoModel.objects.create(on_dataset=dataset, model_name='Synthetic P1 classifier',
                                      labels='positive,negative', label_schema=['positive', 'negative'], a_preprocess_fun='')
    cfg = validate_dataset(dataset.to_dict())
    _ensure(manifests.pvc(model.id), NAMESPACE)
    fixture = manifests.verification(cfg, model.id, name='p1-tiny-base', run_id=str(uuid.uuid4()), attempt_id=str(uuid.uuid4()),
        path='tiny-base', labels=['positive', 'negative'], artifact_version=2)
    container = fixture['spec']['template']['spec']['containers'][0]
    container['volumeMounts'][0]['readOnly'] = False
    container['args'] = ['-c', """from pathlib import Path
from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
p=Path('data/06_models/tiny-base'); p.mkdir(parents=True,exist_ok=True)
v=['[PAD]','[UNK]','[CLS]','[SEP]','[MASK]','a','good','bad','synthetic','product','.']
(p/'vocab.txt').write_text('\\n'.join(v))
t=BertTokenizerFast(vocab_file=str(p/'vocab.txt')); t.save_pretrained(p)
m={0:'positive',1:'negative'}
BertForSequenceClassification(BertConfig(vocab_size=len(v),hidden_size=16,num_hidden_layers=1,num_attention_heads=2,intermediate_size=32,id2label=m,label2id={v:k for k,v in m.items()})).save_pretrained(p)
"""]
    _ensure(fixture, NAMESPACE)
    session, _ = start_annotation(dataset.id, 'p1-annotation')
    state = {'dataset_id': dataset.id, 'model_id': model.id, 'annotation_id': str(session.id), 'namespace': NAMESPACE}
    path.write_text(json.dumps(state))
    def observe():
        run = advance_annotation(session.id)
        if run.startup_status == 'FAILED':
            raise RuntimeError(run.startup_error)
        return run
    until(observe, lambda r: r.status == 'READY', 'Annotation is ready for browser acceptance.')
    until(lambda: _get('Job', 'p1-tiny-base', NAMESPACE), lambda j: 'Complete' in _conditions(j), 'Tiny base checkpoint is ready.')
    (REPORT / 'workflow.json').write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps({'service': f'annotation-{session.id}', 'browser_port': 18881}), flush=True)


def training_stage():
    from django.conf import settings
    from django.test import Client
    from django.utils import timezone
    from kedrogy import serving_resources as resources
    from kedrogy.annotation import stop_annotation, advance_annotation
    from kedrogy.dataset_bindings import read_bound_annotations
    from kedrogy.models import DjangoDataset, DjangoModel, ServingRun
    from kedrogy.prediction import predict
    from kedrogy.serving import start_serving, stop_serving, advance_serving, _advance
    from kedrogy.training import start_training, advance_run, ACTIVE
    from kedrogy.training_preflight import preflight
    from kedrogy.kubernetes import command

    state = json.loads((PRIVATE / 'workflow.json').read_text())
    dataset = DjangoDataset.objects.get(pk=state['dataset_id'])
    model = DjangoModel.objects.select_related('on_dataset').get(pk=state['model_id'])
    summary = preflight(model)
    if summary['usable'] < 4:
        raise AssertionError('Complete balanced browser annotations before training.')
    print(json.dumps({'preflight': summary}), flush=True)
    session = stop_annotation(dataset.id)
    if session is not None:
        until(lambda: advance_annotation(session.id), lambda r: r.status == 'STOPPED', 'Annotation stopped after saved browser answers.')
    training, _ = start_training(model.id, 'p1-real-training-' + settings.KEDROGY_ML_IMAGE.split(':')[-1][:12])
    trained = until(lambda: advance_run(training.id), lambda r: r.status not in ACTIVE, 'Training finished.', 900)
    if trained.status != 'SUCCEEDED' or trained.artifact.get('version') != 2:
        raise AssertionError(f'Training failed: {trained.error}')
    first, _ = start_serving(model.id, 'p1-ready')
    first = until(lambda: advance_serving(first.id), lambda r: r.status == 'READY', 'The new model is ready through its per-run Service.')
    prediction = predict(model.id, 'A good synthetic product.')
    if prediction['label'] not in ['positive', 'negative'] or prediction.get('class_schema_version') != 2:
        raise AssertionError('Prediction mapping differs from explicit annotation classes.')
    stop_serving(model.id)
    until(lambda: advance_serving(first.id), lambda r: r.status == 'STOPPED', 'First serving run stopped.')

    # A real create call is held at the last external boundary, then resumed after Stop/new READY.
    old, _ = start_serving(model.id, 'p1-delayed')
    owner = uuid.uuid4()
    ServingRun.objects.filter(pk=old.id).update(lease_owner=owner, lease_epoch=1, lease_until=timezone.now() + timedelta(minutes=5))
    old.refresh_from_db()
    real_command = resources.command
    newer = []
    trace = []
    def delayed(args, **kwargs):
        if args[0] == 'create' and kwargs['document']['kind'] == 'Deployment' and not newer:
            trace.append('old-create-paused')
            ServingRun.objects.filter(pk=old.id).update(lease_until=timezone.now() - timedelta(seconds=1))
            stop_serving(model.id)
            until(lambda: advance_serving(old.id), lambda r: r.status == 'STOPPED', 'Stopped the delayed old run.')
            run, _ = start_serving(model.id, 'p1-replacement')
            newer.append(run)
            newer[0] = until(lambda: advance_serving(run.id), lambda r: r.status == 'READY', 'Replacement is READY before old create resumes.')
            trace.append('new-ready')
        return real_command(args, **kwargs)
    with patch('kedrogy.serving_resources.command', side_effect=delayed):
        _advance(old, owner)
    trace.append('old-create-resumed')
    replacement = ServingRun.objects.get(pk=newer[0].id)
    before = [(r['kind'], r['name'], r['uid']) for r in replacement.resource_plan['resources']]
    until(lambda: advance_serving(old.id), lambda r: r.cleanup_observed_at is not None and not resources.inventory(r),
          'Late old resources collected without changing the replacement.')
    after = ServingRun.objects.get(pk=replacement.id)
    if before != [(r['kind'], r['name'], r['uid']) for r in after.resource_plan['resources']]:
        raise AssertionError('A delayed worker changed the newer resources.')
    result = predict(model.id, 'A bad synthetic product.')
    if result['serving_run_id'] != str(replacement.id):
        raise AssertionError('Prediction used a stale serving version.')
    stop_serving(model.id)
    until(lambda: advance_serving(replacement.id), lambda r: r.status == 'STOPPED', 'Replacement stopped cleanly.')

    conflicts = []
    for kind in ['ConfigMap', 'Deployment', 'Service']:
        run, _ = start_serving(model.id, 'p1-foreign-' + kind.lower())
        ref = next(r for r in [run.resource_plan['anchor'], *run.resource_plan['resources']] if r['kind'] == kind)
        foreign = copy.deepcopy(ref['document'])
        foreign['metadata']['labels'] = {'fixture-owner': 'unrelated'}
        foreign['metadata'].pop('annotations', None)
        if kind == 'ConfigMap':
            foreign['data'] = {'sentinel': 'unrelated'}
        if kind == 'Deployment':
            foreign['spec']['replicas'] = 0
        created = command(['create', '-f', '-', '-o', 'json'], namespace=NAMESPACE, document=foreign, json_output=True)
        observed = advance_serving(run.id)
        remaining = resources._get(kind, ref['name'], NAMESPACE)
        if observed.error.get('code') != 'SERVING_IDENTITY_MISMATCH' or created['metadata']['uid'] != remaining['metadata']['uid']:
            raise AssertionError('Foreign resource ownership was not rejected.')
        if created.get('spec') != remaining.get('spec') or created.get('data') != remaining.get('data'):
            raise AssertionError('Foreign resource contents changed.')
        conflicts.append({'kind': kind, 'uid': created['metadata']['uid'], 'preserved': True})
        ServingRun.objects.filter(pk=run.id).update(status='FAILED')
    report = state | {'preflight': summary, 'training_run': str(trained.id), 'artifact': trained.artifact,
        'first_prediction': prediction, 'replacement_prediction': result, 'replacement_resources': before,
        'race_trace': trace, 'foreign_resources': conflicts, 'namespace_cleanup_pending': True}
    (REPORT / 'runtime-acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print('P1 real Kubernetes, PostgreSQL and training/inference acceptance passed.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['annotation', 'training'])
    args = parser.parse_args()
    initialize()
    annotation_stage() if args.stage == 'annotation' else training_stage()
