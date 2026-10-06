"""Offline checkpoint serving with explicit version identity and bounded inference."""

import argparse
import asyncio
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from kedrogy_contracts import CONTRACT_VERSION, artifact_mapping
from pydantic import BaseModel, ConfigDict, Field, StrictStr
from transformers import AutoModelForSequenceClassification, AutoTokenizer


@dataclass(frozen=True)
class ServeConfig:
    checkpoint: Path
    training_run_id: str
    serving_run_id: str
    artifact: dict
    preprocess: str = ""


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: StrictStr = Field(min_length=1, max_length=20000)


class BodyLimit:
    """Bound request bytes before JSON decoding, including chunked requests."""

    def __init__(self, app, limit=65536):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"Request body exceeds the size limit."}'})
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def verify_files(config):
    """Check the receipt before loading any tokenizer or model files."""
    uuid.UUID(config.training_run_id)
    uuid.UUID(config.serving_run_id)
    receipt = config.artifact
    mapping = artifact_mapping(receipt)
    root = config.checkpoint
    if root.is_symlink() or not root.is_dir() or any(p.is_symlink() for p in root.parents):
        raise ValueError("Checkpoint path is invalid.")
    if receipt.get("run_id") != config.training_run_id or receipt.get("verified") is not True:
        raise ValueError("Checkpoint identity is invalid.")
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Checkpoint symlinks are not supported.")
        if path.is_file() and path.name != "kedrogy-manifest.json":
            with path.open("rb") as stream:
                files[str(path.relative_to(root))] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not files or files != receipt["files"] or not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Checkpoint checksums do not match the verified receipt.")
    if not receipt.get("legacy"):
        manifest = json.loads((root / "kedrogy-manifest.json").read_text())
        if any(manifest.get(key) != value for key, value in receipt.items() if key != "pvc"):
            raise ValueError("Checkpoint manifest does not match the receipt.")
    return mapping


def load_runtime(config):
    mapping = verify_files(config)
    if config.preprocess:
        matches = list(entry_points(group="ysz.predict", name=config.preprocess))
        if len(matches) != 1:
            raise ValueError("The configured preprocessing entry point is unavailable or ambiguous.")
        preprocess = matches[0].load()
    else:
        preprocess = lambda text: text
    tokenizer = AutoTokenizer.from_pretrained(config.checkpoint, local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.checkpoint, local_files_only=True, trust_remote_code=False, use_safetensors=True)
    if (model.config.id2label != dict(enumerate(mapping)) or model.config.num_labels != len(mapping)
            or model.config.label2id != {label: i for i, label in enumerate(mapping)}):
        raise ValueError("Checkpoint class mappings are inconsistent.")
    model.eval()
    limits = [value for value in (getattr(tokenizer, "model_max_length", None),
              getattr(model.config, "max_position_embeddings", None)) if isinstance(value, int) and 0 < value < 1000000]
    if not limits:
        raise ValueError("Checkpoint does not specify a supported token limit.")
    limit = min(limits)

    def infer(text):
        prepared = preprocess(text)
        if not isinstance(prepared, str) or not prepared.strip():
            raise HTTPException(422, "Preprocessing produced empty or invalid text.")
        if len(prepared) > 20000:
            raise HTTPException(422, "Preprocessed text exceeds the character limit.")
        inputs = tokenizer(prepared, return_tensors="pt", truncation=False)
        if inputs["input_ids"].shape[-1] > limit:
            raise HTTPException(422, f"Text exceeds the model limit of {limit} tokens.")
        with torch.inference_mode():
            logits = model(**inputs).logits
        if tuple(logits.shape) != (1, len(mapping)) or not torch.isfinite(logits).all().item():
            raise RuntimeError("The model produced invalid logits.")
        class_id = logits.argmax(dim=-1).item()
        result = {"class_id": class_id, "label": mapping[class_id], "contract_version": CONTRACT_VERSION,
                "training_run_id": config.training_run_id, "serving_run_id": config.serving_run_id}
        if config.artifact["version"] == 2:
            result["class_schema_version"] = 2
        return result

    infer("Model readiness check.")
    return infer


def create_app(config: ServeConfig) -> FastAPI:
    """Importable application factory; command-line parsing is confined to main."""
    @asynccontextmanager
    async def lifespan(app):
        app.state.ready = False
        app.state.inflight = None
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference") as executor:
            app.state.executor = executor
            app.state.infer = await asyncio.get_running_loop().run_in_executor(executor, load_runtime, config)
            app.state.ready = True
            try:
                yield
            finally:
                app.state.ready = False
                app.state.infer = None

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(BodyLimit)

    @app.get("/livez")
    async def live():
        return {"live": True}

    @app.get("/readyz")
    async def ready():
        if not getattr(app.state, "ready", False):
            raise HTTPException(503, "The model is not ready.")
        return {"ready": True, "contract_version": CONTRACT_VERSION,
                "training_run_id": config.training_run_id, "serving_run_id": config.serving_run_id}

    @app.post("/predict")
    async def predict(params: Params):
        if not params.text.strip():
            raise HTTPException(422, "Enter nonempty text to classify.")
        if not app.state.ready:
            raise HTTPException(503, "The model is not ready.")
        if app.state.inflight is not None and not app.state.inflight.done():
            raise HTTPException(429, "The model is busy. Retry shortly.", headers={"Retry-After": "1"})
        # Hold the slot until the actual thread completes, even if the caller disconnects.
        future = app.state.executor.submit(app.state.infer, params.text)
        app.state.inflight = future
        try:
            return await asyncio.shield(asyncio.wrap_future(future))
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 -- never expose model internals or input text through HTTP errors
            app.state.ready = False
            raise HTTPException(503, "The model could not complete inference.") from None

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("-p", "--preprocess", default="")
    parser.add_argument("--training-run-id", required=True)
    parser.add_argument("--serving-run-id", required=True)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args()
    config = ServeConfig(args.checkpoint, args.training_run_id, args.serving_run_id,
                         json.loads(args.artifact), args.preprocess)
    uvicorn.run(create_app(config), host="0.0.0.0", port=8888)
