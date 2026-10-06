# Kedrogy: remaining issues after fixes 2–16

Audit date: 26 September 2026. Scope: the current working copy, including the uncommitted implementation work. This is an audit, not another implementation stage. Application source, working records, annotations and Kubernetes resources were not changed.

The project has improved substantially: operation records, stable annotation bindings, validation, artifact verification and controlled cleanup are present and covered by tests. Nevertheless, the current implementation still has **30 actionable findings: 4 P1, 21 P2 and 5 P3**. Several are older issues outside the completed scope; others are gaps in the new lifecycle implementation. The most important remaining risks are serving-resource ownership, delayed workers overwriting newer serving state, incorrect training targets, and destructive source ingestion.

Authentication remains explicitly deferred at the user's request. It is not included in these 30 findings. No claim of safe public deployment is made.

## Evidence and limits

| Check performed in this audit | Result |
| --- | --- |
| Existing Django domain/API/transport/deployment tests | 86 passed |
| Existing TypeScript runtime-contract tests | 15 passed |
| Existing ML/artifact/configuration tests | 11 passed |
| Existing PostgreSQL query test module | 4 skipped: no disposable PostgreSQL available |
| New audit probes | 13 Django cases, 5 ML cases and 1 real synthetic subprocess case reproduced the asserted defects |
| Frontend production build | TypeScript and Vite passed |
| Frontend lint | Failed before checking files: ESLint configuration is missing |
| Django migration drift | No changes detected |
| Python syntax | 124 project/test/script files parsed without syntax errors |
| Whitespace check | `git diff --check` passed |
| Local frontend | HTTP 200 on port 5173 |
| Local backend | `/health/` returned 200; dataset/model APIs returned 500 |
| Local infrastructure | Docker socket unavailable; logs show PostgreSQL connection refused on port 30001 |

**112 existing tests passed in this audit, not 122.** The previous stage's 10 real PostgreSQL concurrency cases were not rerun because Docker was unavailable. The new audit probes intentionally assert defective behavior: their passing does not mean the product is correct. The deterministic lifecycle probes use real Django records in an in-memory database and mocked Kubernetes boundaries; they establish the faulty control flow, not a new live-cluster reproduction.

Reviewed areas include Django APIs and legacy views, serializers and data models, training/serving/annotation/deletion controllers, ML conversion/training/inference, React pages and task polling, Kubernetes manifests, Docker/packaging configuration, setup scripts and test/workflow coverage. Generated bundles, every notebook and third-party internals were not exhaustively audited. Relevant installed Transformers initialization code was inspected for R17.

Live Kubernetes ownership, network policies, current annotation counts and a new full training cycle could not be reverified. Historical inventory from the previous implementation report is explicitly historical. No database export or working-data browser session was used.

A fresh npm vulnerability scan was blocked by automatic approval review because it would send dependency names and versions to the public registry. No workaround was attempted. Earlier advisory counts are **not** presented as current results. A fresh Python vulnerability scan and a clean Docker dependency rebuild were also not completed.

## Priorities and index

P1 means a substantial correctness or data-integrity problem to resolve before relying on the main workflow. P2 means a material reliability, quality, usability or operational problem. P3 is lower-priority correctness or handoff work. “Reproduced” refers to the attached isolated probes unless explicitly marked as a live observation; “source” means the mechanism is confirmed in code but was not exercised end to end.

