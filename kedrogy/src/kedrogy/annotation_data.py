"""Cached, bounded annotation observations, independent of annotation sessions."""

import json
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .dataset_bindings import read_bound_annotations, reader
from .kubernetes import OperationError
from .models import DjangoDataset


def public_data(dataset):
    value = dataset.annotation_data or {"status": "UNKNOWN", "counts": None, "error": None}
    observed = dataset.annotation_observed_at
    if observed is None or timezone.now() - observed > timedelta(seconds=settings.KEDROGY_ANNOTATION_DATA_FRESHNESS):
        value = value | {"status": "UNKNOWN", "error": {"code": "OBSERVATION_STALE", "message": "Refresh the annotation data observation."}}
    return value | {"observed_at": observed.isoformat() if observed else None,
                    "refresh_requested": dataset.annotation_refresh_requested}


def observe_data(identifier):
    dataset = DjangoDataset.objects.get(pk=identifier)
    started = timezone.now()
    if dataset.annotations_deleted:
        value = {"status": "EMPTY", "counts": {"total": 0, "accepted": 0, "rejected": 0, "ignored": 0, "invalid": 0}, "error": None}
    else:
        try:
            _, rows = read_bound_annotations(dataset)
            value = summarize(rows, policy=dataset.annotation_policy)
        except OperationError as error:
            value = {"status": "INVALID" if error.code == "INVALID_ANNOTATIONS" else "UNKNOWN", "counts": None, "error": error.public()}
    # Binding changes or newer observations must not be overwritten by a slow read.
    DjangoDataset.objects.filter(pk=identifier, prodigy_dataset_id=dataset.prodigy_dataset_id,
        annotations_deleted=dataset.annotations_deleted, annotation_observed_at=dataset.annotation_observed_at).update(
        annotation_data=value, annotation_observed_at=started, annotation_refresh_requested=False)
    return value


def summarize(rows, *, policy="reject-other-v1"):
    counts = {"total": len(rows), "accepted": 0, "rejected": 0, "ignored": 0, "invalid": 0}
    for row in rows:
        answer = row.get("answer") if isinstance(row, dict) else None
        valid = isinstance(answer, str) and answer in {"accept", "reject", "ignore"}
        if valid and answer != "ignore":
            valid = isinstance(row.get("text"), str) and bool(row["text"].strip())
        if valid and answer == "accept":
            if policy == "single-label-choice-v2":
                choices = row.get("accept")
                valid = (isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], str)
                         and isinstance(row.get("meta"), dict) and row["meta"].get("_annotation_policy") == policy
                         and isinstance(row["meta"].get("_class_schema"), list)
                         and choices[0] in row["meta"].get("_class_schema", []))
            else:
                valid = isinstance(row.get("label"), str) and bool(row["label"].strip())
        counts[{"accept": "accepted", "reject": "rejected", "ignore": "ignored"}[answer] if valid else "invalid"] += 1
    return {"status": "INVALID" if counts["invalid"] else "PRESENT" if rows else "EMPTY", "counts": counts, "error": None}


def observe_many(identifiers):
    """Batch identity/count reads; scan at most the configured limit per selected dataset."""
    datasets = list(DjangoDataset.objects.filter(pk__in=identifiers, deletion_pending=False))
    pending = [d for d in datasets if d.binding_state == "BOUND" and not d.annotations_deleted]
    if not pending:
        for dataset in datasets:
            observe_data(dataset.pk)
        return
    observations = {}
    started = timezone.now()
    try:
        with reader() as connection:
            identities = connection.execute("""SELECT d.id,d.name,count(l.example_id)
                FROM public.dataset d LEFT JOIN public.link l ON l.dataset_id=d.id
                WHERE d.name=ANY(%s) AND d.session IS NOT TRUE GROUP BY d.id,d.name""",
                ([d.prodigy_dataset_name for d in pending],)).fetchall()
            identities = {name: (identifier, count) for identifier, name, count in identities}
            for dataset in pending:
                found = identities.get(dataset.prodigy_dataset_name)
                try:
                    if found is None or found[0] != dataset.prodigy_dataset_id:
                        raise OperationError("DATASET_REPLACED", "The bound annotation dataset is missing or has been replaced. Review its binding.")
                    if found[1] > settings.KEDROGY_MAX_ANNOTATIONS:
                        raise OperationError("INVALID_ANNOTATIONS", "This dataset exceeds the configured annotation limit.")
                    rows = connection.execute("""SELECT e.content FROM public.link l
                        JOIN public.example e ON e.id=l.example_id WHERE l.dataset_id=%s ORDER BY e.id LIMIT %s""",
                        (dataset.prodigy_dataset_id, settings.KEDROGY_MAX_ANNOTATIONS)).fetchall()
                    try:
                        value = summarize([json.loads(bytes(row[0])) for row in rows], policy=dataset.annotation_policy)
                    except (ValueError, TypeError):
                        raise OperationError("INVALID_ANNOTATIONS", "Stored annotations contain invalid JSON or text encoding.") from None
                except OperationError as error:
                    value = {"status": "INVALID" if error.code == "INVALID_ANNOTATIONS" else "UNKNOWN", "counts": None, "error": error.public()}
                observations[dataset.pk] = value
    except OperationError as error:
        observations = {d.pk: {"status": "UNKNOWN", "counts": None, "error": error.public()} for d in pending}
    for dataset in datasets:
        if dataset.pk not in observations:
            observe_data(dataset.pk)
            continue
        DjangoDataset.objects.filter(pk=dataset.pk, prodigy_dataset_id=dataset.prodigy_dataset_id,
            annotations_deleted=dataset.annotations_deleted, annotation_observed_at=dataset.annotation_observed_at).update(
            annotation_data=observations[dataset.pk], annotation_observed_at=started, annotation_refresh_requested=False)
