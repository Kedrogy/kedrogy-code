import assert from 'node:assert/strict';
import test from 'node:test';
import { parseAnnotationData, parseAnnotationSession, parseDeletionPreview, parseLegacyCleanupReview } from '../src/api/operations.ts';
import { parseTaskResult } from '../src/api/tasks.ts';

test('annotation counts describe saved answers independently of a running session', () => {
  const value = { status: 'PRESENT', counts: { total: 3, accepted: 1, rejected: 1, ignored: 1, invalid: 0 }, observed_at: null, error: null, refresh_requested: false };
  assert.equal(parseAnnotationData(value).counts.total, 3);
  for (const counts of [{ ...value.counts, total: 99 }, { ...value.counts, accepted: -1 }]) {
    assert.throws(() => parseAnnotationData({ ...value, counts }));
  }
});

test('legacy review requires exact resource identities in one namespace', () => {
  const resource = { kind: 'Deployment', name: 'serve-20', namespace: 'default', uid: 'exact-uid' };
  const review = { model_id: 20, namespace: 'default', resources: [resource], issues: [], evidence: ['Storage matches.'], review_token: 'signed-token' };
  assert.equal(parseLegacyCleanupReview(review).resources[0].uid, 'exact-uid');
  for (const invalid of [{ ...resource, uid: '' }, { ...resource, uid: null }, { ...resource, namespace: 'other' }]) {
    assert.throws(() => parseLegacyCleanupReview({ ...review, resources: [invalid] }));
  }
  assert.throws(() => parseLegacyCleanupReview({ ...review, evidence: [null] }));
  assert.throws(() => parseLegacyCleanupReview({ ...review, review_token: null }));
});

test('deletion preview exposes reviewable model IDs without treating an ID as a count', () => {
  const preview = { action: 'model', target: 'model:20', model_ids: [20], resources: [], issues: ['Ownership unresolved.'],
    preview_token: 'signed-token', retains_annotations: true, retains_source_rows: true, legacy_review_model_ids: [20] };
  assert.deepEqual(parseDeletionPreview(preview).legacy_review_model_ids, [20]);
  assert.throws(() => parseDeletionPreview({ ...preview, legacy_review_model_ids: '20' }));
  assert.throws(() => parseDeletionPreview({ ...preview, legacy_review_model_ids: [-20] }));
});
test('only a ready session can expose an HTTP application URL', () => {
  const session = { id: 'run-a', dataset_id: 1, status: 'READY', observed_at: null, error: null, url: 'http://label.localhost' };
  assert.equal(parseAnnotationSession(session).dataset_id, 1);
  assert.throws(() => parseAnnotationSession({ ...session, status: 'STOPPED' }));
  assert.throws(() => parseAnnotationSession({ ...session, url: 'javascript:alert(1)' }));
});
test('cleanup review is terminal for polling but preserves explicit retry and bounded progress', () => {
  const value = { status: 'NEEDS_REVIEW', is_finished: true, logs: '', error: { code: 'VOLUME_IN_USE', message: 'Review the consumer.' }, can_retry: true, step: 'Removing volume', progress: { completed: 2, total: 4 } };
  assert.equal(parseTaskResult(value).can_retry, true);
  assert.throws(() => parseTaskResult({ ...value, progress: { completed: 5, total: 4 } }));
  assert.throws(() => parseTaskResult({ ...value, is_finished: false }));
  assert.throws(() => parseDeletionPreview({ action: 'dataset', resources: [] }));
});
