#

example usage from .venv of `../example`

```sh
> serve ../example/mykedro/data/06_models/best/ -p a_preprocess_fun
preprocess arg: a_preprocess_fun
using plugin a_preprocess_fun
preprocess_fun hello
INFO:     Started server process [15411]
INFO:     Waiting for application startup.
serving: ../example/mykedro/data/06_models/best/
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8888 (Press CTRL+C to quit)
using ../example/mykedro/data/06_models/best/
text='Hello, world'
Hello, world
preprocess_fun Hello, world
INFO:     127.0.0.1:49499 - "POST /predict HTTP/1.1" 200 OK
^CINFO:     Shutting down
INFO:     Waiting for application shutdown.
Shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [15411]

```

and request like that

```sh
> curl -H "Content-Type: application/json" http://0.0.0.0:8888/predict -d '{"text":"Hello, world"}'
{"predicted_class_id":"OTHER"}
```
