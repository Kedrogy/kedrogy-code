# Implementation of audit findings 05–08

Date: 2026-09-24. Scope: the approved `PLAN_FIXES_05_08_EN.md`. Login/password protection remains deferred. This report concerns these four findings, not all findings in the original project audit.

All four planned implementation areas are complete and checked in the local workspace. The application is running at `http://localhost:5173` with its API on loopback port 8002. The deployment profile was exercised in an isolated namespace; no public deployment was made. Model 20 remains unusable until its checkpoint/configuration is repaired or it is successfully retrained.

## 05 — Read-only HTTP operations

The legacy prediction endpoint now requires POST, matching the other state-changing legacy actions. GET/HEAD cannot start a process, enqueue a task, change a model flag, or execute inference through these routes. CSRF protection remains enabled for legacy forms. Terminal result pages render persisted results without updating training flags or accessing the return value of a failed queue task.

The localized URL namespace is `kedrogy_i18n`; existing URLs and the ordinary `kedrogy` namespace remain available. This removes the duplicate-namespace system warning. Legacy result pages stop polling after failures and do not show the former success message.

Evidence: backend HTTP regression tests, read-only database comparisons, process/enqueue guards, real HEAD and CSRF rejection checks through HTTPS.

## 07 — Bounded operations and truthful task results

`kubernetes.py` is the shared execution boundary. Commands use argument lists and structured JSON on stdin. Both output pipes are drained concurrently into bounded tails; JSON responses have a stricter size limit and fail rather than parsing truncated data. Every operation has a deadline. Timeout and exceptional exits terminate the process group, reap the child, and close pipes. Temporary stdin is unlinked automatically.

Prediction uses a loopback-only, OS-assigned port-forward with a context manager. HTTP calls have connection/read timeouts, validate the prediction type, and return public error codes. This change does not implement the full serving lifecycle from finding 09.

Failed queue results never access `return_value`. Public task data contains only approved summaries and error messages; legacy raw logs and tracebacks are not returned. External command failures record a classification, exit code and duration. Arbitrary stderr is deliberately not persisted because it can contain rejected manifests and credentials. Operators retain access to Kubernetes events/logs under their existing administrative permissions. Application logging filters known secrets and credential-bearing URLs.

The four React task pages share a checked status contract and polling hook. Polling is sequential, stops on terminal results, aborts on navigation, and has a 15-second request timeout. A network/protocol error offers an explicit retry. A result from a previous route cannot appear as the current task's result. FAILED/TIMED_OUT/INTERRUPTED have distinct failure treatment; only SUCCEEDED displays completion. The model page separates the published verified model from the latest training attempt.

## 08 — Durable training and verified artifacts

Migration `0010_djangomodel_artifact_status_trainingrun_and_more` adds `TrainingRun`, a published-run reference and artifact status. It is additive and was applied first to disposable PostgreSQL and then to the working database. Existing records and model volumes were not deleted or copied into test fixtures.

A run stores an immutable launch snapshot, labels, image, options, idempotency key, namespace, unique Job name/UID, attempts, timestamps, lease, public error and artifact receipt. A database partial unique constraint permits only one active run per model. Model row locking serializes concurrent requests; repeated idempotency keys return the original run.

Run creation and queue insertion use one PostgreSQL transaction. The installed `DatabaseBackend` writes the queue row on the same database connection, so this avoids the gap between committing a run and an `on_commit` enqueue failure. This guarantee requires retaining the database-backed queue; a future external queue would require an outbox or equivalent change.

Each run has a distinct Job and immutable ConfigMap. Each Pod attempt writes under `runs/<run UUID>/<Pod UID>/`. Training saves to a temporary directory, reloads the tokenizer and safetensors checkpoint offline, checks both label mappings, executes a finite forward pass, computes SHA-256 hashes, writes a manifest, and atomically renames the artifact directory.

A completed training Job is only an intermediate state. A separate Job mounts the volume read-only and independently loads and verifies the checkpoint. Its bounded receipt must match the run, successful training Pod UID, image, labels, path and hashes. Only then is the run SUCCEEDED and the model's published pointer updated. Failed retraining leaves the previous published artifact available. Serve receives this explicit artifact path and rejects models without a verified publication.

Reconciliation is leased and can run independently of queue workers through `reconcile_training --watch`. It observes existing Job UIDs instead of reapplying/restarting an old Job. Lost/replaced Jobs, failed verification, deadlines and prolonged cluster unavailability cannot become successful training. Deadline deletion includes a Kubernetes UID precondition. Model/dataset record deletion is serialized with training requests and rejects active runs, including cascading dataset deletion.

