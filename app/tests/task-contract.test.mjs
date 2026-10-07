import assert from 'node:assert/strict';
import test from 'node:test';
import { parseTaskResult, responseError } from '../src/api/tasks.ts';

for (const status of ['READY', 'QUEUED', 'RUNNING', 'VERIFYING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'INTERRUPTED']) {
  test(`accepts consistent ${status} status`, () => {
    const terminal = ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'INTERRUPTED'].includes(status);
    assert.equal(parseTaskResult({ status, is_finished: terminal, logs: '', error: null }).is_finished, terminal);
  });
}
test('rejects malformed or contradictory status payloads', () => {
  for (const payload of [null, [], {}, { status: 'UNKNOWN', is_finished: false, logs: '', error: null },
    { status: 'FAILED', is_finished: false, logs: '', error: null },
    { status: 'RUNNING', is_finished: true, logs: '', error: null },
    { status: 'FAILED', is_finished: true, logs: '', error: 'private-error' }]) {
    assert.throws(() => parseTaskResult(payload));
  }
});
test('HTTP errors preserve public validation messages without rendering raw HTML', async () => {
  assert.equal(await responseError(Response.json({ fields: { labels: ['Unknown label.'] } }, { status: 400 })), 'labels: Unknown label.');
  assert.equal(await responseError(Response.json({ error: { code: 'X', message: 'Training failed.' } }, { status: 503 })), 'Training failed.');
  assert.equal(await responseError(new Response('<html>private traceback</html>', { status: 500 })), 'Request failed (HTTP 500).');
});
