"""Real tiny-checkpoint inference, lifecycle, limits, and cancellation regressions."""

import asyncio
import threading
import unittest
from unittest.mock import patch

import httpx
import test_artifacts
import torch
from fastapi.testclient import TestClient
from kedrogy_contracts import annotation_summary
from mykedro.pipelines.train.nodes import labelled_examples
from ysz.predict.serve import ServeConfig, create_app


class InferenceTests(unittest.TestCase):
    setUp = test_artifacts.ArtifactTests.setUp
    publish = test_artifacts.ArtifactTests.publish

    def config(self):
        manifest = self.publish()
        return ServeConfig((self.root / manifest["path"]).resolve(), self.run_id, self.attempt, manifest)

    def test_real_prediction_health_and_zero_class(self):
        with torch.no_grad():
            self.model.classifier.weight.zero_()
            self.model.classifier.bias.zero_()
            self.model.classifier.bias[0] = 100
        config = self.config()
        with TestClient(create_app(config)) as client:
            self.assertEqual(client.get("/livez").status_code, 200)
            ready = client.get("/readyz").json()
            self.assertEqual(ready["serving_run_id"], self.attempt)
            response = client.post("/predict", json={"text": "good product"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"class_id": 0, "label": "OTHER", "contract_version": 1,
                "training_run_id": self.run_id, "serving_run_id": self.attempt})
            for text in ["", " ", 123, None, "good " * 600]:
                with self.subTest(text_type=type(text).__name__):
                    self.assertEqual(client.post("/predict", json={"text": text}).status_code, 422)
            self.assertEqual(client.post("/predict", content=b"x" * 65537).status_code, 413)

    def test_changed_files_and_unknown_preprocessor_never_ready(self):
        config = self.config()
        from dataclasses import replace
        with self.assertRaises(ValueError), TestClient(create_app(replace(config, preprocess="missing-plugin"))):
            pass
        (config.checkpoint / "config.json").write_text("{}")
        with self.assertRaises(ValueError), TestClient(create_app(config)):
            pass

    def test_busy_health_and_cancelled_request_retain_one_thread_slot(self):
        config = self.config()
        entered, release = threading.Event(), threading.Event()
        def blocked(_):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Synthetic inference was not released.")
            return {"class_id": 0, "label": "OTHER"}
        async def scenario():
            app = create_app(config)
            with patch("ysz.predict.serve.load_runtime", return_value=blocked):
                async with app.router.lifespan_context(app):  # noqa: SIM117 -- keep lifespan outside the HTTP client for teardown ordering
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                        first = asyncio.create_task(client.post("/predict", json={"text": "first"}))
                        try:
                            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                            self.assertEqual((await client.get("/livez")).status_code, 200)
                            self.assertEqual((await client.get("/readyz")).status_code, 200)
                            first.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await first
                            self.assertEqual((await client.post("/predict", json={"text": "second"})).status_code, 429)
                        finally:
                            release.set()
                            await asyncio.wrap_future(app.state.inflight)
        asyncio.run(scenario())

    def test_training_rechecks_same_rows_and_fingerprint(self):
        rows = [{"text": f"Synthetic example {i}", "answer": "accept", "accept": [label],
                 "meta": {"_annotation_policy": "single-label-choice-v2", "_class_schema": ["P", "N"],
                          "_source_id": "source", "_record_id": str(i), "_content_digest": "a" * 64}}
                for i, label in enumerate(["P", "N", "P", "N"])]
        summary = annotation_summary(rows, ["P", "N"], dataset_id=1)
        parameters = {"dataset_name": "synthetic", "prodigy_dataset_id": 1, "max_annotations": 100,
            "labels": ["P", "N"], "conversion_policy": summary["policy"], "annotation_fingerprint": summary["fingerprint"]}
        with patch("mykedro.pipelines.train.nodes.read_annotations", return_value=rows):
            self.assertIs(labelled_examples(parameters), rows)
        for changed in [rows + [rows[0]], [rows[0] | {"text": "Changed"}, *rows[1:]]]:
            with patch("mykedro.pipelines.train.nodes.read_annotations", return_value=changed), self.assertRaises(ValueError):
                labelled_examples(parameters)