The actual Kedro pipeline was exercised with synthetic PostgreSQL annotations and a real tiny BERT classifier. All four pipeline nodes ran, including training, saving and the independent verification Job. This proves the integration and artifact protocol; it is not a quality evaluation of the multilingual production model or the user's dataset. The data split now uses the saved data seed, and the image creates the intermediate directories required by the installed datasets package.

## 06 — Local/deployment boundary

Settings are split into base, local and deployment profiles. `mysite.settings` remains a compatibility alias for local development. Deployment rejects DEBUG, weak/missing required configuration, wildcard and `testserver` hosts, and unrestricted proxy networks. It requires explicit HTTPS origins and uses secure session/CSRF cookies.

The generated deployment explicitly selects the profile for migration, Uvicorn, worker and reconciler. Uvicorn runs with `--no-proxy-headers`; Django trusts forwarding claims only from configured networks. The web proxy overwrites forwarding headers. Deployment NetworkPolicies restrict backend ingress to the web proxy and web/annotation ingress to Traefik. PostgreSQL is ClusterIP in deployment; the existing local database access remains in the local profile.

`Dockerfile-web` builds React and serves its assets plus collected Django static through Nginx. API, admin, legacy forms and frontend routes are routed explicitly; `/legacy/` opens the old index. App and Prodigy use distinct named hosts. The old hostless annotation ingress was replaced with `label.localhost` for the local cluster. No public domain or Internet deployment was created.

The API error boundary covers DRF errors, routing, Host validation, middleware and unexpected 500 responses. Responses contain a safe code/message and request ID, with validation fields where applicable. No debug traceback is sent to clients.

A disposable deployment used `app.kedrogy.test` and `label.kedrogy.test`, an ephemeral local certificate, the real k3d Traefik ingress, Nginx, Uvicorn, worker/reconciler and a separate synthetic Prodigy database. TLS was verified against that certificate rather than disabled. The certificate was not installed in the system trust store.

`django check --deploy` reports only W004 for HSTS duration zero. HSTS is intentionally staged until a real domain and valid long-lived TLS configuration are selected; preload and includeSubDomains are not enabled. No system checks were silenced.

## Working-data observations

- Model 20 was checked by a read-only verifier Job. It did not produce a valid checkpoint receipt; its artifact status is now INVALID and `trained` is false. Its files were not overwritten and it was not retrained on unknown labels. The original Prediction failed issue must not be declared solved by these changes.
- One March 2026 legacy training queue record was still RUNNING although its local worker no longer existed. After verifying its task identity, arguments and start date, it was marked failed with `LEGACY_INTERRUPTED`. No old training or serving resources were deleted.
- Other existing models remain UNVERIFIED until explicitly checked or successfully retrained. Their old Boolean flags are not treated as proof of a usable artifact.

## Reproduction and evidence

| Check | Result |
| --- | --- |
| Backend HTTP, task, training and deployment tests | 42 passed |
| Real PostgreSQL concurrency and transaction rollback tests | 3 passed |
| Offline model/tokenizer verification tests | 5 passed |
| Frontend runtime-contract tests | 10 passed |
| React TypeScript/Vite build | Passed |
| Actual HTTP/TLS routes and error responses on final images | 14 passed |
| Direct backend Service, backend Pod and web Service connections from an untrusted Pod | All 3 blocked; legitimate HTTPS routes still passed |
| Real prediction tunnel after an HTTP transport failure | Child reaped and both pipes closed |
| Worker SIGKILL and independent recovery | SUCCEEDED; original Job UID preserved |
| Migration consistency and ordinary Django system checks | No pending model changes or system-check issues |
| Deployment Django system checks | Only the documented HSTS W004 warning |
| Focused Ruff checks and `git diff --check` | Passed |

Browser checks covered a failed task with a safe reason, successful completion, unknown-task retry, a previously published model surviving failed retraining, and Serve being disabled for the invalid working model 20. These checks complement the 60 automated tests above; they do not represent a complete accessibility or cross-browser audit.

Fast backend suite:

```bash
mysite/.venv/bin/python -m django test \
  kedrogy.tests kedrogy.test_operations kedrogy.test_training kedrogy.test_deployment \
  --settings mysite.test_settings
```

PostgreSQL concurrency suite requires explicitly disposable PG variables and never reads the working database:

```bash
KEDROGY_TEST_DATABASE=disposable mysite/.venv/bin/python -m django test \
  kedrogy.test_training_concurrency --settings mysite.test_postgres_settings --noinput
```

