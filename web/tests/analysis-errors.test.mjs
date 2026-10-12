import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { explain } from '../src/api.ts';
import { explainAnalysisError } from '../src/analysis-errors.ts';

const source = name => readFileSync(new URL(`../src/${name}.tsx`, import.meta.url), 'utf8');
const contexts = ['current_version', 'paired_daily_background', 'minute_selection_and_daily'];
const limit = new Error('query_row_limit');

test('current-version guidance describes the full count budget and a viable recovery', () => {
  const text = explainAnalysisError(limit, 'current_version');
  for (const part of ['显示窗口外的上下文', '当前完整数据版本总条数', '20,000',
    '缩小显示源序号窗口或提前截止均不能降低', '改选不超过上限的较小来源数据版本']) assert.ok(text.includes(part), part);
  assert.ok(text.endsWith('（query_row_limit）'));
});

test('background guidance identifies the paired daily version, independently of display and anchor', () => {
  const text = explainAnalysisError(limit, 'paired_daily_background');
  for (const part of ['用于对照的日线数据版本', '完整日线版本总条数', '20,000',
    '缩小分钟显示窗口、背景历史窗口或提前分钟锚点均不能降低', '改选不超过上限的较小日线数据版本']) assert.ok(text.includes(part), part);
  assert.ok(text.endsWith('（query_row_limit）'));
});

test('reconciliation guidance keeps both possible failure sides conditional', () => {
  const text = explainAnalysisError(limit, 'minute_selection_and_daily');
  for (const part of ['分钟选择与用于对照的完整日线数据版本各有 20,000 条上限',
    '若分钟选择超限，请缩小源序号窗口并重新查询',
    '若完整日线版本总条数超限，缩小分钟窗口无效', '改选不超过上限的较小日线数据版本']) assert.ok(text.includes(part), part);
  assert.ok(text.endsWith('（query_row_limit）'));
});

test('all contexts delegate every other safe or unsafe error to the public explanation', () => {
  for (const context of contexts) {
    for (const error of [new Error('raw_object_corrupt'), new Error('invalid_query_response'),
      new Error('background_symbol_mismatch'), new Error('response_limit'), new Error('unrecognized_safe_code'),
      new Error('query_row_limit\nPRIVATE_BODY'), new Error('<private raw payload>'),
      new Error('QUERY_ROW_LIMIT'), new Error('query_row_limit '), new Error('x'.repeat(81)),
      'query_row_limit', { message: 'query_row_limit' }, null, undefined, 12]) {
      assert.equal(explainAnalysisError(error, context), explain(error), context);
    }
  }
});

const entries = [
  ['VolumeAnalysis', 'volume', 'current_version', 'setReport', '[query, lookback]'],
  ['PriceChannel', 'price-channel', 'current_version', 'onReport', '[query, lookback, onReport]'],
  ['VolatilityAnalysis', 'true-range', 'current_version', 'setReport', '[query, period]'],
  ['DailyVolume', 'daily-volume', 'current_version', 'setReport', '[query, lookback]'],
  ['PathEfficiency', 'path-efficiency', 'current_version', 'setReport', '[query, lookback]'],
  ['PivotAnalysis', 'source-pivots', 'current_version', 'onReport', '[query, radius, onReport]'],
  ['GapAnalysis', 'source-gaps', 'current_version', 'setReport', '[query]'],
  ['DailyBackground', 'daily-background', 'paired_daily_background', 'setReport', '[minuteSnapshot, dailySnapshot, ordinal, label, window]'],
  ['MinuteDailyReconciliation', 'minute-daily-reconciliation', 'minute_selection_and_daily', 'setReport', '[query, dailySnapshot, multiplier]'],
];