| ID | Priority | Remaining issue | Evidence |
| --- | --- | --- | --- |
| R01 | P1 | Serve can overwrite an unrelated Deployment or Service | Reproduced |
| R02 | P1 | A delayed serving worker can write after Stop and a newer launch | Reproduced |
| R03 | P2 | Annotation resources can appear after Stop has released its slot | Reproduced |
| R04 | P2 | Normal inference contention makes a healthy model unavailable | Reproduced |
| R05 | P2 | One inference exception permanently disables the process | Reproduced |
| R06 | P2 | Streaming response errors escape prediction error handling | Reproduced |
| R07 | P2 | Retrying a failed annotation-cleanup Job cannot recover it | Reproduced |
| R08 | P2 | Stopping the local supervisor leaves its worker alive | Reproduced with real synthetic processes |
| R09 | P2 | Backend readiness stays green while its database is down | Live HTTP plus source |
| R10 | P2 | Sequential health checks can make unrelated services stale | Source |
| R11 | P1 | Rejecting a wrong label becomes a false OTHER target | Reproduced |
| R12 | P2 | Active-learning suggestions still come from a random dummy model | Source |
| R13 | P2 | Annotation exhausts its input after five examples | Source |
| R14 | P1 | Re-ingestion replaces the source table and reassigns IDs | Source; destructive path not run |
| R15 | P2 | Source changes can reuse incompatible annotation identities | API acceptance reproduced; SQL mechanism inspected |
| R16 | P2 | Training accepts leakage, missing classes and misleading evaluation | Reproduced plus source |
| R17 | P2 | The training seed is applied after classifier initialization | Source and installed Trainer inspection |
| R18 | P2 | Heavy workloads have no CPU/memory budgets or retention policy | Source |
| R19 | P2 | List endpoints have N+1 queries and unbounded history loading | Query counts reproduced |
| R20 | P3 | Training history marks stopped serving revisions as served | Reproduced |
| R21 | P2 | Several UI mutations can hang or create duplicate drafts | Source |
| R22 | P2 | Home/dataset error state remains misleading after recovery | Source |
| R23 | P2 | Production styling depends on external, mismatched CDN assets | Built output and source |
| R24 | P2 | Regression checks are not enforced; a database test has rotted | Lint failure, signature probe and workflow inspection |
| R25 | P3 | Fresh-install instructions assume a pre-existing environment | Source |
| R26 | P2 | Main navigation and rename actions are inaccessible by keyboard | Source |
| R27 | P3 | Home hides model names and IDs, making models indistinguishable | Source |
| R28 | P3 | Annotation startup can succeed after its configured deadline | Reproduced |
| R29 | P2 | Logout reports success without ending the Django session | Reproduced |
| R30 | P3 | Cleanup accepts JSON parsing but crashes on a non-object body | Reproduced |

## Lifecycle and inference

### R01 — Serve overwrites resources without proving ownership

Location: `kedrogy/src/kedrogy/serving.py:121` (`_put`) and `:154` (`_advance`).

When a Deployment exists with a different `kedrogy/serving-id`, `_advance` calls `_put`. `_put` copies the existing UID and resourceVersion, adopts its selector, and replaces the object. The Service path has the same absence of an ownership guard. Thus a matching `serve-{model_id}` name is sufficient to modify an unrelated or historical workload. This is inconsistent with deletion's conservative ownership checks.

The isolated probe supplied a Deployment owned by another application. The resulting command was `replace` using that foreign UID, with no rejection.

**Fix:** require recorded ownership and exact identity before updating an existing resource. Treat historical adoption as an explicit reviewed action. Prefer unique revision resources and a separately controlled route. **Acceptance:** an unrelated same-name Deployment/Service is unchanged and Serve returns a visible identity conflict.

### R02 — Database ownership checks do not fence late serving writes

Location: `serving.py:97`, `:121`, `:154`.

`_owned` does not check lease expiry. More importantly, there is a gap between its check and external mutation. A paused worker can pass that check, lose its lease, have its run stopped, and resume after a new revision starts. `_put` then obtains the *current* Kubernetes resourceVersion, so its replacement is not rejected as stale. It can replace the newer Deployment or reroute its Service to the old revision. Conditional database observations do not undo that external write.

The deterministic probe advances the database to a newer serving revision at this boundary and confirms that the old worker still sends both resource writes. A separate probe confirms that an expired lease still passes `_owned`.

**Fix:** use revision-specific resources and a route update protected by a version captured before the ownership check, or an equivalent external fencing mechanism. Include lease validity but do not treat another database check alone as sufficient. **Acceptance:** deliberately pause an old owner, complete Stop/new Serve, then release it; the new resource spec and route must remain unchanged.

### R03 — A stopped annotation run can leave newly created resources behind

Location: `annotation.py:195` and its `_ensure` calls.

The per-document ownership check precedes the external create. An old owner paused in that gap can resume after another owner completes Stop and clears the slot. Its Deployment or ConfigMap is then created for a run already marked STOPPED. STOPPED runs are no longer reconciled, so the object is stranded. The route fence prevents the old run from taking over shared routing; it does not fence creation of these objects.

The probe reproduced a Deployment creation after the database run became STOPPED and the annotation slot became empty. It does not claim that this orphan Pod successfully starts: its ConfigMap may already have been removed.

