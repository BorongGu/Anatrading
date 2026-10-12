import { useEffect, useRef, useState } from 'react';
import { explain, safeCode } from './api.ts';
import { buildMinuteHistoryRequest, loadMinuteHistory, MinuteHistoryGate, minuteHistoryInputIssue,
  minuteHistorySourceDate, minuteHistorySourceKey } from './minute-label-history.ts';
import type { MinuteHistoryFraction, MinuteHistoryReport } from './minute-label-history.ts';
import type { Query, Row } from './types.ts';

const reasons: Record<string, string> = {
  missing_endpoint: '缺少端点记录', duplicate_endpoint: '端点存在重复记录', endpoint_uniqueness_unknown: '有时钟无法定位的记录，端点唯一性未知',
  source_identity_conflict: '证券或市场身份声明冲突', source_adjustment_conflict: '复权声明冲突',
  source_adjustment_check_failed: '复权检查未通过', source_label_conflict: '来源标签定义或检查冲突',
  source_structure_failed: '来源结构检查未通过', price_scale_conflict: '价格尺度声明冲突',
  missing_close: '端点收盘值缺失', invalid_close: '端点收盘值非法', nonpositive_close: '端点收盘值非正', source_quarantined: '来源处于隔离状态',
};

export function explainMinuteHistoryError(error: unknown): string {
  return safeCode(error) === 'query_row_limit'
    ? '历史同标签记录需要整个数据版本的上下文，完整版本上限为 20,000 条。缩小显示源序号窗口无效，请改选不超过上限的较小来源数据版本。（query_row_limit）'
    : explain(error);
}

