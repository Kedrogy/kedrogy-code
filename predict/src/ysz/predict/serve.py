from typing import Annotated
import os
import json
import argparse
from contextlib import asynccontextmanager
from importlib.metadata import entry_points

from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import uvicorn

# this takes a while to load
from transformers import AutoTokenizer
import torch
from transformers import AutoModelForSequenceClassification


# h/t: https://stackoverflow.com/a/42279784
class MyProgramArgs(argparse.Namespace):
    checkpoint: str
    preprocess: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.checkpoint = "checkpoint"  # type: str
        self.preprocess = "preprocess"  # type: str


parser = argparse.ArgumentParser(
    prog="serve",
    description="Serve transformers model",
    epilog="",
)
parser.add_argument("checkpoint")
parser.add_argument("-p", "--preprocess")
args = parser.parse_args(namespace=MyProgramArgs())  # type: MyProgramArgs


class Params(BaseModel):
    text: str


def create_app(args: MyProgramArgs):
    print("preprocess arg:", args.preprocess)

    def preprocess_none(text: str) -> str:
        print("preprocess_none")
        return text

    plugin_loaded = preprocess_none
    for plugin in entry_points(group="ysz.predict"):
        if plugin.name == args.preprocess:
            print("using plugin", plugin.name)
            # print(plugin)
            x = plugin.load()
            # print(x)
            # x("hello")
            plugin_loaded = x
    plugin_loaded("hello")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.checkpoint_here = args.checkpoint
        print("serving:", app.state.checkpoint_here)

        checkpoint_here = app.state.checkpoint_here
        app.state.tokenizer = AutoTokenizer.from_pretrained(
            checkpoint_here, local_files_only=True
        )
        app.state.model = AutoModelForSequenceClassification.from_pretrained(
            checkpoint_here, local_files_only=True
        )

        app.state.plugin_loaded = plugin_loaded
        yield
        print("Shutdown.")

    app = FastAPI(lifespan=lifespan)

    # # https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#simple-http-basic-auth
    # security = HTTPBasic()

    # curl -H "Content-Type: application/json" http://0.0.0.0:8888/predict -d '{"text":"foo"}'
    @app.post(
        "/predict"  # , response_class=PlainTextResponse)
    )
    async def predict(
        # credentials: Annotated[HTTPBasicCredentials, Depends(security)],
        request: Request,
        params: Params,
    ):
        print("using", request.app.state.checkpoint_here)
        print(params)
        # if not (credentials.username == os.getenv('USERNAME') ) or not (credentials.password == os.getenv('PASSWORD') ):
        #     raise HTTPException(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         detail="Incorrect username or password",
        #         headers={"WWW-Authenticate": "Basic"},
        #     )
        print(params.text)

        preprocessed_text = app.state.plugin_loaded(params.text)
        inputs = app.state.tokenizer(preprocessed_text, return_tensors="pt")
        with torch.no_grad():
            logits = app.state.model(**inputs).logits
        predicted_class_id = logits.argmax().item()
        return {
            "predicted_class_id": app.state.model.config.id2label[predicted_class_id]
        }

    return app


def main():
    app = create_app(args)
    uvicorn.run(
        app, host="0.0.0.0", port=8888
    )  # , reload=True)#does not work with app object


if __name__ == "__main__":
    main()