**Fix:** add a safe cleanup/ownership protocol for creations that race with Stop, including observation of stopped-run resources. **Acceptance:** delayed creates after Stop are rejected or subsequently removed, while resources belonging to a newer run remain untouched.

### R04 — A busy model is misclassified as unhealthy

Location: `prediction.py:53`, `serving.py:advance_serving`, and `predict/src/ysz/predict/serve.py:170`.

Every serving observation performs a real prediction after `/readyz`. The inference process has one execution slot. If a user prediction occupies it, the health prediction receives HTTP 429. This becomes `PREDICTION_BUSY`, which the serving controller stores as UNAVAILABLE. Django then rejects user predictions before trying the service, until a later observation succeeds. Normal contention therefore causes a wider outage and can make the first request's final revision check fail.

**Fix:** distinguish saturation from unhealthy state; avoid competing with users for periodic health checks or preserve a fresh READY observation on a busy response. **Acceptance:** a long valid prediction overlapping a health check leaves the model ready, and only genuinely excess requests receive 429.

### R05 — One runtime inference exception causes a permanent outage

Location: `predict/src/ysz/predict/serve.py:170` and `manifests.py:serving`.

A runtime exception sets `app.state.ready = False`. Future predictions reject immediately; there is no reload or retry transition. Meanwhile `/livez` continues returning 200, so the configured Kubernetes liveness probe does not restart the process. A recoverable one-off exception can therefore leave the instance unavailable until an operator recreates it.

The synthetic inference function failed once and would have succeeded on its next call. The second request was rejected without calling it; readiness returned 503 while liveness returned 200.

**Fix:** define explicit recoverable/fatal failure behavior. A fatal runtime should trigger supervised restart; a recoverable error should use bounded recovery without serving an unverified model. **Acceptance:** a transient fault recovers, and a persistent one remains visibly failed with bounded attempts.

### R06 — Low-level response read failures bypass prediction error mapping

Location: `prediction.py:29`.

The response is read with `response.raw.read(...)`. This bypasses Requests' normal iteration/error translation: urllib3 `ReadTimeoutError` or `ProtocolError` can escape the existing `requests.Timeout`/`RequestException` handlers. The public API then returns generic HTTP 500 instead of the intended timeout/unavailable error, and the expected readiness invalidation is skipped.

The probe injected `ReadTimeoutError` at exactly this read and observed it escape `call`.

**Fix:** use bounded Requests streaming with correct exception translation, or handle the relevant underlying exceptions explicitly. Preserve the byte cap and close the response/tunnel. **Acceptance:** truncated and stalled response bodies return the intended public status without leaking a raw exception.

### R07 — Cleanup retry repeatedly observes the same failed Job

Location: `deletion.py:179` and `:189`.

Retry resets the operation state and timer, but retains `plan.annotation_job`. `_annotation_cleanup` reads that same Job; its Kubernetes `Failed` condition is terminal. Even after a temporary database fault is resolved, retry immediately produces `ANNOTATION_DELETE_FAILED` again. The operation retains dataset/model reservations. Deleting the Job manually instead changes the error to an unresolved outcome, so it is not a supported recovery procedure.

The probe replayed the failed Job twice across `retry_deletion`; no replacement attempt was created.

**Fix:** persist a database-side deletion receipt and distinguish “did not commit” from “outcome unknown.” Only a proven safe retry may create a new attempt with a new identity. Add an explicit operator-resolution path for uncertain outcomes. **Acceptance:** a rolled-back transient failure can recover without broadening deletion scope; a committed-but-unobserved outcome is not blindly executed again.

### R08 — SIGTERM stops the supervisor but leaves its queue worker running

Location: `scripts/run_local.py:13`.

The supervisor waits in `subprocess.run` and handles KeyboardInterrupt, but does not forward SIGTERM or reap its child in a shutdown handler. Stopping only its PID can leave a database worker consuming work. Restarting the supervisor can then add another worker, making “the worker is stopped” an unsafe assumption during maintenance.

A real isolated subprocess reproduction used the actual supervisor with an inert child and disabled environment-file loading. After supervisor exit `-15`, the child remained alive. All synthetic processes were then terminated; no working worker was touched.

**Fix:** own the child/process group explicitly, forward termination and wait for exit. **Acceptance:** both SIGINT and SIGTERM terminate the supervisor and all its children within a bounded interval.

### R09 — Deployment readiness checks only process liveness

Location: `mysite/src/mysite/errors.py:131`; `scripts/render_infrastructure.py:87`.

