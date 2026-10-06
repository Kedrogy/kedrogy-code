# Kedrogy technical audit from 22 September 2026

The audit covered the current working copy, including pre-existing uncommitted changes, local Python environments, running frontend, Django API, PostgreSQL and k3d-kedrogy. Application source was not repaired during the audit. This report and its evidence appendices record the checks.

The project combines the necessary components but does not yet make the annotation → training → deployment → prediction workflow reliable. Database/UI claims diverge from actual data, tasks and Kubernetes state. Repairing one model or form therefore does not resolve the underlying lifecycle problem.

A thesis demonstration needs one reproducible verified scenario on fixed data. Access by other users additionally requires authorization, injection repairs and safe configuration. Replacing React, Django, Kedro or Kubernetes is unnecessary.

## Scope and limitations

- Reviewed all 48 Python files in principal source directories, React/TypeScript pages, routes, serializers, Django templates, Kedro parameters/catalog, the custom Prodigy recipe, FastAPI inference, Kubernetes templates, Dockerfiles, workflows and startup instructions.
- Checked used ysz.kedro_datasets adapters and django-tasks behavior. Generated CSS/JS and every dependency's internals were not audited line by line.
- Ran frontend production build, attempted lint, parsed Python syntax, checked Django deployment settings/migrations and inspected HTTP/browser behavior.
- Reproduced function, serializer and template failures in isolation. PostgreSQL checks used default_transaction_read_only=on. Dangerous test YAML was not sent to Kubernetes.
- Tested short and long synthetic inputs on the existing serve-18 service. Did not run new complete training, full resource creation/deletion, load benchmarks, backup recovery or every annotation variation.
- Scanned installed public npm/backend/ML packages, not container SBOMs. Licensed, local and Git-installed Python packages were excluded; the scan does not establish their safety.
- Applied Python, TypeScript and E2E review checklists, including security, data, async errors and validation. Cosmetic findings were distinguished from functional failures.

## Priorities and evidence

| Label | Meaning |
| --- | --- |
| P0 | Fix before untrusted access or public service/image release. Database, containers or secrets may be affected; this does not claim the local installation was compromised. |
| P1 | Fix before a complete demonstration: the workflow fails, loses evidential reliability or leaves invalid state. |
| P2 | Significant reliability, data quality, operations or usability work after blockers. |
| P3 | Maintainability, clarity and presentation; do not distract from blockers. |
| Reproduced | Observed in isolation, API, browser or working environment. |
| Source review | Mechanism identified in code without executing dangerous/mutating scenarios. |
| Scanner | An affected installed version was found; application-specific applicability needs review. |

## Check results

| Check | Result |
| --- | --- |
| npm run build | Passed TypeScript/Vite; does not establish business correctness. |
| npm run lint | Could not start: eslint.config.js/mjs/cjs missing. |
| Python syntax | All 48 files parsed. |
| Source tests | Found backend/pipeline templates with zero implemented test functions; no frontend test script. |
| Django deployment checks | Eight warnings: seven security settings and one duplicate URL namespace. A Kubernetes-mutating startup hook was disabled only in the isolated check. |
| Current database migrations | None unapplied. |
| Dataset/model lists | HTTP 200 without authentication. |
| Unknown task status | HTTP 500 rather than controlled client error. |
| Existing FAILED task status | HTTP 500, ValueError: Task failed. |
| Model #20 | Training failed, its volume is empty and serving restarts, while API stores trained=true and served=true. |
| Ready serve-18 | Short input returned 200. 1,024 hello words returned 500 with lengths 1,026 versus 512. |
| Dataset/Prodigy binding | None of three DjangoDataset names occurs among Prodigy dataset names. This proves naming inconsistency, not deletion of annotations. |
| Django tasks | 301 SUCCEEDED, one FAILED, one RUNNING; the RUNNING task began 16 March 2026. Queue statuses do not prove Kubernetes Job success. |
| Kubernetes | 15 serve-* Deployments, one ready; 14 lack a matching current model ID. Of 14 training Jobs, 12 failed. This is a historical/current resource snapshot, not new-run statistics. |
| Worker Role | Referenced db-worker-kubectl-role absent from repository and checked cluster. |
| npm audit | 11 affected packages: seven high, one moderate, three low by scanner classification. |
| Python backend | 10 affected public packages of 68; 38 unique package/advisory pairs. |
| Python ML | 27 affected public packages of 209; 116 unique pairs. Do not add overlapping backend totals. |

## Security and access boundaries

### 01 · P0 · Anonymous API control of datasets, models and tasks

Evidence: reproduced and source review.

