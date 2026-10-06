"""Offline artifact integrity checks using real tiny Transformers checkpoints."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from mykedro.artifacts import publish_checkpoint, validate_checkpoint, verify_artifact
from safetensors import SafetensorError
from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast


def tiny_checkpoint(path: Path, labels=None):
    path.mkdir(parents=True, exist_ok=True)
    labels = labels or ["positive", "negative"]
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "good", "bad", "product", "."]
    (path / "vocab.txt").write_text("\n".join(vocab))
    tokenizer = BertTokenizerFast(vocab_file=str(path / "vocab.txt"))
    tokenizer.save_pretrained(path)
    mapping = {0: "OTHER", **{i+1: label for i,label in enumerate(labels)}}
    model = BertForSequenceClassification(BertConfig(vocab_size=len(vocab), hidden_size=16,
        num_hidden_layers=1, num_attention_heads=2, intermediate_size=32,
        id2label=mapping, label2id={value:key for key,value in mapping.items()}))
    model.save_pretrained(path)
    return model, tokenizer


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.labels = ["positive", "negative"]
        self.model, self.tokenizer = tiny_checkpoint(self.root / "base")
        self.run_id, self.attempt = str(uuid.uuid4()), str(uuid.uuid4())
        self.receipt_env = patch.dict(os.environ, {"KEDROGY_TERMINATION_LOG":str(self.root / "receipt.json")})
        self.receipt_env.start()
        self.addCleanup(self.receipt_env.stop)

    def publish(self, quality=None):
        model = self.model
        class Saver:
            def save_model(self, path):
                model.save_pretrained(path)
        return publish_checkpoint(Saver(), self.tokenizer, root=self.root, run_id=self.run_id,
            attempt_id=self.attempt, labels=self.labels, image="synthetic-image", artifact_version=1, quality=quality)

    def verify(self, path, **changes):
        args = {"run_id": self.run_id, "attempt_id": self.attempt, "labels": self.labels, "image": "synthetic-image"}
        return verify_artifact(path, **(args | changes))

    def test_round_trip_and_finite_inference(self):
        manifest = self.publish()
        self.assertEqual(self.verify(self.root / manifest["path"]), manifest)
        self.assertEqual(json.loads((self.root / "receipt.json").read_text()), manifest)
        with self.assertRaises(ValueError):
            self.publish()

    def test_quality_report_is_saved_hashed_and_round_tripped(self):
        quality = {"version":1,"split":"validation","samples":4,"train_samples":12,
                   "training_steps":24,"accuracy":.75,"macro_f1":.73,
                   "majority_baseline":.5,"warnings":["small_validation_sample"],
                   "confusion_matrix":[[2,0],[1,1]]}
        manifest = self.publish(quality)
        path = self.root / manifest["path"]
        self.assertEqual(json.loads((path / "quality.json").read_text()), quality)
        self.assertIn("quality.json", manifest["files"])
        self.assertEqual(self.verify(path)["quality"]["accuracy"], .75)
        (path / "quality.json").write_text("{}")
        with self.assertRaises(ValueError):
            self.verify(path)

    def test_wrong_run_and_modified_checksum_fail(self):
        manifest = self.publish()
        path = self.root / manifest["path"]
        with self.assertRaises(ValueError):
            self.verify(path, run_id=str(uuid.uuid4()))
        with (path / "config.json").open("a") as stream:
            stream.write("\n")
        with self.assertRaises(ValueError):
            self.verify(path)

    def test_missing_weights_tokenizer_and_wrong_labels_fail(self):
        base = self.root / "base"
        with self.assertRaises(ValueError):
            validate_checkpoint(base, ["different", "labels"])
        (base / "model.safetensors").unlink()
        with self.assertRaises(OSError):
            validate_checkpoint(base, self.labels)
        self.model.save_pretrained(base)
        for name in ["tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt"]:
            (base / name).unlink(missing_ok=True)
        with self.assertRaises((OSError, ValueError, TypeError)):
            validate_checkpoint(base, self.labels)

    def test_corrupt_weights_and_foreign_manifest_fail(self):
        manifest = self.publish()
        path = self.root / manifest["path"]
        (path / "model.safetensors").write_bytes(b"invalid weights")
        with self.assertRaises(SafetensorError):
            self.verify(path)

    def test_empty_and_symlink_paths_fail(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            validate_checkpoint(empty, self.labels)
        alias = self.root / "alias"
        alias.symlink_to(self.root / "base", target_is_directory=True)
        with self.assertRaises(ValueError):
            validate_checkpoint(alias, self.labels)


if __name__ == "__main__":
    unittest.main()