The backend readiness and liveness probes both use `/health/`, which always returns `{"status":"ok"}` without checking PostgreSQL. During this audit, that endpoint returned 200 while both list APIs returned 500 because the database was unreachable. Kubernetes would continue treating the backend as ready under this configuration.

**Fix:** retain a cheap liveness endpoint and add a separate, bounded readiness check for required application dependencies. Handle expected database unavailability as a service-level failure. **Acceptance:** a database outage makes readiness fail without causing a liveness restart loop; readiness recovers after reconnection.

### R10 — One slow observer can make other healthy models appear stale

Location: `management/commands/reconcile_serving.py:handle`, `reconcile_operations.py:handle`, and `settings_base.py` freshness settings.

Serving revisions are checked sequentially. A single Kubernetes call can wait 30 seconds; local tunneling and HTTP checks add time. Serving observations expire after 30 seconds, and the loop also sleeps between complete passes. A slow or unreachable revision can therefore make otherwise healthy revisions stale and disable prediction. Annotation observation shares its loop with cleanup and annotation-data reads, producing a similar coupling.

**Fix:** schedule independent observations with bounded concurrency and a per-operation time budget, or separate health work from slow cleanup/data refresh. Set freshness against the supported observation capacity. **Acceptance:** inject a stalled check for one model and show that another remains freshly READY throughout.

## Annotation, source data and model quality

### R11 — Reject/OTHER conversion produces incorrect supervised targets

Location: `example/mykedro/src/mykedro/pipelines/train/nodes.py:55`; `contracts/src/kedrogy_contracts/__init__.py:CONVERSION_VERSION`.

Rejecting a suggested category means “this category is wrong,” not “this text belongs to none of the categories.” With positive/negative sentiment, rejecting a negative suggestion for “I love it” currently trains class 0, OTHER. The probe confirms this exact mapping. This is especially damaging with the random suggestions described in R12.

The earlier implementation deliberately retained `reject-other-v1` for compatibility. That choice makes the behavior explicit, but does not establish its scientific correctness.

**Fix:** choose an annotation objective first: explicit mutually exclusive label selection, multilabel binary decisions, or a carefully defined true OTHER class. Version the conversion and review old annotations; do not silently reinterpret stored rejects. **Acceptance:** reviewed examples map to the intended targets, including every reject/ignore case.

### R12 — The “active learning” loop is still a dummy implementation

Location: `example/myrecipes/src/myrecipes/textcat_custom_model.py:9`.

`DummyModel` chooses labels and scores randomly; `update` replaces a random scalar. It never loads the trained classifier or learns from answers. `prefer_uncertain` consequently sorts random numbers, not meaningful uncertainty. The code is a demo recipe, so the product cannot currently substantiate a claim of model-driven active learning.

**Fix:** either integrate a versioned classifier with appropriate scoring/update behavior, or use an honest manual-labeling mode and describe active learning as future work. **Acceptance:** a test proves suggestions come from the intended model version and that the acquisition policy behaves predictably on controlled scores.

### R13 — Every annotation session receives only five source examples

Location: `example/mykedro/src/mykedro/db_queries.py:47`; `manifests.py:annotation`.

The loader contains a literal `LIMIT 5`. It runs as an initialization step and writes a finite JSONL stream; there is no pagination or refill while Prodigy remains running. After those examples are consumed, the interface can look exhausted although the source has many unseen rows. Starting a new batch requires stopping and launching the session again.

**Fix:** provide a configurable bounded batch size with an explicit next-batch operation, or a safe paginated stream. **Acceptance:** a source containing more than five unseen rows can be annotated to completion without an undocumented restart ritual.

### R14 — Re-ingestion destroys the previous source snapshot and changes identities

Location: `example/mykedro/conf/base/catalog.yml:all_data_postgres`; `pipelines/convert/nodes.py:11`.

The SQLTableDataset saves with `if_exists: replace`. Conversion discards any stable original identity and creates IDs from the current row order. Reordering/replacing the source can therefore change the text associated with an ID already present in saved annotation metadata. The unseen-example query continues using those IDs, so it can exclude the wrong text. Old source rows are also lost from the replaced table.

This path requires the explicit ingest role and is not reachable through the approved annotation launch pipeline. No destructive ingestion was executed during this audit.

