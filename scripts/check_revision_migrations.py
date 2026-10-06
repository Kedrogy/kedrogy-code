"""Exercise historical-data migration and rollback using only disposable records."""

import json
import os
from pathlib import Path


def main():
    env = json.loads(Path('.local/revisions-env.json').read_text())
    if env.get('KEDROGY_TEST_DATABASE') != 'disposable' or env.get('PGDATABASE') != 'revisions':
        raise RuntimeError('Only the disposable revision database is allowed.')
    os.environ.update(env)
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    old = [('kedrogy', '0010_djangomodel_artifact_status_trainingrun_and_more')]
    new = [('kedrogy', '0013_normalize_legacy_drafts')]
    executor.migrate(old)
    apps = executor.loader.project_state(old).apps
    Dataset, Model = apps.get_model('kedrogy', 'DjangoDataset'), apps.get_model('kedrogy', 'DjangoModel')
    Model.objects.all().delete()
    Dataset.objects.all().delete()
    first = Dataset.objects.create(dataset_name='Repeated title')
    second = Dataset.objects.create(dataset_name='Repeated title')
    Model.objects.create(on_dataset=first, labels=' POS, NEG ', served=True)
    Model.objects.create(on_dataset=second, labels='P, P', served=True)
    executor = MigrationExecutor(connection)
    executor.migrate(new)
    apps = executor.loader.project_state(new).apps
    Dataset, Model = apps.get_model('kedrogy', 'DjangoDataset'), apps.get_model('kedrogy', 'DjangoModel')
    if list(Dataset.objects.values_list('binding_state', 'prodigy_dataset_name')) != [('UNRESOLVED', None), ('UNRESOLVED', None)]:
        raise AssertionError('Historical bindings were guessed.')
    if list(Model.objects.order_by('id').values_list('label_schema', flat=True)) != [['POS', 'NEG'], None]:
        raise AssertionError('Legacy class normalization changed semantics.')
    if Model.objects.filter(served=True).exists():
        raise AssertionError('Legacy serving flags remained trusted.')
    executor = MigrationExecutor(connection)
    executor.migrate(old)
    apps = executor.loader.project_state(old).apps
    if list(apps.get_model('kedrogy', 'DjangoModel').objects.order_by('id').values_list('labels', flat=True)) != [' POS, NEG ', 'P, P']:
        raise AssertionError('Rollback lost original class strings.')
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    from kedrogy.models import DjangoDataset
    DjangoDataset.objects.all().delete()
    print('PostgreSQL forward migration, rollback, preserved legacy values, and unresolved bindings passed.')


if __name__ == '__main__':
    main()