Offline checkpoint and frontend contract checks:

```bash
PYTHONPATH=example/mykedro/src example/.venv/bin/python -m unittest discover -s tests -p test_artifacts.py
cd app
node --experimental-strip-types --test tests/task-contract.test.mjs
npm run build
```

Runtime evidence is recorded beside this report in `training-runtime.json`, `http-runtime.json`, `worker-recovery.json`, `network-runtime.json`, `tunnel-runtime.json`, `checks.json`, `release-images.json` and `image-audit.json`. Fixture scripts under `scripts/check_*` are for the isolated `kedrogy-check-20260924` namespace and the disposable `reliability` database; they are not production setup commands. They intentionally require private generated fixture configuration and do not copy working records. `scripts/reliability_fixture.py` creates a fresh fixture namespace/schema and refuses conflicting existing resources.

## Problems encountered during acceptance

Docker stopped during concurrent image export/build activity. The full-layer secret scan was cancelled; the final three images were checked against six known private values in their metadata and build history only, with no matches. This is explicitly not a full filesystem/layer-clean claim. Final image digests are recorded in `release-images.json`.

The real worker-crash run also crossed that Docker/database outage. After the persisted lease expired, an independent reconciliation process observed the original Job, launched verification and published the matching artifact. Earlier fixture attempts exposed interference from a still-running test reconciler and an overly short 300-second deadline under contention; their results are retained in `worker-recovery.json` rather than counted as successful runs.

A direct-access probe initially bypassed NetworkPolicy after Docker restarted. Inspection showed missing per-Pod firewall chains. Restarting the existing local k3d node restored those chains; all three denial probes and the 14 legitimate HTTP/TLS checks then passed. No cluster or volume was recreated. The precise controller failure was not established; policy enforcement must be tested on the intended deployment cluster rather than inferred from successful manifest application. K3s documents its [embedded network-policy controller](https://docs.k3s.io/networking/networking-services).

The final fixture rollout also caught an incorrectly formatted test image-allowlist value; it was corrected to a JSON array. A Prodigy route was initially checked before its startup pipeline completed and returned 404. Once its endpoint was ready, the route passed. These fixture failures were not hidden by weakening the production checks.

## Final local state and cleanup

The disposable namespace, its Jobs/PVCs/Secrets and the synthetic PostgreSQL container/volume were removed after evidence collection. Test API/frontend listeners and temporary tunnels were stopped. Generated fixture credentials, runtime settings and the test TLS key/certificate were removed from `.local`.

The working database, original model volumes and historical resources remain in place. React is running on port 5173, the API on loopback port 8002, and the local queue worker and independent reconciler were restarted. A final request through the frontend proxy returned model 20 as `artifact_status=INVALID`, `trained=false`, `served=true`. That last flag is the existing stale serving flag covered by finding 09, not evidence of a usable inference service. No login/password was introduced.

## Deliberate limits and follow-up work

- Authentication is still deferred as requested. A deployment profile and TLS do not make the application suitable for unrestricted public access.
- Full inference readiness, serving recovery, stale served flags and the original model-20 prediction failure belong to finding 09 and remain separate work.
- Legacy import supports safely loadable safetensors checkpoints. Old pickle/bin-only checkpoints are not silently deserialized; retrain or explicitly migrate them through a trusted offline process.
- Full resource deletion/retention, storage quotas and cleanup of historical Jobs/PVCs remain separate lifecycle work. This implementation prevents deleting records during active training; it does not redesign every concurrent serving/deletion operation.
- Image admission remains an operator-controlled allowlist. When changing the approved image, keep digests needed by active runs in the allowlist until they finish. Saved runs never silently switch their image.
- The test classifier demonstrates mechanics, not prediction accuracy. Training data, class balance, evaluation metrics and the OTHER-label redesign remain separate ML work.
- External Prodigy/YSZ credential rotation from finding 04 still requires the credential owner's action. This implementation does not claim those external credentials were rotated.
- The repository's existing broad dependency/audit findings remain outside 05–08. In particular, the frontend build reports dependency advisories, and the pre-existing `npm run lint` command has no ESLint configuration; TypeScript build, focused contract tests and browser checks were used here.
- Tilt configuration was updated, but `tilt up` was not executed because Tilt is not installed on this machine. The local application and the generated deployment manifests were run directly.
- The containerized worker and reconciler are supervised by Kubernetes. For the documented local shell workflow, restart those processes if their database connection terminates during a database/cluster restart; this was done after the acceptance outage.
