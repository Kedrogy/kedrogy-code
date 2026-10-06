# Legacy cleanup ownership repair

The original fixed-name resources for model #20 had no recorded ownership, so the deletion preview correctly refused to delete them. A dedicated legacy review now checks the known resource graph and records exact Kubernetes identities before enabling the separate deletion action.

## Changes

- Added a signed, ten-minute review endpoint and an English-language review panel with an explicit ownership acknowledgment.
- Review checks the namespace UID, resource UIDs, specifications, approved images, model volume mounts, training dataset binding, prediction selectors and unrelated resource consumers.
- The training ConfigMap is included in ownership inventory and cleanup; it can no longer be silently orphaned.
- Cleanup rechecks reviewed identities and uses UID plus resource-version delete preconditions. Completed cleanup clears obsolete review metadata; the cleanup operation retains its original plan.
- Migration `0017_legacy_cleanup_review` adds the private review record without altering existing checkpoints or annotation data.
- Added read-only inventory permissions for ReplicaSets, StatefulSets, DaemonSets and CronJobs. Updated dependency locks for the safe YAML parser.
- The preview now says `Affected model IDs: #20`, avoiding confusion with a count of twenty models.

## Validation and local outcome

- 120 backend tests passed on disposable PostgreSQL databases, including existing concurrency tests and 13 legacy cleanup tests.
- 18 frontend contract tests passed; the TypeScript/Vite production build passed.
- Migration consistency and `git diff --check` passed.
- Model #20's five resources passed the actual review. The ownership step was exercised in Chrome. A subsequent separate deletion request completed successfully.
- The complete legacy profile remains intentionally conservative: missing resources prevent automatic ownership confirmation. The user chose not to expand the interface for model #19. Under the later explicit request to remove all old models and datasets, its four remaining resources were reviewed individually and removed using exact identities. See `manual-model-19-cleanup.json`.
- Source text was preserved. Saved historical annotations remain available under retained annotations.

The local API, worker and reconcilers were restarted with the final code. No new container release was built for this repair.
