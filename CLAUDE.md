# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

Copy `.env-example` to `.env`, fill in credentials, then:

```sh
export $(cat .env | sed '/^#/d')
uv sync --all-packages --dev --no-managed-python
```

PostgreSQL is required. The database connection is configured entirely via `PG*` environment variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).

On macOS, building psycopg2 requires:
```sh
export LDFLAGS="-L/opt/homebrew/opt/openssl/lib"
export CPPFLAGS="-I/opt/homebrew/opt/openssl/include"
```

## Commands

### Backend (Django)

All Django commands use `--settings mysite.settings` and require `PG*` env vars set:

```sh
python -m django runserver --settings mysite.settings
python -m django migrate --settings mysite.settings
python -m django db_worker --settings mysite.settings   # background task worker
```

### Frontend (React SPA)

```sh
cd app && npm run dev      # dev server (Vite)
cd app && npm run build    # production build
cd app && npm run lint     # ESLint
```

### Local Kubernetes (Tilt)

```sh
tilt up
```

### Django + Jupyter

```sh
cd notebooks && python -m django shell_plus --notebook --settings mysite.settings
```

### HTML template linting

```sh
djlint kedrogy/src/kedrogy/templates/
```

## Architecture

This is a **uv workspace monorepo** with these packages:

- `kedrogy/` — reusable Django app (published to pypi.ysz.vc); the core ML workflow orchestrator
- `mysite/` — Django project that installs `kedrogy` and configures settings/URLs
- `app/` — React 19 SPA (Vite + TypeScript + Tailwind v4 + DaisyUI)
- `predict/` — FastAPI prediction service (`ysz-predict`), deployed as a K8s Deployment to serve trained models
- `example/` — reference Kedro project (`mykedro`) and custom Prodigy recipes (`myrecipes`)

### ML Workflow Lifecycle

Kedrogy manages three phases for NLP model development:

1. **Label** — deploys a [Prodigy](https://prodi.gy) annotation server as a Kubernetes Deployment so users can annotate data
2. **Train** — runs a Kedro pipeline as a Kubernetes Job to train a spaCy model using labeled data
3. **Serve** — deploys the trained model via `ysz-predict` (FastAPI) as a Kubernetes Deployment for inference

### Key Backend Components

**`kedrogy/src/kedrogy/tasks.py`** — `django-tasks` background tasks that orchestrate K8s operations. Each task runs `kubectl apply` on a rendered Jinja2 manifest, then streams logs back via `context.metadata["logs"]` (polled by HTMX in the UI).

**`kedrogy/src/kedrogy/templates_k8s/`** — Jinja2 templates for K8s manifests: `prodigy.yaml.jinja` (labeling), `train.yaml.jinja` + `pvc.yaml.jinja` (training), `serve.yaml.jinja` (serving).

**`kedrogy/src/kedrogy/models.py`** — Three models: `DjangoDataset` (stores image, workingDir, Kedro pipeline, Prodigy recipe options), `DjangoModel` (FK to dataset, labels, trained/served status), `DjangoLastDataset` (tracks active Prodigy deployment).

**`mysite/src/mysite/settings.py`** — Configures `django-tasks` with `DatabaseBackend` (tasks stored in PostgreSQL). The `DJANGO_SETTINGS_MODULE` is `mysite.settings`.

### Frontend / API Boundary

The React SPA (`app/`) mirrors the Django HTML view flow and communicates with JSON API endpoints under `kedrogy/urls.py` (prefixed `/api/`):
- `GET /api/datasets/<id>/` — dataset details
- `POST /api/models/<id>/train/` and `POST /api/models/<id>/serve/` — start tasks
- `GET /api/train/result/<result_id>/` and `GET /api/serve/result/<result_id>/` — poll task status

The legacy Django UI uses HTMX for polling task results and Alpine.js for interactivity.

### Kubernetes Dependency

The Django server and tasks worker must run inside (or with access to) a K8s cluster — `tasks.py` shells out to `kubectl` directly. For local development, use `k3d` (see `HACKING.md` for cluster setup) and `tilt up`.
