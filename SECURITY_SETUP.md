# Local and deployment setup

The application remains passwordless for the local diploma demo. SQL validation,
launch restrictions and service credentials do not implement user authentication.

## Run locally

Use the existing `mysite/.venv`, or install the restored workspace with `uv sync --locked`.
Copy `.env.example` to `.env`, supply private values, then load it with `uv run --env-file .env`.
The local setup created during this change has a populated, ignored `.env` already.
Do not publish `.env`, `.local`, generated configuration files, or credential files.

Start the API, queue worker, and three independent reconcilers in separate terminals from the repository root. Port 8002 avoids the other local project currently using 8000:

```sh
mysite/.venv/bin/python scripts/run_local.py api
mysite/.venv/bin/python scripts/run_local.py worker
mysite/.venv/bin/python scripts/run_local.py training
mysite/.venv/bin/python scripts/run_local.py serving
mysite/.venv/bin/python scripts/run_local.py operations
```

Frontend: run `VITE_DEV_API_TARGET=http://127.0.0.1:8002 npm run dev -- --host 127.0.0.1` in `app`. Open `http://localhost:5173`. The default Vite proxy target is port 8002. The local annotation ingress uses `http://label.localhost:8081` in this k3d configuration; set `KEDROGY_ANNOTATION_URL` to that URL in `.env`.

`AppConfig.ready()` no longer changes the database or Kubernetes. Install static
resources explicitly with `kubectl apply -f infra/rbac.json` and
`kubectl apply -f kedrogy/src/kedrogy/templates_k8s/prodigy-svc-ingress.yaml`.
Create the Prodigy schema once with its standard PostgreSQL connector under the
setup account, before provisioning the annotation role. Ordinary annotation uses
the `kedrogy_postgresql` adapter and never creates schema objects.

## Database roles and secrets

`scripts/configure_database.py` requires administrative `PG*` environment variables.
It changes service-role credentials and grants, but does not export or edit records.
Use a **new private output directory for every rotation**; existing credential
files are not overwritten. Keep previous credentials privately until cutover is
verified. Do not run this script during ordinary application startup.

```sh
python scripts/configure_database.py --output-dir .local/credentials-new
```

Roles: `kedrogy_app` (Django/queue DML), `kedrogy_reader` (approved source/annotation
SELECT), `kedrogy_annotator` (annotation DML), `kedrogy_ingest` (source-table owner),
and `kedrogy_migrator` (Django-table owner). They are not PostgreSQL superusers.
The current ingest implementation replaces `all_data`; its owner therefore needs
DDL on that source. Neither the application nor the reader can drop that table.

Add an `admin.env` file to the same private directory for explicit setup and
PostgreSQL initialization, then run `scripts/publish_local_secrets.py` with
`DJANGO_SECRET_KEY` and `KEDROGY_ML_IMAGE` loaded. This helper uses `python-dotenv` from the development
environment. Secret contents go through stdin and are not echoed or placed in
kubectl's last-applied annotation.

```sh
python scripts/publish_local_secrets.py --credentials .local/credentials-new
```

Set `.env` PG variables to the new **app** role and restart Django/worker. Prodigy
and ML workloads obtain their own role from Secret references. Updating a Secret
does not update already running process environments: restart the affected
workload and verify connectivity before retiring previous credentials.
For an existing PostgreSQL volume, changing `POSTGRES_PASSWORD` in a Deployment
is not enough; rotate the actual role password using an administrator connection.

Kedro ingest reads `KEDROGY_INGEST_URL` through the environment. Use the ingest
role's credentials and a correctly encoded SQLAlchemy PostgreSQL URL. This URL
is not needed by the annotation loader or training queries.

## Approved launches

The server controls `KEDROGY_ML_IMAGE`, preferably a digest. The JSON array
`KEDROGY_ML_IMAGE_ALIASES` lists accepted API spellings and does not determine the
actual image launched. The existing `kedrogy-registry:5000/mykedro:latest` spelling
can therefore map to a pinned, reviewed image.

The supported profile uses `workingDir=mykedro`, `pipeline=load_examples`, and
`recipe_options=-l positive,negative` (choose the actual labels). An old full
recipe command is accepted only when its dataset name matches the current record
and its path is `./data/00_examples/examples.jsonl`. A stale recipe referring to
`test3` is deliberately rejected if the Django dataset has another name; it must
be corrected explicitly, not silently redirected to different annotations.

`KEDROGY_SOURCES` maps API source keys to approved schema/table/ID fields. It is
trusted operator configuration, not request data. The default exposes only
`public.all_data`, with ID column `id`. The same mapping is passed into the loader.
The approved preprocessing entry point is `a_preprocess_fun`; empty means none.

New workload Pods use `kedrogy-workload` without a Kubernetes API token. The
controller Role is namespace-scoped and excludes Secret reads and RBAC writes.
A local process needs its own restricted kubeconfig too:

