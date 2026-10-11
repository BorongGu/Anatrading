import { explain, safeCode } from './api.ts';
import type { Snapshot } from './types.ts';
import type { ResearchEnvelope, SingleResult, PairResult, UniverseResult } from './research-types.ts';

export type ResearchKind = 'single' | 'pair' | 'universe';
export interface ResearchExpected {
  kind: ResearchKind;
  snapshotIds: readonly string[];
  methodId: string;
  parameters: { cutoff: string | null; lookback: number; horizon?: number; test_start?: string | null };
}
const methods = { single: 'daily-causal-research-v1', pair: 'paired-daily-research-v1', universe: 'selected-universe-research-v1' };
const hexId = /^[a-f0-9]{64}$/;
const maxRows = 20_000;
function day(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, date] = value.split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return year > 0 && month >= 1 && month <= 12 && date >= 1
    && date <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
function integer(value: unknown, min = 0, max = maxRows): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
}
export function buildResearchRequest(kind: ResearchKind, ids: readonly string[], cutoff = '', lookback = 20, horizon = 5, testStart = '') {
  if (!Object.hasOwn(methods, kind) || !Array.isArray(ids) || ids.some(id => typeof id !== 'string' || !hexId.test(id))
    || new Set(ids).size !== ids.length || (kind === 'single' ? ids.length !== 1 : kind === 'pair' ? ids.length !== 2 : ids.length < 2 || ids.length > 50)
    || typeof cutoff !== 'string' || (cutoff !== '' && !day(cutoff)) || (kind !== 'single' && !cutoff)
    || !integer(lookback, kind === 'pair' ? 5 : 2, 252) || ![1, 5, 10, 20].includes(horizon)
    || typeof testStart !== 'string' || (testStart !== '' && !day(testStart))
    || (testStart && cutoff && testStart > cutoff) || (kind !== 'single' && (testStart !== '' || horizon !== 5))) {
    throw new Error('invalid_research_request');
  }
  const snapshotIds = kind === 'universe' ? [...ids].sort() : [...ids];
  const parameters: ResearchExpected['parameters'] = { cutoff: cutoff || null, lookback };
  const query = new URLSearchParams();
  if (kind === 'pair') { query.set('left', snapshotIds[0]); query.set('right', snapshotIds[1]); }
  if (kind === 'universe') query.set('snapshot_ids', snapshotIds.join(','));
  if (cutoff) query.set('cutoff', cutoff);
  query.set('lookback', String(lookback));
  if (kind === 'single') {
    parameters.horizon = horizon; parameters.test_start = testStart || null;
    query.set('horizon', String(horizon));
    if (testStart) query.set('test_start', testStart);
  }
  return { path: `/api/research/${kind}${kind === 'single' ? `/${snapshotIds[0]}` : ''}?${query}`,
    expected: { kind, snapshotIds, methodId: methods[kind], parameters } satisfies ResearchExpected };
}