**Fix:** use stable source IDs, versioned snapshots or controlled upserts, and an explicit replacement workflow when replacement is intended. **Acceptance:** reordering identical input preserves identities; updating/removing source content cannot silently invalidate existing annotation provenance.

### R15 — A bound annotation dataset can switch to another source with overlapping IDs

Location: `kedrogy/src/kedrogy/serializers.py:DjangoDatasetSerializer.update`; `example/mykedro/src/mykedro/db_queries.py:47`.

After stopping annotation, PATCH may change the source table or ID field while retaining the same Prodigy binding and saved answers. The unseen-example query matches dataset name and the ID value, without source identity. If source A and source B both contain ID 1, an annotation from A can exclude B's unrelated row. Training also continues reading the old annotation set.

The probe confirms that a BOUND dataset with a PRESENT observation accepts a change to another approved source while retaining its numeric annotation identity. Cross-source exclusion follows directly from the inspected SQL; it was not rerun on PostgreSQL this turn.

**Fix:** freeze source identity after annotation begins, or version source/binding metadata and include that provenance in matching. **Acceptance:** a source switch with overlapping IDs requires explicit migration/new binding and never silently skips another source's text.

### R16 — Preflight and evaluation permit misleading model quality

Location: `contracts/src/kedrogy_contracts/__init__.py:41`; training nodes `:72` and `:93`; artifact publication and `training.py:public_run`.

Preflight requires only four usable rows. It accepts four copies of one text and accepts a configured class with zero examples. Splitting is neither grouped by text/source identity nor stratified. The probes show the same text in training and validation, and a four-row split whose only minority-class example is placed in validation, leaving training without that class.

Only accuracy is calculated. There is no published evaluation summary with class support, per-class precision/recall/F1 or split evidence. A verified artifact establishes loadability and identity, not useful classifier performance.

**Fix:** validate duplicate/conflicting examples and class support; split by the correct independent unit; stratify where feasible and fail clearly when it is not. Publish a bounded quality report and persist the split definition. **Acceptance:** no group crosses partitions; unsupported classes cannot silently pass; the UI distinguishes artifact verification from evaluated quality.

### R17 — Seeded Trainer creation does not seed earlier classifier initialization

Location: training nodes `:103`, `:111`, `:134`; installed Transformers `trainer.py:452`.

`AutoModelForSequenceClassification.from_pretrained` constructs the model before Trainer applies `TrainingArguments.seed`. When the base checkpoint has no matching classification head, that head is randomly initialized before the recorded seed takes effect. Repeating the run with the same seed therefore does not guarantee the same initial classifier weights.

The source also downloads the base model without an explicit upstream revision in `Dockerfile-example`; a fixed application image digest stabilizes an existing image, but does not make a future clean image rebuild resolve the same upstream revision.

**Fix:** seed all relevant RNGs before model construction or use a properly seeded model factory, and record/pin the base-model revision. **Acceptance:** two isolated CPU runs with the same inputs and supported determinism settings produce the same initial head and split; document remaining hardware nondeterminism.

## Operations, API scaling and interface

### R18 — Heavy workloads have no CPU/memory budgets, and artifacts accumulate

Location: `kedrogy/src/kedrogy/manifests.py:container`, `:training`, `:serving`, `:verification`; `scripts/render_infrastructure.py`.

Training, verification and inference containers have no CPU/memory requests or limits. Per-model operation locks do not limit simultaneous training across different models. Multiple BERT workloads can therefore compete with PostgreSQL and the API on the same node without an intentional scheduling budget.

Completed Jobs, per-run training checkpoints and published artifact copies are retained until explicit cleanup. `save_total_limit=1` applies inside a training attempt, not across all runs. The 1 GiB PVC request is not an application retention policy.

**Fix:** profile the supported model, set workload budgets and admission/concurrency limits, then add an explicit retention policy that protects published/served artifacts. **Acceptance:** concurrent launches remain within the supported node budget; retention cannot remove an artifact still in use. Do not bulk-delete historical volumes as an audit “fix.”

### R19 — List queries scale with record count and load complete histories

Location: `api_views.py` querysets; `serializers.py:65` and `:159`.

Every serialized model executes a separate unfinished-cleanup lookup. The probe measured **3 SQL queries for one model and 13 for eleven**. Dataset serialization likewise performs per-record cleanup lookups. List endpoints have no pagination, while prefetches load all annotation/training runs even though the list needs only the latest run. History snapshots can contain substantial JSON.

