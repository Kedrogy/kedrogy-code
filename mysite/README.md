# how to use kedrogy in a django project

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

migrate/create superuser once if needed

```sh
python -m django createsuperuser --no-input --settings mysite.settings
# to delete superuser 
psql -c "delete from auth_user where username='superuser';"
```

## create django site

```sh
uvx --from=django@6.0.1 django-admin startproject mysite .
cd mysite/
uv init --python=3.12
uv sync --no-managed-python
uv add "django>=6.0.1"
```

add kedrogy

```sh
uv add --editable ../kedrogy
```

add to `urls.py`

```python
urlpatterns = [
    path("", include("kedrogy.urls")),
```

add to `settings.py`

```python
INSTALLED_APPS = [
    "django_htmx",
    "kedrogy.apps.DatasetNewConfig",

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