type RecordValue = Record<string, unknown>;
function ensure(condition: unknown): asserts condition {
  if (!condition) throw new Error('invalid_research_response');
}
function record(value: unknown): RecordValue {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  return value as RecordValue;
}
function keys(value: RecordValue, required: readonly string[], exact = false): void {
  ensure(required.every(key => Object.hasOwn(value, key)) && (!exact || Object.keys(value).length === required.length));
}
function array(value: unknown, max = maxRows): unknown[] { ensure(Array.isArray(value) && value.length <= max); return value; }
function text(value: unknown): value is string { return typeof value === 'string' && value.length > 0 && value.length <= 4096; }
function optionalText(value: unknown): boolean { return value === null || text(value); }
function estimate(value: unknown): value is number | null { return value === null || (typeof value === 'number' && Number.isFinite(value)); }
function fraction(value: unknown): boolean { return value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1); }
function dateBefore(value: unknown, cutoff: string | null, nullable = false): boolean {
  return (nullable && value === null) || (day(value) && (cutoff === null || value <= cutoff));
}
function same(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const left = a as RecordValue, right = b as RecordValue;
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every(key => Object.hasOwn(right, key) && same(left[key], right[key]));
}
// Every JSON number is checked, including fields added by a later backend. Bound
// nesting and collection sizes before inspecting method-specific values.
function safeJson(value: unknown, depth = 0): void {
  ensure(depth <= 16);
  if (value === null || typeof value === 'boolean') return;
  if (typeof value === 'number') { ensure(Number.isFinite(value)); return; }
  if (typeof value === 'string') { ensure(value.length <= 4096); return; }
  if (Array.isArray(value)) { ensure(value.length <= maxRows); for (const item of value) safeJson(item, depth + 1); return; }
  const obj = record(value);
  ensure(Object.keys(obj).length <= 128);
  for (const [key, item] of Object.entries(obj)) { ensure(key.length <= 128); safeJson(item, depth + 1); }
}
function numbers(row: RecordValue, names: readonly string[]): void { for (const name of names) ensure(estimate(row[name])); }
function reasons(row: RecordValue, names: readonly string[]): void { for (const name of names) ensure(optionalText(row[name])); }
function counts(value: unknown, names: readonly string[], max = maxRows): RecordValue {
  const obj = record(value); for (const name of names) ensure(integer(obj[name], 0, max)); return obj;
}
function seriesRows(value: unknown, cutoff: string | null): RecordValue[] {
  let last = '';
  return array(value).map(item => {
    const row = record(item); ensure(dateBefore(row.date, cutoff) && (row.date as string) > last); last = row.date as string; return row;
  });
}
function distribution(value: unknown): void {
  const d = counts(value, ['count', 'positive_count', 'zero_count', 'negative_count']);
  numbers(d, ['mean', 'median', 'q05', 'q25', 'q75', 'q95']); ensure(fraction(d.positive_fraction));
  ensure(d.count === (d.positive_count as number) + (d.zero_count as number) + (d.negative_count as number));
  for (const key of ['mean', 'median', 'q05', 'q25', 'q75', 'q95', 'positive_fraction']) ensure((d[key] === null) === (d.count === 0));
}
function eventPartition(value: unknown): void {
  const p = record(value), c = counts(p.counts, ['candidate_dates', 'rule_computable', 'raw_events', 'overlap_excluded', 'selected_events', 'valid', 'immature', 'invalid', 'purged']);
  ensure(c.raw_events === (c.overlap_excluded as number) + (c.selected_events as number));
  ensure(c.selected_events === (c.valid as number) + (c.immature as number) + (c.invalid as number) + (c.purged as number));
  distribution(p.statistics); ensure(record(p.statistics).count === c.valid);
  const b = record(p.baseline), bc = counts(b.counts, ['candidate_dates', 'valid', 'immature', 'invalid', 'purged']);
  distribution(b.statistics); ensure(record(b.statistics).count === bc.valid);
}
function singleResult(result: RecordValue, expected: ResearchExpected): void {
  const cutoff = expected.parameters.cutoff, rows = seriesRows(result.series, cutoff);
  coverage(result.coverage); record(result.parameters);
  ensure(result.numeric_kind === 'estimate_float64' && text(result.qualification));
  for (const row of rows) {
    ensure((row.ordinal === null || integer(row.ordinal, 1, Number.MAX_SAFE_INTEGER)) && optionalText(row.close) && optionalText(row.prior_high)
      && (row.segment_id === null || integer(row.segment_id, 1)) && integer(row.segment_observations)
      && typeof row.warmup === 'boolean' && text(row.status) && [true, false, null].includes(row.breakout as boolean | null));
    numbers(row, ['kalman_level', 'kalman_slope', 'kalman_price', 'ema_log', 'ema_price', 'model_deviation', 'log_return', 'ewma_volatility', 'return_shock']);
    reasons(row, ['reason', 'reset_reason', 'return_shock_reason', 'breakout_reason']);
    ensure(row.ewma_volatility === null || (row.ewma_volatility as number) >= 0);
  }
  const e = record(result.events); eventPartition(e);
  ensure(e.lookback === expected.parameters.lookback && e.horizon === expected.parameters.horizon && e.test_start === expected.parameters.test_start
    && dateBefore(e.evaluation_as_of, cutoff, true) && text(e.mode));
  const events = seriesRows(e.rows, cutoff); ensure(events.length === record(e.counts).raw_events);
  for (const row of events) {
    ensure(integer(row.index, 0, rows.length - 1) && rows[row.index as number].date === row.date
      && rows[row.index as number].ordinal === row.ordinal && rows[row.index as number].breakout === true
      && typeof row.selected === 'boolean' && text(row.partition) && text(row.evaluation_status) && text(row.label_status)
      && optionalText(row.label_reason) && dateBefore(row.label_end, cutoff, true) && estimate(row.price_change)
      && row.signal_as_of === row.date && row.evaluation_as_of === e.evaluation_as_of);
  }
  for (const partition of Object.values(record(e.partitions))) eventPartition(partition);
}
function pairResult(result: RecordValue, expected: ResearchExpected): void {
  const rows = seriesRows(result.series, expected.parameters.cutoff);
  ensure(result.regression_direction === 'left_Y_on_right_X' && result.estimate_type === 'float64'
    && result.price_window_includes_current === false && result.return_window_includes_current === true);
  const a = counts(result.alignment, ['left_only_dates', 'right_only_dates', 'common_dates', 'valid_common_dates']);
  ensure(a.common_dates === rows.length && (a.valid_common_dates as number) <= rows.length);
  for (const side of ['left', 'right']) {
    coverage(a[side]);
  }
  const roles = record(result.roles); identity(roles.left); identity(roles.right);
  ensure(record(roles.left).symbol !== record(roles.right).symbol);
  if (result.baseline !== null) {
    const base = record(result.baseline); ensure(dateBefore(base.date, expected.parameters.cutoff) && text(base.left_close) && text(base.right_close));
  }
  for (const row of rows) {
    for (const side of ['left_ordinal', 'right_ordinal']) ensure(row[side] === null || integer(row[side], 1, Number.MAX_SAFE_INTEGER));
    numbers(row, ['left_log_return', 'right_log_return', 'return_correlation', 'return_beta', 'log_price_alpha', 'log_price_beta', 'residual_scale', 'residual_deviation', 'relative_strength']);
    reasons(row, ['reason', 'correlation_reason', 'return_beta_reason', 'price_regression_reason', 'deviation_reason', 'relative_strength_reason', 'coverage_reason']);
    ensure(integer(row.n_prices, 0, expected.parameters.lookback) && integer(row.n_returns, 0, expected.parameters.lookback));
    for (const name of ['return_start_date', 'price_start_date', 'price_end_date', 'returns_start_date', 'returns_end_date']) ensure(dateBefore(row[name], row.date as string, true));
    ensure(row.return_correlation === null || Math.abs(row.return_correlation as number) <= 1);
    ensure(row.residual_scale === null || (row.residual_scale as number) >= 0);
    ensure(row.price_end_date === null || (row.price_end_date as string) < (row.date as string));
  }
}
function coverage(value: unknown): void {
  const c = counts(value, ['source_rows', 'date_groups', 'valid_groups', 'invalid_groups', 'duplicate_groups', 'unlocated_rows', 'unreadable_date_rows']);
  ensure(integer(c.batch_unlocated_rows, 0, Number.MAX_SAFE_INTEGER) && typeof c.coverage_known === 'boolean'
    && c.date_groups === (c.valid_groups as number) + (c.invalid_groups as number));
}
function identity(value: unknown): void {
  const i = record(value); for (const name of ['symbol', 'code', 'venue', 'market', 'qualification']) ensure(text(i[name]));
}
function universeResult(result: RecordValue, expected: ResearchExpected): void {
  ensure(result.cutoff === expected.parameters.cutoff && result.estimate_type === 'float64');
  const members = array(result.members, 50), ids = new Set(expected.snapshotIds), symbols = new Set<string>();
  ensure(members.length === ids.size);
  for (const item of members) {
    const m = record(item); ensure(typeof m.snapshot_id === 'string' && ids.delete(m.snapshot_id));
    identity(m.identity); const symbol = record(m.identity).symbol as string; ensure(!symbols.has(symbol)); symbols.add(symbol);
    ensure(typeof m.cutoff_present === 'boolean' && typeof m.cutoff_valid === 'boolean' && (!m.cutoff_valid || m.cutoff_present)
      && integer(m.n_prices, 0, expected.parameters.lookback + 1) && integer(m.n_returns, 0, expected.parameters.lookback)
      && (m.rank === null || integer(m.rank, 1, members.length)) && dateBefore(m.start_date, expected.parameters.cutoff, true)
      && (m.end_date === null || m.end_date === expected.parameters.cutoff));
    numbers(m, ['momentum', 'volatility', 'max_drawdown']); reasons(m, ['momentum_reason', 'volatility_reason', 'max_drawdown_reason']); coverage(m.coverage);
    ensure((m.volatility === null || (m.volatility as number) >= 0) && (m.max_drawdown === null || ((m.max_drawdown as number) >= -1 && (m.max_drawdown as number) <= 0))
      && (m.momentum === null) === (m.rank === null));
  }
  const b = counts(result.breadth, ['selected', 'cutoff_present', 'cutoff_valid', 'momentum_valid', 'volatility_valid', 'max_drawdown_valid', 'positive', 'zero', 'negative'], members.length);
  ensure(b.selected === members.length && b.momentum_valid === (b.positive as number) + (b.zero as number) + (b.negative as number));
  for (const key of ['positive_momentum_fraction', 'momentum_coverage', 'cutoff_coverage']) ensure(fraction(b[key]));
  ensure((b.positive_momentum_fraction === null) === (b.momentum_valid === 0));
  ensure(b.cutoff_present === members.filter(item => record(item).cutoff_present).length
    && b.cutoff_valid === members.filter(item => record(item).cutoff_valid).length);
  const metrics = record(b.metrics);
  for (const key of ['momentum', 'volatility', 'max_drawdown']) {
    const m = counts(metrics[key], ['eligible', 'missing', 'invalid', 'short_history'], members.length);
    ensure((m.eligible as number) + (m.missing as number) + (m.invalid as number) + (m.short_history as number) === members.length
      && m.eligible === b[`${key}_valid`] && m.eligible === members.filter(item => record(item)[key] !== null).length);
  }
}
function validateModel(model: RecordValue, expected: ResearchExpected): void {
  const { lookback, horizon, test_start } = expected.parameters;
  const fixed: RecordValue = expected.kind === 'single' ? {
    period: '1d', kalman_r: 1e-4, kalman_q_level: 1e-6, kalman_q_slope: 1e-8,
    kalman_p0_level: 1e-4, kalman_p0_slope: 1e-4, kalman_initial_slope: 0,
    ema_half_life: 10, ewma_half_life: 20, warmup_observations: 20,
    reset_policy: 'invalid_or_duplicate_date_group', initialization: 'full_source_prefix',
    lookback, horizon, test_start,
  } : expected.kind === 'pair' ? {
    lookback, price_variance_floor: 1e-12, return_variance_floor: 1e-16, residual_scale_floor: 1e-10,
  } : { lookback, volatility_ddof: 1 };
  keys(model, [...Object.keys(fixed), ...(expected.kind === 'single' ? ['ema_alpha', 'ewma_decay'] : [])], true);
  for (const [key, value] of Object.entries(fixed)) ensure(model[key] === value);
  if (expected.kind === 'single') {
    ensure(typeof model.ema_alpha === 'number' && Math.abs(model.ema_alpha - (1 - 2 ** (-1 / 10))) < 1e-14
      && typeof model.ewma_decay === 'number' && Math.abs(model.ewma_decay - 2 ** (-1 / 20)) < 1e-14);
  }
}
export function assertResearchReply(reply: unknown, expected: ResearchExpected): asserts reply is ResearchEnvelope<SingleResult | PairResult | UniverseResult> {
  safeJson(reply);
  const envelope = record(reply);
  keys(envelope, ['method_id', 'analysis_id', 'inputs', 'parameters', 'mode', 'limitations', 'result'], true);
  ensure(envelope.method_id === expected.methodId && typeof envelope.analysis_id === 'string' && hexId.test(envelope.analysis_id)
    && envelope.mode === 'retrospective');
  const inputs = array(envelope.inputs, 50); ensure(inputs.length === expected.snapshotIds.length);
  const queryIds = new Set<string>();
  inputs.forEach((item, index) => {
    const input = record(item); keys(input, ['snapshot_id', 'query_id'], true);
    ensure(input.snapshot_id === expected.snapshotIds[index] && typeof input.query_id === 'string' && hexId.test(input.query_id) && !queryIds.has(input.query_id));
    queryIds.add(input.query_id as string);
  });
  const parameters = record(envelope.parameters), result = record(envelope.result);
  keys(parameters, [...Object.keys(expected.parameters), 'model'], true);
  for (const [key, value] of Object.entries(expected.parameters)) ensure(parameters[key] === value);
  ensure(same(record(parameters.model), record(result.parameters)));
  validateModel(record(parameters.model), expected);
  const limitations = array(envelope.limitations, 100);
  ensure(limitations.every(text) && ['retrospective_source_version', 'adjustment_basis_unverified',
    'historical_availability_unverified', 'calendar_and_bar_closure_unverified',
    'descriptive_estimates_not_trading_returns'].every(code => limitations.includes(code)));
  if (expected.kind === 'single') singleResult(result, expected);
  else if (expected.kind === 'pair') pairResult(result, expected);
  else universeResult(result, expected);
}

