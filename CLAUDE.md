# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

Copy `.env.example` to the ignored `.env` file and configure service credentials. Use the setup and role instructions in [SECURITY_SETUP.md](SECURITY_SETUP.md). Install the locked workspace dependencies:

```sh
uv sync --locked
```

PostgreSQL is required. The database connection is configured entirely via `PG*` environment variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).

On macOS, building psycopg2 requires:
```sh
export LDFLAGS="-L/opt/homebrew/opt/openssl/lib"
export CPPFLAGS="-I/opt/homebrew/opt/openssl/include"
```

## Commands

### Backend (Django)

Select local or deployment settings explicitly. Local service commands load the ignored environment file:

```sh
uv run --env-file .env python -m django runserver --settings mysite.settings_local
uv run --env-file .env python -m django migrate --settings mysite.settings_local
uv run --env-file .env python -m django db_worker --settings mysite.settings_local
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
2. **Train** — runs a Kedro pipeline as a Kubernetes Job to train a Hugging Face text classifier using explicit class choices, then verifies the saved model, tokenizer and class mapping
3. **Serve** — deploys the trained model via `ysz-predict` (FastAPI) as a Kubernetes Deployment for inference

### Key Backend Components

**`kedrogy/src/kedrogy/tasks.py`** — `django-tasks` entry points for persisted annotation, training, serving and cleanup operations. The lifecycle modules coordinate state, leases, resource ownership and reconciliation. The bounded Kubernetes adapter preserves safe diagnostics and checks actual outcomes.

**`kedrogy/src/kedrogy/manifests.py`** — structured Kubernetes document builders. The former dynamic Jinja workload templates were replaced with serialized documents and server-validated launch configuration.

**`kedrogy/src/kedrogy/models.py`** — datasets and models plus durable TrainingRun, ServingRun, AnnotationSession and deletion state. Display names are separate from stable annotation/source identities. Legacy compatibility fields do not replace verified run/artifact status.

**`mysite/src/mysite/settings_base.py`** — shared settings including database-backed tasks. `settings_local.py` and `settings_deploy.py` select explicit runtime profiles; isolated test settings avoid working-cluster access.

### Frontend / API Boundary

The React SPA (`app/`) uses the Django REST API in `kedrogy/api_urls.py`, mounted under `/api/`:
- `GET /api/datasets/<id>/` — dataset details
- `POST /api/models/<id>/train/` and `POST /api/models/<id>/serve/` — start tasks
- `GET /api/tasks/<task_type>/<result_id>/status/` — poll validated task outcomes

The legacy Django UI uses HTMX for polling task results and Alpine.js for interactivity.

### Kubernetes Dependency

Workflow controllers require a scoped Kubernetes connection. Application import and isolated checks do not bootstrap resources or require the working cluster. For local setup, consult [HACKING.md](HACKING.md), [SECURITY_SETUP.md](SECURITY_SETUP.md) and [SOURCE_AND_MODEL_CONTRACTS.md](SOURCE_AND_MODEL_CONTRACTS.md). Frontend styles are bundled by Vite from the installed Tailwind/DaisyUI packages.
