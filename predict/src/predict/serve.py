from typing import Annotated
import os
import json

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import uvicorn


class Params(BaseModel):
    text: str


app = FastAPI()

# # https://fastapi.tiangolo.com/advanced/security/http-basic-auth/#simple-http-basic-auth
# security = HTTPBasic()


# curl -H "Content-Type: application/json" http://0.0.0.0:8888/predict -d '{"text":"foo"}'
@app.post(
    "/predict"  # , response_class=PlainTextResponse)
)
async def predict(
    # credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    params: Params,
):
    print(params)
    # if not (credentials.username == os.getenv('USERNAME') ) or not (credentials.password == os.getenv('PASSWORD') ):
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Incorrect username or password",
    #         headers={"WWW-Authenticate": "Basic"},
    #     )
    print(params.text)

    return {}


def main():
    uvicorn.run("predict.serve:app", host="0.0.0.0", port=8888, reload=True)


if __name__ == "__main__":
    main()
