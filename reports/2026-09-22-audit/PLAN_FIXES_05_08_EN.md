# Kedrogy repair plan for findings 05–08 after the first implementation

Date: 23 September 2026. Based on the [initial audit](REPORT_EN.md), [02–05 implementation report](IMPLEMENTED_02_05_EN.md) and another source review. This document is a plan; no new repairs or working database/cluster changes were made while preparing it. Password login remains deferred.

## Existing behavior and remaining goals

| Finding | Current state | Goal |
| --- | --- | --- |
| 05: commands over GET | Seven primary legacy commands require POST and result polling no longer writes. predict_model still accepts GET and can start port-forward before failing. | Close the remaining handler, expand route checks and preserve CSRF. |
| 06: deployment settings | DEBUG is off by default, secrets are external and local hosts are configured. Separate local/deploy profiles, TLS settings and safe errors are incomplete. | Separate modes, define host/TLS/proxy settings and verify external responses. |
| 07: kubectl diagnostics | Exit codes and timeouts are checked, but stderr is hidden, output is buffered before trimming and errors reach API/UI poorly. | Bound process resources and expose clear safe failure reasons throughout the application. |
| 08: false trained=true | Workers wait for Job Complete without checking artifacts. Runs lack history, Job names and best paths are reused, and historical booleans are unreliable. | Success requires a specific completed run with a verified checkpoint and independently stored run results. |

Order: 05 → 07 → 08 → 06 → combined checks. Process execution and errors must precede training verification. Profile design can proceed independently, but final response checks follow 07–08.

## 05 Complete the prohibition of commands over GET

Primary files: views, URLs/API URLs, HTML templates and tests.

1. Preserve existing require_POST for creation, Label, Train, Serve and deletion.
2. Require POST for legacy predict_model. GET currently leaves text_input undefined after starting port-forward. Reject GET/HEAD before all external processes.
3. Match forms/buttons to endpoint methods. Creation, launch, deletion and prediction use POST; navigation links open pages. Preserve CSRF and test a valid form, not only missing-token rejection.
4. Check regular, /en/, /ru/ routes and REST actions. Commands reject GET/HEAD with 405 while read pages/statuses remain available. Resolve the duplicate namespace with compatible paths and verified template reverse lookups.
5. Confirm polling never creates/deletes objects or changes the dataset pointer, whether the task succeeded or failed.

Acceptance: forbidden GET/HEAD does not enqueue, write SQL, start kubectl/port-forward or call inference. Row/task counts stay fixed. Valid POST performs one operation per request; repeated Train submission protection is specified in 08.

## 07 Reliable Kubernetes execution and actionable task errors

Primary files: tasks, API views, legacy result views and React Train/Serve/Label/Delete pages.

1. Extract process execution into kubernetes.py. Small result/error types record operation, resource, exit code, duration, timeout and reason code. Retain argument lists, explicit namespaces, server resource names and no shell.
2. Separate finite commands from long-lived processes. Reads/apply/wait have deadlines. A port-forward context manager bounds startup and guarantees termination on success, failure or interruption. Terminate, wait boundedly, kill if necessary, wait and close streams. Inference HTTP gets connect/read timeouts.
3. Bound output during reading. Trimming capture_output results to 16,000 characters limits database writes but not process memory. Drain stdout/stderr without one blocking the other and retain bounded tails, for example 64 KiB each. Separately bound published snippets. Prefer JSONPath for structured kubectl reads over complete object dumps.
4. Retain filtered stderr for local diagnostics, not arbitrary stderr in an open API. Public errors expose safe codes/messages and resource context for timeout, RBAC denial, API unavailability and Job failure. Remove secrets, DSNs and manifest fragments before saving/logging; test values split across chunks. Do not publish raw CalledProcessError output.
5. Batch database log updates by size/time and at completion rather than every line. stderr warnings with exit zero do not alone fail a task; nonzero exits always do. Logging failure cannot turn operation failure into success.
6. Read return_value only for SUCCEEDED. Installed django_tasks throws ValueError for FAILED even when is_finished is true. Existing failed tasks return HTTP 200 with status=FAILED, is_finished=true, return_value=null and safe error. Unknown IDs return 404; wrong task types produce controlled errors without tracebacks.
7. Apply the contract to legacy/React results. Success text and navigation occur only after success. Failed screens show reasons and retry actions, stop polling and distinguish polling-network failures. Shared polling avoids overlapping requests, cancels transports/timers on unmount and validates JSON. Catch values are unknown.

Acceptance uses real child processes: exit seven yields FAILED and a visible reason. Cover timeout, absent executable, stderr-only output, large streams, hung processes and cleanup. Control secrets remain absent from HTTP, metadata and accessible logs. Polling FAILED does not itself produce HTTP 500 or success UI. Use events or deadline polling instead of fixed sleeps.