Home repeats the list requests every ten seconds, amplifying this cost as data grows.

**Fix:** batch/annotate the latest run and cleanup state, paginate lists, and fetch history separately with a stable limit. **Acceptance:** query count stays approximately constant as a page grows, and response/memory budgets are measured on realistic history sizes.

### R20 — History says a stopped training version is served

Location: `api_views.py:MLModelViewSet.runs`.

The `served` history flag compares only `current_serving.training_run_id` with the training run. Stop intentionally retains the `current_serving` pointer for history, so the flag stays true for STOPPED or stale/unavailable revisions. The isolated API probe confirms `served: true` after Stop.

**Fix:** define whether this means “currently ready” or “last selected for serving”; use the fresh public serving state for the former and rename the field for the latter. **Acceptance:** the detail page and history cannot simultaneously claim STOPPED and currently served.

### R21 — Mutation requests lack consistent pending, timeout and replay behavior

Location: `app/src/pages/HomePage.tsx:65`, `DatasetDetailPage.tsx:80`, and mutation handlers in `ModelDetailPage.tsx`.

Create Dataset and Create Model do not disable submission or retain an idempotency key, so double submission or retry after an ambiguous response can create duplicate drafts. Train, Serve, Stop, Predict and rename requests on the model page omit the timeout/abort mechanism already used by polling. A request that never settles leaves submission/prediction disabled indefinitely. Navigation also does not cancel these mutation-response handlers.

**Fix:** use one mutation lifecycle with bounded waiting, clear pending state and safe handling of an unknown outcome. Use server-backed request identity where duplicate creation matters. **Acceptance:** double-clicking creates one intended draft; a stalled request offers recovery; navigation prevents obsolete responses from updating another view.

### R22 — Home and dataset pages retain stale connection errors

Location: `HomePage.tsx:load`; `DatasetDetailPage.tsx:refresh`.

A successful refresh updates data but does not clear the preceding refresh error. The application can display fresh working data alongside “Failed to load data.” Home additionally suppresses all errors when the combined signal is aborted; that includes its timeout signal, so a timeout can leave an apparently empty/loading page without an explanation. An old READY annotation link is also retained when refresh fails, without an explicit stale-state treatment.

**Fix:** separate load errors from mutation errors, clear each on its corresponding success, distinguish timeout from unmount cancellation, and show stale observations as stale. **Acceptance:** failure → success clears the failure message; timeout is visible; old session health is not presented as a fresh observation.

### R23 — The built frontend still depends on development CDN styling

Location: `app/index.html`, `app/src/main.tsx`, `app/vite.config.ts`.

The HTML loads Tailwind from `cdn.tailwindcss.com` and DaisyUI 4.12.10 from jsDelivr. The package graph installs Tailwind 4 and DaisyUI 5, but no application stylesheet is imported to produce the expected local CSS bundle. The production build emits the JavaScript bundle and leaves those remote assets in the HTML.

The result depends on network availability during a diploma presentation and uses a different component/style version from the installed dependencies. A successful JavaScript build does not verify the intended appearance offline.

**Fix:** compile and serve local CSS using one compatible version set. **Acceptance:** the production build renders correctly with external network access disabled and does not execute a runtime Tailwind compiler.

### R24 — Tests exist, but the regression gate is still incomplete

Location: `app/package.json`, `.github/workflows/*`, `tests/test_db_queries.py:17` and `:34`.

`npm run lint` exits 2 because ESLint 9 has no flat configuration. The checked-in workflows build/publish packages on tags or manual dispatch; they do not run the application checks on pull requests. Frontend tests currently validate data contracts, not rendered component interaction, so the UI bugs above remain uncovered.

The disposable SQL test module is stale: it calls `read_annotations(name)` although `dataset_id` is now required, and its synthetic dataset table lacks the `session` column used by the current reader. The signature mismatch is reproduced without connecting to a database. Its four cases were skipped by this audit's baseline run, so that run does not establish SQL integration coverage.

**Fix:** restore lint configuration; update the database fixture and reader-contract assertions; add a repeatable CI entry point and a small set of meaningful component and PostgreSQL tests. **Acceptance:** a clean CI run actually executes the relevant suites and fails when an invariant from this report is reintroduced.

### R25 — Fresh installation still relies on the previous machine setup

Location: root `README.md`; `SECURITY_SETUP.md:8` and local launch commands.

