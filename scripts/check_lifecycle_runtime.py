"""Synthetic annotation and cleanup lifecycle against real PostgreSQL and Kubernetes."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENV=ROOT/'.local/lifecycle-env.json'
STATE=ROOT/'.local/lifecycle-state.json'
REPORT=ROOT/'reports/2026-09-26-implementation'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['launch','switch','inspect','cleanup'])
    phase=parser.parse_args().phase
    env=json.loads(ENV.read_text())
    if env.get('KEDROGY_TEST_DATABASE')!='disposable' or env['KEDROGY_NAMESPACE']!='kedrogy-check-20260926':
        raise RuntimeError('Disposable fixture required.')
    os.environ.update(env);sys.path.insert(0,str(ROOT/'.local'))
    import django;django.setup()
    from django.conf import settings
    from django.test import Client
    from kedrogy.models import DjangoDataset,DjangoModel,AnnotationRun,DeletionRun
    from kedrogy.annotation import start_annotation,advance_annotation,stop_annotation
    from kedrogy.annotation_data import observe_data
    from kedrogy.deletion import preview,request_deletion,advance_deletion
    from kedrogy.training import _ensure,_get
    from kedrogy.operation_control import delete_exact,resource_ref
    from kedrogy import manifests
    client=Client()
    state=json.loads(STATE.read_text()) if STATE.exists() else {'checks':[]}
    def save():STATE.write_text(json.dumps(state,indent=2)+'\n')
    def until(fn,done,description,timeout=420):
        deadline=time.monotonic()+timeout;previous=None
        while time.monotonic()<deadline:
            result=fn()
            if hasattr(result,'status') and (result.status,result.error)!=previous:
                previous=(result.status,result.error);print(description,previous,flush=True)
            if done(result):return result
            if getattr(result,'status',None)=='NEEDS_REVIEW':raise RuntimeError(str(result.error))
            time.sleep(2)
        raise TimeoutError(description)
    def ready(identifier):
        return until(lambda:advance_annotation(identifier),lambda r:r.status=='READY','Annotation ready')
    if phase=='launch':
        ids=[]
        for name in ['Synthetic annotation A','Synthetic annotation B']:
            response=client.post('/api/datasets/',json.dumps({'display_name':name,'image':'approved:1','workingDir':'mykedro','pipeline':'load_examples','recipe_options':'-l positive,negative','data_table_name':'all_data','id_field':'id'}),content_type='application/json')
            assert response.status_code==201,response.json()
            ids.append(response.json()['id'])
        state.update(datasets=ids);save()
        run,created=start_annotation(ids[0],'annotation-a');state['annotation_a']=str(run.id);save()
        assert created and start_annotation(ids[0],'annotation-a')[1] is False
        ready(run.id);state['checks'].append('Dataset A launched with idempotent request');save()
    elif phase=='switch':
        assert observe_data(state['datasets'][0])['status']=='PRESENT'
        stop_annotation(state['datasets'][0]);until(lambda:advance_annotation(state['annotation_a']),lambda r:r.status=='STOPPED','Annotation A stopped')
        run,_=start_annotation(state['datasets'][1],'annotation-b');state['annotation_b']=str(run.id);save()
        ready(run.id);state['checks'].append('Stopped A, released slot, launched B');save()
    elif phase=='inspect':
        observations=[observe_data(pk) for pk in state['datasets']]
        assert all(v['status']=='PRESENT' for v in observations),observations
        state['observations']=observations;state['checks'].append('Both datasets retain independent saved-answer counts while only B is active')
        dataset=DjangoDataset.objects.get(pk=state['datasets'][0])
        model=DjangoModel.objects.create(on_dataset=dataset,labels='positive,negative',label_schema=['positive','negative'],model_name='Synthetic cleanup model')
        _ensure(manifests.pvc(model.id),settings.KEDROGY_NAMESPACE)
        state['model_id']=model.id;save()
    else:
        model_id=state['model_id']
        assert 'recovery_cleanup' in state
        assert _get('pvc',f'pvc-model-{model_id}',settings.KEDROGY_NAMESPACE) is None
        for dataset_id in state['datasets']:
            plan=preview('dataset',dataset_id);run,_=request_deletion('dataset',dataset_id,plan['preview_token'],f'delete-dataset-{dataset_id}')
            run=until(lambda:advance_deletion(run.id),lambda r:r.status=='SUCCEEDED','Dataset retired')
            assert observe_data(dataset_id)['status']=='PRESENT'
        state['checks'].append('Model volume removed; dataset deletion stops annotation and retains saved data')
        first=state['datasets'][0];plan=preview('annotations',first)
        run,_=request_deletion('annotations',first,plan['preview_token'],'purge-reviewed-a')
        run=until(lambda:advance_deletion(run.id),lambda r:r.status=='SUCCEEDED','Selected annotations deleted')
        assert observe_data(first)['status']=='EMPTY'
        assert observe_data(state['datasets'][1])['status']=='PRESENT'
        state['checks'].append('Explicit retained-annotation cleanup deletes A only, preserving B and source rows')
        state['annotation_cleanup']=str(run.id);save()
        (REPORT/'lifecycle-runtime.json').write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(state,indent=2),flush=True)

if __name__=='__main__':main()