```sh
python scripts/refresh_kubeconfig.py
```

The file `.local/kubeconfig.json` contains a bounded token requested for 24 hours.
Set `KUBECONFIG` to its absolute path in `.env`. Refresh it before a later demo or
when the token expires. The helper uses the user's administrative kubeconfig only
to issue the scoped token; it does not alter the user's current kubectl context.
API authorization and stronger admission restrictions remain separate work.

## Build and verify

Docker uses explicit COPY instructions and `.dockerignore`. Neither Dockerfile
accepts a password through ARG or persistent ENV. Supply package-index credentials
through the environment; `scripts/build_image.py` passes them as BuildKit secrets
and redacts their values from logs. SSH access uses a forwarded agent when needed.
The ML image disables Hugging Face Xet downloads because the current endpoint
returned HTTP 404 during verification; ordinary HTTPS model download succeeded.

```sh
python scripts/build_image.py --dockerfile Dockerfile --tag kedrogy-backend:test --log .local/build/backend.log
python scripts/build_image.py --dockerfile Dockerfile-example --tag kedrogy-ml:test --log .local/build/ml.log
python scripts/audit_image.py kedrogy-backend:test
python scripts/audit_image.py kedrogy-ml:test
```

The image audit checks every layer, not only the merged filesystem. It searches
for private paths and known long secret values from the environment plus original
unique hardcoded secrets. It is not proof that all unknown secrets are absent,
and it does not claim that previously published images have been cleaned.

Regression tests:

```sh
mysite/.venv/bin/python -m django test kedrogy.tests --settings=mysite.test_settings
PYTHONPATH=example/mykedro/src mysite/.venv/bin/python tests/test_config_secrets.py
```

SQL tests in `tests/test_db_queries.py` require a disposable PostgreSQL and
`KEDROGY_TEST_DATABASE=disposable`. They create and truncate synthetic fixture
tables. Never point that test at the working database. Provision-role tests and
Prodigy integration should also use disposable databases initialized from code.

The legacy command URLs reject GET and HEAD with 405. Existing HTML forms use
POST and CSRF. The result polling endpoint is read-only; the annotation task
updates the legacy last-dataset pointer only after a successful rollout.
The meaning of that pointer and the rest of the original audit remain separate
issues; this work is not a complete fix for model #20's missing checkpoint.


## Training lifecycle and recovery

Run database migrations using the migration role before starting the updated API/worker. Runtime processes use the app role. A new training attempt gets its own TrainingRun UUID, Job, immutable ConfigMap and attempt directory. Repeating an `Idempotency-Key` returns the same attempt. A different request while one attempt is active returns HTTP 409.

`trained` is derived from a verified published artifact, not accepted from API requests. Job completion alone does not publish a model. `reconcile_training --watch` runs independently of the queue worker and must remain enabled so interrupted workers do not strand training runs. Its recovery lease lasts at most six minutes per observation step; cluster failures remain retryable until the run deadline. GET task status does not reconcile or mutate state.

The optional legacy check is read-only unless `--apply` is supplied:

```sh
uv run --env-file .env python -m django verify_legacy_models --model 20 --settings mysite.settings_local
uv run --env-file .env python -m django verify_legacy_models --model 20 --apply --settings mysite.settings_local
```

Verification failures require retraining or an explicit trusted artifact migration. They must not be repaired by setting `trained=True`. The published artifact remains available when a later training attempt fails. Keep the approved digests of active runs in `KEDROGY_ML_IMAGE_ALIASES` during an image upgrade.

## Deployment profile

Generate a separate deployment directory; do not overwrite local manifests when preparing another environment:

```sh
python scripts/render_infrastructure.py --profile deploy \
  --backend-image "$BACKEND_IMAGE_DIGEST" --web-image "$WEB_IMAGE_DIGEST" \
  --app-host app.example.com --label-host label.example.com \
  --tls-secret kedrogy-tls --trusted-proxy-cidrs "$TRUSTED_WEB_PROXY_CIDRS" \
  --output-dir .local/deploy
```

Use actual registry references ending in `@sha256:...`, not `:latest`. For local k3d, the host pushes to `kedrogy-registry.localhost:5500`; Pods use `kedrogy-registry:5000`. Build the web image with the matching backend image so collected Django static comes from the same release:

```sh
docker build -f Dockerfile-web --build-arg BACKEND_IMAGE="$BACKEND_BUILD_REFERENCE" -t "$WEB_BUILD_REFERENCE" .
```

The generated profile explicitly selects `mysite.settings_deploy` for migration, API, worker and reconciler. It requires the usual database/config Secrets plus a TLS Secret for both hosts. Install the generated `mysite.yaml` and `infra/web.json` in the intended namespace; `postgres.yaml` uses ClusterIP in this profile. The ingress definitions target the existing k3d Traefik installation and its `traefik.io` CRDs. Another ingress controller requires equivalent controller-specific routing and redirect configuration.

