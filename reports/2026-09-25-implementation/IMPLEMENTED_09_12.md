# Implementation of audit findings 09–12

Date: 2026-09-25. Implementation and isolated acceptance checks are complete. Working model 20 still needs an explicit class interpretation before retraining; its data-dependent repair is not claimed complete.

The focused Python, SQL, TypeScript, E2E and UX guides listed in the
[approved implementation plan](../2026-09-24-implementation/PLAN_FIXES_09_12.md)
were applied to validation, transaction boundaries, reconciliation, runtime
contracts and user feedback.

## Changes

### 12: Stable annotation identities

- Dataset titles remain editable through `display_name`. The existing `dataset_name` API field is a transitional display-name alias; conflicting aliases are rejected.
- New datasets reserve a generated `dataset-UUID` technical key. Training and annotation commands use this key rather than the display title.
- A binding records both the Prodigy name and numeric record ID. Uniqueness and state consistency are enforced by database constraints. Recreating a Prodigy dataset under the same name does not silently select new data.
- Historical bindings remain UNRESOLVED unless a saved full recipe establishes an exact, unique non-session Prodigy identity. Inventory and explicit mapping are available through the `dataset_bindings` management command.
- Display-only PATCH requests do not launch annotation work and can succeed even when unrelated historical launch configuration needs repair.

### 11: Class contracts and preflight

- The dependency-free `kedrogy-contracts` package provides shared ordered-label, annotation-fingerprint, and prediction-response validation.
- Canonical editable classes are JSON string arrays. The legacy comma-separated input adapter trims outer whitespace while preserving order and case. Empty, duplicate, non-string, control-containing, comma-containing and reserved OTHER values fail validation.
- Train checks the established annotation binding, accepted class names, usable text, answer types, minimum sample count, and configured maximum annotation count before creating a run or queue entry.
- Annotation reads use the dedicated reader credentials, a read-only repeatable-read transaction, a connection timeout and statement timeout. Public summaries contain counts and a fingerprint, never annotation text.
- The training process reads once, rechecks the exact content fingerprint and conversion version, and trains on those same checked rows. Changed input produces an explicit ANNOTATIONS_CHANGED failure.
- Class edits are drafts. Published artifacts and serving revisions retain their own class order and label maps. The existing reject-to-OTHER behavior is named `reject-other-v1`; this implementation does not claim that conversion is scientifically appropriate.

### 10: Independent retraining

- Existing TrainingRun UUIDs, independent Job/ConfigMap names, Pod-attempt paths, verified publication and database queue transactions are retained.
- Idempotency replay occurs before validating a newer draft. A new training request captures its configuration, validates external annotations outside the model lock, then locks and compares the draft before creating the run.
- The interface shows recent training runs, saved classes, safe failure reasons, the published run and the run selected for serving.
- PostgreSQL tests check same-key retries, competing keys, queue rollback, duplicate Serve, and Train/resource-deletion races.

### 09: Serving lifecycle and inference

- ServingRun pins the training run, artifact receipt, runtime image, preprocessing choice, namespace, Deployment UID/generation and request key. The runtime image is the currently approved serving implementation captured once at Serve; the original training image remains in the artifact receipt. This lets a verified older checkpoint use the new HTTP contract after full offline startup verification.
- Startup outcome is immutable after completion; runtime health remains observable independently. The serving reconciler runs separately from the queue worker. Stale observations are reported as unavailable without writes during GET.
- The inference app is importable without parsing CLI arguments. Lifespan verifies checkpoint hashes and mappings, loads offline with safetensors and no remote code, calls eval, and performs a warm-up forward pass.
- Prediction responses include an integer class ID, its checkpoint label, contract version, training-run ID and serving-run ID. Django and TypeScript validate these fields. The public `predicted_class` display-label alias remains for compatibility.
- Startup/readiness/liveness probes, observed rollout generation, revision identity and a real Service prediction are required before READY.
- Inference runs in a single bounded executor slot outside the event loop. A busy model rejects additional requests; cancellation does not release the slot before the underlying thread ends.
- Empty/non-string, oversized and over-token-limit input is rejected without silent truncation. Request text logging was removed from inference and the approved identity preprocessing plugin.
- Stop is idempotent, wins over late readiness observations, and deletes only resources carrying the expected revision with Kubernetes UID preconditions. Recreate permits a brief outage while avoiding two large models sharing a single slot.
- Model-resource deletion reserves the model before queueing. Train, Serve and draft mutations cannot interleave with that deletion.
- React polls health independently of startup completion and retains input after prediction errors. Legacy forms use the same domain operations and checked display labels.

## Working metadata

The additive migrations were tested on disposable PostgreSQL, including rollback with original legacy class strings preserved. Data normalization is separated from schema changes to avoid PostgreSQL deferred-trigger/index conflicts. No working database export or backup was performed.

The working database had no active TrainingRun records when migrations were applied. Dataset 19 (`product-reviews-sentiment`) was bound to Prodigy record 6, `test3`, based on its saved full recipe. Its display title was retained. Dataset 20 (`medical-notes-ner`) and dataset 21 (`support-tickets-triage`) remain UNRESOLVED because their saved short recipes do not establish a technical identity.

Model 20's invalid preprocessing entry-point name was corrected to the installed identity function. Its draft classes remain `positive, negative`, while actual accepted annotation classes are `P` and `N`. This now fails preflight explicitly. No semantic P/N-to-sentiment conversion or annotation rewrite has been made. The user's class interpretation is still pending; model 20 is not claimed ready or successfully retrained.

## Local operation

Start Docker and the existing project cluster first. The private `.env` and separate reader credential file must be configured. From the repository root, run these services in separate terminals:

```sh
mysite/.venv/bin/python scripts/run_local.py api
mysite/.venv/bin/python scripts/run_local.py worker
mysite/.venv/bin/python scripts/run_local.py training
mysite/.venv/bin/python scripts/run_local.py serving
npm run dev --prefix app
```

The interface uses `http://127.0.0.1:5173`, proxying the API on port 8002. Port 8000 belongs to another local project and is not changed. Refresh the scoped controller token with `scripts/refresh_kubeconfig.py` when needed.

Inspect or explicitly resolve historical bindings using the configured environment:

```sh
python -m django dataset_bindings
python -m django dataset_bindings --bind APP_ID --name EXACT_PRODIGY_NAME --prodigy-id RECORD_ID
```

## Verification and limits

| Check | Current result |
| --- | --- |
| Django domain, REST, legacy, transport and deployment regressions | 60 passed |
| PostgreSQL concurrency | 5 passed |
| PostgreSQL forward migration and rollback on populated synthetic records | Passed |
| Real tiny-checkpoint inference and artifact checks | 4 inference checks and 5 artifact checks passed |
| TypeScript runtime contracts | 12 passed |
| TypeScript and Vite production build | Passed |
| Focused Ruff and whitespace checks | Passed |
| Kubernetes training/serving lifecycle with real tiny BERT | Passed: two independent runs, prediction, recovery, Stop and explicit restart |
| Browser acceptance with synthetic records | Passed: history, loaded classes, successful prediction, retained input after validation error, successful retry |
| Built backend/web/ML images | Passed: installed package checks and real deployment |
| Allowed HTTP through the deployed web proxy | Passed: SPA, health, model API, legacy page, expected 404 and real prediction |
| Network isolation | Three denial checks passed after local node recovery; allowed HTTP rechecked afterward |

There are 86 passing automated test cases across the Django, PostgreSQL, inference, artifact and TypeScript suites. Migration, Kubernetes and browser acceptance checks are additional. Focused checks also verify that a delayed readiness response cannot overwrite a newer prediction failure. Generated Django migrations retain their normal import and mutable-class-attribute conventions; their Ruff check excludes I001 and RUF012.

### Runtime evidence

The disposable fixture used 24 synthetic annotations and a tiny locally created BERT checkpoint. It did not train on working annotations. The two successful training runs used different class orders, Job UIDs and artifact directories. Both artifact receipts were verified before publication.

The scenario renamed the dataset, retrained, started serving, edited the draft classes to `future, draft`, and received a prediction using the saved checkpoint classes. It then verified stale health rejection, Pod replacement recovery, external Deployment mutation detection, Stop, and a separate explicit serving restart. Startup success remained historical after runtime health changed. A fault-injection scale command was initially denied by the scoped controller RBAC; the external perturbation was performed using administrative access restricted to the disposable namespace, without expanding the controller role.

The browser showed `READY`, both successful runs, the published/served version, and loaded classes `OTHER, negative, positive` alongside the edited draft. `good product` returned `Predicted class: OTHER`. An input containing 600 repeated tokens produced the token-limit message and retained all 3,000 input characters; replacing it with `bad product` succeeded. The tiny model proves the request and lifecycle mechanics, not sentiment accuracy.

The final images were also deployed in the disposable namespace. All four backend containers became ready. After stopping the local test reconciler, the deployed reconciler published a new health observation, and prediction through web → Django → inference returned HTTP 200 with matching training and serving identities.

| Evidence | Contents |
| --- | --- |
| [Runtime lifecycle](revision-runtime.json) | Independent run/Job/artifact identities and checked lifecycle scenarios |
| [Browser acceptance](browser-acceptance.json) | Observed success, validation and retry behavior |
| [Deployment HTTP](deployment-http.json) | Allowed routes, expected error and prediction after policy recovery |
| [Network checks](deployment-network.json) | Denied backend Service, backend Pod and web Service access from an unapproved Pod |
| [Release images](release-images.json) | Pinned local-registry image digests |
| [Installed packages](installed-packages.json) | Source files checked inside the backend and ML images |

### Local infrastructure finding

Immediately after the earlier Docker restart, the local K3s network controller had policy chains but no per-Pod firewall chains. The synthetic probe could reach all three restricted destinations. Restarting the existing `k3d-kedrogy-server-0` node restored those chains without recreating the cluster or its volumes. All three denial checks then passed; the allowed web-to-backend path and real prediction also passed afterward. This repeats the environment issue recorded during 05–08. Its underlying controller defect is not fixed by this application change: test actual enforcement after a Docker/cluster restart, and do not infer it from successful manifest application.

The working local queue worker and reconcilers were restarted after their database connections were interrupted by that node restart. The working interface and API recovered, and model 20 now correctly reports `trained=false`, `served=false`, `artifact_status=INVALID`, and serving `UNVERIFIED`.

### Cleanup and remaining scope

The synthetic namespace, fixture database and volume, temporary HTTP services, browser tab, port-forward and generated fixture credentials are removed after acceptance. The working database, annotation records, historical model resources and volumes are retained. Built images remain in the local registry. No public deployment, commit or pull request was created.

User authentication remains deferred. Annotation-session status, scientific reject/OTHER semantics, full preprocessing parity, model quality, dataset snapshots, historical workload cleanup and general retention remain separate work. A dead process during resource deletion can retain the model's deletion reservation; recovery requires verifying that no deletion worker is still active before clearing or resuming it.

An automatic approval review denied opening the working model page through the browser connector because of possible private-data transmission. Browser acceptance is restricted to the disposable fixture containing only synthetic records. No alternative browser route is used to access the blocked working page.