for (const [name, route, context, reset, dependencies] of entries) {
  test(`${name}: actual catch calls the assigned explanation and suppresses aborted errors`, () => {
    const text = source(name);
    assert.ok(text.includes("import { explainAnalysisError } from './analysis-errors.ts';"));
    const bodies = [...text.matchAll(/(?:\.catch\(error =>|catch \(error\)) \{ ([^\n]+?) \}/g)];
    assert.equal(bodies.length, 1, 'only the analysis request catch is changed');
    const body = bodies[0][1];
    assert.equal(body, `if (!controller.signal.aborted) setIssue(explainAnalysisError(error, '${context}'));`);
    // Execute the actual source catch in isolation; this is not mounted React or browser coverage.
    const handle = new Function('controller', 'setIssue', 'explainAnalysisError', 'error', body);
    const received = [], controller = new AbortController();
    for (const error of [limit, new Error('invalid_query_response'), new Error('<private raw payload>')]) {
      handle(controller, value => received.push(value), explainAnalysisError, error);
      assert.equal(received.at(-1), explainAnalysisError(error, context));
    }
    controller.abort();
    handle(controller, value => received.push(value), explainAnalysisError, limit);
    assert.equal(received.length, 3);

    const requestAt = text.indexOf(`/api/${route}/`), resetAt = text.indexOf(`${reset}(null);`);
    assert.ok(resetAt >= 0 && resetAt < requestAt, 'previous report cleared before request');
    assert.ok(text.indexOf("setIssue('');") < requestAt);
    assert.ok(text.includes('signal: controller.signal'));
    assert.ok(text.includes('if (controller.signal.aborted) return;'));
    assert.ok(text.includes(dependencies));
    assert.ok(text.includes('className="error-banner">{issue}</p>'));
    if (['PivotAnalysis', 'GapAnalysis'].includes(name)) {
      assert.ok(text.includes('return () => abort.current?.abort();'));
      assert.ok(text.includes('abort.current?.abort();\n    const controller = new AbortController();'));
      assert.ok(text.includes("finally { if (!controller.signal.aborted) setLoading(false); }"));
      assert.ok(text.includes(`${reset}(null); setBody(''); setIssue(''); setLoading(true); setPage(0);`));
    } else {
      assert.ok(text.includes('return () => controller.abort();'));
    }
    if (name === 'DailyBackground') {
      assert.ok(text.includes("setReport(null); setDailyRow(null); setIssue('');"));
      assert.ok(text.includes("setIssue(explain(new Error('chart_render_failed')))"), 'chart errors remain public');
    } else {
      assert.ok(text.includes("['cutoff', 'ordinal_start', 'ordinal_end']"), 'selection retained');
    }
  });
}

test('ordinary query, exports, company actions and minute aggregation retain public recovery guidance', () => {
  assert.equal(explain(limit), '当前选择超过 20,000 条上限，请缩小源序号窗口。（query_row_limit）');
  for (const name of ['App', 'SourceActions', 'MinuteAggregation']) {
    const text = source(name);
    assert.doesNotMatch(text, /explainAnalysisError|analysis-errors/);
    assert.ok(text.includes('setIssue(explain(error))'));
  }
  const app = source('App');
  const query = app.slice(app.indexOf('async function loadQuery('), app.indexOf('async function importFile('));
  assert.match(query, /catch \(error\) \{\s+if \(!gate.current.isCurrent\(generation\)\) return;\s+invalidate\(\); setIssue\(explain\(error\)\);/);
  const exports = app.slice(app.indexOf('async function exportSelection('), app.indexOf('const snapshot = snapshots.find', app.indexOf('async function exportSelection(')));
  assert.ok(exports.includes("const route = format === 'geometry' ? 'geometry-export' : 'export';"));
  assert.match(exports, /catch \(error\) \{\s+if \(gate.current.isCurrent\(generation\)\) \{ invalidate\(\); setIssue\(explain\(error\)\);/);
});

test('the existing minute-history special explanation and request gate are preserved', () => {
  const text = source('MinuteLabelHistory');
  assert.ok(text.includes("safeCode(error) === 'query_row_limit'"));
  assert.ok(text.includes('历史同标签记录需要整个数据版本的上下文，完整版本上限为 20,000 条。缩小显示源序号窗口无效，请改选不超过上限的较小来源数据版本。（query_row_limit）'));
  assert.ok(text.includes('if (gate.current.isCurrent(token, latestKey.current)) setIssue(explainMinuteHistoryError(error));'));
  assert.doesNotMatch(text, /explainAnalysisError|analysis-errors/);
});