Local tunnel cleanup belongs here; full inference and deployed readiness belong to 09.

## 08 Verifiable training and separate TrainingRun records

Primary files: models/migrations, tasks/manifests, serializers/API, train nodes and ModelDetail/Home/Train pages.

1. Add TrainingRun with UUID, model/task links, Job namespace/name/UID, status/timestamps, safe error and immutable parameter snapshot: labels, source/dataset, seeds and image digest. Separate it from editable model cards. Record Pod attempts and verified artifact PVC/path/manifest/checksums. Exclude secrets. Parameter snapshots do not themselves snapshot dataset contents.
2. Define QUEUED → RUNNING → VERIFYING → SUCCEEDED and active-state exits FAILED, TIMED_OUT and INTERRUPTED. Success is terminal. Transitions atomically verify the current state; do not hold a database transaction while waiting on Kubernetes.
3. Enforce one active run per model in the database. Duplicate deliveries reuse the run/Job; repeated POST with one idempotency key returns the same run. Another key during active training returns 409 and its ID. Terminal completion permits a new independent run.
4. Job/ConfigMap names include the run UUID. Do not reuse train-{model_id}. Publish queue work after run commit; recovery handles commit/enqueue gaps and worker crashes. Retried workers verify Job UID/ownership and resume observation instead of creating duplicates.
5. Observe Job conditions and container attempts: Complete, Failed, DeadlineExceeded, exits, OOMKilled and image/start failures. Do not wait an hour solely for Complete. Set activeDeadlineSeconds plus an application wait limit. A local timeout does not stop a Job; deadline cleanup addresses only the verified run/UID. See [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).
6. Store run artifacts under runs/<run_id> on the existing model PVC. Each Pod attempt writes a temporary directory. Old best files or another attempt's partial files are not new output. Preserve the last verified successful artifact after retraining failure. Publish the directory/marker atomically on the volume.
7. Save model/config/tokenizer and verify by loading, not file existence. Load locally in the ML image, check labels/num_labels and perform a finite forward pass. Support actual formats, including sharded weights. Write the run/parameter/checksum manifest only after verification.
8. Mark SUCCEEDED only after Job success and valid verification bound to the current run, Job, Pod and artifact path. Interrupted delivery is recovered by a scoped read-only verification container. An arbitrary success log line is insufficient.
9. Distinguish the last attempt's outcome from available verified model versions in API/UI. A failed latest run may coexist with an earlier usable version. Transitional trained indicates artifact availability; failure does not destroy the prior version.
10. Serve selects a particular verified artifact and passes its path to inference; fail clearly before container launch if absent. Readiness/full serving state belong to 09. Editing card labels does not rewrite checkpoint metadata.
11. Historical models remain unverified. Do not manufacture SUCCEEDED runs from trained=true. A separate command previews old-volume checks before recording verified legacy artifacts or missing/invalid results. Model #20's empty volume must report no usable model. Do not delete historical Jobs/PVCs or silently change case/classes.
12. Reconcile incomplete runs at worker startup or on a schedule: resume live Jobs, verify completed output, retry boundedly on network failure, or record interrupted/timed-out states after confirmed loss and expiry. GET remains read-only. Extend RBAC only for any necessary selected CronJob operation.

Acceptance: failed Jobs, mismatched labels, empty/corrupt checkpoints, missing tokenizers and foreign manifests never yield SUCCEEDED. Valid save/load does. Sequential training creates independent runs/Jobs/directories, concurrent requests cannot double-launch, restart cannot duplicate or leave permanent RUNNING, and failed retraining preserves the old verified version.

Separate fast state tests, temporary PostgreSQL transactions and real Kubernetes Jobs. Positive ML checks use a small synthetic model/dataset. Before closing the phase, complete a real short standard-pipeline cycle with consistent labels; dummy files do not replace it.

## 06 Local/deploy settings and safe responses

Primary files: settings, ASGI/WSGI/URLconf, infrastructure renderer, mysite/postgres manifests, Prodigy ingress, Docker/Tilt and startup docs.

