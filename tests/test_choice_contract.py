"""Explicit annotation semantics, source identity and artifact compatibility."""

import copy
import tempfile
import unittest
from pathlib import Path

from kedrogy_contracts import (
    CONVERSION_VERSION, ContractError, annotation_summary, artifact_mapping,
    legacy_annotation_preview, training_examples, validate_prediction,
)
from myrecipes.textcat_choice import choice_stream, validate_choice


def answers(labels=("positive", "negative")):
    source = [{"text": "same text", "meta": {"_source_id": "source", "_record_id": str(i), "_content_digest": "a" * 64}}
              for i in range(len(labels) * 2)]
    return [task | {"answer": "accept", "accept": [labels[i % len(labels)]]}
            for i, task in enumerate(choice_stream(source, labels))]


class ChoiceContractTests(unittest.TestCase):
    def test_reject_and_ignore_never_supply_a_target(self):
        rows = answers()
        rejected = rows[0] | {"answer": "reject", "label": "negative", "accept": []}
        ignored = rows[0] | {"answer": "ignore", "accept": []}
        examples, summary = training_examples([*rows, rejected, ignored], ["positive", "negative"], dataset_id=7)
        self.assertEqual([row["label"] for row in examples], [0, 1, 0, 1])
        self.assertEqual((summary["usable"], summary["needs_review"], summary["ignored"]), (4, 1, 1))

    def test_invalid_choices_fail_before_training(self):
        for selection in [[], ["positive", "negative"], ["unknown"], "positive", [False]]:
            with self.subTest(selection=selection), self.assertRaises((ContractError, ValueError)):
                rows = answers()
                rows[0]["accept"] = selection
                validate_choice(rows[0])
                training_examples(rows, ["positive", "negative"], dataset_id=7)

    def test_distinct_source_records_survive_identical_text(self):
        rows = answers()
        self.assertEqual(len({row["_input_hash"] for row in rows}), 4)
        other_source = copy.deepcopy(rows[0])
        other_source["meta"]["_source_id"] = "other-source"
        task = next(choice_stream([other_source], ["positive", "negative"]))
        self.assertNotEqual(task["_input_hash"], rows[0]["_input_hash"])

    def test_conflicting_answers_are_not_silently_weighted(self):
        rows = answers()
        with self.assertRaises(ContractError) as error:
            training_examples([*rows, rows[0] | {"accept": ["negative"]}], ["positive", "negative"], dataset_id=7)
        self.assertEqual(error.exception.code, "CONFLICTING_ANNOTATIONS")
        _, summary = training_examples([*rows, rows[0]], ["positive", "negative"], dataset_id=7)
        self.assertEqual((summary["usable"], summary["duplicate_accepted"]), (4, 1))

    def test_order_policy_and_identity_are_fingerprinted(self):
        rows = answers()
        initial = annotation_summary(rows, ["positive", "negative"], dataset_id=7)
        reordered = annotation_summary(rows, ["negative", "positive"], dataset_id=7)
        self.assertNotEqual(initial["fingerprint"], reordered["fingerprint"])
        self.assertEqual(initial["fingerprint"], annotation_summary(list(reversed(rows)), ["positive", "negative"], dataset_id=7)["fingerprint"])
        rows[0]["meta"]["_source_id"] = "other"
        self.assertNotEqual(initial["fingerprint"], annotation_summary(rows, ["positive", "negative"], dataset_id=7)["fingerprint"])
        with self.assertRaises(ContractError):
            annotation_summary(rows, ["positive", "negative"], dataset_id=7, policy="reject-other-v1")

    def test_other_is_only_an_explicit_class_in_v2(self):
        examples, _ = training_examples(answers(("positive", "OTHER")), ["positive", "OTHER"], dataset_id=7)
        self.assertEqual([row["label"] for row in examples], [0, 1, 0, 1])
        legacy = {"version": 1, "labels": ["positive", "negative"]}
        current = {"version": 2, "class_schema_version": 2, "conversion_policy": CONVERSION_VERSION, "labels": ["positive", "negative"]}
        self.assertEqual(artifact_mapping(legacy), ["OTHER", "positive", "negative"])
        self.assertEqual(artifact_mapping(current), ["positive", "negative"])
        for version in [True, 3, None]:
            with self.assertRaises(ContractError):
                artifact_mapping(current | {"version": version})
        for schema in [True, 1.0, "1"]:
            with self.subTest(schema=schema), self.assertRaises(ContractError):
                artifact_mapping(legacy | {"class_schema_version": schema})
        value = {"class_id": 0, "label": "positive", "contract_version": 1, "class_schema_version": 2,
                 "training_run_id": "t", "serving_run_id": "s"}
        args = {"labels": current["labels"], "training_run_id": "t", "serving_run_id": "s", "artifact_version": 2}
        self.assertEqual(validate_prediction(value, **args)["label"], "positive")
        with self.assertRaises(ContractError):
            validate_prediction(value | {"class_schema_version": 1}, **args)

    def test_legacy_preview_never_infers_opposite_class(self):
        result = legacy_annotation_preview([{"answer": "reject", "label": "negative"},
            {"answer": "accept", "label": "positive"}, {"answer": "accept", "label": "P"}], ["positive", "negative"])
        self.assertEqual(result["counts"], {"requires_reannotation": 1, "accepted_exact_label": 1, "unresolved": 1})
        self.assertFalse(result["applied"])

    def test_stratified_split_uses_the_catalog_dataframe_contract(self):
        from mykedro.pipelines.train.nodes import split_examples
        from ysz.kedro_datasets.fasttext_dataset import FasttextDataset
        rows = [row | {"text": f"Distinct training example {index}"}
                for index, row in enumerate(answers())]
        examples, _ = training_examples(rows, ["positive", "negative"], dataset_id=7)
        with tempfile.TemporaryDirectory() as directory:
            catalog = FasttextDataset(str(Path(directory) / "examples.csv"))
            catalog.save(examples)
            train, validation = split_examples(catalog.load(), {"data_seed": 42})
        self.assertEqual(set(train["label"]), {0, 1})
        self.assertEqual(set(validation["label"]), {0, 1})
        self.assertTrue(set(train.index).isdisjoint(validation.index))
