"""
This is a boilerplate pipeline 'train'
generated using Kedro 1.2.0
"""

from collections.abc import Iterable

from srsly.util import JSONInput
import psycopg
from transformers import AutoTokenizer
from transformers import DataCollatorWithPadding
from transformers import AutoModelForSequenceClassification, TrainingArguments, Trainer
import evaluate
import numpy as np
from datasets import Dataset


def labelled_examples(parameters: dict) -> Iterable[JSONInput]:
    dataset_name = parameters["dataset_name"]
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
    select replace(encode(content, 'escape'), '\\"', '\"')::json
    FROM
        link
    LEFT JOIN dataset ON dataset.id = link.dataset_id
    LEFT JOIN example ON example.id = link.example_id
    WHERE
    dataset.name = '{dataset_name}';
                """)
            labelled_jsonl = [x[0] for x in cur.fetchall()]
    return labelled_jsonl


def make_id2label_label2id(lst):
    id2label = {}
    label2id = {}
    for i, label in enumerate(lst):
        id2label[str(i + 1)] = label
        label2id[label] = str(i + 1)
    return {**id2label, **{"0": "OTHER"}}, {**label2id, **{"OTHER": "0"}}


def jsonl_to_fasttext(
    stream: Iterable[JSONInput], parameters: dict
) -> Iterable[JSONInput]:
    _, label2id = make_id2label_label2id(parameters["labels"])

    def eg_to_fasttext(eg):
        if eg["answer"] == "accept":
            # like this
            # https://flairnlp.github.io/docs/tutorial-training/how-to-load-custom-dataset#fasttext-format
            LABEL = label2id[eg["label"]]
        elif eg["answer"] == "reject":
            LABEL = 0  # "__label__OTHER"
        else:
            return None  # ignore
        return {"label": LABEL, "text": eg["text"]}

    all = []
    for eg in stream:
        eg_fasttext = eg_to_fasttext(eg)
        if eg_fasttext:
            all.append(eg_fasttext)
            # yield eg_to_fasttext(eg)
    return all


def train(ads: Dataset, parameters: dict):
    tokenizer = AutoTokenizer.from_pretrained("bert-base-multilingual-uncased")

    def preprocess_function(examples):
        return tokenizer(examples["text"], truncation=True)

    tokenized_ads = ads.map(preprocess_function, batched=True)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    accuracy = evaluate.load("accuracy")

    def compute_metrics(eval_pred):
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)
        return accuracy.compute(predictions=predictions, references=labels)

    # id2label.json
    # id2label = {"0": "OTHER", "1": "ADS"}
    # label2id = {"OTHER": 0, "ADS": 1}
    id2label, label2id = make_id2label_label2id(parameters["labels"])
    print(id2label, label2id)
    model = AutoModelForSequenceClassification.from_pretrained(
        "bert-base-multilingual-uncased",
        num_labels=len(parameters["labels"]) + 1,  # and __label__OTHER
        id2label=id2label,
        label2id=label2id,
    )

    training_args = TrainingArguments(
        output_dir="data/06_models/train",
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        num_train_epochs=1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        # eval_strategy="epoch",
        # save_strategy="best",#"epoch",
        # save_total_limit=1,
        # load_best_model_at_end=True,
        # https://discuss.huggingface.co/t/offline-transformers-trainer/27703/3
        push_to_hub=False,  # otherwise: 401 Client Error: Unauthorized for url: https://huggingface.co/api/repos/create
        data_seed=parameters["data_seed"],  # 123,
        seed=parameters["seed"],  # 123,
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
    # https://clear.ml/docs/latest/docs/guides/frameworks/huggingface/transformers/
    trainer.train()

    # return model
    trainer.save_model(output_dir="data/06_models/best")
