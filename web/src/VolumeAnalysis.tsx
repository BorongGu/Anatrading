import { useEffect, useState } from 'react';
import { jsonRequest } from './api.ts';
import { explainAnalysisError } from './analysis-errors.ts';
import type { Query, Row, VolumeComparison, VolumeReport } from './types.ts';

const reasons: Record<string, string> = {
  history_insufficient: '历史来源日期不足', missing_slot: '所需时槽缺失', duplicate_slot: '所需时槽重复',
  missing_quantity: '源数量缺失', invalid_quantity: '源数量无效', zero_baseline: '历史均量为零，比值未定义',
  unlocated_label: '源标签无法定位', outside_observed_template: '超出观测时槽模板', unsupported_period: '仅适用于1分钟数据',
};

export function VolumeAnalysis({ query, selected }: { query: Query; selected: Row | null }) {
  const [lookback, setLookback] = useState(20);
  const [report, setReport] = useState<VolumeReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    const parameters = new URLSearchParams({ lookback: String(lookback) });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    jsonRequest<VolumeReport>(`/api/volume/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.query_id !== query.query_id || result.lookback !== lookback
        || result.method_id !== 'source-volume-at-time-v1' || result.qualification !== 'conditional_source_values'
        || !Array.isArray(result.rows) || !Array.isArray(result.unlocated)
        || result.rows.length !== query.rows.length || result.unlocated.length !== query.unlocated.length
        || result.rows.some((row, i) => row.ordinal !== query.rows[i].ordinal)
        || result.unlocated.some((row, i) => row.ordinal !== query.unlocated[i].ordinal)) throw new Error('invalid_query_response');
      setReport(result);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explainAnalysisError(error, 'current_version')); });
    return () => controller.abort();
  }, [query, lookback]);

  const current = report?.query_id === query.query_id && report.lookback === lookback ? report : null;
  const focus = selected ?? query.rows.at(-1);
  const value = current && focus ? [...current.rows, ...current.unlocated].find(row => row.ordinal === focus.ordinal) : null;
  return <section className="panel" aria-label="历史同刻源数量比较">
    <div className="section-heading"><h2>历史同刻源数量比较</h2><label>历史窗口 <select value={lookback} onChange={event => setLookback(Number(event.target.value))}>
      {[20, 10, 5, 2].map(n => <option value={n} key={n}>{n} 个来源日期</option>)}
    </select></label></div>
    <p className="inline-note amber">回顾已收到值；闭合、单位、覆盖和股份可比性未核。比值依赖历史数量尺度与股份基础可比，预测效力未检验。</p>
    <p className="subtle">按此前 {lookback} 个可读来源日期比较；缺值不补，可读的问题日期不跳。日历未知，日期不可读时历史日期集合完整性未知。累计仅覆盖观测模板 09:31–11:30、13:01–15:00 到当前标签的时槽。</p>
    {lookback === 2 && <p className="inline-note amber">2日为显式小样本比较，均值容易受单日影响。</p>}
    {issue ? <p className="error-banner">{issue}</p> : !current ? <p className="subtle">正在计算…</p> : <>
      <p className="subtle">本次选择：同槽比 {current.rows.filter(row => row.regular?.ratio).length} 条、累计比 {current.rows.filter(row => row.cumulative?.ratio).length} 条可计算。</p>
      {(current.excluded_unlocated_rows > 0 || current.outside_template_rows > 0) && <p className="inline-note amber">上下文中 {current.excluded_unlocated_rows} 条标签无法定位、{current.outside_template_rows} 条位于模板外，数量未纳入时槽求和；有可读日期的记录仍占历史日期窗口。</p>}
      {value && focus ? <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号 {focus.ordinal}</strong>{!selected && '（最新所选记录；点击K线可切换）'}</p>
        <p className="subtle">实际历史日期：{value.history_dates.join('、') || '无'}</p>
        {value.reason ? <p className="inline-note amber">{reasons[value.reason] ?? value.reason}</p> : <div className="exact-grid">
          <Comparison title="当日模板累计" value={value.cumulative!} />
          <Comparison title="本分钟同槽" value={value.regular!} />
        </div>}
      </> : <p className="subtle">当前选择没有记录。</p>}
    </>}
  </section>;
}

function Comparison({ title, value }: { title: string; value: VolumeComparison }) {
  return <div><h3>{title}</h3><p>当前源数量 <code>{value.current ?? '∅'}</code></p>
    <p>历史均量 <code>{value.baseline_mean ? `≈${value.baseline_mean.display}` : '∅'}</code></p>
    <p>相对均量 <code>{value.ratio ? `≈${value.ratio.display} 倍` : '∅'}</code></p>
    {value.reason && <p className="amber">{reasons[value.reason] ?? value.reason}</p>}
    <details><summary>历史成员与精确分数</summary>
      {value.members.map(member => <p key={member.date}>{member.date}：<code>{member.value ?? '∅'}</code>{member.reason && ` · ${reasons[member.reason] ?? member.reason}`}</p>)}
      {value.baseline_mean && <p>均量 <code>{value.baseline_mean.numerator}/{value.baseline_mean.denominator}</code></p>}
      {value.ratio && <p>比值 <code>{value.ratio.numerator}/{value.ratio.denominator}</code></p>}
      <p className="subtle">近似值独立舍入至4位小数，采用四舍六入五成双。</p>
    </details>
  </div>;
}
