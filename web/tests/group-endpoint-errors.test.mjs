import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { explain } from '../src/api.ts';
import * as group from '../src/group-endpoint-model.ts';
import { explainFilter, ResearchRequestController } from '../src/filter-model.ts';
import { explanationReasons, explainExplanationError } from '../src/two-group-model.ts';
import { createUniverseDraft, prepareUniverseRequest, loadUniverseRequest, universeErrorTarget } from '../src/universe-request.ts';

// Execute the actual banner expression, without implying mounted React or browser coverage.
const source = readFileSync(new URL('../src/UniverseResearch.tsx', import.meta.url), 'utf8');
const expression = source.match(/id="universe-error-summary" tabIndex=\{-1\}>\{([^\n]+)\}<\/p>/)?.[1];
assert.ok(expression, 'the shared request-error banner must be present');
const evaluate = new Function('draft', 'requestState', 'groupReason', 'explainGroupEndpointError', 'explainExplanationError', 'explainFilter', `return (${expression});`);
const banner = (error, mode = 'group_endpoints') => evaluate({ mode }, { status: 'error', error }, group.groupReason, group.explainGroupEndpointError, explainExplanationError, explainFilter);

const recovery = [
  ['raw_object_corrupt', '请恢复正确原件再查询'],
  ['raw_object_missing', '请恢复正确原件再查询'],
  ['snapshot_not_found', '请刷新目录后重新选择'],
  ['service_busy', '请稍后重试'],
  ['connection_error', '请确认本地服务仍在运行'],
  ['service_closing', '重新启动'],
  ['storage_io_error', '请检查数据目录后重试'],
  ['internal_error', '当前操作未获确认'],
];
for (const [code, instruction] of recovery) test(`group request banner preserves shared recovery: ${code}`, () => {
  const error = new Error(code), text = banner(error);
  assert.equal(text, explain(error));
  assert.ok(text.includes(instruction));
  assert.doesNotMatch(text, /来源限制/);
});

test('group request banner retains endpoint-specific input, budget and response reasons', () => {
  for (const code of ['invalid_dates', 'group_result_limit', 'group_fraction_limit', 'research_member_limit',
    'duplicate_member', 'invalid_group_endpoint_response', 'research_row_limit', 'universe_row_limit']) {
    assert.equal(banner(new Error(code)), group.groupReason(code), code);
  }
  assert.match(banner(new Error('research_row_limit')), /修改日期不会缩减读取/);
});

test('unknown, non-Error and unsafe request errors use the existing safe fallback', () => {
  for (const error of [new Error('unrecognized_safe_code'), new Error('constructor'), new Error('__proto__'), new Error('toString'), new Error('invalid_query_response'),
    new TypeError('Failed to fetch'), new Error('<private raw payload>'), new Error('/private/path'), new Error('invalid_dates\nPRIVATE_BODY'),
    new Error('INVALID_DATES'), new Error('invalid_dates '), new Error('x'.repeat(81)),
    'invalid_dates', { message: 'invalid_dates' }, null, undefined, 12]) {
    assert.equal(banner(error), explainFilter(error));
    assert.doesNotMatch(banner(error), /private|PRIVATE_BODY|来源限制|native code/);
  }
});

test('existing research and two-group request explanations are unchanged', () => {
  for (const error of [new Error('raw_object_corrupt'), new Error('invalid_filter_threshold'), new Error('invalid_dates'), new Error('<private>'), null]) {
    assert.equal(banner(error, 'existing'), explainFilter(error));
    assert.equal(banner(error, 'explanation'), error instanceof Error && explanationReasons[error.message] || explainFilter(error));
  }
});

test('member and endpoint row reasons retain their original display fallback', () => {
  assert.equal(group.groupReason('missing_endpoint'), '共同日期缺少记录');
  assert.equal(group.groupReason('unsupported_source'), '当前仅支持已核对格式的腾讯日线');
  for (const code of ['unrecognized_safe_code', '__proto__', 'constructor', 'toString', '未知核验']) {
    assert.equal(group.groupReason(code), `来源限制：${code}`);
  }
});

test('invalid cutoff uses shared guidance while group start retains its own reason and focus', async () => {
  const ids = ['a', 'b', 'c', 'd'].map(value => value.repeat(64));
  const draft = { ...createUniverseDraft(), mode: 'group_endpoints', ids, cutoff: '2026-09-30', groupStart: '2026-09-01' };
  for (const [field, code, target] of [['cutoff', 'invalid_cutoff', 'universe-cutoff'], ['groupStart', 'invalid_dates', 'universe-group-start']]) {
    await assert.rejects(() => prepareUniverseRequest({ ...draft, [field]: '2026-02-30' }, ids), error => {
      assert.equal(error.message, code);
      assert.equal(universeErrorTarget(error), target);
      assert.equal(banner(error), field === 'cutoff' ? explainFilter(error) : group.groupReason(code));
      return true;
    });
  }
});

test('actual group request failures clear prior results, retain inputs and recover on explicit retry', async () => {
  const f = JSON.parse(readFileSync(new URL('./group-endpoint-fixtures.json', import.meta.url), 'utf8')).complete;
  const draft = { ...createUniverseDraft(), mode: 'group_endpoints', ids: f.expected.ids, cutoff: f.expected.end, groupStart: f.expected.start };
  const saved = structuredClone(draft), old = globalThis.fetch;
  let failure = null;
  globalThis.fetch = async () => {
    if (failure === 'connection_error') throw new TypeError('Failed to fetch');
    return failure ? Response.json({ error: failure }, { status: failure === 'service_busy' ? 503 : failure === 'snapshot_not_found' ? 404 : 409 }) : Response.json(f.reply);
  };
  const controller = new ResearchRequestController(() => {});
  const run = () => controller.run(() => prepareUniverseRequest(draft, draft.ids), loadUniverseRequest);
  try {
    await run();
    assert.equal(controller.state.status, 'ready');
    for (const [code] of recovery.slice(0, 5)) {
      failure = code;
      await run();
      assert.equal(controller.state.status, 'error');
      assert.equal(controller.state.result, null);
      assert.equal(banner(controller.state.error), explain(new Error(code)));
      assert.deepEqual(draft, saved);
      failure = null;
      await run();
      assert.equal(controller.state.status, 'ready');
      assert.deepEqual(controller.state.result.report, f.reply);
    }
  } finally { controller.dispose(); globalThis.fetch = old; }
});
