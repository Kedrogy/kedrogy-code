"""Synthetic ML audit reproductions; passing tests confirm current defects."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from kedrogy_contracts import annotation_summary
from mykedro.db_queries import read_annotations
from mykedro.pipelines.train.nodes import jsonl_to_fasttext, split_examples
from ysz.predict.serve import create_app


class MLDefects(unittest.TestCase):
    def test_rejecting_wrong_suggestion_becomes_other(self):
        rows = [{"text": "I love it", "label": "negative", "answer": "reject"}] * 4
        self.assertEqual(jsonl_to_fasttext(rows, {"labels": ["positive", "negative"]})[0]["label"], 0)

    def test_duplicate_single_class_data_passes_and_leaks_across_split(self):
        rows = [{"text": "identical synthetic text", "label": "positive", "answer": "accept"}] * 4
        summary = annotation_summary(rows, ["positive", "negative"], dataset_id=1)
        self.assertEqual(summary["label_counts"], {"positive": 4, "negative": 0})
        examples = jsonl_to_fasttext(rows, {"labels": ["positive", "negative"]})
        train, test = split_examples(examples, {"data_seed": 123})
        self.assertEqual(len({row["text"] for row in train} & {row["text"] for row in test}), 1)

    def test_unstratified_split_can_remove_a_class_from_training(self):
        examples = [{"text": str(i), "label": 1 if i == 3 else 0} for i in range(4)]
        train, test = split_examples(examples, {"data_seed": 123})
        self.assertEqual({row["label"] for row in train}, {0})
        self.assertEqual({row["label"] for row in test}, {1})

    def test_one_inference_failure_never_recovers_despite_live_probe(self):
        calls = []
        def transient(_):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Synthetic transient failure")
            return {"class_id": 0, "label": "OTHER"}
        with patch("ysz.predict.serve.load_runtime", return_value=transient), TestClient(create_app(None)) as client:
            self.assertEqual(client.post("/predict", json={"text": "one"}).status_code, 503)
            self.assertEqual(client.get("/livez").status_code, 200)
            self.assertEqual(client.get("/readyz").status_code, 503)
            self.assertEqual(client.post("/predict", json={"text": "two"}).status_code, 503)
            self.assertEqual(len(calls), 1)

    def test_disposable_database_regression_uses_obsolete_signature(self):
        # Mirrors tests/test_db_queries.py without connecting to PostgreSQL.
        with self.assertRaisesRegex(TypeError, "dataset_id"):
            read_annotations("synthetic")


if __name__ == "__main__":
    unittest.main(verbosity=2)
