import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, createChartEx } from 'lightweight-charts';
import type { IChartApiBase } from 'lightweight-charts';
import { checkedFetch, explain } from './api.ts';
import { assertAggregationReport, buildAggregationPlot } from './model.ts';
import { SequenceAxis } from './sequence-axis.ts';
import { fields, fieldNames } from './types.ts';
import type { AggregateBucket, AggregationReport, Query, Row } from './types.ts';

const reasons: Record<string, string> = { not_in_selected_records: '期待标签未在所选记录中', right_labels_not_observed: '右端标签尚未观察到',
  duplicate_label: '重复标签', unlocated_membership_unknown: '无法定位记录使成员覆盖未知', missing_field: '字段缺失', invalid_field: '字段无效',
  no_members: '没有成员', missing_ohlc: 'OHLC缺失', invalid_price: '价格无效', negative_price: '负价格', invalid_ohlc: 'OHLC边界无效',
  unlocated_label: '标签无法定位', outside_observed_template: '模板以外的标签', outside_asof: '截止范围之外', outside_asof_date: '截止日期之后', unsupported_period: '仅支持1分钟' };

function AggregateChart({ report, onChoose }: { report: AggregationReport; onChoose: (bucket: AggregateBucket) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [issue, setIssue] = useState('');
  const plot = useMemo(() => buildAggregationPlot(report), [report]);
  useEffect(() => {
    if (!host.current || !plot.buckets.length) return;
    setIssue('');
    let chart: IChartApiBase<number> | null = null;
    try {
      chart = createChartEx(host.current, new SequenceAxis(plot.labels), {
        autoSize: true, layout: { background: { type: ColorType.Solid, color: '#fffdf8' }, textColor: '#6b6656', attributionLogo: true },
        crosshair: { mode: CrosshairMode.Normal },
        timeScale: { ignoreWhitespaceIndices: false, enableConflation: false, precomputeConflationOnInit: false, tickMarkMaxCharacterLength: 20 },
      });
      const candles = chart.addSeries(CandlestickSeries, { lastValueVisible: false, priceLineVisible: false }, 0);
      const volume = chart.addSeries(HistogramSeries, { lastValueVisible: false, priceLineVisible: false, priceFormat: { type: 'volume' } }, 1);
      candles.setData(plot.candles); volume.setData(plot.volumes);
      chart.panes()[1].setHeight(100);
      chart.subscribeClick(event => { if (event.time !== undefined && plot.buckets[event.time]) onChoose(plot.buckets[event.time]); });
      chart.timeScale().fitContent();
    } catch { chart?.remove(); chart = null; setIssue('聚合图无法绘制，精确表格仍可核对。'); }
    return () => chart?.remove();
  }, [plot, onChoose]);
  return <>{issue && <p className="error-banner">{issue}</p>}
    {plot.buckets.length ? <div ref={host} className="chart-host" aria-label="分钟来源聚合图" /> : <p>当前观察尚未到达任何桶的名义右端；部分桶见下表。</p>}
    <p className="subtle">按桶顺序等距，午休不占位；横轴不表示连续自然时间。图仅定位到已观察到的名义右端；未齐备或无效OHLC留空，数量按自身资格绘制。点击桶查看精确字段和源成员，坐标为近似显示。</p></>;
}

export function AggregationDetails({ query, report, selected, onChoose }: {
  query: Query; report: AggregationReport; selected: Row | null; onChoose: (row: Row) => void;
}) {
  const [choice, setChoice] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  useEffect(() => { setChoice(null); }, [selected]);
  const chooseBucket = useCallback((bucket: AggregateBucket) => {
    setChoice(bucket.bucket_id);
    const ordinal = bucket.members.at(-1)?.ordinal;
    const source = query.rows.find(row => row.ordinal === ordinal);
    if (source) onChoose(source);
  }, [query, onChoose]);
  const focus = report.buckets.find(bucket => bucket.bucket_id === choice)
    ?? report.buckets.find(bucket => bucket.members.some(member => member.ordinal === selected?.ordinal)) ?? report.buckets.at(-1);
  function sourceLink(member: { ordinal: number; label: string }) {
    const source = query.rows.find(row => row.ordinal === member.ordinal);
    return source ? <button key={member.ordinal} onClick={() => onChoose(source)}>{member.label} · 源序号{member.ordinal}</button> : null;
  }
  return <>
    <p>{report.target_minutes}分钟 · {report.buckets.length}桶 · 模板成员齐备 {report.buckets.filter(bucket => bucket.template_complete).length}桶 · 截至 {report.as_of_label ?? '无可定位记录'}</p>
    <AggregateChart report={report} onChoose={chooseBucket} />
    <div className="table-scroll"><table><thead><tr><th>模板标签范围</th><th>成员／状态</th>{fields.map(field => <th key={field}>{fieldNames[field]}（齐备值）</th>)}</tr></thead>
      <tbody>{report.buckets.slice(page * 100, (page + 1) * 100).map(bucket => <tr key={bucket.bucket_id}>
        <td><button onClick={() => chooseBucket(bucket)}>{bucket.first_label}～{bucket.end_label}</button></td>
        <td>{bucket.members.length}／{report.target_minutes} · {bucket.membership_reason ? reasons[bucket.membership_reason] ?? bucket.membership_reason : '模板成员齐备'}</td>
        {fields.map(field => <td key={field}><code>{bucket.values[field] ?? '∅'}</code></td>)}</tr>)}</tbody></table></div>
    {report.buckets.length > 100 && <div className="pagination"><button disabled={!page} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1}／{Math.ceil(report.buckets.length / 100)}</span><button disabled={(page + 1) * 100 >= report.buckets.length} onClick={() => setPage(page + 1)}>下一页</button></div>}
    {focus && <details open><summary>桶 {focus.first_label}～{focus.end_label} · 已观察到 {focus.last_observed_label ?? '没有成员'}</summary>
      <p>{focus.template_complete ? '期待成员齐备；交易闭合仍未核。' : reasons[focus.membership_reason!] ?? focus.membership_reason}</p>
      <p>所选已定位成员的部分描述（不补缺槽）：{fields.map(field => <span key={field}>{fieldNames[field]} <code>{focus.observed_values[field] ?? '∅'}</code>　</span>)}</p>
      {Object.entries(focus.observed_reasons).filter(([, reason]) => reason).map(([field, reason]) => <p key={field}>{field === 'ohlc' ? 'OHLC' : field === 'volume' ? '源数量' : '源金额'}：{reasons[reason!] ?? reason}</p>)}
      {focus.missing_labels.length > 0 && <p>未在所选成员中：{focus.missing_labels.join('、')}</p>}
      {focus.future_labels.length > 0 && <p>名义未来标签：{focus.future_labels.join('、')}</p>}
      {focus.duplicate_labels.length > 0 && <p>重复：{focus.duplicate_labels.join('、')}</p>}
      <div className="pagination">{focus.members.map(sourceLink)}</div>
    </details>}
    {report.excluded.length > 0 && <details><summary>单独保留的 {report.excluded.length} 条记录</summary>{report.excluded.map(row => <p key={row.ordinal}>源序号{row.ordinal} · {row.label ?? '无法定位'} · {reasons[row.reason] ?? row.reason}</p>)}</details>}
  </>;
}