1. Extract settings_base, settings_local and settings_deploy. Retain mysite.settings as a compatible local entry point and isolated tests. Deployments, workers and migrations explicitly select DJANGO_SETTINGS_MODULE/CLI profiles.
2. Local uses loopback HTTP and explicit localhost/127.0.0.1 hosts/origins with deliberate DEBUG opt-in. Deploy always disables DEBUG and requires hosts/origins/secrets without wildcard/testserver defaults. Invalid required settings stop startup by field name without values.
3. Document TLS at ingress/proxy. Deploy uses secure session/CSRF cookies and consistent HTTPS redirects. Add HSTS after TLS verification without automatic preload/all-subdomain policy. Trust SECURE_PROXY_SSL_HEADER only behind a proxy that removes client values and sets its own; prohibit backend bypass. See [Django settings](https://docs.djangoproject.com/en/6.0/ref/settings/#secure-proxy-ssl-header).
4. Replace hostless Prodigy / ingress with distinct explicit application/annotation hosts. app.kedrogy.test and label.kedrogy.test are isolated test names, not selected public domains. Retain simple local HTTP. Deploy PostgreSQL stays internal; local external access is not inherited automatically.
5. Configure CORS/CSRF origins through environment without accepting arbitrary origins. Test actual React/Vite/API paths and legacy POST forms. CORS is not authorization and login remains deferred.
6. Standardize /api/ errors: code, message, request ID and optional field errors. Cover DRF and outside-DRF failures, including CSRF, routing, host validation, middleware and 500s. HTML keeps normal error pages. External responses exclude traceback, paths and environment values; logs are filtered.
7. Verify the whole profile: Uvicorn, built frontend, collectstatic, safe health endpoints and immutable backend image references. Distinguish host and cluster registry addresses in k3d; synchronize renderer and final YAML instead of retaining host/latest references.
8. Run django check --deploy with deploy settings. Interpret warnings rather than globally silencing them. Document deliberate exceptions such as HSTS preload. See the [deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/).

Acceptance: local remains password-free without forced HTTPS. Deploy hides tracebacks, rejects unknown Hosts, respects trusted proxy HTTPS without loops and does not trust direct-client spoofed headers. API errors have intended statuses/JSON; frontend, Django static and Prodigy use their intended routes.

No public domain/certificate has been selected. This phase prepares and isolates a deployment profile; it does not publish externally. External Prodigy/YSZ credential rotation remains an open part of 04, not a prerequisite for designing these changes.

## Scope and dependencies

- Failed-state presentation touches 14–15 and is necessary for 07 acceptance.
- TrainingRun and unique Jobs touch 10 and are necessary to bind success to a run.
- Clear label/empty-data rejection does not encompass a complete OTHER/data/metrics redesign.
- From 09, include only verified artifact selection and refusing Serve without it. Serving reconciliation and complete Prediction failed repair are not claimed.
- Preserve user changes. Test additive migrations on synthetic databases before touching existing rows/volumes. Historical resource cleanup and working-database transfer are outside fixtures.

## Pattern analysis

Problem: reconcile a background task, external Kubernetes Job and saved ML artifact across controlled failures, retries and restarts.

Patterns: bounded process I/O/deadlines/context management (Python concurrency 67; robustness 82, 83, 88); typed errors/results and explicit invalid-result exceptions (robustness 81, 85; collaboration 118, 121, 124); persisted TrainingRun plus small dataclass/enum results (classes/interfaces 56; dictionaries 29); pure transitions with isolated DB/Kubernetes adapters and real processes/PostgreSQL (testing 109–112); concurrency invariants with events/deadline polling; and one TypeScript boundary error contract, unknown catch values and request cancellation.

Rejected: new Celery/Redis, broad asyncio migration or a custom operator; trained/Job-Complete-only success; unconditional retries; publishing raw stderr/tracebacks; replacing every test or frontend page.

Proposed module split:

```text
mysite/src/mysite/
  settings_base.py, settings_local.py, settings_deploy.py
  settings.py, test_settings.py        # Compatibility and test isolation
  errors.py                           # Safe API/HTML errors
kedrogy/src/kedrogy/
  kubernetes.py                       # Processes, diagnostics and tunnels
  training.py                         # TrainingRun transitions/coordinator
  task_results.py                     # Shared task result presentation
  models.py, migrations/              # TrainingRun and artifact links
  tasks.py, manifests.py               # Per-run execution/documents
  api_views.py, serializers.py, views.py
  management/commands/                # Legacy verification/recovery
example/mykedro/src/mykedro/
  artifacts.py                        # Checkpoint save/load/manifest
  pipelines/train/nodes.py             # Verification after training
app/src/
  api/tasks.ts, hooks/useTaskStatus.ts  # Contracts and controlled polling
  pages/*TaskPage.tsx, TrainModelPage.tsx, ModelDetailPage.tsx, HomePage.tsx
tests/                                # Processes, API, transactions, ML, deploy
```

Decisions: retain django_tasks; TrainingRun models the domain rather than replacing the queue. One active run per model is easier to verify than concurrent writes to one PVC. Use run/attempt directories on the existing volume and verify later deletion preserves the published version. A bounded synchronous subprocess adapter covers current Linux/macOS use; an async framework is unnecessary.