export function formatEstimate(value: unknown, digits = 3): string {
  if (!integer(digits, 0, 20)) throw new Error('invalid_display_precision');
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  const formatted = value.toFixed(digits); return Number(formatted) === 0 ? (0).toFixed(digits) : formatted;
}
export function formatPercent(value: unknown, digits = 2): string {
  const formatted = formatEstimate(typeof value === 'number' ? value * 100 : null, digits);
  return formatted === '—' ? formatted : `${formatted}%`;
}
export function isDailySnapshot(snapshot: Snapshot): boolean { return snapshot.metadata?.period === '1d'; }
export function snapshotName(snapshot: Snapshot): string {
  const name = typeof snapshot.metadata?.source_name === 'string' ? snapshot.metadata.source_name.trim() : '';
  const code = typeof snapshot.metadata?.source_code === 'string' ? snapshot.metadata.source_code.trim() : '';
  return [name, code].filter(Boolean).join(' · ') || '未标注证券';
}
const reasonNames: Record<string, string> = {
  computed: '已计算', warming_up: '估计预热中', invalid: '不可计算', valid: '有效', immature: '尚未成熟',
  purged: '跨分段边界已排除', overlap_excluded: '重叠事件已排除', history_insufficient: '历史记录不足',
  invalid_history_window: '历史窗口含异常记录', invalid_label_window: '后续窗口含异常记录',
  missing_ohlc: '价格字段缺失', invalid_price: '价格无效', invalid_ohlc: '价格关系异常', duplicate_date: '来源日期重复',
  unlocated_label: '来源日期无法定位', numerical_failure: '数值估计失败', no_prior_variance: '尚无前期波动估计',
  initial_observation: '首个有效来源观测，开始初始化', insufficient_future_records: '后续来源记录不足，标签尚未成熟',
  invalid_current_pair: '当前两侧价格无法共同计算',
  no_return: '尚无前一期区间收益', price_scale_out_of_range: '价格尺度超出数值范围',
  invalid_price_window: '拟合价格窗口含异常记录', invalid_return_window: '区间收益窗口含异常记录', baseline_unavailable: '共同起点不可用',
  zero_scale: '波动尺度为零', residual_scale_too_small: '拟合残差尺度过小', return_variance_too_small: '区间收益方差过小',
  price_variance_too_small: '拟合价格方差过小', unequal_source_coverage: '两侧来源日期覆盖不一致',
  date_set_integrity_unknown: '来源日期完整性未核', cutoff_missing: '缺少截止日期记录', missing_cutoff: '缺少截止日期记录',
  unsupported_period: '仅支持日线', invalid_lookback: '观察窗口超出范围', invalid_horizon: '观察跨度无效',
  invalid_test_start: '评价分段日期无效', invalid_research_date: '请输入有效日线日期', invalid_snapshot_id: '数据版本无效',
  duplicate_snapshot: '不能重复选择同一数据版本', research_member_limit: '请选择 2 至 50 个不同证券的数据版本',
  research_row_limit: '研究记录超过上限（单版本 20,000 条、合计 200,000 条），请提前截止日期或减少成员', invalid_research_request: '研究参数无效，请检查选择和日期',
  invalid_research_response: '研究响应与当前选择或数据合同不符', invalid_research_input: '研究输入不满足计算要求',
  research_duplicate_symbol: '所选数据含同一证券的多个版本，请每只证券保留一个版本', research_market_unknown: '证券市场无法识别，请核对来源市场或导入声明',
  research_market_mismatch: '证券市场不一致，请选择同一市场的证券', research_identity_conflict: '证券身份声明不一致，请核对来源代码与导入声明',
  retrospective_source_version: '以当前保存的数据版本回顾历史', adjustment_basis_unverified: '复权口径未核',
  historical_availability_unverified: '历史当时可得性未核', calendar_and_bar_closure_unverified: '交易日历与收盘完整性未核',
  descriptive_estimates_not_trading_returns: '描述性估计不代表可成交交易收益',
  current_selected_membership: '使用当前所选成员回顾历史，存在成员选择偏差',
  selected_sample_no_historical_sector_inference: '仅代表所选样本，未推断历史板块成员',
  source_claim: '来源文件声明，尚未经独立核验',
  source_claim_and_declared: '来源文件与用户声明一致，尚未经独立核验',
  declared: '用户声明，尚未经来源核验',
  conditional_source_observations: '基于来源观测的条件估计',
  conditional_located_source_values: '仅描述可定位的来源记录',
  source_coverage_unknown: '来源日期覆盖未知',
  source_rejected: '来源资格未通过，当前数据不能用于研究',
  source_identity_conflict: '来源证券身份冲突，请核对原文件与导入声明',
  source_adjustment_conflict: '来源复权口径冲突，请核对原文件与导入声明',
  source_adjustment_check_failed: '来源复权检查未通过，请核对复权字段',
  known_negative_source: '来源已标为无效样本，不能用于正常行情研究',
  calendar_and_coverage_unverified: '交易日历与来源覆盖未核',
  adjustment_and_corporate_actions_unverified: '复权口径与公司行动未核',
  fixed_engineering_parameters_not_calibrated: '使用固定工程参数，未按行情校准',
  no_prediction_or_trading_return_claim: '结果未验证预测能力或交易收益',
  descriptive: '全段描述性评价', time_split_descriptive: '按时间分段描述性评价', train: '前段', test: '后段',
  short_history: '历史记录不足', missing: '记录缺失', eligible: '可计算',
  research_identity_unavailable: '无法识别证券身份，请核对来源代码或导入声明',
  research_identity_unknown: '证券身份未知，请核对来源代码或导入声明',
  research_duplicate_snapshot: '数据版本重复，请为每只证券选择一个版本',
  research_cutoff_mismatch: '两侧截止日期不一致，请重新选择统一日期',
  research_invalid_member_count: '请选择 2 至 50 只不同证券的数据版本',
  research_total_row_limit: '所选来源合计超过 200,000 条，请减少成员或提前截止日期',
  ordinal_window_not_supported: '递推研究需要完整来源前缀，请取消源序号范围',
  invalid_evaluation_as_of: '评价截止日期无效，请填写完整年月日',
  invalid_date: '来源日期无效，请核对原始日期字段',
  invalid_cutoff: '截止日期无效，请填写有效的完整年月日',
  invalid_label_cutoff: '截止日期无效，请填写有效的完整年月日',
  duplicate_instrument: '同一证券被重复选择，请为每只证券保留一个版本',
  unknown_instrument: '无法识别证券身份，请核对来源代码或导入声明',
  incompatible_market: '证券市场不兼容，请选择同一市场的证券',
  unknown_market: '证券市场无法识别，请核对来源市场或导入声明',
  same_instrument: '双股比较需要两只不同证券，请更换其中一只',
  same_snapshot: '双股比较需要不同数据版本，请重新选择',
  invalid_series: '来源序列不符合研究要求，请核对数据周期与价格字段',
  invalid_parameters: '研究参数无效，请检查窗口、日期和观察跨度',
  invalid_universe: '所选集合不符合研究要求，请核对证券身份与日期',
  invalid_member_count: '请选择 2 至 50 只不同证券的数据版本',
};
export function researchReason(code: string | null | undefined): string {
  if (code === null || code === undefined || code === '') return '—';
  if (Object.hasOwn(reasonNames, code)) return reasonNames[code];
  const safeCode = String(code).replace(/[\u0000-\u001f\u007f]/g, '').slice(0, 128);
  return `未识别状态（${safeCode}）`;
}

export function explainResearch(error: unknown): string {
  const code = safeCode(error);
  return Object.hasOwn(reasonNames, code) ? `${reasonNames[code]}（${code}）` : explain(error);
}
