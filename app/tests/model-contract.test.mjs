import assert from 'node:assert/strict';
import test from 'node:test';
import { parseServing, parsePrediction, parseDataset, parseModel } from '../src/api/models.ts';

const serving = { id: 'serve-a', status: 'READY', training_run_id: 'train-a', labels: ['P', 'N'], class_schema_version: 1, conversion_policy: 'reject-other-v1', observed_at: '2026-09-25T00:00:00Z', error: null };
test('class zero displays OTHER and stays bound to the loaded class order', () => {
  const value = { class_id: 0, label: 'OTHER', contract_version: 1, training_run_id: 'train-a', serving_run_id: 'serve-a' };
  assert.equal(parsePrediction(value, serving), 'OTHER');
  for (const changes of [{ class_id: false }, { label: 'P' }, { class_id: 4 }, { serving_run_id: 'serve-b' }, { training_run_id: 'train-b' }]) {
    assert.throws(() => parsePrediction({ ...value, ...changes }, serving));
  }
});
test('serving states are explicit and malformed response payloads fail closed', () => {
  for (const status of ['UNVERIFIED', 'STARTING', 'READY', 'UNAVAILABLE', 'FAILED', 'STOPPING', 'STOPPED']) assert.equal(parseServing({ ...serving, status }).status, status);
  assert.throws(() => parseServing({ ...serving, status: 'OK' }));
  assert.throws(() => parseServing({ ...serving, labels: [42] }));
  assert.throws(() => parseDataset({ id: 1, dataset_name: 'Missing binding state' }));
  assert.throws(() => parseModel({ served: true, serving: { ...serving, status: 'FAILED' } }));
});

test('explicit class zero and schema versions stay consistent across prediction', () => {
  const current = { ...serving, class_schema_version: 2, conversion_policy: 'single-label-choice-v2' };
  const result = { class_id: 0, label: 'P', contract_version: 1, class_schema_version: 2, training_run_id: 'train-a', serving_run_id: 'serve-a' };
  assert.equal(parsePrediction(result, parseServing(current)), 'P');
  for (const change of [{ label: 'OTHER' }, { class_schema_version: 1 }, { class_schema_version: undefined }]) {
    assert.throws(() => parsePrediction({ ...result, ...change }, current));
  }
  assert.throws(() => parseServing({ ...current, class_schema_version: 99 }));
  assert.throws(() => parseServing({ ...current, conversion_policy: 'reject-other-v1' }));
});
