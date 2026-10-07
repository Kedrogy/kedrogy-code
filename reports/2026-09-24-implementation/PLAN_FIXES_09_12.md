# Plan for audit findings 09–12

Date: 2026-09-24. Status: design only. This document is based on the original audit, the completed 05–08 implementation, and a fresh source review. No application code, database records, Kubernetes resources or credentials were changed while preparing it. User authentication remains deferred.

## Current baseline

| Finding | What already exists | Remaining work |
| --- | --- | --- |
| 09 — truthful serving readiness | Verified artifact required before Serve, explicit checkpoint path, bounded subprocess/HTTP transport, rollout wait | Model-aware probes, durable serving identity, ongoing health reconciliation, a consistent prediction response contract and UI state |
| 10 — independent retraining | TrainingRun UUIDs, unique Jobs and immutable ConfigMaps, Pod attempts, separate artifact paths, saved parameters, database idempotency and one-active-run constraint | Close remaining regression scenarios and expose useful run history; retain the existing implementation |
| 11 — class validation | External whitespace trimming, empty/duplicate checks, ordered run snapshots, reserved OTHER rejection at Train, checkpoint label-map verification | Structured editable labels, early annotation compatibility checks, immutable published/served class semantics and a safe legacy migration |
| 12 — dataset rename | A stable application primary key, but one mutable dataset_name still controls both presentation and annotation queries | Separate display name from Prodigy identity, migrate known bindings, diagnose ambiguous historical bindings and route all annotation/training reads through the stable identity |

An additional confirmed source defect belongs in 09: `predict/src/ysz/predict/serve.py` returns a label string in `predicted_class_id`, while `kedrogy/prediction.py` requires that field to be an integer. The previous stage's transport checks did not cover a successful real inference response. A healthy container alone will therefore not close the prediction bug. The new acceptance test must traverse inference → Django → React with a real tiny model.

The previous implementation report records model 20 as INVALID with a stale served flag. That is a previous observation, not a fresh database inspection in this planning turn.

## Installed plugin guidance used

This plan applies focused domain guides, rather than adopting an unrelated framework or rewriting the project around a generic design template.

| Installed guide | Concrete application |
| --- | --- |
| [Python: classes and interfaces](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/classes-interfaces/SKILL.md), Items 48, 51, 56 | Pure validation functions and small immutable launch/label/observation records; explicit adapters around DB, Kubernetes and inference I/O |
| [Python: robustness](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/robustness/SKILL.md), Items 80–85, 88 | Typed domain failures, short exception boundaries, context-managed cleanup, no swallowed errors or assert-based input validation |
| [Python: concurrency](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/concurrency/SKILL.md), Items 67–78 | Reuse bounded subprocess transport; keep blocking inference off the async event loop; bound execution rather than spawning arbitrary threads |
| [Python: testing](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/testing-debugging/SKILL.md), Items 109–112 | Real PostgreSQL and inference integration tests, isolated fixtures, injectable clocks/adapters for deterministic transition tests |
| [SQL: PostgreSQL DDL](/Users/millafedotova/.codex/plugins/cache/personal/sql-best-practices/0.1.0/skills/postgresql-ddl-security/SKILL.md), Golden Rules 1–3, PG-D6 | Named uniqueness/FK/check constraints; uniqueness enforced by PostgreSQL; referenced artifacts protected from deletion while used |
| [SQL: native types](/Users/millafedotova/.codex/plugins/cache/personal/sql-best-practices/0.1.0/skills/postgresql-native-types/SKILL.md), PG-T1, PG-T2, PG-T8, PG-T12 | UUID identities, explicit timestamp/state columns, JSON only for bounded label lists and immutable receipts, not an unbounded replacement for related records |
| [SQL: data scrubbing](/Users/millafedotova/.codex/plugins/cache/personal/sql-best-practices/0.1.0/skills/data-scrubbing/SKILL.md), TiS 10.4, 10.5, 10.7 | Diagnose old values before tightening constraints; separate overloaded names; do not silently change annotation case or collapse ambiguous records |
| [E2E: concurrency](/Users/millafedotova/.codex/plugins/cache/personal/e2e-testing-best-practices/0.1.1/skills/testing-concurrency/SKILL.md), Rules 1, 4, 8–13, 19–20 | Test observable invariants, use barriers and bounded condition waits, verify intermediate states, inject time instead of relying on fixed sleeps |
| [TypeScript: runtime validation](/Users/millafedotova/.codex/plugins/cache/personal/claude-typescript/0.1.0+codex.20260618094037/skills/runtime-types-and-validation/SKILL.md), Rules 1–3, 7 | Treat fetch JSON as unknown; validate serving/prediction/dataset contracts; behavior tests in addition to tsc |
| [UX: attention and focus](/Users/millafedotova/.codex/plugins/cache/personal/ux-best-practices/0.1.0/skills/attention-focus/SKILL.md), Rules 5, 9, 10 | Inline actionable status, separate model configuration from launch actions, show class names rather than internal class IDs |

