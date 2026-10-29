// Offline tests for worker.js (fetch is always mocked). Run: node --test
import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { dispatch, dispatchRequest, slotIso } from './worker.js';

const SLOT = Date.UTC(2026, 9, 30, 7, 5, 0, 412);
const TOKEN = 'github_pat_DUMMY_ONLY_NOT_A_REAL_TOKEN';
const noSleep = async () => {};

function mockFetch(...statuses) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    const next = statuses.shift();
    if (next instanceof Error) throw next;
    return { status: next };
  };
  fn.calls = calls;
  return fn;
}

test('slot is whole-second UTC accepted by the workflow input pattern', () => {
  assert.equal(slotIso(SLOT), '2026-10-30T07:05:00Z');
  assert.match(slotIso(SLOT), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
});

test('request targets the production workflow with fixed, safe inputs', () => {
  const { url, body } = dispatchRequest({}, SLOT);
  assert.equal(url, 'https://api.github.com/repos/mdvar2/matatiele-storm-early-warning-system/actions/workflows/scheduled-storm-sms.yml/dispatches');
  assert.deepEqual(body, { ref: 'main', inputs: { send_test_sms: 'false', trigger_source: 'external_scheduler', scheduled_for: '2026-10-30T07:05:00Z' } });
});

test('successful dispatch: one POST, bearer token only in the header', async () => {
  const f = mockFetch(204);
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), 'dispatched');
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].init.method, 'POST');
  assert.equal(f.calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.ok(!f.calls[0].init.body.includes(TOKEN));
  assert.ok(!f.calls[0].url.includes(TOKEN));
});

test('any 2xx counts as dispatched and is never retried', async () => {
  const f = mockFetch(200, 204);
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), 'dispatched');
  assert.equal(f.calls.length, 1);
});

test('missing token or invalid configuration never calls GitHub', async () => {
  const f = mockFetch();
  assert.equal(await dispatch({}, SLOT, f, noSleep), 'not_configured');
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN, GITHUB_REPOSITORY: 'x/y/../z?' }, SLOT, f, noSleep), 'invalid_configuration');
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN, WORKFLOW_FILE: 'other.sh' }, SLOT, f, noSleep), 'invalid_configuration');
  assert.equal(f.calls.length, 0);
});

test('4xx is not retried (bad token, missing permission, unknown workflow)', async () => {
  for (const status of [401, 403, 404, 422]) {
    const f = mockFetch(status, 204);
    assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), `rejected_http_${status}`);
    assert.equal(f.calls.length, 1);
  }
});

test('5xx or network error is retried exactly once', async () => {
  let f = mockFetch(502, 204);
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), 'dispatched');
  assert.equal(f.calls.length, 2);
  f = mockFetch(new TypeError('fetch failed'), 503);
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), 'failed_http_503');
  assert.equal(f.calls.length, 2);
  f = mockFetch(new TypeError('a'), new TypeError('b'));
  assert.equal(await dispatch({ GITHUB_DISPATCH_TOKEN: TOKEN }, SLOT, f, noSleep), 'failed_network_error');
});

test('scheduled handler logs the outcome but never the token, and throws on failure', async () => {
  const realFetch = globalThis.fetch;
  const logs = [];
  const realLog = console.log;
  console.log = (...a) => logs.push(a.join(' '));
  try {
    globalThis.fetch = mockFetch(204);
    await worker.scheduled({ scheduledTime: SLOT }, { GITHUB_DISPATCH_TOKEN: TOKEN }, {});
    globalThis.fetch = mockFetch(401);
    await assert.rejects(worker.scheduled({ scheduledTime: SLOT }, { GITHUB_DISPATCH_TOKEN: TOKEN }, {}), /rejected_http_401/);
  } finally {
    globalThis.fetch = realFetch;
    console.log = realLog;
  }
  assert.equal(logs.length, 2);
  assert.ok(logs.every((line) => !line.includes(TOKEN)));
  assert.match(logs[0], /outcome=dispatched/);
});

test('worker exposes no HTTP endpoint', () => {
  assert.equal(typeof worker.scheduled, 'function');
  assert.equal(worker.fetch, undefined);
});
