"""Validate the intended training data before creating any Kubernetes Job."""

import json

from kedrogy_contracts import CONVERSION_VERSION, ContractError, annotation_summary

from .dataset_bindings import read_bound_annotations
from .kubernetes import OperationError
from .launch_config import parse_labels


def model_labels(model):
    return parse_labels(model.label_schema if model.label_schema is not None else model.labels)


def preflight(model) -> dict:
    if model.on_dataset.annotation_policy != CONVERSION_VERSION:
        raise OperationError("ANNOTATION_POLICY_REVIEW", "Legacy binary answers need review. Create a new dataset with explicit class choices before training.")
    if len(json.dumps(list(model_labels(model)), ensure_ascii=False).encode()) > 1200:
        raise OperationError("CLASS_SCHEMA_TOO_LARGE", "Class names exceed the artifact receipt budget (1200 UTF-8 bytes). Shorten them before training.")
    dataset_id, rows = read_bound_annotations(model.on_dataset)
    try:
        return annotation_summary(rows, model_labels(model), dataset_id=dataset_id, policy=model.on_dataset.annotation_policy)
    except ContractError as error:
        raise OperationError(error.code, str(error)) from error
