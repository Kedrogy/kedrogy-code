"""Explicit single-label annotation without random suggestions or text deduplication."""

import prodigy
import srsly
from kedrogy_contracts import CONVERSION_VERSION, normalize_labels
from prodigy.util import set_hashes, split_string


def choice_stream(rows, labels):
    labels = normalize_labels(labels, policy=CONVERSION_VERSION)
    for row in rows:
        meta = dict(row.get("meta", {}))
        if not all(isinstance(meta.get(key), str) and meta[key] for key in ("_source_id", "_record_id", "_content_digest")):
            raise ValueError("Explicit-choice tasks require stable source provenance.")
        meta.update(_annotation_policy=CONVERSION_VERSION, _class_schema=list(labels))
        task = {"text": row["text"], "meta": meta,
                "_source_identity": [meta["_source_id"], meta["_record_id"]],
                "options": [{"id": label, "text": label} for label in labels]}
        yield set_hashes(task, input_keys=("text", "_source_identity"), task_keys=("options",), overwrite=True)


def validate_choice(task):
    if task.get("answer") == "accept":
        selected = task.get("accept")
        allowed = [option["id"] for option in task["options"]]
        if not isinstance(selected, list) or len(selected) != 1 or selected[0] not in allowed:
            raise ValueError("Select exactly one configured class, or skip/reject this record.")


@prodigy.recipe("myrecipes.textcat.choice",
    dataset=("Dataset receiving explicit class choices", "positional", None, str),
    source=("JSONL with stable source metadata", "positional", None, str),
    label=("At least two comma-separated classes", "option", "l", split_string))
def textcat_choice(dataset, source, label):
    labels = normalize_labels(label, policy=CONVERSION_VERSION)
    return {"dataset": dataset, "view_id": "choice", "stream": choice_stream(srsly.read_jsonl(source), labels),
            "validate_answer": validate_choice,
            "config": {"labels": list(labels), "choice_style": "single", "choice_auto_accept": False,
                       "exclude_by": "input", "description": "Choose one class, then accept. Skip and reject do not assign a class."}}