NetworkPolicies require enforcement by the cluster's network plugin. Adapt the Traefik namespace/pod selectors if the ingress controller lives elsewhere. Only trusted ingress traffic reaches the web proxy in deployment; the proxy overwrites forwarding headers. Django accepts its HTTPS claim only from the explicitly configured proxy network. Never set that network to `0.0.0.0/0` or disable Uvicorn's `--no-proxy-headers` without reevaluating this trust boundary.

Verify enforcement with an untrusted Pod connecting directly to both the backend and web Services while legitimate HTTPS requests still succeed. Successful manifest application alone is insufficient. During local acceptance, a Docker restart left the embedded controller without per-Pod firewall chains; restarting the existing k3d node restored enforcement. The repeat checks and the incident are recorded in `reports/2026-09-24-implementation/network-runtime.json` and the implementation report. The isolated-fixture probe is `scripts/check_network_runtime.py`; adapt its explicit namespace and evidence paths before using an equivalent check in another environment.

`/` serves React, `/api/` serves the API, `/admin/` and `/static/` serve the Django UI, and `/legacy/` opens the legacy homepage. Prodigy has a separate host. `/health/` returns a minimal liveness response; it is intentionally not a database/cluster diagnostic endpoint.

HSTS starts at zero; set `DJANGO_HSTS_SECONDS` only after validating real TLS and domain routing. Preload and includeSubDomains remain off. Run `django check --deploy --settings mysite.settings_deploy` with the actual deployment environment. W004 is the documented HSTS staging exception, not a silenced check.

No user authentication is introduced by this profile. Keep the current passwordless deployment restricted to the local/private demonstration environment until the deferred access-control work is complete.

Tilt generates its own local manifests under `.local/tilt` and uses the host/cluster registry mapping supported by [Tilt default_registry](https://docs.tilt.dev/api.html#api.default_registry). It forwards the backend to local port 8002. The committed manifests can therefore stay pinned independently of Tilt development builds.

In the shell-based local workflow, restart `db_worker` and `reconcile_training --watch` if the database/cluster is restarted and their connections terminate. Kubernetes supervises the corresponding processes in the generated deployment.


## Annotation and cleanup operations (13–16)

Annotation data observations are independent of session health. The operations
reconciler batches up to five dataset identity/count observations per pass and
validates at most `KEDROGY_MAX_ANNOTATIONS` records per dataset. GET and HEAD do not
enqueue work. Use Refresh data counts to request an observation; old counts are
marked UNKNOWN after five minutes. Counts describe stored answers, not unique
texts or the suitability of a dataset for a particular model.

Each namespace permits one managed annotation session. Stop it before switching
datasets. Configuration, image and resource identities are pinned to the run.
A failed startup retains the slot until Stop has disconnected routing and removed
the session's Pods. Existing unmanaged `Deployment/prodigy` is never adopted or
stopped automatically: inventory it and resolve its ownership before managed
annotation is used. The legacy `DjangoLastDataset` table is retained only for
migration compatibility and is no longer an application status source.

Deletion requires a fresh signed preview. Delete all model files removes every
checkpoint version on the listed volume; Delete model and Delete dataset retire
application records after cleanup. Run history and deletion receipts remain.
Dataset deletion preserves saved annotations by default. The separate Retained
annotations screen offers explicit cleanup of one verified Prodigy binding.
Source rows and associated session datasets are preserved.

A cleanup reservation remains active during RUNNING, RETRY_WAIT and NEEDS_REVIEW.
Open unfinished cleanup from the model or dataset to inspect it. Retry the same
operation after resolving a transient outage or volume consumer; changing the
reviewed resource UID or annotation fingerprint requires operator investigation,
not automatic adoption. Never clear `resources_deleting` manually or remove PVC
protection finalizers to force success. A disappeared annotation cleanup Job with
an unrecorded outcome also requires review: absence alone does not prove success.

```sh
# Read-only; does not replay historical tasks or delete discovered resources.
uv run --env-file .env python -m django operation_inventory --resources --settings=mysite.settings_local
```

The local worker launcher restarts a crashed worker after five seconds; it does
not requeue old RUNNING deliveries. Watch-mode reconcilers reconnect after a
Django database outage. Kubernetes runs them as restartable sidecars. Domain
operation status remains authoritative over a queue delivery's result.

Defaults: annotation startup 600 seconds; annotation health freshness 45 seconds;
data freshness 300 seconds; cleanup attempt deadline 900 seconds. Configure with
`KEDROGY_ANNOTATION_TIMEOUT`, `KEDROGY_ANNOTATION_FRESHNESS`,
`KEDROGY_ANNOTATION_DATA_FRESHNESS` and `KEDROGY_CLEANUP_TIMEOUT`.

After restarting Docker/K3s, verify actual network denial and a legitimate HTTP
request. A successfully installed NetworkPolicy is not proof that the local node's
firewall chains are functioning; this environment has required a node restart.
