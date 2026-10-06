"""Inspect old model volumes before explicitly importing verified artifacts."""

import json
import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from kedrogy.kubernetes import OperationError, command
from kedrogy.launch_config import LaunchConfig, parse_labels
from kedrogy.models import DjangoModel, TrainingRun
from kedrogy.training import (
    ACTIVE,
    _conditions,
    _ensure,
    _get,
    _pods,
    _winner,
    validate_receipt,
)

from kedrogy import manifests


class Command(BaseCommand):
    help = 'Verify legacy best/ checkpoints read-only; --apply imports only verified results.'

    def add_arguments(self, parser):
        parser.add_argument('--model', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        model = DjangoModel.objects.select_related('on_dataset').get(pk=options['model'])
        if model.training_runs.filter(status__in=ACTIVE).exists():
            raise OperationError('TRAINING_ACTIVE', 'Wait for training before checking legacy artifacts.')
        identifier = uuid.uuid4()
        labels = list(parse_labels(model.labels))
        cfg = LaunchConfig(image=settings.KEDROGY_ML_IMAGE, working_dir='/app/mykedro',
                           pipeline='load_examples', dataset_name=model.on_dataset.dataset_name,
                           table_name='all_data', id_field='id', recipe_args=())
        run = TrainingRun(id=identifier, model=model, idempotency_key=f'legacy-{identifier}',
                          status='SUCCEEDED', namespace=settings.KEDROGY_NAMESPACE,
                          job_name=f'legacy-{identifier}', snapshot={
                              'dataset': model.on_dataset.to_dict(), 'labels': labels,
                              'image': cfg.image, 'options': {}, 'legacy': True})
        artifact = None
        state = 'INVALID'
        created = False
        try:
            if _get('pvc', f'pvc-model-{model.id}', run.namespace) is None:
                state = 'MISSING'
            else:
                document = manifests.verification(cfg, model.id, name=run.job_name, run_id=str(identifier),
                    attempt_id='legacy', path='best', labels=labels, legacy=True)
                job = _ensure(document, run.namespace)
                created = True
                deadline = time.monotonic() + 330
                while time.monotonic() < deadline:
                    if 'Failed' in _conditions(job):
                        break
                    if 'Complete' in _conditions(job):
                        winner = _winner(_pods(job, run.namespace), 'verify')
                        if winner:
                            artifact = validate_receipt(winner[1].get('message', ''), run, 'legacy', legacy=True)
                            state = 'VERIFIED'
                        break
                    time.sleep(2)
                    job = _get('job', run.job_name, run.namespace)
                    if job is None:
                        raise OperationError('JOB_LOST', 'The verification Job disappeared.')
                else:
                    raise OperationError('VERIFICATION_TIMEOUT', 'Legacy verification timed out; its state remains unverified.')
            if options['apply']:
                with transaction.atomic():
                    current = DjangoModel.objects.select_for_update().get(pk=model.pk)
                    if current.training_runs.filter(status__in=ACTIVE).exists():
                        raise OperationError('TRAINING_ACTIVE', 'A new training run started during verification.')
                    if current.published_run_id:
                        raise OperationError('ALREADY_PUBLISHED', 'A verified version already exists; legacy import would replace it.')
                    if artifact:
                        run.artifact = artifact
                        run.finished_at = timezone.now()
                        run.public_logs = 'Legacy checkpoint verified and imported.'
                        run.save()
                        current.published_run = run
                    current.artifact_status = state
                    current.trained = artifact is not None
                    current.save(update_fields=['published_run', 'artifact_status', 'trained'])
            self.stdout.write(json.dumps({'model_id': model.id, 'artifact_status': state,
                                          'applied': options['apply'], 'verified_files': len(artifact['files']) if artifact else 0}))
        finally:
            if created:
                command(['delete', 'job', run.job_name, '--ignore-not-found', '--wait=false'], namespace=run.namespace)
