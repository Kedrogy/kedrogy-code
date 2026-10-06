"""Check the additive lifecycle migration and rollback on synthetic records."""
import json
import os
from pathlib import Path

env = json.loads(Path('.local/lifecycle-env.json').read_text())
if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env['PGDATABASE'] != 'lifecycle':
    raise RuntimeError('Disposable fixture required.')
os.environ.update(env)
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
old = [('kedrogy','0013_normalize_legacy_drafts')]
new = [('kedrogy','0014_durable_annotation_cleanup')]
executor = MigrationExecutor(connection); executor.migrate(old)
apps = executor.loader.project_state(old).apps
Dataset, Model = apps.get_model('kedrogy','DjangoDataset'), apps.get_model('kedrogy','DjangoModel')
dataset = Dataset.objects.create(dataset_name='Migration fixture', binding_state='UNRESOLVED', prodigy_dataset_name=None)
model = Model.objects.create(on_dataset=dataset, labels='P, N', label_schema=['P','N'])
for target in [new, old, new]:
    executor = MigrationExecutor(connection); executor.migrate(target)
    state = executor.loader.project_state(target).apps
    found = state.get_model('kedrogy','DjangoModel').objects.get(pk=model.pk)
    assert found.labels == 'P, N' and found.on_dataset_id == dataset.pk
    if target == new:
        assert not state.get_model('kedrogy','AnnotationRun').objects.exists()
        assert not state.get_model('kedrogy','DeletionRun').objects.exists()
        assert state.get_model('kedrogy','DjangoDataset').objects.get(pk=dataset.pk).annotation_data == {}
executor = MigrationExecutor(connection); executor.migrate(executor.loader.graph.leaf_nodes())
from kedrogy.models import DjangoDataset, DjangoModel
DjangoModel.objects.get(pk=model.pk).delete(); DjangoDataset.objects.get(pk=dataset.pk).delete()
print('Populated forward migration, rollback, conservative unknown state, and preserved class strings passed.')
