"""Run the real training pipeline and failure/recovery checks in isolated fixtures."""

import json
import os
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = json.loads((ROOT / ".local/reliability-env.json").read_text())
    if (
        env.get("KEDROGY_TEST_DATABASE") != "disposable"
        or env["KEDROGY_NAMESPACE"] != "kedrogy-check-20260924"
    ):
        raise ValueError("Only isolated reliability fixtures are permitted.")
    os.environ.update(env)
    import django

    django.setup()
    from django.conf import settings
    from kedrogy.launch_config import validate_dataset
    from kedrogy.models import DjangoDataset, DjangoModel, TrainingRun
    from kedrogy.tests import dataset_values
    from kedrogy.training import (
        ACTIVE,
        _conditions,
        _ensure,
        _get,
        advance_run,
        start_training,
    )

    from kedrogy import manifests

    settings.KEDROGY_ML_IMAGE = env["KEDROGY_ML_IMAGE"]
    settings.KEDROGY_ML_IMAGE_ALIASES = {"approved:1", env["KEDROGY_ML_IMAGE"]}
    settings.KEDROGY_NAMESPACE = env["KEDROGY_NAMESPACE"]
    settings.KEDROGY_TRAIN_OPTIONS = {
        "base_model": "data/06_models/tiny-base",
        "max_steps": 1,
    }
    settings.KEDROGY_TRAIN_TIMEOUT = 300
    dataset = DjangoDataset.objects.create(
        **(
            dataset_values()
            | {
                "dataset_name": "reliability-fixture",
                "recipe_options": "-l positive,negative",
            }
        )
    )
    model = DjangoModel.objects.create(
        on_dataset=dataset,
        labels="positive,negative",
        model_name="Synthetic reliability check",
    )
    cfg = validate_dataset(dataset.to_dict())
    _ensure(manifests.pvc(model.id), settings.KEDROGY_NAMESPACE)
    code = """from pathlib import Path
from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
p=Path("data/06_models/tiny-base");p.mkdir(parents=True,exist_ok=True)
v=["[PAD]","[UNK]","[CLS]","[SEP]","[MASK]","good","bad","product","."]
(p/"vocab.txt").write_text("\\n".join(v))
t=BertTokenizerFast(vocab_file=str(p/"vocab.txt"));t.save_pretrained(p)
m={0:"OTHER",1:"positive",2:"negative"}
BertForSequenceClassification(BertConfig(vocab_size=len(v),hidden_size=16,num_hidden_layers=1,num_attention_heads=2,intermediate_size=32,id2label=m,label2id={v:k for k,v in m.items()})).save_pretrained(p)
"""
    fixture = manifests.verification(
        cfg,
        model.id,
        name=f"fixture-{uuid.uuid4()}",
        run_id=str(uuid.uuid4()),
        attempt_id=str(uuid.uuid4()),
        path="tiny-base",
        labels=["positive", "negative"],
    )
    container = fixture["spec"]["template"]["spec"]["containers"][0]
    container["args"] = ["-c", code]
    container["volumeMounts"][0]["readOnly"] = False
    _ensure(fixture, settings.KEDROGY_NAMESPACE)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        job = _get("job", fixture["metadata"]["name"], settings.KEDROGY_NAMESPACE)
        if "Failed" in _conditions(job):
            raise RuntimeError("Tiny model fixture failed.")
        if "Complete" in _conditions(job):
            break
        time.sleep(3)
    else:
        raise TimeoutError("Fixture model creation timed out.")
    print("Fixture checkpoint ready.", flush=True)

    def finish(run):
        last = None
        deadline = time.monotonic() + 650
        while time.monotonic() < deadline:
            run = advance_run(run.id)
            if run.status != last:
                print(f"{run.id}: {run.status} {run.error}", flush=True)
                last = run.status
            if run.status not in ACTIVE:
                return run
            time.sleep(3)
        raise TimeoutError("Run did not reach a terminal state.")

    first, _ = start_training(model.id, "real-pipeline-first")
    first = finish(first)
    if first.status != "SUCCEEDED":
        raise RuntimeError(f"Pipeline failed: {first.error}")
    second, _ = start_training(model.id, "real-pipeline-restarted-observer")
    second = advance_run(second.id)
    # No queue worker is running. Leave the Job alive, then recover via a new reconciliation call.
    original_uid = second.job_uid
    time.sleep(10)
    second = finish(second)
    if (
        second.status != "SUCCEEDED"
        or second.job_uid != original_uid
        or first.artifact["path"] == second.artifact["path"]
    ):
        raise RuntimeError("Recovery or immutable attempt paths failed.")
    model.labels = "unknown,labels"
    model.save(update_fields=["labels"])
    failed, _ = start_training(model.id, "real-pipeline-invalid-labels")
    failed = finish(failed)
    model.refresh_from_db()
    if failed.status != "FAILED" or model.published_run_id != second.id:
        raise RuntimeError("Failed retraining discarded the previous artifact.")
    # Exercise UID-guarded deadline deletion on a real running Job.
    model.labels = "positive,negative"
    model.save(update_fields=["labels"])
    timed, _ = start_training(model.id, "real-deadline")
    timed = advance_run(timed.id)
    from datetime import timedelta

    from django.utils import timezone

    TrainingRun.objects.filter(pk=timed.id).update(
        created_at=timezone.now() - timedelta(hours=4)
    )
    timed = advance_run(timed.id)
    if timed.status != "TIMED_OUT":
        raise RuntimeError(f"Deadline cleanup failed: {timed.error}")
    report = {
        "namespace": settings.KEDROGY_NAMESPACE,
        "model_id": model.pk,
        "runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "job": run.job_name,
                "error": run.error,
                "artifact_path": run.artifact.get("path"),
            }
            for run in [first, second, failed, timed]
        ],
        "checks": [
            "full Kedro pipeline with synthetic PostgreSQL annotations and tiny BERT",
            "independent read-only artifact verification",
            "second run has distinct checkpoint directory",
            "observer restart reuses Job UID",
            "failed retraining preserves published artifact",
            "deadline deletion uses UID precondition",
        ],
    }
    output = ROOT / "reports/2026-09-24-implementation"
    output.mkdir(parents=True, exist_ok=True)
    (output / "training-runtime.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
