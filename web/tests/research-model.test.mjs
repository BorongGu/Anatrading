import test from 'node:test';
import assert from 'node:assert/strict';
import { Generation } from '../src/model.ts';
import { buildResearchRequest, assertResearchReply, formatEstimate, formatPercent, researchReason, explainResearch, snapshotName, isDailySnapshot } from '../src/research-model.ts';

// Synthetic contracts test UI safety only, without asserting research value.
const a = 'a'.repeat(64), b = 'b'.repeat(64), q = 'c'.repeat(64);
const cutoff = '2026-10-11';

test('invalid identities, dates, bounds and unsupported horizons fail before fetching', () => {
  for (const args of [
    ['single', [], '', 20], ['single', [a, b], '', 20], ['pair', [a, a], cutoff, 20],
    ['pair', [a, b], '', 20], ['universe', [a], cutoff, 20], ['single', ['x'], '', 20],
    ['single', [a], '2026-02-30', 20], ['single', [a], '0000-01-01', 20],
    ['single', [a], '2026-1-01', 20], ['single', [a], '2026-01-01T00:00', 20],
    ['single', [a], '', 1], ['pair', [a, b], cutoff, 4], ['universe', [a, b], cutoff, 253],
    ['single', [a], '', NaN], ['single', [a], '', Infinity], ['single', [a], '', true],
    ['single', [a], '', 20.5], ['single', [a], '', '20'], ['single', [a], '', 20, 2],
    ['single', [a], cutoff, 20, 5, '2026-10-12'], ['single', [a], '', 20, 5, '2026-13-01'],
    ['unknown', [a], '', 20], ['pair', [a, b], cutoff, 20, 5, '2026-01-01'],
  ]) assert.throws(() => buildResearchRequest(...args), /invalid_research_request/);
  const ids = Array.from({ length: 51 }, (_, i) => i.toString(16).padStart(64, '0'));
  assert.throws(() => buildResearchRequest('universe', ids, cutoff), /invalid_research_request/);
});

test('request paths bind source roles, normalized membership and every selected parameter', () => {
  const single = buildResearchRequest('single', [a], '', 2, 1);
  const url = new URL(single.path, 'http://localhost');
  assert.equal(url.pathname, `/api/research/single/${a}`);
  assert.equal(url.searchParams.get('lookback'), '2');
  assert.equal(url.searchParams.get('horizon'), '1');
  assert.equal(url.searchParams.has('cutoff'), false);
  assert.equal(url.searchParams.has('test_start'), false);
  const split = new URL(buildResearchRequest('single', [a], cutoff, 252, 20, '2024-02-29').path, 'http://localhost');
  assert.equal(split.searchParams.get('test_start'), '2024-02-29');
  assert.equal(split.searchParams.get('cutoff'), cutoff);
  const pair = new URL(buildResearchRequest('pair', [b, a], cutoff, 5).path, 'http://localhost');
  assert.equal(pair.searchParams.get('left'), b); assert.equal(pair.searchParams.get('right'), a);
  const ids = [b, a];
  assert.deepEqual(buildResearchRequest('universe', ids, cutoff), buildResearchRequest('universe', [a, b], cutoff));
  assert.deepEqual(ids, [b, a]);
});

test('display formatting keeps true zero distinct from missing and rejects coercion/nonfinite values', () => {
  assert.equal(formatEstimate(0), '0.000'); assert.equal(formatPercent(0), '0.00%');
  assert.equal(formatPercent(0.125), '12.50%'); assert.equal(formatPercent(-0.02), '-2.00%');
  assert.equal(formatEstimate(-0), '0.000');
  for (const value of [null, undefined, NaN, Infinity, -Infinity, '0', '', false, {}, []]) {
    assert.equal(formatEstimate(value), '—'); assert.equal(formatPercent(value), '—');
  }
  assert.equal(formatPercent(Number.MAX_VALUE), '—');
  for (const digits of [-1, 21, NaN, '2']) assert.throws(() => formatEstimate(1, digits));
});

test('safe Chinese reasons and source names do not invent instrument identity or period', () => {
  assert.equal(researchReason('warming_up'), '估计预热中');
  assert.match(researchReason('future_status'), /未识别.*future_status/);
  assert.equal(researchReason(null), '—');
  const snapshot = { snapshot_id: a, metadata: { period: '1d', source_code: '600001.SH', source_name: '测试证券' } };
  assert.match(snapshotName(snapshot), /测试证券/); assert.match(snapshotName(snapshot), /600001.SH/);
  assert.match(snapshotName({ snapshot_id: a, metadata: {} }), /未标注证券/);
  assert.equal(isDailySnapshot(snapshot), true);
  for (const period of ['1m', 'day', '', null, undefined]) assert.equal(isDailySnapshot({ ...snapshot, metadata: { period } }), false);
});

