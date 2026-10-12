import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { explain, safeCode } from '../src/api.ts';
import { explainFilter, ResearchRequestController } from '../src/filter-model.ts';
import { explainGroupEndpointError } from '../src/group-endpoint-model.ts';
import { explainPeerNeighborError } from '../src/peer-neighbor-model.ts';
import * as explanation from '../src/two-group-model.ts';
import { createUniverseDraft, prepareUniverseRequest, loadUniverseRequest } from '../src/universe-request.ts';
import { fixture } from './two-group-fixtures.mjs';

// Execute the component's real expression; this does not mount React or use a browser.
const source = readFileSync(new URL('../src/UniverseResearch.tsx', import.meta.url), 'utf8');
const expression = source.match(/id="universe-error-summary" tabIndex=\{-1\}>\{([^\n]+)\}<\/p>/)?.[1];
assert.ok(expression, 'the shared request-error banner must be present');
const evaluate = new Function('draft', 'requestState', 'explainPeerNeighborError', 'explainGroupEndpointError',
  'explanationReasons', 'explainExplanationError', 'explainFilter', `return (${expression});`);
const banner = (error, mode = 'explanation') => evaluate({ mode }, { status: 'error', error },
  explainPeerNeighborError, explainGroupEndpointError, explanation.explanationReasons, explanation.explainExplanationError, explainFilter);

for (const code of ['constructor', '__proto__', 'toString', 'hasOwnProperty']) {
  test(`two-group source reason preserves inherited name as text: ${code}`, () => {
    assert.equal(explanation.explainReason(code), `来源或数值限制：${code}`);
  });
  test(`two-group request banner uses shared safe fallback for inherited name: ${code}`, () => {
    const error = new Error(code), text = banner(error);
    assert.equal(text, explainFilter(error));
    assert.equal(typeof text, 'string');
    const html = renderToStaticMarkup(createElement('p', { role: 'alert' }, text));
    assert.match(html, /role="alert"/);
    assert.doesNotMatch(html, /native code|\[object Object\]|来源或数值限制/);
  });
}

test('two-group known reasons keep their exact member and request strings', () => {
  for (const [code, text] of Object.entries(explanation.explanationReasons)) {
    assert.equal(explanation.explainReason(code), text, code);
    assert.equal(banner(new Error(code)), text, code);
  }
  assert.equal(banner(new Error('invalid_groups')), '请将全部成员明确分入A/B两组，每组至少两只。');
  assert.equal(banner(new Error('invalid_dates')), '当前起点须早于终点。');
});

test('two-group unknown source facts remain literal, including Unicode and markup', () => {
  for (const code of ['unrecognized_safe_code', '未知核验', '<img src=x onerror="alert(1)">', '']) {
    assert.equal(explanation.explainReason(code), `来源或数值限制：${code}`);
  }
});

const recovery = ['raw_object_missing', 'raw_object_corrupt', 'snapshot_not_found', 'service_busy',
  'connection_error', 'service_closing', 'storage_io_error', 'internal_error'];
test('two-group request errors retain shared recovery without member fallback', () => {
  for (const code of recovery) {
    assert.equal(banner(new Error(code)), explain(new Error(code)), code);
    assert.doesNotMatch(banner(new Error(code)), /来源或数值限制/);
  }
});

test('two-group unknown, non-Error and unsafe requests use the existing safe fallback', () => {
  for (const error of [new Error('unrecognized_safe_code'), new Error('invalid_query_response'),
    new TypeError('Failed to fetch'), new Error('<private raw payload>'), new Error('/private/path'),
    new Error('invalid_dates\nPRIVATE_SECRET'), new Error('invalid_dates '), new Error('INVALID_DATES'),
    new Error('未知核验'), new Error('x'.repeat(81)), 'invalid_dates', { message: 'invalid_dates' }, null, undefined, 12]) {
    const text = banner(error);
    assert.equal(text, explainFilter(error));
    assert.ok(text.includes(safeCode(error)));
    assert.doesNotMatch(text, /private|PRIVATE_SECRET|未知核验|来源或数值限制|native code/);
  }
});

test('other research modes retain their existing error mappings', () => {
  for (const error of [...recovery, 'invalid_filter_threshold', 'invalid_dates', 'invalid_target',
    'group_result_limit', 'peer_neighbor_result_limit', 'constructor', '__proto__', 'toString',
    'unknown_safe_code', '<private>'].map(code => new Error(code)).concat([null, { message: 'invalid_dates' }])) {
    assert.equal(banner(error, 'existing'), explainFilter(error));
    assert.equal(banner(error, 'group_endpoints'), explainGroupEndpointError(error));
    assert.equal(banner(error, 'peer_neighbors'), explainPeerNeighborError(error));
  }
});

test('actual two-group loader failures clear results, preserve drafts and recover on explicit retry', async () => {
  const f = fixture();
  const draft = { ...createUniverseDraft(), ids: f.expected.ids, cutoff: f.expected.end, mode: 'explanation',
    lookback: 'unused legacy input', filter: { enabled: true, groups: [] },
    explanation: { start: f.expected.start, roles: Object.fromEntries(f.expected.ids.map((id, i) => [id, i < 2 ? 'A' : 'B'])) } };
  const saved = structuredClone(draft), originalFetch = globalThis.fetch, calls = [];
  let failure = null;
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    if (failure === 'connection_error') throw new TypeError('Failed to fetch');
    return failure ? Response.json({ error: failure }, { status: failure === 'service_busy' ? 503 : 409 }) : Response.json(f.reply);
  };
  const states = [], controller = new ResearchRequestController(state => states.push(state));
  const run = async () => {
    const before = calls.length;
    await controller.run(() => prepareUniverseRequest(draft, draft.ids), loadUniverseRequest);
    assert.equal(calls.length, before + 1, 'each explicit run makes exactly one request');
    assert.match(calls.at(-1)[0], /^\/api\/research\/two-group-explanation\?/);
    assert.doesNotMatch(calls.at(-1)[0], /lookback|rule|target/);
    assert.equal(calls.at(-1)[1].cache, 'no-store');
    assert.equal(states.at(-2).status, 'loading');
    assert.equal(states.at(-2).result, null);
  };
  try {
    await run();
    assert.equal(controller.state.status, 'ready');
    for (const code of [...recovery.slice(0, 5), 'constructor', '__proto__', 'toString', 'unknown_safe_code', '/private/path']) {
      failure = code;
      await run();
      assert.equal(controller.state.status, 'error');
      assert.equal(controller.state.result, null);
      const expectedCode = /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : 'invalid_response';
      assert.equal(banner(controller.state.error), explainFilter(new Error(expectedCode)));
      assert.deepEqual(draft, saved);
      failure = null;
      await run();
      assert.equal(controller.state.status, 'ready');
      assert.equal(controller.state.error, null);
      assert.equal(controller.state.result.kind, 'explanation');
      assert.deepEqual(controller.state.result.report, f.reply);
      assert.deepEqual(draft, saved);
    }
  } finally { controller.dispose(); globalThis.fetch = originalFetch; }
});