## Execution order

1. Preserve the current changes and establish focused regression tests, including the prediction-contract mismatch.
2. Implement 12: stable annotation identity and compatible display-name editing.
3. Implement 11: structured class configuration and annotation preflight.
4. Complete the remaining 10 regression/history work against the new identity and class contracts.
5. Implement 09: inference contract, probes, serving lifecycle, reconciliation and UI.
6. Run one isolated end-to-end lifecycle, migrate validated working metadata, and produce an evidence report. Resolve model 20 only with an established annotation binding and class configuration.

The inference-contract test and implementation can be developed before the data migrations. The final working-data demonstration depends on 12 and 11.

## 12 — Preserve annotation identity when renaming

1. Introduce `display_name` as the editable presentation field and `prodigy_dataset_name` as a stable technical key. Keep the application dataset primary key unchanged. New technical names are server-generated from a stable identifier and never derived from the display title. Ordinary PATCH must not change an existing binding.
2. Store binding state (`PENDING`, `BOUND`, `UNRESOLVED`) and the observed Prodigy dataset record ID once it exists. Scope uniqueness by the configured annotation-store alias if the application supports more than one store. Detect external deletion/recreation under the same name rather than silently selecting replacement data. Do not add unmanaged cross-database foreign keys into Prodigy's schema.
3. Preserve compatibility deliberately: keep the existing database name column if useful, expose `display_name` through the serializer, and temporarily accept the old API `dataset_name` field as a display-name alias. Reject conflicting old/new values in one request. There must be one stored display value, not two independently editable copies.
4. Update dataset serialization, launch validation, recipe arguments, example exclusion queries, training annotation reads and run snapshots to use the technical binding. A title-only edit validates the title and leaves launch configuration unchanged. Runtime launch checks remain mandatory.
5. Support existing long-form recipe options through a validated adapter: resolve the old recipe's dataset argument once, check its relationship to the established binding, then build future arguments from structured fields. Renaming a title must neither rewrite an active ConfigMap nor launch/restart Prodigy.
6. Add a read-only binding inventory command. Compare application IDs, exact Prodigy names/IDs, relevant saved recipe/configuration evidence and annotation counts. Exclude session-only sets where the installed Prodigy schema identifies them. Do not export annotation texts or credentials into the report.
7. Automatically backfill only unambiguous, verified bindings. Matching a similar display name, selecting the active Prodigy set, or taking the only nonempty set is insufficient evidence. Keep uncertain rows UNRESOLVED, with a precise diagnostic and an explicit mapping command. If evidence cannot establish intent, obtain the user's choice for those particular rows; continue independent implementation and synthetic tests.
8. For new datasets, persist the generated technical key before queueing annotation work. Mark it BOUND only after the corresponding Prodigy set is observed. An unresolved historical row must not silently create a fresh empty set under its new display title.

Acceptance: rename a dataset before, during and after training/annotation; its Prodigy key, selected example identities and existing TrainingRun snapshots remain unchanged. Two concurrent creates cannot claim one technical key. Unknown/ambiguous bindings fail before training. Display names may repeat if their technical identities differ.

## 11 — Validate classes before expensive training

