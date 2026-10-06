"""
This is a boilerplate pipeline 'train'
generated using Kedro 1.2.0
"""

import json
import os
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from datasets import Dataset
from kedrogy_contracts import (
    CONVERSION_VERSION,
    ContractError,
    annotation_summary,
    class_mapping,
    training_examples,
)
from sklearn.model_selection import train_test_split
from srsly.util import JSONInput
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
    set_seed,
)

from mykedro.artifacts import publish_checkpoint
from mykedro.db_queries import read_annotations
from mykedro.quality import quality_report
from kedrogy_contracts.training import DEFAULTS, training_options
from sklearn.metrics import f1_score


def labelled_examples(parameters: dict) -> Iterable[JSONInput]:
    try:
        rows = read_annotations(parameters["dataset_name"], dataset_id=parameters["prodigy_dataset_id"],
                                limit=parameters["max_annotations"])
        summary = annotation_summary(rows, parameters["labels"], dataset_id=parameters["prodigy_dataset_id"], policy=parameters["conversion_policy"])
        if (parameters["conversion_policy"] != CONVERSION_VERSION
                or summary["fingerprint"] != parameters["annotation_fingerprint"]):
            raise ContractError("ANNOTATIONS_CHANGED", "Annotations changed after preflight. Start a new training run.")
        return rows
    except ContractError as error:
        destination = Path(os.environ.get("KEDROGY_TERMINATION_LOG", "/dev/termination-log"))
        destination.write_text(json.dumps({"error": {"code": error.code, "message": str(error)}}))
        raise


def make_id2label_label2id(labels):
    """Class zero is the first explicitly configured class under v2."""
    id2label = dict(enumerate(class_mapping(labels, artifact_version=2)))
    return id2label, {label: index for index, label in id2label.items()}


def jsonl_to_fasttext(stream: Iterable[JSONInput], parameters: dict) -> Iterable[JSONInput]:
    examples, _ = training_examples(list(stream), parameters["labels"],
        dataset_id=parameters["prodigy_dataset_id"], policy=parameters["conversion_policy"])
    return examples


def split_examples(examples, parameters: dict):
    """Use the saved data seed for a repeatable training/validation split."""
    import math
    # Identical texts must not leak across the training and validation sets.
    examples = examples.copy()
    keys = examples["text"].str.strip().str.casefold().str.replace(r"\s+", " ", regex=True)
    if examples.groupby(keys)["label"].nunique().max() > 1:
        raise ValueError("Identical training texts have conflicting labels.")
    examples = examples.loc[~keys.duplicated()]
    classes = examples["label"].tolist()
    validation_count = max(len(set(classes)), math.ceil(len(examples) / 4))
    return train_test_split(examples, random_state=parameters["data_seed"],
                            test_size=validation_count, stratify=classes)


def train(ads: Dataset, parameters: dict):
    options = training_options({key: parameters[key] for key in DEFAULTS if key in parameters})
    # Seed before initializing the randomly initialized classification head.
    set_seed(options["seed"])
    base_model = options["base_model"]
    run_id = parameters["run_id"]
    attempt_id = os.environ["KEDROGY_POD_UID"]
    root = Path("data/06_models")
    work = root / "runs" / run_id / attempt_id / "training"
    tokenizer = AutoTokenizer.from_pretrained(base_model, local_files_only=True)

    def preprocess_function(examples):
        return tokenizer(examples["text"], truncation=True, max_length=options["max_length"])

    tokenized_ads = ads.map(preprocess_function, batched=True)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)


    def compute_metrics(eval_pred):
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)
        return {"accuracy": float(np.mean(predictions == labels)),
                "macro_f1": float(f1_score(labels, predictions, labels=list(range(len(parameters["labels"]))), average="macro", zero_division=0))}

    id2label, label2id = make_id2label_label2id(parameters["labels"])
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model,
        local_files_only=True,
        num_labels=len(parameters["labels"]),
        ignore_mismatched_sizes=True,
        id2label=id2label,
        label2id=label2id,
    )

    training_args = TrainingArguments(
        output_dir=str(work), max_steps=options["max_steps"],
        report_to="none", save_total_limit=1,
        learning_rate=options["learning_rate"],
        per_device_train_batch_size=options["train_batch_size"],
        per_device_eval_batch_size=options["eval_batch_size"],
        num_train_epochs=options["num_train_epochs"], weight_decay=options["weight_decay"],
        eval_strategy="epoch", save_strategy="epoch", load_best_model_at_end=True,
        metric_for_best_model="macro_f1", greater_is_better=True,
        push_to_hub=False, data_seed=options["data_seed"], seed=options["seed"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ads["train"],
        eval_dataset=tokenized_ads["test"],
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )
    trainer.train()

    evaluation = trainer.predict(tokenized_ads["test"])
    quality = quality_report(evaluation.label_ids, np.argmax(evaluation.predictions, axis=1),
        classes=len(parameters["labels"]), training_steps=trainer.state.global_step,
        train_samples=len(tokenized_ads["train"]))
    print("Validation quality: " + json.dumps(quality, sort_keys=True), flush=True)
    publish_checkpoint(
        trainer, tokenizer, root=root, run_id=run_id, attempt_id=attempt_id,
        labels=parameters["labels"], image=parameters["image"], artifact_version=2, quality=quality,
    )
