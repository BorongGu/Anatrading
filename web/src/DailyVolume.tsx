import { useEffect, useState } from 'react';
import { jsonRequest } from './api.ts';
import { explainAnalysisError } from './analysis-errors.ts';
import { historicalVolumeMedian } from './volume-median.ts';
import type { DailyVolumeReport, Query, Row, VolumeFraction } from './types.ts';

const reasons: Record<string, string> = {
  history_insufficient: '历史来源日期不足', duplicate_date: '同一来源日期有重复记录',
  unlocated_label: '源标签无法定位', missing_quantity: '源数量缺失', invalid_quantity: '源数量无效',
  zero_baseline: '历史均量为零，比值未定义', unsupported_period: '仅适用于日线',
};

export function DailyVolume({ query, selected, lookback, onLookbackSelect }: {
  query: Query; selected: Row | null; lookback: number; onLookbackSelect: (value: number) => void;
}) {
  const [report, setReport] = useState<DailyVolumeReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    const parameters = new URLSearchParams({ lookback: String(lookback), mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    jsonRequest<DailyVolumeReport>(`/api/daily-volume/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.query_id !== query.query_id || result.lookback !== lookback
        || result.method_id !== 'prior-source-daily-volume-v1' || result.qualification !== 'conditional_source_values'
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
  const median = value && current && focus ? historicalVolumeMedian(value, { lookback: current.lookback,
    currentDate: focus.label, historyDates: value.history_dates, kind: 'daily' }) : null;
  function fraction(value: VolumeFraction | null) {
    return value && typeof value.display === 'string' && typeof value.numerator === 'string' && typeof value.denominator === 'string' ? <><code>≈{value.display}</code>（精确值 <code>{value.numerator}/{value.denominator}</code>）</> : <code>∅</code>;
  }
  return <section className="panel" aria-label="日线源数量与前序均量">
    <div className="section-heading"><h2>日线源数量 · 前序均量</h2><label>历史来源日期数<select value={lookback} onChange={event => onLookbackSelect(Number(event.target.value))}>
      <option value={20}>20日</option><option value={10}>10日</option><option value={55}>55日</option>
      {![10, 20, 55].includes(lookback) && <option value={lookback}>{lookback}日（筛选窗口）</option>}
    </select></label></div>
    <p className="inline-note amber">跨日数量尺度、股本口径可比性是假设；单位、日期覆盖、行情闭合和历史可得时点未知。当前数值可能尚未覆盖全天。</p>
    <p className="subtle">当前源数量除以前N个可读来源日期的均量，排除当前日期。异常日期不跳过、不补齐，零数量保留。</p>
    <p className="subtle">当前/均量的分母仍为均值，中位数供并列核对。</p>
    {lookback === 2 && <p className="subtle">2个历史值的中位数与均值相同。</p>}
    {issue ? <p className="error-banner">{issue}</p> : !current ? <p className="subtle">正在计算…</p> : <>
      {!!current.context_unlocated_rows && <p className="inline-note amber">上下文有 {current.context_unlocated_rows} 条无法定位记录，其中 {current.unreadable_date_rows} 条日期不可读；历史日期集合完整性未知。</p>}
      {value && focus ? <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号 {focus.ordinal}</strong>{!selected && '（最新所选记录）'}</p>
        <p>当前源数量 <code>{typeof value.current === 'string' ? value.current : '∅'}</code> · 前序均量 {fraction(value.baseline_mean)}</p>
        <p>历史中位数（源数量） <code>{median?.exact_text ?? '∅'}</code>{median?.status === 'available' && '（精确）'}{median?.status === 'invalid' && ' · 中位数摘要无法核对'}</p>
        <p>当前 / 前序均量 {fraction(value.ratio)}</p>
        {typeof value.reason === 'string' && <p className="amber">{Object.hasOwn(reasons, value.reason) ? reasons[value.reason] : value.reason}</p>}
        <details><summary>完整窗口与精确值</summary>
          {Array.isArray(value.members) && value.members.filter(member => member && typeof member.date === 'string').map((member, i) => <p key={`${member.date}:${i}`}>{member.date} · 源数量 <code>{typeof member.value === 'string' ? member.value : '∅'}</code>{typeof member.reason === 'string' && ` · ${Object.hasOwn(reasons, member.reason) ? reasons[member.reason] : member.reason}`}</p>)}
          <p>历史数量总和 <code>{typeof value.baseline_sum === 'string' ? value.baseline_sum : '∅'}</code></p>
          <p>历史上下文 <code>{current.context_query_id}</code></p><p>计算版本 <code>{current.volume_id}</code></p>
        </details>
      </> : <p className="subtle">当前选择没有记录。</p>}
    </>}
  </section>;
}
