# Plan for audit findings 13–16

Date: 2026-09-25. Status: implemented on 2026-09-26; see the [implementation report](../2026-09-26-implementation/IMPLEMENTED_13_16.md). The text below records the approved plan. All implementation text, comments, diagnostics and documentation will be in English. Authentication remains deferred.

## Current baseline

This plan follows a fresh source review and the [09–12 implementation report](IMPLEMENTED_09_12.md). Original findings are in the [initial audit](../2026-09-22-audit/REPORT_EN.md). Historical resource counts and the March queue task in that audit are past observations, not a new live inventory.

| Finding | Already implemented | Remaining defect |
| --- | --- | --- |
| 13 — annotation status | The annotation worker updates the legacy pointer after rollout; stable Prodigy name/ID bindings exist; model creation in React now uses binding state | `labelled` still means “selected by DjangoLastDataset”; the Home badge incorrectly chooses the last dataset in a list; neither proves annotations exist or Prodigy is available |
| 14 — failed task reporting | `task_results.present()` reads return values only on success; missing/mismatched results become 404; shared React progress UI distinguishes failure and connection errors | Preserve these fixes, extend them to durable annotation/deletion operations, and cover recovery and partial deletion failures |
| 15 — coordinated deletion | Resource deletion reserves the model, stops serving and attempts Service/Job/ConfigMap/PVC cleanup; active operations block record deletion | Ordinary record deletion can still leave resources; dataset cascade bypasses external cleanup; some resource deletes identify objects only by name; a crashed deletion worker can leave `resources_deleting=True` indefinitely |
| 16 — conflicts and recovery | Training and serving have durable identities, idempotency, constraints, leases and independent reconciliation | Annotation still overwrites one shared Deployment without a durable operation; deletion has only a Boolean reservation; legacy queue RUNNING rows do not establish whether work is alive |

Retain the existing TrainingRun and ServingRun implementations. Do not replace the queue or introduce a general workflow engine.

## Installed plugin guidance

| Guide | Application |
| --- | --- |
| [Python robustness](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/robustness/SKILL.md), Items 80–85, 88 | Explicit domain errors, short exception boundaries, cleanup and actionable partial failures |
| [Python concurrency](/Users/millafedotova/.codex/plugins/cache/personal/python-best-practices/0.1.0/skills/concurrency/SKILL.md), Items 67, 71–74 | Bounded external calls and separate operation logic from scheduling; process-local locks are not sufficient for multiple workers |
| [SQL PostgreSQL DDL](/Users/millafedotova/.codex/plugins/cache/personal/sql-best-practices/0.1.0/skills/postgresql-ddl-security/SKILL.md), Golden Rules 1–3 and PG-D6 | Named uniqueness/check/FK constraints, protected history and explicit deletion ownership |
| [E2E concurrency](/Users/millafedotova/.codex/plugins/cache/personal/e2e-testing-best-practices/0.1.1/skills/testing-concurrency/SKILL.md), Rules 1, 4, 8–13, 19–20 | Observable invariants, PostgreSQL races, injected time and bounded waits around crash/recovery scenarios |
| [TypeScript runtime validation](/Users/millafedotova/.codex/plugins/cache/personal/claude-typescript/0.1.0+codex.20260618094037/skills/runtime-types-and-validation/SKILL.md), Rules 1–3, 7 | Validate new operation and annotation payloads at HTTP boundaries; test behavior as well as types |
| [UX controls](/Users/millafedotova/.codex/plugins/cache/personal/ux-best-practices/0.1.0/skills/controls-components/SKILL.md), Rules 1, 2, 4, 12, 16–20 | Distinct action labels, visible progress, output-only status and one concrete deletion preview |

## Execution order

1. Preserve current changes; add regressions for the remaining defects and retain the existing failed-task tests.
2. Establish durable annotation/deletion identities, operation ownership and transition rules from 16.
3. Implement annotation lifecycle and per-dataset data observations for 13.
4. Implement resumable deletion and explicit retention choices for 15.
5. Extend the shared status API and React/legacy screens for 14.
6. Run isolated acceptance, inspect historical operations/resources read-only, and write the implementation report.

## 13 — Separate annotation data from the active session

### Data observations