Locations: [settings.py:172](../../mysite/src/mysite/settings.py#L172), [api_views.py:21](../../kedrogy/src/kedrogy/api_views.py#L21).

AllowAny and ModelViewSet expose create, update and delete; train/serve/delete actions inherit the same permissions. Isolated permission checks allowed anonymous POST and real GETs needed no login. These actions subsequently use server database/Kubernetes privileges. CORS is not authorization.

Repair: require authentication, define at least viewing/annotation/management roles, check object/task access and protect legacy views. A simple correct single-user login can suffice. Acceptance: anonymous POST/PATCH/DELETE/task launches and foreign-object access fail before writes or Kubernetes calls. See [DRF permissions](https://www.django-rest-framework.org/api-guide/permissions/).

### 02 · P0 · User values are interpolated into SQL

Evidence: source review; database privileges checked.

Locations: [train/nodes.py:22](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L22), [load_examples/nodes.py:20](../../example/mykedro/src/mykedro/pipelines/load_examples/nodes.py#L20).

dataset_name, data_table_name and id_field enter f-string SQL, breaking valid quoted values and enabling injection. The checked connection uses postgres with rolsuper=true, so potential impact exceeds one table. Destructive proof queries were not run.

Repair: parameterize values, compose identifiers with psycopg.sql.Identifier, restrict sources/columns and separate application, reader and migration roles. Acceptance: apostrophes remain data, injected SQL cannot change the query and runtime is not superuser. See [Psycopg parameters](https://www.psycopg.org/psycopg3/docs/basic/params.html).

### 03 · P0 · API fields can change Kubernetes YAML and select arbitrary images

Evidence: reproduced without deployment.

Locations: [serializers.py:5](../../kedrogy/src/kedrogy/serializers.py#L5), [train.yaml.jinja:32](../../kedrogy/src/kedrogy/templates_k8s/train.yaml.jinja#L32), [tasks.py:31](../../kedrogy/src/kedrogy/tasks.py#L31).

Image/directory strings enter YAML without structural serialization. A validator accepted a newline-bearing image value that locally rendered an added privileged securityContext. This proves changed manifest structure, not actual cluster admission. Arbitrary images also receive configured database credentials. Maximum impact depends on RBAC/admission policies.

Repair: structured document building/serialization, approved registries and launch parameters, rejected control characters and least-privilege accounts/containers. Acceptance: multiline inputs fail or remain strings; users cannot add PodSpec fields or launch unverified images.

### 04 · P0 · Hardcoded secrets may enter Docker images

Evidence: source review.

Locations: [prodigy.yaml.jinja:158](../../kedrogy/src/kedrogy/templates_k8s/prodigy.yaml.jinja#L158), [settings.py:24](../../mysite/src/mysite/settings.py#L24), [Dockerfile:43](../../Dockerfile#L43), [.dockerignore:1](../../.dockerignore#L1).

Source contains fixed Prodigy, Django and PostgreSQL credentials. .dockerignore omits .env, app/.env, .git, mysite/.venv and app/node_modules while Dockerfile copies the entire root. Builds can include confidential files/history and unnecessary dependencies. Registry credentials also use build arguments. Values were deliberately omitted; historical image exposure was not checked in this initial audit.

Repair: external environment/Secret storage, BuildKit build secrets, explicit COPY and strict context exclusions. Inspect released artifacts and rotate credentials actually exposed. Acceptance: image layers/context contain neither local secrets nor Git history/passwords.

### 05 · P1 · Legacy Django routes mutate over GET

Evidence: source review.

Locations: [views.py:78](../../kedrogy/src/kedrogy/views.py#L78), [views.py:88](../../kedrogy/src/kedrogy/views.py#L88), [views.py:155](../../kedrogy/src/kedrogy/views.py#L155), [urls.py:9](../../kedrogy/src/kedrogy/urls.py#L9).

Dataset deletion, annotation, training, serving and cleanup handlers do not restrict methods. Visiting URLs can launch operations or delete rows. Routes remain enabled alongside React; CSRF does not make mutating GET safe.

Repair: read-only GET, require_POST/correct methods and authorization, or retire unsupported routes. Acceptance: every command GET returns 405 without tasks. Working data was not deleted through these routes during the audit.

### 06 · P1 · No separate safe deployment settings

Evidence: reproduced.

Locations: [settings.py:23](../../mysite/src/mysite/settings.py#L23), [settings.py:164](../../mysite/src/mysite/settings.py#L164), [prodigy-svc-ingress.yaml:36](../../kedrogy/src/kedrogy/templates_k8s/prodigy-svc-ingress.yaml#L36).

DEBUG is always enabled, ALLOWED_HOSTS empty and secure cookies/HTTPS absent. API errors returned HTML tracebacks. Prodigy's hostless / ingress complicates coexistence. Local HTTP itself is acceptable; reusing its settings for external access is the defect.

Repair: separate development/deployment settings, environment configuration, defined domain/TLS boundary, debug off and safe JSON errors. Acceptance: meaningful deployment checks and external responses without tracebacks/local paths.

## Tasks and lifecycle

### 07 · P1 · kubectl wrapper swallows process failures and stderr

Evidence: reproduced.

Locations: [tasks.py:17](../../kedrogy/src/kedrogy/tasks.py#L17).

The wrapper returns stdout without checking exit status, controlled completion or overall timeout; stderr is absent from log metadata. A process exited seven while the function successfully returned stdout. Per-line sleep slows logs and each line rewrites the entire accumulated database log.

Repair: one executor with returncode, stderr, deadlines/log bounds, child cleanup and propagated failures. Finite commands can use checked subprocess.run; streaming needs proper management. Acceptance: nonzero exit produces FAILED and a visible reason.

### 08 · P1 · trained=true does not verify successful training

Evidence: reproduced.

Locations: [tasks.py:190](../../kedrogy/src/kedrogy/tasks.py#L190).

After waiting for Pod Ready and reading logs, code unconditionally sets trained=True. Neither readiness nor log completion proves training/checkpoint success. Both current models are marked trained despite failed Jobs 19/20; model #20's volume is empty.

Repair: verify terminal Job conditions, container exit and weights/config/tokenizer; store per-run status and verify before success. Acceptance: label/checkpoint failures produce FAILED; successful saved models produce SUCCEEDED. See [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

### 09 · P1 · served=true means submitted manifest rather than ready inference

Evidence: reproduced.

Locations: [tasks.py:221](../../kedrogy/src/kedrogy/tasks.py#L221), [serve.yaml.jinja:18](../../kedrogy/src/kedrogy/templates_k8s/serve.yaml.jinja#L18).

served=True follows kubectl apply without checking an artifact, model loading or endpoint readiness. Model #20 displays Yes while CrashLoopBackOff and prediction returns 500.

Repair: starting/ready/failed/stopped states, prelaunch checkpoints, startup/readiness probes and a smoke request; reconcile later failures. Acceptance: missing weights never become Ready; healthy HTTP does; crashes become failed/unavailable.

### 10 · P1 · Repeated Train reuses the same Job

Evidence: source review and current resources.

Locations: [train.yaml.jinja:20](../../kedrogy/src/kedrogy/templates_k8s/train.yaml.jinja#L20), [tasks.py:141](../../kedrogy/src/kedrogy/tasks.py#L141).

Every Job is train-{model_id}; reapplying a completed/failed Job is not a new run. ConfigMap updates do not restart Jobs; Pod-template changes may hit immutability. Pod lookup concatenates multiple attempt names into one logs/wait argument.

Repair: unique TrainingRun/Job identities and run → Job → attempts → artifact links. Observe the selected current attempt. Acceptance: sequential training requests produce independent parameters/logs/runs.

### 11 · P1 · Class labels are not normalized or checked against annotations

Evidence: reproduced.

Locations: [tasks.py:150](../../kedrogy/src/kedrogy/tasks.py#L150), [train/nodes.py:35](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L35), [ModelDetailPage.tsx:58](../../app/src/pages/ModelDetailPage.tsx#L58).

Comma splitting preserves outer whitespace; POS, NEG yields a leading-space class. Empty/duplicate/OTHER rules are unchecked, and case must match the agreed schema. Job #20 failed on KeyError: N with p and a leading-space n. Editing Django labels does not update checkpoint/runtime mapping; quotes also break assembled YAML.

Repair: structured classes, trimmed outer spaces, uniqueness/data checks and immutable published mappings. Do not change case without an annotation migration. Acceptance: supported input parses; unknown classes fail before Jobs; schema changes create versions.

### 12 · P1 · Dataset renaming breaks Prodigy binding

Evidence: naming mismatch reproduced; mechanism confirmed in source.

Locations: [DatasetDetailPage.tsx:25](../../app/src/pages/DatasetDetailPage.tsx#L25), [models.py:6](../../kedrogy/src/kedrogy/models.py#L6), [train/nodes.py:29](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L29).

dataset_name is both a display title and annotation key. PATCH changes Django only, not Prodigy, ConfigMaps or recipe options. All three application names are absent from Prodigy; active annotation uses test3 while a model card reports product-reviews-sentiment.

Repair: mutable display names and stable Prodigy identities, reviewed historical rebinding and uniqueness constraints. Acceptance: renaming does not change training selection or create new annotation sets.

### 13 · P1 · labelled depends on a last-dataset pointer not updated by React

Evidence: source review and checked data.

Locations: [serializers.py:22](../../kedrogy/src/kedrogy/serializers.py#L22), [views.py:114](../../kedrogy/src/kedrogy/views.py#L114), [api_views.py:90](../../kedrogy/src/kedrogy/api_views.py#L90), [DatasetDetailPage.tsx:167](../../app/src/pages/DatasetDetailPage.tsx#L167).

The flag means DjangoLastDataset exists rather than usable annotations. Legacy HTML polling updates it; React REST polling does not. Successful React annotation launch may never enable New model; switching the pointer removes another dataset's indirect labelled status.

Repair: independent active annotation sessions and actual counts/data readiness. Tasks update state without page visits. Acceptance: two annotated datasets remain trainable and closing a tab does not prevent completion/state publication.

### 14 · P1 · Polling a failed task itself returns HTTP 500

Evidence: reproduced.

Locations: [api_views.py:103](../../kedrogy/src/kedrogy/api_views.py#L103), [TrainModelPage.tsx:27](../../app/src/pages/TrainModelPage.tsx#L27).

django-tasks marks both success and failure finished, but reading FAILED return_value raises ValueError. A real failed-task request returned 500; missing tasks also return 500. React interprets any finished state as success and redirects.

Repair: branch by status, read values only on success, structured safe errors/logs and 404 for unknown IDs. Display failure without success text/navigation. Acceptance: READY/RUNNING/SUCCEEDED/FAILED/unknown have distinct verified responses/screens.

### 15 · P1 · Deletion does not reconcile database, resources, volumes and annotations

Evidence: source review and observed resource drift.

Locations: [models.py:39](../../kedrogy/src/kedrogy/models.py#L39), [api_views.py:21](../../kedrogy/src/kedrogy/api_views.py#L21), [tasks.py:230](../../kedrogy/src/kedrogy/tasks.py#L230).

ModelViewSet DELETE removes a row without Kubernetes cleanup. Dataset deletion cascades model rows but leaves workloads/volumes/Prodigy. Separate delete_model removes Deployment/Job/PVC but not Service/ConfigMap/model row; PVC deletion destroys checkpoints. Fourteen serve-* resources lack current models. Their exact origin is unproven, but coordinated cleanup is absent.

Repair: distinct stop/version-artifact-delete/model-dataset-delete actions, controlled retries/errors and in-use volume protection. Acceptance: explicit retention/deletion sets, safe repetition and visible partial failure.

### 16 · P1 · Conflicting operations and abandoned runs lack recovery

Evidence: source review and current state.

Locations: [api_views.py:37](../../kedrogy/src/kedrogy/api_views.py#L37), [tasks.py:88](../../kedrogy/src/kedrogy/tasks.py#L88), [prodigy.yaml.jinja:30](../../kedrogy/src/kedrogy/templates_k8s/prodigy.yaml.jinja#L30).

Repeated requests enqueue duplicates without idempotency, model locks or transition checks. Train/Serve/Delete contend for shared PVC/Job state. One prodigy Deployment serves every annotation session, so switching may interrupt another session. A task started 16 March remains RUNNING across restarts.

Repair: explicit transitions, one active run, command idempotency, leases/heartbeats and reconciliation. Either enforce one locked annotation session or allocate per-session resources. Acceptance: double-click cannot duplicate and crashed work reaches a defined outcome/retry.

### 17 · P1 · AppConfig.ready performs database and Kubernetes mutations

Evidence: source review and observed startup.

Locations: [apps.py:11](../../kedrogy/src/kedrogy/apps.py#L11).

Startup connects to PostgreSQL, creates a test Prodigy dataset if needed and runs kubectl apply. This affects servers, workers, migrate/check/tests and multiple processes. Cluster failure blocks diagnostics/migrations and concurrent starts can race bootstrap. The audit disabled the hook only in isolation.

Repair: explicit idempotent bootstrap/schema setup outside ready. Acceptance: import/check work without Kubernetes, bootstrap requires a command and servers do not create test data.

## Data, training and inference

### 18 · P1 · Rejecting a suggested class creates a false OTHER target

Evidence: reproduced.

Locations: [train/nodes.py:49](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L49), [textcat_custom_model.py:25](../../example/myrecipes/src/myrecipes/textcat_custom_model.py#L25).

The recipe proposes a random class. Reject maps to class zero/OTHER, but not positive can mean negative rather than OTHER. A test confirmed every rejected positive suggestion becomes OTHER, allowing successful training on misinterpreted labels.

Repair: explicit exclusive-class choice or a clear binary text/category formulation, with repeated-answer rules. Acceptance: negative text does not become OTHER merely because positive was rejected.

### 19 · P2 · Active learning is a demonstration stub

Evidence: source review.

Locations: [textcat_custom_model.py:9](../../example/myrecipes/src/myrecipes/textcat_custom_model.py#L9).

DummyModel returns random classes/scores and updates a random number without learning from answers. prefer_uncertain orders those fabricated scores. This demonstrates recipe wiring, not informative selection or measured active-learning benefit.

Repair: disclose a manual annotation integration/stub, or connect a real model and compare against random selection. Acceptance: thesis claims match implementation and, if implemented, new answers affect predictions/order.

### 20 · P1 · PostgreSQL JSON decoding breaks non-ASCII text

Evidence: reproduced.

Locations: [train/nodes.py:23](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L23), [load_examples/nodes.py:23](../../example/mykedro/src/mykedro/pipelines/load_examples/nodes.py#L23).

encode(content, escape)::json plus manual replacements generates invalid JSON escapes for UTF-8 bytea with Cyrillic. The exact project expression failed with InvalidTextRepresentation on a synthetic Cyrillic greeting, while ASCII/quotes passed. This depends on serialization and does not prove every saved annotation is corrupt.

Repair: Prodigy API or correct UTF-8 convert_from and JSON parsing without manual escape rewriting. Acceptance: Russian, English, emoji, quotes and backslashes round-trip exactly.

### 21 · P1 · Example loading is tied to one table and fragile IDs

Evidence: source review; NULL behavior confirmed.

Locations: [load_examples/nodes.py:23](../../example/mykedro/src/mykedro/pipelines/load_examples/nodes.py#L23).

SQL hardcodes all_data.source despite a configurable table; other aliases fail. IDs are forced to INTEGER, excluding UUID/string keys. NULL in a NOT IN subquery can empty the selection. Each run returns at most five examples without defined order or configurable batch size.

Repair: an approved source schema, consistent identifiers/aliases, preserved IDs, NOT EXISTS with missing-meta handling and parameterized batch/order. Acceptance covers another table, string IDs and annotations without meta.id.

### 22 · P1 · Repeated ingest replaces the source and positional IDs

Evidence: source review.

Locations: [catalog.yml:12](../../example/mykedro/conf/base/catalog.yml#L12), [convert/nodes.py:15](../../example/mykedro/src/mykedro/pipelines/convert/nodes.py#L15).

if_exists: replace recreates all_data and DataFrame positions become IDs. Reordering input changes what an ID means while saved meta.id still points to the old text, breaking exclusions/provenance. A destructive repeated import was not run against real data.

Repair: stable upstream IDs or agreed content hashes, source versions, staging/validation and controlled upsert instead of unconditional replacement. Acceptance: replay is idempotent, order does not change identity and old annotations retain meaning.

### 23 · P1 · Unknown preprocessing is ignored and train/serve can diverge

Evidence: source review and model #20 logs.

Locations: [serve.py:53](../../predict/src/ysz/predict/serve.py#L53), [example/mykedro/pyproject.toml:68](../../example/mykedro/pyproject.toml#L68), [train/nodes.py:74](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L74).

UI suggests preprocessing_fun while the registered plugin is a_preprocess_fun. Mismatch silently keeps preprocess_none, as model #20 logs show. The selected plugin affects inference only; training uses tokenizer preprocessing. Current identity behavior masks future train/serve skew.

Repair: approved plugins, invalid-name failure, versioned shared preprocessing and no unnecessary hello probe at app creation. Acceptance: typos fail before launch and both stages transform the same input consistently.

### 24 · P1 · Long input breaks the working inference service

Evidence: reproduced.

Locations: [serve.py:42](../../predict/src/ysz/predict/serve.py#L42), [serve.py:106](../../predict/src/ysz/predict/serve.py#L106).

Training truncates; inference does not. On serve-18, 1,024 words returned HTTP 500 from BERT position lengths 1,026 versus 512; short text returned 200. Input limits/policy are undocumented.

Repair: documented truncation with notice, chunking or rejection; consistent tokenizer settings and empty/type/request-size checks. Acceptance: zero, one, over-512 tokens, long Unicode and newlines yield documented outcomes rather than internal errors.

### 25 · P2 · PyTorch blocks the async endpoint and full inputs are logged

Evidence: source review.

Locations: [serve.py:90](../../predict/src/ysz/predict/serve.py#L90).

Synchronous tokenization/model work inside async predict blocks its event loop. Concurrency/queue limits are absent, so CPU and long-input latency can grow. Printing params and text copies complete user content into infrastructure logs, especially problematic for private/medical inputs.

Repair: bounded inference workers/pool or a properly limited synchronous endpoint, load/time limits and request IDs/durations/lengths/result codes instead of full text. Acceptance: load checks establish queue limits and sensitive samples never appear in logs.

### 26 · P2 · Model reproducibility and quality reporting are insufficient

Evidence: source review.

Locations: [train/pipeline.py:27](../../example/mykedro/src/mykedro/pipelines/train/pipeline.py#L27), [train/nodes.py:81](../../example/mykedro/src/mykedro/pipelines/train/nodes.py#L81), [models.py:38](../../kedrogy/src/kedrogy/models.py#L38).

Splitting has neither random_state nor stratification; setting the Trainer seed later cannot fix the earlier split. Minimum class support is unchecked. Accuracy, split sizes, dataset/image/run parameters do not become application results. The set called test is used for per-epoch evaluation and best-model selection, making it validation rather than an independent final test.

Repair: repeatable checked splits, independent final test for quality evaluation, data snapshots/hashes, seeds, run parameters, macro-F1, per-class precision/recall and confusion matrix; define a thesis baseline. Acceptance: repeat runs retain example IDs and reported independent results are reproducible.

## API and error handling

### 27 · P1 · Django prediction lacks deadlines and guaranteed tunnel cleanup

Evidence: source review and model #20 failure.

Locations: [api_views.py:54](../../kedrogy/src/kedrogy/api_views.py#L54), [views.py:252](../../kedrogy/src/kedrogy/views.py#L252).

Each local request starts port-forward without an overall stdout deadline. requests.post lacks timeouts/status/schema checks; child termination follows only successful prediction, not finally. Service/connection/unexpected-response failures return 500 and may leave processes. In-cluster legacy execution also has finding 29.

Repair: configured service URL/managed development tunnel, per-stage deadlines, finally plus reaping and HTTP/schema validation. Distinguish safe 400/503/504 errors. Acceptance: unready returns timely 503, timeout 504 and repeated failure does not accumulate tunnels.

### 28 · P1 · API accepts unusable configurations and rejects advertised defaults

Evidence: reproduced.

Locations: [models.py:9](../../kedrogy/src/kedrogy/models.py#L9), [serializers.py:5](../../kedrogy/src/kedrogy/serializers.py#L5), [i18n/config.ts:19](../../app/src/i18n/config.ts#L19).

A name-only dataset validates while infrastructure fields remain N/A. A form promises an empty default pipeline, but pipeline: empty string is rejected as blank. Source, recipe, pipeline and Serve readiness are unchecked until after enqueueing.

Repair: distinguish drafts/launchable settings, define actual defaults and validate commands with field errors before enqueue. Align frontend/backend schemas. Acceptance: a valid dataset launches without manual database fixes; empty-default behavior matches the form.

### 29 · P2 · Legacy Django UI has exceptions and a placeholder logout

Evidence: reproduced and source review.

Locations: [views.py:48](../../kedrogy/src/kedrogy/views.py#L48), [views.py:279](../../kedrogy/src/kedrogy/views.py#L279), [mysite/views.py:5](../../mysite/src/mysite/views.py#L5), [mysite/urls.py:39](../../mysite/src/mysite/urls.py#L39).

GET new_dataset uses uninitialized locals. In-cluster predict_model uses process defined only in the local branch. Both failed in isolation. logout returns text without ending the session. Duplicate kedrogy namespaces produce warnings/ambiguous reverse paths.

Repair: decide legacy support, then remove unsupported routes or share business logic, fix methods/branches, use real logout and unique namespaces. Acceptance: supported legacy smoke checks and invalidated sessions after logout.

### 30 · P2 · Unlimited lists and one labelled query per dataset

Evidence: source review.

Locations: [api_views.py:22](../../kedrogy/src/kedrogy/api_views.py#L22), [serializers.py:22](../../kedrogy/src/kedrogy/serializers.py#L22), [HomePage.tsx:46](../../app/src/pages/HomePage.tsx#L46).

API lists have no pagination or explicit ordering and each dataset triggers exists(). UI loads both collections completely and treats the final row as the last dataset. Query count, payload and rendering grow with records.

Repair: stable order, pagination/search, aggregated Exists/annotations and an explicit current-session endpoint. Acceptance: SQL queries per page do not grow linearly with rows and ordering is defined.

## Interface and user workflows

### 31 · P1 · Card-loading failures are hidden or treated as records

Evidence: reproduced in browser.

Locations: [ModelDetailPage.tsx:30](../../app/src/pages/ModelDetailPage.tsx#L30), [ModelDetailPage.tsx:127](../../app/src/pages/ModelDetailPage.tsx#L127), [DatasetDetailPage.tsx:18](../../app/src/pages/DatasetDetailPage.tsx#L18).

A missing model sets error but if-not-model returns permanent Loading before it. Dataset fetch ignores res.ok and turns Not found JSON into a blank card with Delete/Label. Paths models/999999 and datasets/999999 reproduced this.

Repair: loading/success/not-found/error states, HTTP/runtime schemas, retry/back actions and cancellation on ID changes. Acceptance: 404 has no record actions, network failure offers retry and 200 displays a valid card.

### 32 · P1 · Home invents Prodigy status and lacks annotation navigation

Evidence: reproduced and source review.

Locations: [HomePage.tsx:131](../../app/src/pages/HomePage.tsx#L131), [CreateDatasetTaskPage.tsx:27](../../app/src/pages/CreateDatasetTaskPage.tsx#L27).

Any existing dataset causes Prodigy running and the last array entry to be shown. Browser displayed medical-notes-ner while the Deployment used test3. This is not health checking. Label returns to Home without an annotation link; annotator deployment also does not prove completed human labels.

Repair: actual session status, identity, URL/Open annotation and separate saved-answer counts. Acceptance: stopped/unready Prodigy is not called running and annotation opens without knowing ports manually.

### 33 · P2 · Forms hide field errors and require infrastructure knowledge

Evidence: source review and serializer probes.

Locations: [HomePage.tsx:68](../../app/src/pages/HomePage.tsx#L68), [DatasetDetailPage.tsx:64](../../app/src/pages/DatasetDetailPage.tsx#L64).

Detailed DRF errors become generic create failures. Image, directory, pipeline and full recipe are entered manually without presets/combination checks. Optional preprocessing may submit blank despite backend rejection. any types and unchecked JSON worsen contract drift.

Repair: shared API/field-error client, typed schemas, approved pipelines/recipes/plugins and a working demonstration preset. Acceptance: nearby field errors and supported setup without reading Kubernetes templates.

### 34 · P2 · Actions remain active and stale predictions survive failure

Evidence: source review.

Locations: [ModelDetailPage.tsx:75](../../app/src/pages/ModelDetailPage.tsx#L75), [ModelDetailPage.tsx:109](../../app/src/pages/ModelDetailPage.tsx#L109), [HomePage.tsx:68](../../app/src/pages/HomePage.tsx#L68).

No submitting/predicting state prevents duplicate clicks or out-of-order inference. New predict clears error but not the old result, leaving a red failure alongside an unrelated green prediction.

Repair: pending states, conflict-button disabling, server idempotency, request/input-bound results, cleared old output and ignored stale responses. Acceptance: one operation on double-click and output always matches displayed input.

### 35 · P2 · Task polling overlaps requests and leaks redirects

Evidence: source review.

Locations: [TrainModelPage.tsx:18](../../app/src/pages/TrainModelPage.tsx#L18), [ServeModelPage.tsx:18](../../app/src/pages/ServeModelPage.tsx#L18), [DeleteModelPage.tsx:18](../../app/src/pages/DeleteModelPage.tsx#L18).

Two-second async setInterval starts before prior requests finish. One transient failure stops observation. Redirect timers survive unmount and fetch is not aborted. Four duplicate implementations need consistent repair.

Repair: shared sequential task hook, AbortController, bounded backoff, explicit retry and timer cleanup. Keep terminal logs and explicit navigation. Acceptance: one poll per task at a time and no delayed redirect after leaving.

### 36 · P1 · Hardcoded loopback API conflicts with deployment and CORS

Evidence: reproduced and source review.

Locations: [api.ts:1](../../app/src/api.ts#L1), [vite.config.ts:10](../../app/vite.config.ts#L10), [settings.py:165](../../mysite/src/mysite/settings.py#L165).

Absolute http://127.0.0.1:8000 addresses each visitor's machine and bypasses the existing /api Vite proxy. CORS permits localhost:5173 but not 127.0.0.1:5173; the latter preflight lacked Allow-Origin. HTTPS deployment is inconsistent with HTTP API.

Repair: same-origin /api proxying or an explicit base URL, aligned cookies/CSRF/authentication. Acceptance: documented local and second-device/domain usage without editing source.

### 37 · P2 · Incomplete translations and reset language preference

Evidence: source review.

Locations: [i18n/config.ts:82](../../app/src/i18n/config.ts#L82), [DatasetDetailPage.tsx:102](../../app/src/pages/DatasetDetailPage.tsx#L102), [ModelDetailPage.tsx:201](../../app/src/pages/ModelDetailPage.tsx#L201).

Initialization always selects en without persistence. Missing save/cancel keys do not reliably fall back through t(key) || text because missing keys are nonempty. States, errors, confirmations and titles are hardcoded; html lang stays en.

Repair: complete dictionaries, proper defaults, persisted preference and document-language updates. Acceptance: core RU/EN flows have no accidental keys/mixed messages and survive reload.

### 38 · P2 · Important actions lack expected keyboard access

Evidence: source/UI structure review.

Locations: [HomePage.tsx:162](../../app/src/pages/HomePage.tsx#L162), [DatasetDetailPage.tsx:106](../../app/src/pages/DatasetDetailPage.tsx#L106), [ModelDetailPage.tsx:149](../../app/src/pages/ModelDetailPage.tsx#L149).

Mouse-clickable table rows/headings are not semantic links/buttons. Rename is hidden in title clicks; some inputs lack connected labels and group legends do not replace individual semantics. Errors/statuses lack controlled assistive announcements.

Repair: links/buttons, visible Edit, connected labels/focus styles and appropriate alert/live regions. Acceptance: Tab/Enter/Escape and manual screen-reader checks cover the workflow. Full WCAG certification was not performed.

### 39 · P3 · Home cannot distinguish model names within one dataset

Evidence: source/browser review.

Locations: [HomePage.tsx:18](../../app/src/pages/HomePage.tsx#L18), [HomePage.tsx:170](../../app/src/pages/HomePage.tsx#L170).

Name displays dataset_name; model_name exists in cards/API but not the Home type/output. Both current models share the shown dataset title, so rename does not help list identification. Versions/training dates are absent.

Repair: model name plus ID/version and separate dataset, using a shared API type. Acceptance: versions are distinguishable and rename updates cards/lists.

## Build, infrastructure and maintainability

### 40 · P1 · Root Python build lacks pyproject.toml

Evidence: reproduced.

Locations: [Dockerfile:43](../../Dockerfile#L43), [Dockerfile:63](../../Dockerfile#L63), [HACKING.md:14](../../HACKING.md#L14).

uv.lock exists without root pyproject.toml; offline lock check reports none found. Docker copies the root and runs locked all-package sync, as startup docs recommend. Existing local environments do not prove clean setup.

Repair: restore the actual uv workspace or explicitly build mysite with aligned paths/lockfiles; document one setup route. Acceptance: clean checkout/image startup without old environments or untracked author files.

### 41 · P1 · Django manifest has missing RBAC and incomplete Prodigy DB config

Evidence: reproduced and source review.

Locations: [mysite.yaml:6](../../mysite.yaml#L6), [mysite.yaml:60](../../mysite.yaml#L60).

RoleBinding references absent db-worker-kubectl-role; the cluster returns NotFound. Personal local kubeconfig hides this container-mode defect. Generated prodigy.json omits the port despite database port 30001; another template includes it.

Repair: explicit minimal Role and can-i checks, consistent port/secrets configuration. Acceptance: cluster server/worker use that account without personal kubeconfig or cluster-admin.

### 42 · P2 · Heavy workloads lack probes and resource policy

Evidence: source and cluster state.

Locations: [serve.yaml.jinja:18](../../kedrogy/src/kedrogy/templates_k8s/serve.yaml.jinja#L18), [train.yaml.jinja:21](../../kedrogy/src/kedrogy/templates_k8s/train.yaml.jinja#L21), [pvc.yaml.jinja:8](../../kedrogy/src/kedrogy/templates_k8s/pvc.yaml.jinja#L8).

Training/inference lack CPU/memory requests/limits and startup/readiness/liveness policy; Jobs lack active deadlines. PVCs hardcode 1Gi/local-path, unsuitable as portable configuration and potentially insufficient for BERT output. Failed/pending/crashloop resources require inventory, not blind volume deletion.

Repair: measure resources, set limits/deadlines/probes, configure storage size/class, retention and backups. Acceptance: readiness follows load, deadlines reach defined outcomes and saved artifacts recover from backups.

### 43 · P2 · Running code and model versions are not recorded

Evidence: source review.

Locations: [serve.yaml.jinja:21](../../kedrogy/src/kedrogy/templates_k8s/serve.yaml.jinja#L21), [train.yaml.jinja:33](../../kedrogy/src/kedrogy/templates_k8s/train.yaml.jinja#L33), [Dockerfile-example:38](../../Dockerfile-example#L38), [example/mykedro/pyproject.toml:51](../../example/mykedro/pyproject.toml#L51).

Mutable latest images/Always and unpinned base-model downloads allow runtime drift. Model rows omit digest, commit, data, preprocessing and artifact versions. Licensed Prodigy and SSH Git packages require extra clean-machine access.

Repair: pinned image/model revisions and run metadata; documented licensing/registry/SSH requirements and verified demonstration image. Check evaluate offline behavior rather than assuming caches. Acceptance: a run identifies exact inputs/runtime/parameters/weights and restart cannot silently change runtime.

### 44 · P2 · Styling depends on a CDN and mismatched installed packages

Evidence: source review and build output.

Locations: [app/index.html:8](../../app/index.html#L8), [main.tsx:1](../../app/src/main.tsx#L1), [package.json:14](../../app/package.json#L14).

HTML loads Tailwind CDN and DaisyUI 4.12.10 while packages specify Tailwind 4/DaisyUI 5. React has no local stylesheet import; production emitted HTML/JS without built CSS. Installed tooling therefore does not guarantee styling offline.

Repair: local CSS entry and compatible versions built into assets. Acceptance: offline production preview retains styling without third-party runtime styles.

### 45 · P1 · Regression tests, lint and workflow CI are absent

Evidence: reproduced and source review.

Locations: [tests.py:1](../../kedrogy/src/kedrogy/tests.py#L1), [test_pipeline.py:1](../../example/mykedro/tests/pipelines/train/test_pipeline.py#L1), [package.json:6](../../app/package.json#L6), [build-publish.yaml:26](../../.github/workflows/build-publish.yaml#L26).

Python test files are boilerplate, frontend lacks a test script and lint cannot start. Tag workflows publish Python packages without API/frontend/training checks. Strict types/build do not catch false-success states, wrong training targets or missing weights.

Repair: reproduced-failure regressions and a small end-to-end scenario, then lint/types before publication. Do not begin with 100% coverage or numerous layout tests. Acceptance: reintroducing findings 07/08/11/14/20/24/31 breaks specific checks.

### 46 · P2 · Git handoff and setup docs differ from the working copy

Evidence: reproduced and source review.

Locations: [app/README.md:1](../../app/README.md#L1), [kedrogy/pyproject.toml:21](../../kedrogy/pyproject.toml#L21), [HACKING.md:63](../../HACKING.md#L63), [app/.gitignore:11](../../app/.gitignore#L11).

At audit start, frontend package/lock/main/tsconfig and a new migration were untracked, so the commit lacked required files. This does not infer user intent. README describes CRA/3000 instead of Vite/5173; docs reference absent Dockerfile-tilt and package metadata absent README.rst. Ignore covers build rather than dist.

Repair: a complete reviewed commit, migrations/build in a clean checkout, consistent setup README/package metadata/ignores, environment names without values and required dependencies/ports. Acceptance: another person can follow instructions without private local files or guessing.

### 47 · P2 · Installed dependencies have advisories with differing applicability

Evidence: scanners.

Locations: [package-lock.json](../../app/package-lock.json), [mysite/uv.lock](../../mysite/uv.lock), [example/uv.lock](../../example/uv.lock), [DEPENDENCIES_EN.md](../../reports/2026-09-22-audit/DEPENDENCIES_EN.md).

npm reported 11 packages including Router, Vite and build tools. Python reported 10 backend and 27 ML packages including Django, DRF, Starlette, Transformers and Torch. Python duplicate IDs were counted as unique package/ID pairs. Windows, SSR/RSC and input-specific conditions mean installation alone does not prove SPA exposure; unused Python functions also need review.

Repair: reachable-runtime analysis, compatible grouped updates with lockfiles/regressions, rescan and actual-image checks. Avoid blind major upgrades. Acceptance: applicable high/critical items are understood/resolved and exceptions document environment bounds. Private-package vulnerabilities are not ruled out.

## Repair order before thesis demonstration

| Phase | Concrete result | Findings |
| --- | --- | --- |
| Preserve data/state | Verified DB/PVC backups, actual Prodigy datasets and reviewed card bindings; no blind deletion. | 12, 15, 22, 42 |
| Make operation outcomes truthful | Checked exits, real training/serving state, failed-task JSON and honest API/UI outcomes. | 07–10, 14, 16, 27 |
| Repair the data path | Stable identities, one class schema, correct answers, UTF-8 and verified training inputs. | 11–13, 18, 20–23, 28 |
| Produce one verified model | Fixed small dataset, artifacts/metrics, deployed short/long-input checks. | 08, 09, 24, 26, 43 |
| Make demonstration UI accurate | Real annotation status/link, proper errors, guarded repeat actions and retained logs. | 31–36, 39 |
| Automate verification | Build/lint/regressions, complete commit, clean setup/docs and bundled styles. | 40, 44–46 |
| Before external access | Authorization, safe SQL/YAML, secrets/settings/RBAC and advisory review. | 01–06, 41, 47 |

These express dependencies, not hour estimates. Estimates would be unreliable before annotation scope, data volume and multi-user requirements are chosen. Security can proceed alongside stabilization but cannot wait until a public demonstration.

## Minimum domain model

| Entity | Stored facts | Purpose |
| --- | --- | --- |
| Dataset | Stable ID, display name, Prodigy identity, source/version and class schema. | Rename-safe annotations and known training provenance. |
| AnnotationSession | Dataset ID, status, deployment identity, URL and usable-answer count. | Separate running annotation from completed labels. |
| Model | Name and dataset/configuration link. | Distinguishable models of one dataset. |
| TrainingRun | Unique ID, config, Job/attempts, times, status/error, metrics and artifact URI. | Retries do not overwrite history or hide failures. |
| Deployment | Training/artifact ID, image digest, state, endpoint and health/error. | Prediction identifies a trained version. |

Implement these within existing Django/PostgreSQL before adding a separate MLOps platform. Kubernetes controls resources; the application persists intent/results and reconciles actual state.

## Minimum post-repair checks

| Scenario | Expected result |
| --- | --- |
| Empty/invalid configuration | Field-level 400 before enqueue; no workload. |
| Spaces/apostrophes in display name | SQL, Prodigy identity and YAML remain valid. |
| Rename after annotation | Saved-answer count/content unchanged. |
| Unknown/duplicate/empty/OTHER label | Clear agreed rule, no Job KeyError. |
| Cyrillic/emoji/quotes in UTF-8 JSON | Exact read → conversion → training preservation. |
| Reject suggested class | No automatically fabricated target. |
| Training exit one/missing checkpoint | FAILED with reason; trained does not become true. |
| Sequential training | Independent run IDs/artifacts/logs. |
| Double Train or concurrent Delete | Defined policy and no shared-volume race. |
| Worker crash/restart | Recoverable state instead of permanent RUNNING. |
| Serve before valid training | Controlled rejection before broken Deployment. |
| Later inference crash | Unavailable/failed state with visible reason. |
| Empty/oversized input | Documented 400/422 or selected handling, not 500. |
| Inference timeout/disconnection | 503/504 without leaked tunnels. |
| Unknown dataset/model/task | 404 with no permanent loading/phantom actions. |
| Failed-task polling | Reason/logs retained, no success message/forced redirect. |
| Stop/delete | Exactly declared deletion set; retained weights/answers protected. |
| Anonymous/foreign-object request | Denied before side effects. |
| SQL/YAML control-character input | Structure cannot change. |
| Clean checkout and offline UI | Reproducible README setup and bundled styles. |
| RU/EN and keyboard | Translated accessible core flow. |

## Claims not supported by the audited snapshot

- Trained: Yes does not establish successful training/high quality; run metrics are absent.
- Full active learning is not demonstrated by DummyModel.
- A dataset named medical-notes-ner does not establish NER; reviewed training/inference classify whole texts.
- Multi-user/public readiness is not established while authorization, state and isolation need repair.
- Project-wide automatic testing is not established by boilerplate files.

The supported description is an integration prototype for annotation, training pipelines and containerized text classification. After blockers and a reproducible full scenario, claims can cover demonstrated integration and verified metrics for a particular model.

## Changes that lack justification

- The selected framework stack is not itself a defect; switching language does not fix state/provenance.
- Two sklearn DataFrames do not prove a broken dataset type: the checked HuggingfaceDataset saves them and reloads DatasetDict. The issue is evaluation/reproducibility.
- Deleting all old workloads/volumes is not a safe repair; volumes may contain the only weights.
- Dependency advisories need applicability review rather than assumptions of exploitation or dismissal.

## Evidence and reproducibility

- [Dependency appendix](DEPENDENCIES_EN.md): scanner versions/counts and deduplication.
- [evidence.json](evidence.json): compact checks without secrets or user text contents.
- [isolated_probes.py](isolated_probes.py): diagnostic reproductions, not complete product testing infrastructure.

All conclusions apply to the audit snapshot. The 47 findings do not prove absence of other defects. Data immutability, safe repeat operations and classifier quality require complete post-repair tests.
