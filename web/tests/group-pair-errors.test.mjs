import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { explain } from '../src/api.ts';
import { explainFilter } from '../src/filter-model.ts';
import { groupPairReason, explainGroupPairError } from '../src/group-pair-model.ts';

// Use the actual request-error banner expression, without claiming mounted React coverage.
const source = readFileSync(new URL('../src/UniverseResearch.tsx', import.meta.url), 'utf8');
const expression = source.match(/id="universe-error-summary" tabIndex=\{-1\}>\{([^\n]+)\}<\/p>/)?.[1];
assert.ok(expression);
const evaluate = new Function('draft', 'requestState', 'explainGroupPairError', `return (${expression});`);
const banner = error => evaluate({ mode: 'group_pairs' }, { status: 'error', error }, explainGroupPairError);

test('051 unknown and prototype diagnostic codes always remain plain strings', () => {
  for (const code of ['constructor', '__proto__', 'toString', 'hasOwnProperty', 'valueOf', 'unknown_safe_code', '未知核验']) {
    const text = groupPairReason(code);
    assert.equal(typeof text, 'string');
    assert.equal(text, `来源限制：${code}`);
    assert.doesNotMatch(text, /native code|function Object|\[object Object\]/);
  }
});
test('051 unknown, prototype and unsafe request errors retain shared safe fallback', () => {
  for (const error of [new Error('constructor'), new Error('__proto__'), new Error('toString'), new Error('hasOwnProperty'),
    new Error('unknown_safe_code'), new Error('peer_neighbor_unknown_code'), new Error('<private payload>'), new Error('/private/path'),
    new Error('group_pair_result_limit\nPRIVATE_BODY'), new TypeError('Failed to fetch'), null, undefined,
    { message: 'group_pair_result_limit' }, 'group_pair_result_limit']) {
    assert.equal(banner(error), explainFilter(error));
    assert.equal(typeof banner(error), 'string');
    assert.doesNotMatch(banner(error), /native code|function Object|private|PRIVATE_BODY|\[object Object\]/);
  }
});
test('051 request guidance retains known limits and shared recovery', () => {
  for (const code of ['group_pair_result_limit', 'invalid_group_pair_response']) {
    assert.equal(banner(new Error(code)), `${groupPairReason(code)}（${code}）`);
  }
  for (const code of ['raw_object_missing','raw_object_corrupt','snapshot_not_found','service_busy','connection_error','service_closing','storage_io_error','internal_error']) {
    assert.equal(banner(new Error(code)), explain(new Error(code)));
  }
  assert.equal(banner(new Error('peer_neighbor_integer_limit')), '精确相关计算失败，整组未发布（peer_neighbor_integer_limit）');
});