test('generation rejects old success/failure after selection, cutoff, roles or parameter changes', () => {
  const gate = new Generation();
  const old = gate.invalidate();
  buildResearchRequest('pair', [a, b], cutoff, 20);
  const current = gate.invalidate();
  buildResearchRequest('pair', [b, a], '2026-10-10', 21);
  assert.equal(gate.isCurrent(old), false); assert.equal(gate.isCurrent(current), true);
  gate.invalidate(); // Failed/replaced request clears all old result state.
  assert.equal(gate.isCurrent(current), false);
});

const coverage = (n = 0) => ({ source_rows: n, date_groups: n, valid_groups: n, invalid_groups: 0,
  duplicate_groups: 0, unlocated_rows: 0, unreadable_date_rows: 0, batch_unlocated_rows: 0, coverage_known: true });
const identity = symbol => ({ symbol, code: symbol.split('.')[0], venue: symbol.split('.')[1], market: 'CN_A', qualification: 'source_claim' });
const distribution = () => ({ count: 0, mean: null, median: null, q05: null, q25: null, q75: null, q95: null,
  positive_count: 0, zero_count: 0, negative_count: 0, positive_fraction: null });
const partition = () => ({ counts: { candidate_dates: 0, rule_computable: 0, raw_events: 0, overlap_excluded: 0,
  selected_events: 0, valid: 0, immature: 0, invalid: 0, purged: 0 }, statistics: distribution(),
  baseline: { counts: { candidate_dates: 0, valid: 0, immature: 0, invalid: 0, purged: 0 }, statistics: distribution() } });
const model = kind => kind === 'single' ? {
  period: '1d', kalman_r: 1e-4, kalman_q_level: 1e-6, kalman_q_slope: 1e-8,
  kalman_p0_level: 1e-4, kalman_p0_slope: 1e-4, kalman_initial_slope: 0,
  ema_half_life: 10, ewma_half_life: 20, ema_alpha: 1 - 2 ** (-1 / 10), ewma_decay: 2 ** (-1 / 20),
  warmup_observations: 20, reset_policy: 'invalid_or_duplicate_date_group', initialization: 'full_source_prefix',
  lookback: 20, horizon: 5, test_start: null,
} : kind === 'pair' ? { lookback: 20, price_variance_floor: 1e-12, return_variance_floor: 1e-16, residual_scale_floor: 1e-10 }
  : { lookback: 20, volatility_ddof: 1 };
function fixture(kind) {
  const expected = buildResearchRequest(kind, kind === 'single' ? [a] : [a, b], cutoff).expected;
  const result = kind === 'single' ? {
    series: [], coverage: coverage(), numeric_kind: 'estimate_float64', qualification: 'conditional_source_observations',
    events: { ...partition(), rows: [], partitions: { descriptive: partition() }, lookback: 20, horizon: 5,
      test_start: null, evaluation_as_of: cutoff, mode: 'descriptive' },
  } : kind === 'pair' ? {
    series: [], alignment: { left: coverage(), right: coverage(), left_only_dates: 0, right_only_dates: 0,
      common_dates: 0, valid_common_dates: 0, coverage_known: true }, roles: { left: identity('600001.SH'), right: identity('000001.SZ') },
    baseline: null, regression_direction: 'left_Y_on_right_X', estimate_type: 'float64',
    price_window_includes_current: false, return_window_includes_current: true,
  } : {
    cutoff, estimate_type: 'float64', members: [a, b].map((id, i) => ({ snapshot_id: id, identity: identity(i ? '000001.SZ' : '600001.SH'),
      cutoff_present: true, cutoff_valid: true, start_date: '2026-09-21', end_date: cutoff, n_prices: 21, n_returns: 20,
      rank: 1, coverage: coverage(21), momentum: 0, volatility: 0, max_drawdown: 0,
      momentum_reason: null, volatility_reason: null, max_drawdown_reason: null })),
    breadth: { selected: 2, cutoff_present: 2, cutoff_valid: 2, momentum_valid: 2, volatility_valid: 2, max_drawdown_valid: 2,
      positive: 0, zero: 2, negative: 0, positive_momentum_fraction: 0, momentum_coverage: 1, cutoff_coverage: 1,
      metrics: Object.fromEntries(['momentum', 'volatility', 'max_drawdown'].map(k => [k, { eligible: 2, missing: 0, invalid: 0, short_history: 0 }])) },
  };
  result.parameters = model(kind);
  return { expected, reply: { method_id: expected.methodId, analysis_id: 'd'.repeat(64), mode: 'retrospective',
    inputs: expected.snapshotIds.map((snapshot_id, i) => ({ snapshot_id, query_id: (i ? 'e' : 'c').repeat(64) })),
    parameters: { ...expected.parameters, model: structuredClone(result.parameters) },
    limitations: ['retrospective_source_version', 'adjustment_basis_unverified', 'historical_availability_unverified',
      'calendar_and_bar_closure_unverified', 'descriptive_estimates_not_trading_returns'], result } };
}
const singleRow = () => ({ date: cutoff, ordinal: 1, close: '10', segment_id: 1, segment_observations: 1,
  warmup: true, status: 'warming_up', reason: null, reset_reason: null, kalman_level: Math.log(10), kalman_slope: 0,
  kalman_price: 10, ema_log: Math.log(10), ema_price: 10, model_deviation: null, log_return: null,
  ewma_volatility: null, return_shock: null, return_shock_reason: 'no_return', prior_high: null,
  breakout: null, breakout_reason: 'history_insufficient' });

