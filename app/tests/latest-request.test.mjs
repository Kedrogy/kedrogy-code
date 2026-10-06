import assert from 'node:assert/strict';
import test from 'node:test';
import { createLatestRequest } from '../src/api/latestRequest.ts';
import { parseQuality } from '../src/api/models.ts';

const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

test('changing input cancels pending transport and ignores a late completion', async () => {
  const requests = createLatestRequest();
  const first = requests.start();
  const response = deferred();
  let visible = null;
  const completion = response.promise.then(value => { if (first.isCurrent()) visible = value; });
  requests.cancel();
  assert.equal(first.signal.aborted, true);
  response.resolve('old prediction');
  await completion;
  assert.equal(visible, null);
});

test('out-of-order responses cannot overwrite the newer request', async () => {
  const requests = createLatestRequest();
  const old = requests.start();
  const oldResponse = deferred();
  let visible = null;
  const completion = oldResponse.promise.then(value => { if (old.isCurrent()) visible = value; });
  const current = requests.start();
  assert.equal(old.isCurrent(), false);
  if (current.isCurrent()) visible = 'new prediction';
  oldResponse.resolve('stale prediction');
  await completion;
  assert.equal(visible, 'new prediction');
  requests.cancel();
  assert.equal(current.isCurrent(), false);
});

test('quality is optional for historical checkpoints and rejects misleading metrics', () => {
  assert.equal(parseQuality(undefined), null);
  const valid = { version: 1, split: 'validation', samples: 44, train_samples: 132, training_steps: 136,
    accuracy: .8, macro_f1: .7, majority_baseline: .75, warnings: ['small_validation_sample'] };
  assert.equal(parseQuality(valid).samples, 44);
  for (const changes of [{accuracy:NaN},{macro_f1:1.2},{samples:0},{training_steps:false},{warnings:['unknown']},{split:'test'}]) {
    assert.throws(() => parseQuality({...valid,...changes}));
  }
});
