"""Recover annotation and deletion independently of queue delivery."""

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections
from django.db.models import Q
from django.utils import timezone
from kedrogy.annotation import LIVE, advance_annotation
from kedrogy.annotation_data import observe_many
from kedrogy.deletion import advance_deletion
from kedrogy.models import AnnotationRun, DeletionRun, DjangoDataset


class Command(BaseCommand):
    help = "Reconcile annotation/deletion operations and refresh bounded annotation observations."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=10)

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise ValueError("Interval must be positive.")
        try:
            while True:
                try:
                    close_old_connections()
                    groups = [(AnnotationRun.objects.filter(status__in=LIVE), advance_annotation),
                              (DeletionRun.objects.filter(status__in=["QUEUED", "RUNNING", "RETRY_WAIT"]), advance_deletion)]
                    for rows, advance in groups:
                        for identifier in rows.values_list("id", flat=True)[:50]:
                            try:
                                run = advance(identifier)
                                if not options["watch"]:
                                    self.stdout.write(f"{run.id}: {run.status}")
                            except DatabaseError:
                                raise
                            except Exception:  # noqa: BLE001 -- isolate an operation; retain its reservation for recovery
                                self.stderr.write(f"Operation {identifier}: observation failed; its reservation is retained.")
                    due = DjangoDataset.objects.filter(deletion_pending=False).filter(
                        Q(annotation_refresh_requested=True) | Q(annotation_observed_at__isnull=True)
                        | Q(annotation_observed_at__lt=timezone.now()-timedelta(seconds=240)))
                    observe_many(list(due.order_by("annotation_observed_at").values_list("id", flat=True)[:5]))
                except DatabaseError:
                    close_old_connections()
                    self.stderr.write("Database unavailable; observations will resume after reconnecting.")
                    if not options["watch"]:
                        raise
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Operation reconciler stopped.")
