"""Observe serving independently of queued startup tasks."""
import time
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections
from kedrogy.models import ServingRun
from kedrogy.serving import LIVE, advance_serving


class Command(BaseCommand):
    help = "Reconcile serving health once or continuously."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=float, default=settings.KEDROGY_SERVE_INTERVAL)

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise ValueError("Interval must be positive.")
        try:
            while True:
                try:
                    close_old_connections()
                    terminal = Q(resource_layout="run-owned-v2", status__in=("FAILED", "STOPPED")) & (
                        Q(cleanup_observed_at__isnull=True) | Q(cleanup_observed_at__lt=timezone.now() - timedelta(minutes=1)))
                    for identifier in list(ServingRun.objects.filter(Q(status__in=LIVE) | terminal)
                            .order_by("cleanup_observed_at", "created_at").values_list("id", flat=True)[:200]):
                        try:
                            run = advance_serving(identifier)
                        except ServingRun.DoesNotExist:
                            continue
                        except Exception:  # noqa: BLE001 -- isolate one failed observation and continue checking other revisions
                            self.stderr.write(f"Serving {identifier}: health could not be checked.")
                        else:
                            if not options["watch"]:
                                self.stdout.write(f"{identifier}: {run.status}")
                except DatabaseError:
                    close_old_connections()
                    self.stderr.write("Database unavailable; reconciliation will resume after reconnecting.")
                    if not options["watch"]:
                        raise
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Serving reconciler stopped.")
