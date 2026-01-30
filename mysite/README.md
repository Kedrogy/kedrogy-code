# how to use label-train-serve in django project

create django site

```sh
uvx --from=django@6.0.1 django-admin startproject mysite .
cd mysite/
uv init --python=3.12
uv sync --no-managed-python
uv add "django>=6.0.1"
```

run site

```sh
python -m django runserver --settings mysite.settings
```
