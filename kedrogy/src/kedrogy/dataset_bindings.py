"""Read-only annotation access and explicit, stable dataset bindings."""

import json
import shlex
from contextlib import contextmanager

import psycopg
from django.conf import settings
from django.db import IntegrityError, transaction

from .kubernetes import OperationError
from .models import DjangoDataset


@contextmanager
def reader():
    """Use the separately configured reader role with bounded, read-only transactions."""
    config = settings.KEDROGY_READER_CONFIG
    if not all(config.get(key) for key in ("host", "dbname", "user", "password")):
        raise OperationError("ANNOTATION_READER_UNCONFIGURED", "The annotation reader connection is not configured.")
    try:
        with psycopg.connect(**config, connect_timeout=5, options="-c default_transaction_read_only=on -c statement_timeout=15000") as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            yield connection
    except psycopg.Error:
        raise OperationError("ANNOTATIONS_UNAVAILABLE", "The annotation database is unavailable or access was denied.") from None


def inventory() -> list[dict]:
    """Return identities and counts only, never annotation texts."""
    with reader() as connection:
        rows = connection.execute("SELECT d.id, d.name, count(l.example_id) FROM public.dataset d LEFT JOIN public.link l ON l.dataset_id=d.id WHERE d.session IS NOT TRUE GROUP BY d.id,d.name ORDER BY d.id").fetchall()
    return [{"id": row[0], "name": row[1], "examples": row[2]} for row in rows]


def read_bound_annotations(dataset: DjangoDataset) -> tuple[int, list[dict]]:
    if dataset.binding_state != "BOUND" or not dataset.prodigy_dataset_name or dataset.prodigy_dataset_id is None:
        raise OperationError("DATASET_UNRESOLVED", "Resolve the annotation dataset binding before training.")
    with reader() as connection:
        found = connection.execute("SELECT id FROM public.dataset WHERE name=%s AND session IS NOT TRUE", (dataset.prodigy_dataset_name,)).fetchall()
        if found != [(dataset.prodigy_dataset_id,)]:
            raise OperationError("DATASET_REPLACED", "The bound annotation dataset is missing or has been replaced. Review its binding.")
        rows = connection.execute("""SELECT e.content
            FROM public.link l JOIN public.example e ON e.id=l.example_id
            WHERE l.dataset_id=%s ORDER BY e.id LIMIT %s""",
            (dataset.prodigy_dataset_id, settings.KEDROGY_MAX_ANNOTATIONS + 1)).fetchall()
    if len(rows) > settings.KEDROGY_MAX_ANNOTATIONS:
        raise OperationError("INVALID_ANNOTATIONS", "This dataset exceeds the configured annotation limit.")
    try:
        values = [json.loads(bytes(row[0])) for row in rows]
    except (ValueError, TypeError):
        raise OperationError("INVALID_ANNOTATIONS", "Stored annotations contain invalid JSON or text encoding.") from None
    return dataset.prodigy_dataset_id, values


def verify_binding(dataset):
    """Validate identity without rescanning annotation content during health checks."""
    with reader() as connection:
        rows = connection.execute("SELECT id FROM public.dataset WHERE name=%s AND session IS NOT TRUE", (dataset.prodigy_dataset_name,)).fetchall()
    if rows != [(dataset.prodigy_dataset_id,)]:
        raise OperationError("DATASET_REPLACED", "The bound annotation dataset is missing or has been replaced. Review its binding.")


def bind_dataset(dataset_id: int, name: str, expected_id: int, *, allow_existing=False) -> None:
    """Bind only an explicitly selected, currently existing Prodigy identity."""
    matches = [row for row in inventory() if row["name"] == name and row["id"] == expected_id]
    if len(matches) != 1:
        raise OperationError("DATASET_UNRESOLVED", "The selected annotation identity was not found.")
    with transaction.atomic():
        dataset = DjangoDataset.objects.select_for_update().get(pk=dataset_id)
        if dataset.binding_state == "BOUND" and (dataset.prodigy_dataset_name != name or dataset.prodigy_dataset_id != expected_id):
            raise OperationError("DATASET_CONFLICT", "An established dataset binding cannot be reassigned.")
        if not allow_existing and dataset.prodigy_dataset_name != name:
            raise OperationError("DATASET_CONFLICT", "The observed dataset does not match the reserved annotation key.")
        if DjangoDataset.objects.exclude(pk=dataset_id).filter(prodigy_dataset_name=name).exists():
            raise OperationError("DATASET_CONFLICT", "Another application dataset already owns this annotation key.")
        if dataset.djangomodel_set.filter(training_runs__status__in=("QUEUED", "RUNNING", "VERIFYING")).exists():
            raise OperationError("DATASET_CONFLICT", "Wait for active training before establishing this binding.")
        try:
            args = shlex.split(dataset.recipe_options)
        except ValueError:
            args = []
        if len(args) == 5 and args[0] == "myrecipes.textcat.custom-model" and args[1] == name and args[2] == "./data/00_examples/examples.jsonl" and args[3] in ("-l", "--label"):
            dataset.recipe_options = "-l " + shlex.quote(args[4])
        dataset.prodigy_dataset_name = name
        dataset.prodigy_dataset_id = expected_id
        dataset.binding_state = "BOUND"
        dataset.annotation_refresh_requested = True
        try:
            with transaction.atomic():
                dataset.save(update_fields=["prodigy_dataset_name", "prodigy_dataset_id", "binding_state", "recipe_options", "annotation_refresh_requested"])
        except IntegrityError:
            raise OperationError("DATASET_CONFLICT", "Another application dataset already owns this annotation key.") from None


def record_created_binding(dataset: DjangoDataset):
    matches = [row for row in inventory() if row["name"] == dataset.prodigy_dataset_name]
    if len(matches) != 1:
        raise OperationError("DATASET_UNRESOLVED", "The annotation service did not create the reserved dataset.")
    bind_dataset(dataset.pk, matches[0]["name"], matches[0]["id"])
