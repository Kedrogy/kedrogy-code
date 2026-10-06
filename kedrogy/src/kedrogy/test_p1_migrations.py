"""Preserve historical semantics when expanding the serving and annotation schema."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class P1MigrationTests(TransactionTestCase):
    def test_populated_legacy_rows_keep_their_meaning(self):
        old = [('kedrogy', '0014_durable_annotation_cleanup')]
        latest = [('kedrogy', '0017_legacy_cleanup_review')]
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        try:
            apps = executor.loader.project_state(old).apps
            Dataset = apps.get_model('kedrogy', 'DjangoDataset')
            Model = apps.get_model('kedrogy', 'DjangoModel')
            Training = apps.get_model('kedrogy', 'TrainingRun')
            Serving = apps.get_model('kedrogy', 'ServingRun')
            dataset = Dataset.objects.create(dataset_name='Historical', binding_state='BOUND', prodigy_dataset_id=7)
            model = Model.objects.create(on_dataset=dataset)
            training = Training.objects.create(model=model, idempotency_key='legacy', job_name='legacy-test', namespace='old')
            serving = Serving.objects.create(model=model, training_run=training, idempotency_key='legacy', namespace='old', deployment_uid='original-uid')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            current = apps.get_model('kedrogy', 'ServingRun').objects.get(pk=serving.pk)
            preserved = apps.get_model('kedrogy', 'DjangoDataset').objects.get(pk=dataset.pk)
            self.assertEqual(current.resource_layout, 'legacy-fixed-v1')
            self.assertEqual(current.resource_plan, {})
            self.assertEqual(current.deployment_uid, 'original-uid')
            self.assertEqual(preserved.annotation_policy, 'reject-other-v1')
            self.assertEqual(preserved.prodigy_dataset_id, 7)
            # Reverse the additive schema before creating any new-format data.
            MigrationExecutor(connection).migrate(old)
            MigrationExecutor(connection).migrate(latest)
            restored = apps.get_model('kedrogy', 'ServingRun').objects.get(pk=serving.pk)
            self.assertEqual(restored.deployment_uid, 'original-uid')
            fresh = apps.get_model('kedrogy', 'DjangoDataset').objects.create(dataset_name='New')
            self.assertEqual(fresh.annotation_policy, 'single-label-choice-v2')
        finally:
            MigrationExecutor(connection).migrate(latest)