1. Replace `DjangoLastDataset` as a source of annotation truth. Expose separate `annotation_session` and `annotation_data` objects. A successful launch is not evidence that anyone saved annotations.
2. Observe data using the established Prodigy name **and numeric ID**, excluding session-only datasets. Reuse the dedicated reader role and bounded read-only transactions. Return counts, safe diagnostics and observation times; do not send annotation texts to status pages.
3. Report `EMPTY`, `PRESENT`, `INVALID` or `UNKNOWN`, with accepted/rejected/ignored/invalid record counts where available. Count stored answers, not “unique texts” or completed labeling percentage. Binding replacement, malformed content and database failure must remain distinguishable from an empty dataset.
4. Refresh observations through an independent bounded observer and an explicit Refresh action. Persist freshness; ordinary GET returns observations without launching work or making one full annotation scan per dataset. Batch identity/count queries and bound deeper validation. Stale observations become unknown rather than silently asserting current data availability.
5. Keep Train's model-specific preflight authoritative. Annotation presence alone cannot prove compatibility with a model's draft classes or sufficient usable examples. Do not change the versioned reject-to-OTHER conversion in this stage.
6. Deprecate the old `labelled` field. During compatibility, it may report true only for a fresh positive data observation; new UI must use the explicit status and never interpret an unknown observation as “no annotations.” Remove the legacy pointer after all maintained consumers have migrated.

### Annotation lifecycle

7. Add an AnnotationRun with UUID, dataset binding, immutable launch snapshot, request key, namespace, resource identities, startup outcome, current health, timestamps, safe errors and a reconciliation lease.
8. Deliberately support **one active annotation session per project namespace**. Reserve a singleton annotation slot transactionally. Keep it reserved through unavailability and incomplete cleanup; do not release it just because a startup deadline elapsed.
9. A repeated request key returns the same operation. Another launch while the slot is occupied returns a conflict identifying the existing session. Provide Open session and Stop annotation actions. Switching datasets requires stopping the old session first; no silent takeover or unsaved-answer migration is promised.
10. Pin recipe/source/image options at submission. Display-only rename remains allowed. Launch-affecting edits must not mutate a running session; reject them while it owns the slot. Use run-specific immutable configuration and resource ownership labels. Prefer run-specific Deployment names while retaining one active slot, so an old worker cannot overwrite a newer Deployment with the same name.
11. Before READY, verify the expected Deployment UID/generation, ready Pods, Service routing to that run and a bounded HTTP check of the actual annotation application. Add a minimal run-identity health adapter if the installed Prodigy interface cannot expose identity; do not invent an undocumented endpoint or treat rollout success alone as application health.
12. Continue observation after startup success. Stale health disables Open session. Pod replacement may restore the same run; Stop wins over late observations. Disconnect shared routing and observe that old Pods are gone before freeing the slot. Failed cleanup leaves a visible unavailable/stopping operation.
13. Home reads the actual active session. Dataset pages independently show data counts and session health. Two annotated datasets remain usable even when only one, or neither, has an active annotation session. Closing the progress tab cannot prevent binding, observation or operation completion.

**Acceptance:** annotate synthetic dataset A, stop it, annotate B, then confirm both retain their own data status. A failed or stale session is never displayed as running. Two concurrent launch requests cannot switch the shared annotation endpoint underneath one another.

## 14 — Preserve truthful task results across all operation types

1. Keep the current common presenter and failure-safe return-value access. Extend domain-operation lookup to annotation and deletion, alongside training and serving. A queue delivery's result must not override a newer domain observation.
2. Define a common operation response: ID, kind, state, terminal flag, current step, bounded progress, retry capability and safe error code/message. Keep runtime health separate from a completed startup result. Progress reflects observed steps, not an invented percentage.
3. Return HTTP 200 for successfully retrieved FAILED/TIMED_OUT/INTERRUPTED operation states, 404 for unknown IDs, a documented 400 for unknown operation kinds, and 409 for conflicting commands. Infrastructure failure while retrieving status is a connection/service error, not evidence that the operation failed.
4. Update TypeScript parsing and shared progress screens together. Preserve the last observation during a network failure, stop polling terminal results, abort obsolete requests and distinguish Retry status check from Retry operation. A retry after ambiguous submission reuses the original key.
5. For deletion, show completed and pending steps plus the exact retry action. For annotation, successful startup offers Open session only when fresh runtime health permits it. Do not redirect away from failures or label every finished operation successful.
6. Keep public diagnostics bounded and sanitized. Raw queue exceptions, annotations, credentials and old untrusted log metadata are not public logs. Apply the same result semantics to legacy HTML, including read-only GET/HEAD polling.

**Acceptance:** cover queued, running, succeeded, failed, timed out, interrupted, unknown ID, wrong operation type, malformed payload, network loss and recovery. Regression tests must prove a failed result's `return_value` is never accessed.

## 15 — Make deletion explicit, owned and resumable

### Action semantics

