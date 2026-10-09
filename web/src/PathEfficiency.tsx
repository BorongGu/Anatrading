import { useEffect, useState } from 'react';
import { explain, jsonRequest } from './api.ts';
import type { EfficiencyReport, Query, Row } from './types.ts';

const reasons: Record<string, string> = {
  history_insufficient: '需要N+1个来源日期的收盘', duplicate_date: '来源日期重复', unlocated_label: '源标签无法定位',
  missing_close: '源收盘缺失', invalid_price: '源价格无效', negative_price: '存在负源价格',
  close_outside_range: '源收盘与有效高低区间矛盾', unsupported_period: '仅适用于日线',
  zero_path_convention: '平坦路径：没有收盘变化，效率按约定记0',
};
const directions = { up: '净上行', down: '净下行', flat: '净位移为零' };

export function PathEfficiency({ query, selected, lookback, onLookbackSelect }: {
  query: Query; selected: Row | null; lookback: number; onLookbackSelect: (value: number) => void;
}) {
  const [report, setReport] = useState<EfficiencyReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    const parameters = new URLSearchParams({ lookback: String(lookback), mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    jsonRequest<EfficiencyReport>(`/api/path-efficiency/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.query_id !== query.query_id || result.lookback !== lookback
        || result.method_id !== 'source-close-path-efficiency-v1' || result.qualification !== 'conditional_source_values'
        || result.flat_policy !== 'zero_with_explicit_reason' || !Array.isArray(result.rows) || !Array.isArray(result.unlocated)
        || result.rows.length !== query.rows.length || result.unlocated.length !== query.unlocated.length
        || result.rows.some((row, i) => row.ordinal !== query.rows[i].ordinal)
        || result.unlocated.some((row, i) => row.ordinal !== query.unlocated[i].ordinal)) throw new Error('invalid_query_response');
      setReport(result);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explain(error)); });
    return () => controller.abort();
  }, [query, lookback]);
  const current = report?.query_id === query.query_id && report.lookback === lookback ? report : null;
  const focus = selected ?? query.rows.at(-1);
  const value = current && focus ? [...current.rows, ...current.unlocated].find(row => row.ordinal === focus.ordinal) : null;
  return <section className="panel" aria-label="收盘路径效率">
    <div className="section-heading"><h2>收盘路径效率 · ER</h2><label>来源日期间变化数<select value={lookback} onChange={event => onLookbackSelect(Number(event.target.value))}>
      <option value={10}>10次变化</option><option value={20}>20次变化</option><option value={55}>55次变化</option>
      {![10, 20, 55].includes(lookback) && <option value={lookback}>{lookback}次变化（筛选窗口）</option>}
    </select></label></div>
    <p className="subtle">净位移绝对值 / 累计收盘涨跌路径。接近1表示所采样收盘较少折返；接近0表示位移抵消较多。只描述收盘序列，不识别盘中路径或无信息量噪声。</p>
    <p className="inline-note amber">跨日尺度、复权可比性是假设；日期覆盖、行情闭合与历史可得时点未知，预测价值尚未验证。</p>
    {issue ? <p className="error-banner">{issue}</p> : !current ? <p className="subtle">正在计算…</p> : <>
      {!!current.context_unlocated_rows && <p className="inline-note amber">上下文有 {current.context_unlocated_rows} 条无法定位记录，其中 {current.unreadable_date_rows} 条日期不可读；日期集合完整性未知。</p>}
      {value && focus ? <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号 {focus.ordinal}</strong>{!selected && '（最新所选记录）'}</p>
        <p>效率 <code>{value.efficiency ? `≈${value.efficiency.display}` : '∅'}</code>{value.direction && ` · ${directions[value.direction]}`}</p>
        <p>源数值净位移 <code>{value.net_change ?? '∅'}</code> · 累计路径 <code>{value.path_length ?? '∅'}</code></p>
        {value.reason && <p className="amber">{reasons[value.reason] ?? value.reason}</p>}
        <details><summary>收盘窗口与精确分数</summary>
          {value.efficiency && <p>精确效率 <code>{value.efficiency.numerator}/{value.efficiency.denominator}</code></p>}
          {value.members.map(member => <p key={member.date}>{member.date} · 源序号 {member.ordinals.join('、')} · 源收盘 <code>{member.close ?? '∅'}</code>{member.reason && ` · ${reasons[member.reason] ?? member.reason}`}</p>)}
          <p>N次变化包含当前及前N个可读来源日期的收盘；异常日期不跳过、不补齐。</p>
          <p>历史上下文 <code>{current.context_query_id}</code></p><p>计算版本 <code>{current.efficiency_id}</code></p>
        </details>
      </> : <p className="subtle">当前选择没有记录。</p>}
    </>}
  </section>;
}