test('valid empty single/pair and zero-valued universe retain exact source payloads', () => {
  for (const kind of ['single', 'pair', 'universe']) {
    const { reply, expected } = fixture(kind), before = structuredClone(reply);
    assert.doesNotThrow(() => assertResearchReply(reply, expected));
    assert.deepEqual(reply, before);
  }
  const { reply, expected } = fixture('single'); reply.result.series = [singleRow()]; reply.result.coverage = coverage(1);
  assert.doesNotThrow(() => assertResearchReply(reply, expected));
  Object.assign(reply.result.series[0], { ordinal: null, segment_id: null, segment_observations: 0,
    status: 'invalid', reason: 'duplicate_date' });
  assert.doesNotThrow(() => assertResearchReply(reply, expected));
});

test('envelope identity, order, mode, parameters and model mismatch all fail closed', () => {
  const mutations = [
    r => { r.method_id = 'other'; }, r => { r.analysis_id = 'short'; }, r => { r.mode = 'live'; },
    r => { r.inputs[0].snapshot_id = b; }, r => { r.inputs[0].query_id = 'bad'; },
    r => { r.inputs[1].query_id = r.inputs[0].query_id; }, r => { r.inputs.reverse(); },
    r => { r.inputs.pop(); }, r => { r.parameters.cutoff = '2026-10-10'; }, r => { r.parameters.lookback = 21; },
    r => { r.parameters.extra = true; }, r => { r.parameters.model = {}; },
    r => { r.result.parameters.lookback = 21; }, r => { r.limitations = 'missing'; }, r => { r.limitations = []; },
    r => { r.result = []; }, r => { r.extra = true; },
    r => { r.parameters.model.price_variance_floor = r.result.parameters.price_variance_floor = 0; },
    r => { r.result.price_window_includes_current = true; },
  ];
  for (const mutate of mutations) {
    const { reply, expected } = fixture('pair'); mutate(reply);
    assert.throws(() => assertResearchReply(reply, expected), /invalid_research_response/);
  }
  const { reply, expected } = fixture('single'); reply.parameters.test_start = '2026-09-01';
  assert.throws(() => assertResearchReply(reply, expected));
});

test('nested nonfinite values, numeric coercion, invalid dates and oversized arrays are rejected', () => {
  for (const mutate of [
    r => { r.result.extra = { value: NaN }; }, r => { r.result.extra = { value: Infinity }; },
    r => { r.result.extra = { value: undefined }; }, r => { r.result.series[0].kalman_slope = '0'; },
    r => { r.result.series[0].date = '2026-02-30'; }, r => { r.result.series[0].date = '2026-10-12'; },
    r => { r.result.series.push(structuredClone(r.result.series[0])); },
    r => { r.result.series = Array(20001).fill(r.result.series[0]); },
    r => { r.result.events.statistics.mean = 0; }, r => { r.result.events.counts.valid = true; },
    r => { r.result.events.counts.raw_events = 1; }, r => { r.result.coverage.valid_groups = -1; },
  ]) {
    const { reply, expected } = fixture('single'); reply.result.series = [singleRow()]; mutate(reply);
    assert.throws(() => assertResearchReply(reply, expected), /invalid_research_response/);
  }
});