1. Make an ordered JSON string array the canonical API/storage shape for editable classes, with the current maximum count/length bounds retained. Keep a temporary comma-string input adapter for existing clients. Reject mixed/non-string arrays, empty values, controls, duplicates after outer trimming and the exact reserved OTHER token. Preserve case and order. Do not split a canonical array element on punctuation; reject commas where the current Prodigy CLI cannot represent them unambiguously.
2. Provide one tested normalization contract for model forms, REST/legacy entry points, annotation configuration and the training input checker. The annotation reader must not silently normalize historical labels. Report whitespace/case differences as proposed corrections; apply no `N → n` or `POS → positive` mapping without explicit data semantics.
3. Add preflight for a new training request: verify the stable dataset binding, parse annotation records, report accepted label counts, rejected/ignored counts, unknown labels, missing/invalid label fields, empty data and insufficient usable examples. Show safe summaries and bounded record identifiers rather than full text. Use the existing reader privilege boundary and bounded DB operations.
4. Run preflight before creating a training Job. Use short database transactions: capture the intended configuration, read/validate external annotations, then lock and compare the configuration revision before atomically creating the TrainingRun and queue row. A changed configuration yields a retryable conflict. Replaying an existing idempotency key returns that run before validating a newer draft.
5. Close the validation/read race without introducing a full dataset-versioning subsystem: save a deterministic fingerprint of the exact relevant annotation rows, binding and conversion-policy version. The training process reads its input once, verifies the fingerprint and uses those same validated rows. If annotations changed after preflight, fail with `ANNOTATIONS_CHANGED`; never train silently on a different selection. This detects changes; it does not freeze all future annotations or claim full input reproducibility across data edits.
6. Treat editable classes as a draft for the next training run. Each TrainingRun retains its ordered class schema and integer `label2id`/`id2label`; each serving revision points to that exact run. Reordering/editing the draft cannot relabel an already published or running checkpoint. Do not reinterpret class ID 0 using the current editable list.
7. Migrate valid legacy comma strings without reordering. Leave invalid/ambiguous legacy values visible as requiring correction and reject their next Train request. Do not overwrite existing artifact manifests or historical run snapshots.
8. Keep the existing `reject → OTHER` conversion explicitly versioned for compatibility in this stage. The audit's separate annotation-semantics finding must decide whether that conversion is scientifically appropriate. Preflight must not present it as proof that rejected examples are a valid OTHER class.

Acceptance: `POS, NEG` becomes `["POS", "NEG"]`; `N` versus `n` is reported before Job creation; duplicates/empty/OTHER inputs fail at the API; changes between preflight and training are detected; changing draft classes does not change the displayed label of a running model.

## 10 — Finish independent retraining and expose its history

1. Retain the existing TrainingRun schema, atomic database queue insertion, unique Job/ConfigMap names, UID checks, Pod-attempt paths and artifact verification. Do not replace them with another job framework.
2. Add missing regression cases: run A succeeds, draft configuration changes, run B creates a new Job and snapshot; the same checks after failure and timeout; late observations from A cannot finish B; a replacement Pod is tracked as a distinct attempt; an unrelated Pod with a misleading label is ignored.
3. Confirm idempotency through API, legacy forms and React: repeated delivery of one user action returns the same run, a deliberate new Train after completion gets a new key, and competing requests during an active run get a conflict without another queue row. Retain the request key after an ambiguous network error.
4. Check changed draft settings and dataset rename against saved run snapshots. Two sequential runs may use different class/options snapshots; editing a card never modifies the earlier run's configuration, receipt or logs.
5. Add a compact run-history view using the existing runs endpoint: state, times, class/configuration summary, safe failure reason and which run is published. Clearly distinguish the published training run from the run currently loaded by inference.
6. Continue to preserve an earlier verified publication on failed retraining. Historical Job/PVC retention and garbage collection remain separate work; this stage must not delete arbitrary old resources to make a test pass.

Acceptance: two deliberate sequential Train actions have different run IDs, Job UIDs and artifact directories; retries of one action have only one run; the UI explains which version is trained and which version is being served.

## 09 — Make serving readiness and predictions trustworthy

### Inference contract and process lifecycle

