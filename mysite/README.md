# how to use label-train-serve in a django project

run db_worker/and site and go to <http://127.0.0.1:8000/>

```sh
python -m django db_worker --settings mysite.settings

# and site
python -m django runserver --settings mysite.settings
```

also

run migrations

```sh
python -m django makemigrations --settings mysite.settings && \
python -m django migrate --settings mysite.settings
```

and collect static (if needed)

```sh
python -m django collectstatic --noinput --settings mysite.settings
```

## create django site

```sh
uvx --from=django@6.0.1 django-admin startproject mysite .
cd mysite/
uv init --python=3.12
uv sync --no-managed-python
uv add "django>=6.0.1"
```

add label-train-serve

```sh
uv add --editable ../label-train-serve
```

add to `urls.py`

```python
urlpatterns = [
    path("", include("label_train_serve.urls")),
```

add to `settings.py`

```python
INSTALLED_APPS = [
    "django_htmx",
    "label_train_serve.apps.DatasetNewConfig",

    "django_tasks",
    "django_tasks.backends.database",
]
```

and

```python
MIDDLEWARE = [

    "django_htmx.middleware.HtmxMiddleware",
]
```

and setup tasks backend

```sh
TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
    },
}
```
