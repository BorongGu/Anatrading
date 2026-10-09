import { useEffect, useState } from 'react';
import { explain, jsonRequest } from './api.ts';
import type { Query, RangeEstimate, RangeReport, Row } from './types.ts';

const reasons: Record<string, string> = {
  no_previous_date: '没有前序来源日期', history_insufficient: '初始化所需TR数量不足',
  invalid_history: '此前平滑历史含无效TR，后续ATR未自动重新初始化', duplicate_date: '来源日期重复',
  unlocated_label: '源标签无法定位', missing_hl: '高低值缺失', missing_close: '收盘缺失',
  invalid_price: '价格无效', negative_price: '存在负价格', invalid_hl: '最低值高于最高值',
  close_outside_range: '收盘与可用高低值矛盾', prior_atr_unavailable: '前序ATR尚未定义',
  zero_prior_atr: '前序ATR为零，比值未定义', prior_atr_not_positive: '前序ATR下界未大于零', unsupported_period: '仅适用于日线',
};
function reasonText(reason: string) {
  return reason.startsWith('previous_') ? `前序日期：${reasons[reason.slice(9)] ?? reason.slice(9)}` : reasons[reason] ?? reason;
}

export function VolatilityAnalysis({ query, selected, period, onPeriodSelect }: {
  query: Query; selected: Row | null; period: number; onPeriodSelect: (value: number) => void;
}) {
  const [report, setReport] = useState<RangeReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    const parameters = new URLSearchParams({ period: String(period), mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    jsonRequest<RangeReport>(`/api/true-range/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.query_id !== query.query_id || result.period !== period || result.method_id !== 'source-wilder-range-v1'
        || result.qualification !== 'conditional_source_values' || result.seed_policy !== 'first_period_subsequent_tr_mean'
        || !Array.isArray(result.rows) || !Array.isArray(result.unlocated)
        || result.rows.length !== query.rows.length || result.unlocated.length !== query.unlocated.length
        || result.rows.some((row, i) => row.ordinal !== query.rows[i].ordinal)
        || result.unlocated.some((row, i) => row.ordinal !== query.unlocated[i].ordinal)) throw new Error('invalid_query_response');
      setReport(result);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explain(error)); });
    return () => controller.abort();
  }, [query, period]);
  const current = report?.query_id === query.query_id && report.period === period ? report : null;
  const focus = selected ?? query.rows.at(-1);
  const value = current && focus ? [...current.rows, ...current.unlocated].find(row => row.ordinal === focus.ordinal) : null;
  return <section className="panel" aria-label="真实波幅与Wilder ATR">
    <div className="section-heading"><h2>真实波幅 · Wilder ATR</h2><label>平滑长度<select value={period} onChange={event => onPeriodSelect(Number(event.target.value))}>
      <option value={14}>14个来源日期</option><option value={7}>7个来源日期</option><option value={20}>20个来源日期</option>
    </select></label></div>
    <p className="inline-note amber">条件性源数值比较。价格尺度、跨日复权可比性是假设；日期覆盖、行情闭合和历史可得时点未知，尚无预测价值验证。</p>
    <p className="subtle">TR取高低差、最高与前收距离、最低与前收距离中的最大值。前收取前一个可读来源日期；首根TR为空，后续首N个TR均值初始化，再用Wilder递推。坏TR不跳过、不自动重新初始化。</p>
    {issue ? <p className="error-banner">{issue}</p> : !current ? <p className="subtle">正在计算…</p> : <>
      {!!current.context_unlocated_rows && <p className="inline-note amber">上下文有 {current.context_unlocated_rows} 条无法定位记录，其中 {current.unreadable_date_rows} 条日期不可读；相邻来源日期可能跨过缺失交易日。</p>}
      {value && focus ? <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号 {focus.ordinal}</strong>{!selected && '（最新所选记录）'}</p>
        <p>TR 精确值 <code>{value.tr ?? '∅'}</code>{value.tr_reason && ` · ${reasonText(value.tr_reason)}`}</p>
        <div className="exact-grid"><Estimate title="Wilder ATR" value={value.atr} reason={value.atr_reason} />
          <Estimate title="前序 ATR" value={value.prior_atr} reason={null} />
          <Estimate title="TR / 前序 ATR" value={value.tr_over_prior_atr} reason={value.ratio_reason} /></div>
        {value.atr_blocked_date && <p className="amber">平滑历史从 {value.atr_blocked_date} 的无效TR起中断。</p>}
        <details><summary>TR组成、初始化与计算版本</summary>
          <p>前序来源日期 {value.previous_date ?? '∅'} · 源序号 {value.previous_ordinals.join('、') || '∅'}</p>
          <p>高低差 <code>{value.components.high_low ?? '∅'}</code> · 高与前收距离 <code>{value.components.high_previous_close ?? '∅'}</code> · 低与前收距离 <code>{value.components.low_previous_close ?? '∅'}</code></p>
          <p>初始化参照来源日期 {current.seed_previous_date ?? '∅'}；参与TR均值的日期：{current.seed_dates.join('、') || '无'}。</p>
          <p>平滑：[(N−1)×前序ATR + 当前TR] / N；相对波幅的分母排除当前日期。</p>
          <p>历史上下文 <code>{current.context_query_id}</code></p><p>计算版本 <code>{current.range_id}</code></p>
        </details>
      </> : <p className="subtle">当前选择没有记录。</p>}
    </>}
  </section>;
}

function Estimate({ title, value, reason }: { title: string; value: RangeEstimate | null; reason: string | null }) {
  return <div><h3>{title}</h3><p><code>{value ? value.display === null ? '显示舍入不确定' : `≈${value.display}` : '∅'}</code></p>
    {reason && <p className="amber">{reasonText(reason)}</p>}
    {value && <details><summary>近似值与数值界</summary><p>近似值 <code>{value.value}</code></p>
      <p>下界 <code>{value.lower}</code></p><p>上界 <code>{value.upper}</code></p>
      <p className="subtle">64位有效数字，逐步向外舍入。上下界仅约束计算误差；不表示未来风险区间。两端舍入一致时才显示4位小数。</p></details>}
  </div>;
}