1. Refactor CLI parsing into `main()` and make `create_app(config)` importable without parsing process arguments. Load the tokenizer/model and the configured preprocessing implementation through FastAPI lifespan. Validate the pinned artifact, load offline with the existing safe-checkpoint policy, call `eval()`, run a small forward pass and clean up on shutdown. Reject an unknown preprocessing entry point explicitly. The planned lifecycle follows [FastAPI lifespan guidance](https://fastapi.tiangolo.com/advanced/events/).
2. Define a versioned response containing integer `class_id`, string `label`, `training_run_id` and `serving_run_id`. Validate the numeric range, mapping and version identity at the Django boundary. Keep the existing public `predicted_class` field as a documented display-label alias during migration; update React and legacy HTML together. An old incompatible inference process must be marked incompatible, not silently guessed/coerced.
3. Add `/livez` for process responsiveness and `/readyz` for a loaded, warmed, correctly identified model. Readiness returns the serving/training identities and contract version, without filesystem paths or secrets. Cheap health probes must not execute a full forward pass repeatedly.
4. Add startup, readiness and conservative liveness probes. Configure the startup budget to allow measured model loading, and keep the controller deadline consistent with that budget. Validate the rollout's observed generation and new Pods, then make an actual prediction through the Service. A successful `kubectl apply` or a Ready Pod from a previous revision cannot complete Serve. These probes have distinct roles described in the [Kubernetes probe documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).
5. Keep blocking tokenization/PyTorch work off the event loop with bounded execution. This is necessary so health checks remain responsive during a prediction. Limit concurrent inference and return an explicit busy response rather than accumulating an unbounded queue. Start conservatively with one model execution at a time; do not claim load-performance targets without measurement.
6. Apply a minimal explicit input policy while touching this endpoint: validate nonempty string/type and request size, reject text beyond the checkpoint's supported token limit with a safe validation error. Do not silently truncate text. Remove raw text prints. This is a narrow dependency on findings 24/25; advanced chunking, throughput tuning and a full load/privacy audit are not claimed complete here.

### Durable serving state

7. Add a serving revision/run tied to a protected TrainingRun reference. Persist its pinned artifact receipt, image, supported preprocessing choice, namespace, resource UID/generation, idempotency key, timestamps, safe error, observation freshness and reconciliation lease. Never build an existing model's inference identity from its mutable draft classes or display name.
8. Use runtime states `STARTING`, `READY`, `UNAVAILABLE`, `FAILED`, `STOPPING`, `STOPPED`, plus an explicit unknown/unverified legacy state. Keep startup-operation completion separate from current runtime health: an operation that once completed successfully stays in history, while its service may later become UNAVAILABLE. Extend shared UI/task contracts deliberately rather than forcing mutable health into a terminal SUCCEEDED task.
9. Reconcile independently of the queue worker, including after startup success. Suggested initial settings are a 10-second observation interval, 30-second maximum freshness, a 5-second health-request timeout and a 5-minute startup budget; expose them in configuration and tune against the measured checkpoint load. Brief infrastructure uncertainty becomes UNAVAILABLE/unknown with last-observed time, not a permanent false READY or immediate destructive recovery.
10. Recovery follows the same pinned revision: a replacement Pod can restore READY after probe and smoke checks; a startup deadline records failure; a deliberately stopped revision is never resurrected. A missing Deployment is diagnosed explicitly and requires a controlled restart, rather than racing manual deletion by blindly reapplying forever. GET status remains read-only.
11. Serialize Serve/retry/Stop and model deletion using a durable per-model operation reservation plus short row locks. Protect changes with revision/UID/resourceVersion checks so stale reconcilers cannot publish or delete a newer deployment. Include Train-versus-delete and Serve-versus-delete guards at both launch and destructive-operation boundaries. Do not hold a database transaction open while waiting for Kubernetes.
12. For this local single-replica project, initially use one deployment slot per model with explicit replacement and a brief STARTING/unavailable interval. This avoids requiring two full model copies or cross-node concurrent mounts of the current ReadWriteOnce volume. A failed replacement keeps historical artifacts; it does not promise uninterrupted serving. Blue/green deployment is a later capacity/lifecycle choice.

### API, UI and migration

13. Expose current serving state, loaded training version, last health observation and a safe reason. Derive the compatibility `served` Boolean from fresh READY state; do not trust the old writable Boolean. A stale observation is conservatively unavailable in the response without writing during GET.
14. Check serving state server-side before Predict, and validate the returned revision identity so a rollout race cannot relabel a response using another model version. Use explicit HTTP outcomes: validation errors for invalid input, conflict for competing operations, unavailable for a non-ready service, and gateway timeout for an inference deadline. Do not turn every failure into HTTP 500.
15. Show inline Starting/Ready/Unavailable/Failed/Stopped states in React and legacy pages. Enable Predict only for a fresh ready version, show labels rather than numeric IDs, and preserve typed text after an error. Poll current health separately from the completed Serve task. Keep the existing cancellation, timeout and retry behavior.
16. Inspect legacy serving resources without deleting them. Adopt a resource only if the artifact, identity and supported HTTP contract can be established. Otherwise mark it unverified/unavailable and require an explicit new Serve after a verified training run. Model 20 cannot be repaired by setting flags; first resolve its data binding/classes, obtain a valid checkpoint, and then demonstrate real prediction.

Acceptance: a missing or broken checkpoint never reaches READY; a real ready service produces a checked label through Django/React; process crash or stale observations remove readiness; Pod recovery is observed without duplicate launches; repeated Serve is idempotent; class edits cannot alter an older deployed model's interpretation; a delayed response from a different revision is rejected safely.

## Proposed module boundaries

| Area | Files/modules |
| --- | --- |
| Dataset identity and compatibility | Existing models/migrations/serializers/launch_config; a focused `dataset_bindings.py` adapter and management inventory/mapping command |
| Class normalization and preflight | A small pure label contract, an annotation-reader adapter and `training_preflight.py`; existing TrainingRun snapshot and training input nodes |
| Serving domain | `serving.py`, an independent management reconciler, existing manifests/tasks/API/views/prediction transport |
| Inference lifecycle | Existing `predict/src/ysz/predict/serve.py` and CLI; small config/response types as needed |
| React | Typed dataset/model/serving contracts; existing dataset/model/task pages; small run-history/status components |
| Checks | Focused domain tests, real PostgreSQL race tests, inference lifespan/contract tests, one browser/Kubernetes fixture |

Reuse existing helpers and small pure functions before introducing generic base classes. A shared ML contract must be packaged so both images use it without importing Django into the ML runtime or creating a circular package dependency. Keep schemas/validation authoritative; if handwritten frontend guards become duplicative, use a small schema library and derive TypeScript types from it. No ORM replacement, new queue, microservice platform, graph extension or authentication system is needed.

Database changes should be additive where possible. Use UUIDs and explicit state/time columns for serving identity, FK protection for referenced runs, and unique constraints for idempotency and dataset bindings. Cross-system Prodigy existence checks belong in the adapter; PostgreSQL CHECK constraints cannot guarantee remote-table consistency. This follows the [PostgreSQL constraint rules](https://www.postgresql.org/docs/18/ddl-constraints.html).

## Verification and rollout

| Scenario | Required observable result |
| --- | --- |
| Dataset display rename concurrent with annotation/training | Same technical binding and selected example identities; old run unchanged |
| Ambiguous old binding or external dataset recreation | Explicit unresolved/conflict result; no guessed data selection |
| Wrong case, empty/duplicate/reserved class | Safe preflight error before any training Job |
| Annotation changes after preflight | Fingerprint mismatch and controlled failure |
| Train success → edit draft → Train again | Two Jobs/receipts with independent snapshots |
| Duplicate requests and parallel different requests | One run per idempotency key; at most one active training run |
| Inference result for class ID 0 | Correct checkpoint label, no falsy-value omission |
| Missing weights, wrong tokenizer, incompatible response | No READY publication; visible reason |
| Ready → process crash → replacement Pod | Unavailable observed, then ready only after checks for the same revision |
| Queue worker/reconciler interruption | Recovery from persisted identity; no duplicate deployment |
| Serve/retry/Stop/delete races | No orphaned active operation, no stale publication and no deletion of a newer revision |
| Real tiny-model end-to-end path | Dataset → annotations → preflight → Train → verified artifact → Serve → Django prediction → label in browser |

First run focused unit and PostgreSQL integration checks, then build the backend and ML images and verify their installed local package contents. Rebuild the web image for matching API contracts. Use an isolated namespace/database with synthetic annotations and a tiny checkpoint, and clean it up after collecting safe receipts. Execute the heavy builds and ML/Kubernetes checks sequentially to avoid repeating the previous Docker resource-contention incident. Also verify network-policy enforcement after any Docker/cluster restart.

Keep the existing 05–08 checks green, including GET/HEAD/CSRF behavior, failed-task handling, artifact verification and subprocess cleanup. Use barriers/condition waits and bounded deadlines for concurrency tests. Browser acceptance must exercise successful inference as well as failure pages; mocked transport failures alone are insufficient.

Before working metadata migration, check actual binding evidence and the status of active runs. Exercise migrations and their rollback on disposable PostgreSQL; keep legacy compatibility fields for the transition and never rewrite completed run receipts. Use the project's permitted backup mechanism if one is available; do not assume an export was taken or bypass the previously rejected database-export action. Record exactly what changed and what remains unresolved. Do not publish 09 as complete for model 20 until its real configuration and inference path pass.

## Scope limits

- Login/password and public deployment remain deferred.
- This stage does not automatically delete old Jobs, PVCs, datasets or models.
- Uncertain historical data mappings require a concrete user choice only when available evidence cannot establish them; no blanket approval gate is needed for implementation or synthetic testing.
- The global annotation-session/labelled redesign (13), reject/OTHER semantics, conflicting annotations, source-ingestion identity, full preprocessing parity, model-quality evaluation and comprehensive serving retention remain separate findings. Narrow dependencies are described above rather than claiming those findings fixed.
- Full dataset snapshots and bit-for-bit model reproducibility are not promised by a fingerprint and saved random seed.
- Successful isolated lifecycle tests prove mechanics; they do not establish the sentiment model's accuracy for the diploma.