export function MinuteAggregation({ query, selected, onChoose }: { query: Query; selected: Row | null; onChoose: (row: Row) => void }) {
  const [minutes, setMinutes] = useState(5);
  const [report, setReport] = useState<AggregationReport | null>(null);
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [issue, setIssue] = useState('');
  const abort = useRef<AbortController | null>(null);
  useEffect(() => { setReport(null); setBody(''); setIssue(''); setLoading(false); return () => abort.current?.abort(); }, [query, minutes]);
  async function read() {
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    setReport(null); setBody(''); setIssue(''); setLoading(true);
    const parameters = new URLSearchParams({ query_id: query.query_id, target_minutes: String(minutes), mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    try {
      const response = await checkedFetch(`/api/minute-aggregation/${query.snapshot_id}?${parameters}`, { signal: controller.signal });
      const text = await response.text();
      if (controller.signal.aborted) return;
      const value = JSON.parse(text) as AggregationReport;
      assertAggregationReport(query, value, minutes); setReport(value); setBody(text);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  const current = report?.query_id === query.query_id && report.target_minutes === minutes ? report : null;
  function download() {
    if (!current || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `minute-aggregation-${current.aggregation_id}.json`;
    link.click(); URL.revokeObjectURL(url);
  }
  return <section className="panel" aria-label="分钟周期聚合与原始成员对照">
    <div className="section-heading"><h2>分钟聚合 · 来源对照</h2><label>目标周期<select value={minutes} onChange={event => setMinutes(Number(event.target.value))}>{[5, 15, 30, 60].map(value => <option key={value} value={value}>{value}分钟</option>)}</select></label></div>
    <p className="subtle">按09:31～11:30、13:01～15:00来源时钟模板分别聚合，只使用当前所选记录。裁剪不重锚，缺槽不填补，午休不拼接。</p>
    <button className="primary" disabled={loading} onClick={() => void read()}>{loading ? '聚合中…' : '聚合当前分钟窗口'}</button>
    <p className="inline-note amber">模板成员齐备不证明交易覆盖、实时闭合或当时可得。量额保持源口径；供应商高周期一致性、去噪效果与预测价值尚未核验。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {current && <><AggregationDetails key={current.aggregation_id} query={query} report={current} selected={selected} onChoose={onChoose} /><button onClick={download}>导出聚合值与全部成员 JSON</button></>}
  </section>;
}