export function MinuteLabelHistory({ query, row }: { query: Query; row: Row }) {
  // A new source/row mounts empty controls, without silently choosing endpoint labels.
  return <MinuteHistoryForm key={minuteHistorySourceKey(query, row)} query={query} row={row} />;
}
function MinuteHistoryForm({ query, row }: { query: Query; row: Row }) {
  const [start, setStart] = useState(''), [end, setEnd] = useState('');
  const [report, setReport] = useState<{ key: string; value: MinuteHistoryReport } | null>(null);
  const [issue, setIssue] = useState(''), [loading, setLoading] = useState(false);
  const gate = useRef(new MinuteHistoryGate());
  const sourceDate = minuteHistorySourceDate(row);
  const key = `${minuteHistorySourceKey(query, row)}\n${start}\n${end}`;
  const latestKey = useRef(key); latestKey.current = key;
  useEffect(() => () => gate.current.cancel(), []);
  function invalidate() { gate.current.cancel(); setReport(null); setIssue(''); setLoading(false); }
  async function read() {
    invalidate();
    const inputIssue = minuteHistoryInputIssue(query, row, start, end);
    if (inputIssue) { setIssue(inputIssue); return; }
    const request = buildMinuteHistoryRequest(query, row, start, end), token = gate.current.begin(key);
    setLoading(true);
    try {
      const result = await loadMinuteHistory(request, token.controller.signal);
      if (!gate.current.isCurrent(token, latestKey.current)) return;
      setReport({ key: request.key, value: result });
    } catch (error) {
      if (gate.current.isCurrent(token, latestKey.current)) setIssue(explainMinuteHistoryError(error));
    } finally {
      if (gate.current.isCurrent(token, latestKey.current)) setLoading(false);
    }
  }
  const current = report?.key === key ? report.value : null;
  return <details className="geometry-details minute-label-history">
    <summary>历史同标签记录</summary>
    <p className="subtle">在所选来源日期 {sourceDate ?? '（规范日期标签缺失）'}，明确填写两个不同的 HH:MM 标签。保留当天与此前最多五个来源日期的同名端点，缺失日不跳过。</p>
    <form onSubmit={event => { event.preventDefault(); void read(); }}>
      <div className="pagination">
        <label>起点标签 <input type="time" required step="60" aria-label="起点标签 HH:MM" value={start}
          onChange={event => { invalidate(); setStart(event.target.value); }} /></label>
        <label>终点标签 <input type="time" required step="60" aria-label="终点标签 HH:MM" value={end}
          onChange={event => { invalidate(); setEnd(event.target.value); }} /></label>
        <button type="submit" disabled={loading || !sourceDate || !start || !end}>{loading ? '读取中…' : '查看同标签记录'}</button>
      </div>
    </form>
    {!sourceDate && <p className="inline-note amber">所选记录缺少可用于此功能的规范日期标签，请选择日期标签有效的记录。</p>}
    <p className="subtle">按标签核对已收到的源值；价格变化以两端共用价格尺度为条件。交易时段、覆盖、闭合及当时可得性未核。</p>
    {issue && <p role="alert" className="error-banner">{issue}</p>}
    {current && <MinuteHistoryResults report={current} />}
  </details>;
}
function signed(value: string): string { return value.startsWith('-') || /^0(?:\.0+)?$/.test(value) ? value : `+${value}`; }
function FractionValue({ value, absolute = false }: { value: MinuteHistoryFraction; absolute?: boolean }) {
  return <><code>{absolute ? value.numerator : signed(value.numerator)}/{value.denominator}</code>（≈{absolute ? value.display : signed(value.display)}）</>;
}
function Endpoints({ rows, clock }: { rows: Row[]; clock: string }) {
  return <div><h4>{clock} 端点</h4>{rows.length === 0 ? <p>缺少记录</p> : rows.map(row => <div key={row.ordinal} className="record-heading">
    <p>收盘 <code>{row.values.close ?? '∅ 缺失 / 非法'}</code><br />
      原始标签 <code>{row.source_label ?? '∅'}</code><br />规范标签 <code>{row.label ?? '∅'}</code><br />
      源序号 {row.ordinal} · <code>{row.locator}</code></p>
    <details><summary>端点原字段与检查</summary><pre>{JSON.stringify({ tokens: row.tokens, values: row.values, checks: row.checks }, null, 2)}</pre></details>
  </div>)}</div>;
}
export function MinuteHistoryResults({ report }: { report: MinuteHistoryReport }) {
  return <div>
    <p className="inline-note">{report.start_clock} → {report.end_clock}：名义时钟差 {report.nominal_minutes} 分钟。未按分钟归一化。</p>
    <p className="subtle">来源日期按日历先后列出；可读的问题日期占据原位置。</p>
    {report.window_status === 'unresolved_dates' ? <p className="inline-note amber">有来源日期无法读取，以下为降级的可读日期列表；此前五个来源日期的集合完整性未知。</p>
      : report.window_status === 'insufficient' ? <p className="inline-note amber">历史来源日期不足五日：已有 {report.history_dates.length} 个来源日期，少 {report.missing_history_dates} 个；缺少的日期不补齐。</p>
        : <p className="subtle">已列出当天与此前五个来源日期。</p>}
    {report.days.map(day => <section className="geometry-details" key={day.source_date} aria-label={`${day.source_date} 同标签端点`}>
      <h4>{day.source_date} · {day.kind === 'current' ? '所选来源日期' : '历史来源日期'}</h4>
      <div className="exact-grid"><Endpoints rows={day.start} clock={report.start_clock} /><Endpoints rows={day.end} clock={report.end_clock} /></div>
      {day.reason ? <p className="inline-note amber">不可计算：{reasons[day.reason] ?? day.reason}</p> : <>
        <p>带符号端点价格变化（终点收盘 / 起点收盘 − 1）：<FractionValue value={day.change!} /></p>
        <p>端点价格变化幅度（绝对值）：<FractionValue value={day.magnitude!} absolute /></p>
      </>}
      {day.unknown_clock_ordinals.length > 0 && <p className="subtle">时钟无法定位的源序号：{day.unknown_clock_ordinals.join('、')}</p>}
    </section>)}
    <details><summary>来源与不确定性</summary>
      <p className="subtle">名义时钟差不证明连续交易时长、柱数或区间内部路径。未知时区、柱边界、交易阶段、闭合、复权基础与历史首次可得时点仍未知；同名标签不认证真实同一时段。以上为回顾性来源端点算术，不能认作波动率、成交收益或预测证据。</p>
      <p className="subtle">精确分数为权威值；近似显示独立保留八位小数，四舍六入五成双。未填补或平滑缺失值。</p>
      {report.unknown_date_ordinals.length > 0 && <p>日期无法读取的源序号：{report.unknown_date_ordinals.join('、')}</p>}
      <dl>
        <dt>数据版本</dt><dd><code>{report.snapshot_id}</code></dd>
        <dt>来源批次</dt><dd><code>{report.batch_id}</code></dd>
        <dt>原件 SHA-256</dt><dd><code>{report.raw_sha256}</code></dd>
        <dt>当前查询标识</dt><dd><code>{report.query_id}</code></dd>
        <dt>完整上下文查询标识</dt><dd><code>{report.context_query_id}</code></dd>
        <dt>本次记录标识</dt><dd><code>{report.history_id}</code></dd>
        <dt>固定截止标签</dt><dd><code>{report.as_of_label}</code></dd>
      </dl>
      <pre>{JSON.stringify({ versions: report.versions, metadata: report.metadata, contract: report.contract, batch_checks: report.batch_checks }, null, 2)}</pre>
    </details>
  </div>;
}
