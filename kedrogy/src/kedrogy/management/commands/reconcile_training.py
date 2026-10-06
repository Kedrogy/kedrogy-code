"""Recover training runs independently of queue-worker availability."""

import time

from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections
from kedrogy.models import TrainingRun
from kedrogy.training import ACTIVE, advance_run


class Command(BaseCommand):
    help = 'Reconcile active training runs once or continuously.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--interval', type=float, default=10)

    def handle(self, *args, **options):
        if options['interval'] <= 0:
            raise ValueError('Interval must be positive.')
        try:
            while True:
                try:
                    close_old_connections()
                    identifiers = list(TrainingRun.objects.filter(status__in=ACTIVE).values_list('id', flat=True))
                    for identifier in identifiers:
                        try:
                            run = advance_run(identifier)
                        except TrainingRun.DoesNotExist:
                            continue
                        except Exception:  # noqa: BLE001 -- isolate a failed run; its terminal state is persisted
                            # The reconciler persists a safe failure; one broken run must not stop others.
                            self.stderr.write(f'Run {identifier}: reconciliation failed; inspect its status.')
                        else:
                            if not options['watch']:
                                self.stdout.write(f'{identifier}: {run.status}')
                except DatabaseError:
                    close_old_connections()
                    self.stderr.write("Database unavailable; reconciliation will resume after reconnecting.")
                    if not options["watch"]:
                        raise
                if not options['watch']:
                    return
                time.sleep(options['interval'])
        except KeyboardInterrupt:
            self.stdout.write('Reconciler stopped.')