The operational instructions correctly help this existing checkout, but offer root `uv sync --locked` followed by commands using `mysite/.venv/bin/python`. A fresh root workspace sync normally creates root `.venv`, not the already-existing package-local environment used by those commands. The root README contains almost no setup information and does not direct a new reader to the operational guide.

**Fix:** document one canonical environment and interpreter path, link the guide from README, and specify prerequisites and startup checks. **Acceptance:** a fresh checkout can reach the application using the documented steps without reusing this machine's existing virtual environments. This audit did not perform a clean installation or a clean Docker dependency rebuild.

### R26 — Primary navigation and rename controls cannot be reached by keyboard

Location: `HomePage.tsx:157` and `:190`; `DatasetDetailPage.tsx:124`; model rename controls.

Clickable table rows have no native link/button or keyboard behavior. Dataset rename is attached to a heading. A keyboard user cannot tab to and activate these actions as they can native links and buttons. Several edit inputs also lack a useful explicit accessible label.

**Fix:** use real links for navigation and named buttons for edit actions; associate labels with inputs and manage focus when editing starts/ends. **Acceptance:** the core open/rename/create workflow works with keyboard only and exposes meaningful accessible names.

### R27 — Home omits the model's own identity

Location: `HomePage.tsx:159`; legacy index model list.

The Name column renders `model.dataset_name`, ignoring `model_name` and the model ID. Two models on the same dataset with the same label set are indistinguishable even when the user has named them differently.

**Fix:** show model name plus a stable ID, and display the dataset separately. **Acceptance:** two differently named models of the same dataset are distinguishable before opening either one.

### R28 — Annotation startup has no strict deadline on successful readiness

Location: `annotation.py:104`.

`_observe` handles READY before checking whether startup has exceeded its timeout. A delayed successful observation can therefore publish READY/SUCCEEDED after the configured deadline, whereas a non-ready observation at that time marks startup failed. The probe used a run created an hour earlier and still obtained startup success.

**Fix:** define and consistently apply the deadline policy before publication and avoid beginning new startup work after expiry. **Acceptance:** the same clock boundary produces a consistent terminal startup outcome regardless of the next observation's ordering.

### R29 — Logout does not clear authentication state

Location: `mysite/src/mysite/views.py:5`.

The view returns “You've been logged out” without calling Django's logout function. The probe logged in a synthetic Django user, requested `/logout/`, and confirmed `_auth_user_id` remained in the session.

End-user authentication is deferred, but Django admin/session authentication already exists; the misleading endpoint is still a real defect for any authenticated session. **Fix:** implement the intended session logout or remove the unused claim until authentication is supported. **Acceptance:** a genuine logout invalidates the session and is protected as an appropriate state-changing action.

### R30 — Cleanup request bodies are not validated as objects

Location: `api_views.py` cleanup/destroy handlers.

These handlers call `request.data.get(...)` directly. A syntactically valid JSON list such as `[]` produces AttributeError and HTTP 500 instead of a controlled 400 response. The probe reproduced this on `POST /api/models/{id}/delete_model/`. No deletion was initiated.

**Fix:** validate a dedicated cleanup-request serializer before accessing fields, consistently across cleanup endpoints. **Acceptance:** list/scalar/null bodies, missing tokens and malformed tokens return documented client errors with no operation or reservation created.

## Earlier findings and intentionally unresolved decisions

| Original audit area | Current assessment |
| --- | --- |
| 1 — authentication | Intentionally deferred; not silently reintroduced into the repair scope |
| 2–4 — SQL/launch injection and embedded credentials | Bound SQL values, approved launch configuration, role separation and secret references are present; existing tests pass. No fresh dependency/image security certification is implied. |
| 5–8 — unsafe GETs, configuration, subprocess errors, false training success | The principal fixes remain present and tested. Unexpected response-stream errors are a remaining transport gap, R06. |
| 9–12 — serving truth, retraining, classes, stable bindings | Core functionality is implemented. Remaining ownership/race/health issues are R01–R06; source provenance and quality are R15–R17. |
| 13–16 — annotation state, task status, deletion and recovery | Durable records and cleanup protections exist. Remaining external-write, retry and supervision gaps are R03, R07–R10 and R28. |
| 17 — startup side effects | App registration no longer changes PostgreSQL or Kubernetes. |
| 18–19, 21–22, 26 — learning/data correctness | Reject semantics, dummy suggestions, five-row loading, source replacement and evaluation remain: R11–R17. The SQL/NULL fixes themselves are retained. |
| 20, 23–25, 27–28 — Unicode, preprocessing selection, inference and validation | Several original mechanisms are fixed: UTF-8 handling, rejection of unknown preprocessors, long-input limits, off-event-loop inference and bounded transport. Training/inference preprocessing currently agree only trivially because the approved implementation is identity; nontrivial parity remains future work. |
| 29–39 — legacy/API/UI | Many loading/task-status defects improved. Remaining issues are R19–R22, R26–R27, R29–R30. Russian translation remains partial, but English is the requested presentation language; translation completeness is not counted as another required fix. |
| 40–47 — packaging, infrastructure, styling and regression control | Workspace/build configuration and substantial tests now exist. R18 and R23–R25 remain. Clean rebuild and fresh vulnerability results are unverified. |