test('universe binds every member, rejects stale cutoff and impossible coverage/counts', () => {
  for (const mutate of [
    r => { r.result.members[1].snapshot_id = a; }, r => { r.result.members[1].identity = r.result.members[0].identity; },
    r => { r.result.members.pop(); }, r => { r.result.cutoff = '2026-10-10'; },
    r => { r.result.members[0].end_date = '2026-10-10'; }, r => { r.result.members[0].max_drawdown = 0.1; },
    r => { r.result.members[0].volatility = -0.1; }, r => { r.result.members[0].rank = 3; },
    r => { r.result.members[0].momentum = null; }, r => { r.result.breadth.selected = 3; },
    r => { r.result.breadth.positive_momentum_fraction = 1.1; }, r => { r.result.breadth.zero = 1; },
    r => { r.result.breadth.metrics.momentum.missing = 1; },
  ]) {
    const { reply, expected } = fixture('universe'); mutate(reply);
    assert.throws(() => assertResearchReply(reply, expected), /invalid_research_response/);
  }
  const { reply, expected } = fixture('universe'); reply.result.members.reverse();
  assert.doesNotThrow(() => assertResearchReply(reply, expected)); // Ranking order is separate from canonical input identity.
});


test('all current research reason/reset/status/identity codes have Chinese explanations', () => {
  const codes = ['warming_up', 'computed', 'invalid', 'initial_observation', 'missing_ohlc', 'invalid_price',
    'invalid_ohlc', 'duplicate_date', 'unlocated_label', 'numerical_failure', 'price_scale_out_of_range',
    'no_return', 'no_prior_variance', 'zero_scale', 'history_insufficient', 'invalid_history_window',
    'insufficient_future_records', 'invalid_label_window', 'valid', 'immature', 'purged', 'overlap_excluded',
    'return_variance_too_small', 'price_variance_too_small', 'residual_scale_too_small', 'invalid_current_pair',
    'invalid_price_window', 'invalid_return_window', 'baseline_unavailable', 'date_set_integrity_unknown',
    'unequal_source_coverage', 'cutoff_missing', 'current_selected_membership',
    'source_claim', 'source_claim_and_declared', 'declared', 'conditional_source_observations',
    'conditional_located_source_values', 'source_coverage_unknown', 'descriptive', 'time_split_descriptive',
    'train', 'test', 'short_history', 'selected_sample_no_historical_sector_inference',
    'source_rejected', 'source_identity_conflict', 'source_adjustment_conflict', 'source_adjustment_check_failed', 'known_negative_source'];
  for (const code of codes) {
    assert.match(researchReason(code), /[\u4e00-\u9fff]/);
    assert.doesNotMatch(researchReason(code), /未识别状态/);
  }
  assert.match(researchReason('source_claim_and_declared'), /未经独立核验/);
});

test('research errors are actionable and preserve safe existing transport/source error explanations', () => {
  for (const code of ['research_identity_conflict', 'research_identity_unavailable', 'research_identity_unknown',
    'research_duplicate_symbol', 'research_duplicate_snapshot', 'research_market_unknown', 'research_market_mismatch',
    'research_cutoff_mismatch', 'research_invalid_member_count', 'research_total_row_limit', 'research_row_limit',
    'invalid_evaluation_as_of', 'invalid_date', 'invalid_cutoff', 'invalid_label_cutoff', 'ordinal_window_not_supported',
    'invalid_lookback', 'invalid_horizon', 'invalid_test_start', 'invalid_research_request', 'invalid_research_response']) {
    const explanation = explainResearch(new Error(code));
    assert.ok(explanation.includes(code));
    assert.doesNotMatch(explanation, /未识别状态|根据安全代码核对/);
  }
  assert.match(explainResearch(new Error('research_row_limit')), /20,000.*200,000/);
  assert.match(explainResearch(new Error('raw_object_corrupt')), /原件哈希/);
  assert.match(explainResearch(new Error('unexpected_future_code')), /unexpected_future_code/);
  assert.match(explainResearch(new Error('<private body>')), /connection_error/);
  assert.doesNotMatch(explainResearch(new Error('<private body>')), /private body/);
});