| Action | Removes | Preserves |
| --- | --- | --- |
| Stop serving | The selected serving revision's Deployment/Pods and Service | Model, training history, checkpoints, dataset and annotations |
| Stop annotation | The selected session's workloads/configuration and its active route | Dataset, source rows and saved annotations |
| Delete model files | Owned model workloads, training/verification Jobs and their configuration, then the model PVC | Model draft, audit/run receipts and dataset; artifact availability becomes removed/missing |
| Delete model | The same owned external resources, then the model is retired from normal use | Minimal tombstone/deletion receipt and immutable historical identities; parent dataset and annotations |
| Delete dataset | Its model cleanup operations, owned annotation resources and application records retired after cleanup | Source tables always; Prodigy annotations by default, with their binding recorded as intentionally retained |
| Delete retained annotations | Explicitly selected bound Prodigy dataset data, after dependent work is stopped | Source tables, unrelated datasets and shared examples still used elsewhere |

Deleting one historical checkpoint version inside a shared model PVC is deferred. The UI must clearly say **all model files** when deleting that PVC, rather than implying only one version will be removed.

### Workflow

1. Add a DeletionRun and persisted resource/step records: target identity, action, retention choices, idempotency key, namespace/kind/name/UID, planned removals, completed steps, retry/deadline details and safe failures. Preserve enough tombstone identity for replay and status lookup after normal record removal.
2. Produce a read-only preview listing affected models, serving/training resources, PVCs and annotation disposition. Bind the submission to the preview's scope/version and revalidate under locks; if ownership or dependencies changed, return a conflict with a fresh preview. Do not silently broaden a deletion request.
3. Replace the independent raw ORM-delete and resource-delete paths with the same domain workflow. Cover REST, legacy forms, dataset cascades and Django admin deletion actions. Use protected relationships or guarded administrative actions so an ORM cascade cannot bypass cleanup.
4. Atomically reserve the dataset/models and create the operation/queue entry. Active training or a shared-resource conflict blocks submission with a specific reason; do not kill training as an implicit part of Delete. Dataset reservation blocks new child models, annotation launches and training/serving starts.
5. Stop relevant serving/annotation runs. Wait for their Pods and any other PVC consumers to stop. Delete owned Jobs/ConfigMaps/Services, then the requested PVC. Persist progress after observing each external outcome. An accepted Kubernetes deletion is not completion; objects may remain terminating because of finalizers. Never strip storage protection finalizers to force a test to pass. [Kubernetes finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/)
6. Require exact namespace, recorded UID and established ownership before destructive operations. Use UID preconditions and resource-version checks as appropriate. A reused name is a conflict; an already absent intended resource completes that step. An unmatched historical resource stays in the inventory for review.
7. Retry the same persisted operation after a crash or partial failure. Re-observe completed/ambiguous steps instead of restarting blindly. Keep mutation reservations while cleanup is incomplete; show a controlled retry/review state rather than clearing a Boolean after one error. Retire the application record only once the selected cleanup policy has been satisfied.
8. Preserve successful training and serving history. Record artifact removal separately from historical training success; a deleted checkpoint is no longer serveable, but its old training run did not retroactively fail.
9. Treat annotation deletion as a separate explicit choice. Verify installed Prodigy deletion behavior against shared-link and session-dataset fixtures; use its supported database API or a narrow tested adapter with existing role separation. A session dataset can be associated with several parent datasets, so association alone does not authorize deleting it. Retained annotations keep a tombstone binding so they are not mistaken for orphans or silently rebound. [Prodigy database API](https://prodi.gy/docs/api-database)
10. Add a read-only inventory of database records, observed resource UIDs and retained data. List verified ownership, ambiguity and proposed cleanup separately. Historical bulk cleanup is not an automatic migration step.

**Acceptance:** failure at every cleanup boundary leaves visible progress and safely resumes; duplicate requests do not duplicate cleanup; replacing a resource under the same name prevents deletion; no checkpoint volume disappears while a Pod uses it; unrelated and retained annotations survive.

## 16 — Complete conflict handling and recovery

1. Retain TrainingRun/ServingRun constraints and leases; add equivalent durable control for annotation and deletion. Use named database constraints and a documented lock order: annotation slot when needed, dataset, models ordered by primary key, then operation rows. Audit existing mutation paths for that order, including model creation and metadata edits.
2. Keep transactions short: reserve/check/persist inside the database transaction, perform Kubernetes/Prodigy I/O outside it, then conditionally record observations for the current owner. The existing database-backed queue entry should commit atomically with its domain operation. [Django transaction guidance](https://docs.djangoproject.com/en/6.0/topics/db/transactions/)
3. Specify legal transitions before coding. Reuse the serving pattern of immutable startup outcome plus mutable session health. For deletion, distinguish progress, retry wait, success and intervention required. A terminal failure does not imply that partially deleted resources have been restored.
4. A lease permits recovery, but does not guarantee that an old process is dead. Fence stale workers with operation ownership checks, run-specific resource names, persisted UIDs and conditional writes. Protect shared Service routing too. Test a delayed old worker after a newer owner has acquired the lease; database checks alone cannot make external side effects exactly once.
5. Extend the launch conflict matrix: deletion excludes new Train/Serve/Label and child creation; live annotation reserves its namespace slot; Stop remains available; annotation may continue while training reads a checked input, retaining the existing fingerprint-change failure policy. Do not accidentally forbid serving an older verified checkpoint while a new training run proceeds safely.
6. Run bounded annotation/deletion reconciliation independently of the queue worker. Recover expired leases by observing actual external state. Use bounded retry/backoff for transport outages, deadlines for startup, and explicit retry/review for ownership conflicts or blocked storage. Do not repeatedly relaunch a deliberately stopped run.
7. Domain operation records are authoritative when a queue worker dies. Add queue-operation links and diagnostics for stuck deliveries. Do not infer task death from age or a missing heartbeat alone. Any queue-row repair must exclude a still-running worker and use supported behavior for the installed django-tasks version; do not patch vendor code or bulk-requeue RUNNING rows.
8. Inventory historical READY/RUNNING tasks without executing them. Link only requests whose operation/resource identities can be established. Legacy label/delete requests without durable identity are quarantined from automatic replay and reported as interrupted/requiring review after confirming the old worker is inactive. The task observed in March must be re-inspected, not blindly marked successful or rerun.
9. Update Kubernetes process supervision and local startup documentation. A database outage must not leave all reconcilers silently stopped: recover connections with bounded retries or use the existing supervised process restart behavior. Publish health/diagnostics for stale observers.

**Acceptance:** double-clicks and network retries create one intent; competing requests conflict cleanly; killing a worker before/after each external step resumes the same operation without damaging a newer resource; a late worker cannot undo Stop or clear another operation's reservation.

## Verification and rollout

| Layer | Required checks |
| --- | --- |
| Domain/API | Observation freshness, status/result contracts, retention rules, transition rejection, read-only GET/HEAD and safe errors |
| Real PostgreSQL | Slot competition, duplicate annotation/delete requests, dataset deletion versus child creation/Train, lease takeover and transaction rollback |
| External adapters | UID mismatch, missing resource, accepted-but-terminating deletion, partial API outage, shared Prodigy links and binding replacement |
| React and legacy | Correct active-session badge, independent dataset counts, failed operation remains visible, deletion preview/progress, status retry versus command retry |
| Isolated Kubernetes | Two synthetic datasets, real annotation save, Stop/switch, worker interruption/recovery, model cleanup, preserved annotations, then explicitly selected fixture annotation deletion |
| Existing regression suite | Keep training/serving/artifact contracts, verified publication, prediction, security boundaries and migration behavior from 02–12 green |

Use injected clocks and barriers for deterministic races. For external checks, wait for observable states with deadlines and assert intermediate progress; a fast no-op must not count as a recovery pass. Use real disposable PostgreSQL, synthetic annotations and a small checkpoint. Rebuild only affected images, verify installed packages, and perform heavy checks sequentially.

Add migrations first, with conservative unknown states for legacy sessions. Test forward migration and rollback on populated synthetic records. Do not create a fake active session from `DjangoLastDataset`, and do not delete old resources during migration. Run the resource/queue inventory read-only before any working cleanup; any requested working-data deletion must have an exact, reviewable scope. No database export is assumed or required by this plan.

After a Docker/cluster restart, retest actual network-policy denial and the legitimate HTTP route, following the environment issue documented in 09–12. Remove the disposable namespace, database, temporary credentials and listeners after acceptance; retain safe operation receipts and the implementation report.

## Scope limits

- Login/password, multi-user authorization and public deployment remain deferred.
- Multi-session annotation capacity, general garbage collection and per-version filesystem deletion are separate extensions.
- No silent P/N-to-sentiment mapping, reject/OTHER reinterpretation, source-row deletion or model-quality claim is included. Model 20 and ambiguous historical dataset bindings retain their explicit unresolved decisions.
- Implementing cleanup does not authorize automatic deletion of historical user volumes or annotations. Routine implementation and disposable acceptance can proceed independently of those decisions.