The previous implementation report also documented an unmanaged legacy Prodigy Deployment, seven ownership conflicts associated with models 19/20, invalid model 20, and unresolved historical bindings. Docker was unavailable during this audit, so those are **previously recorded decisions, not a fresh inventory**. Review identities and retained data before changing or deleting them. The old P/N versus positive/negative decision still requires a deliberate annotation/class mapping; no audit should silently choose it.

Other declared limitations are one managed annotation session per namespace, manual historical-resource cleanup, no per-version artifact deletion, and no measured production-scale capacity. The scope of this audit does not establish model quality, backup/restore readiness, public-access safety or absence of additional defects.

## Recommended repair sequence

1. **Protect serving ownership and Stop/new-launch races:** R01–R03. Use controlled interleavings and then disposable Kubernetes acceptance.
2. **Make availability/recovery truthful:** R04–R10, R20, R28. Include contention, streamed response failure, failed cleanup attempts and supervisor shutdown.
3. **Define scientifically correct data and training behavior:** R11–R17. Resolve annotation semantics before retraining or rewriting old labels. Preserve source provenance.
4. **Set capacity and API budgets:** R18–R19, then inspect retained resource/storage inventory with explicit ownership.
5. **Finish the presentation and regression path:** R21–R27, R29–R30. Bundle CSS, correct input/request behavior, and run a complete synthetic label → train → serve → predict → cleanup scenario in CI or a documented integration job.

Before a diploma presentation, separately restore the local Docker/PostgreSQL prerequisites and verify the demo's actual dataset binding, model classes and artifact. Starting dependencies alone does not resolve the code findings above.

## Guidance and reproducibility

The review used installed [Python review](</Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/review/SKILL.md>), [Python concurrency](</Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/concurrency/SKILL.md>), [E2E review](</Users/millafedotova/.codex/plugins/cache/personal/e2e-testing-best-practices/0.1.1/skills/review/SKILL.md>), [concurrency testing](</Users/millafedotova/.codex/plugins/cache/personal/e2e-testing-best-practices/0.1.1/skills/testing-concurrency/SKILL.md>) and [TypeScript async/error guidance](</Users/millafedotova/.codex/plugins/cache/personal/claude-typescript/0.1.0+codex.20260618094037/skills/async-and-errors/SKILL.md>). In particular: Python concurrency/subprocess lifetime principles for R01–R10; robustness/error boundaries for R06/R30; deterministic scheduling and observable invariants from E2E concurrency rules 8–12 and 20–21; explicit async error behavior for R21–R22. Functional consequences, not stylistic preference, determine priority.

Re-run the audit probes from the repository root:

```sh
PYTHONPATH=reports/2026-09-26-audit DJANGO_SETTINGS_MODULE=mysite.test_settings \
  mysite/.venv/bin/python -m django test probes --noinput
example/.venv/bin/python reports/2026-09-26-audit/ml_probes.py
mysite/.venv/bin/python reports/2026-09-26-audit/supervisor_probe.py
```

Do not promote the assertions as product acceptance tests unchanged: they currently assert the buggy outcomes. Reverse them into the intended invariants during implementation.

Evidence files: [backend reproductions](probes.py), [backend results](backend-probes.log), [ML reproductions](ml_probes.py), [ML results](ml-probes.log), [supervisor reproduction](supervisor_probe.py), [supervisor result](supervisor-probe.json), [runtime status](runtime.json), [syntax results](source-check.json). These contain synthetic inputs, status metadata and code, not exported working annotations or credentials.
