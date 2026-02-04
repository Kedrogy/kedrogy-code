from typing import Annotated
import os
import json
import argparse
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import uvicorn

from transformers import AutoTokenizer
import torch
from transformers import AutoModelForSequenceClassification


parser = argparse.ArgumentParser(
    prog="serve",
    description="Serve transformers model",
    epilog="",
)
parser.add_argument("checkpoint")


class Params(BaseModel):
    text: str


def create_app(args):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.checkpoint = args.checkpoint
        print("serving:", app.state.checkpoint)
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
        print("using", request.app.state.checkpoint)
        print(params)
        # if not (credentials.username == os.getenv('USERNAME') ) or not (credentials.password == os.getenv('PASSWORD') ):
        #     raise HTTPException(
        #         status_code=status.HTTP_401_UNAUTHORIZED,
        #         detail="Incorrect username or password",
        #         headers={"WWW-Authenticate": "Basic"},
        #     )
        print(params.text)

        return {}

    return app


def main():
    args = parser.parse_args()
    app = create_app(args)
    uvicorn.run(
        app, host="0.0.0.0", port=8888
    )  # , reload=True)#does not work with app object


if __name__ == "__main__":
    main()
