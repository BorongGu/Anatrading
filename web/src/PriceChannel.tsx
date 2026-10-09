import { useEffect, useState } from 'react';
import { explain, jsonRequest } from './api.ts';
import type { ChannelReport, Query, Row } from './types.ts';

const reasons: Record<string, string> = {
  history_insufficient: '历史来源日期不足', duplicate_date: '同一来源日期有重复记录',
  unlocated_label: '源标签无法定位', missing_ohlc: 'OHLC缺失', invalid_price: '价格无效',
  negative_price: '存在负价格', invalid_ohlc: 'OHLC包含关系不成立', unsupported_period: '仅适用于日线',
};
const ranges = { both: '上下两侧均越界（先后顺序未知）', upper_only: '最高值越过上界', lower_only: '最低值越过下界', neither: '高低值均未越界' };
const closes = { above: '源收盘高于上界', below: '源收盘低于下界', touch_upper: '源收盘等于上界',
  touch_lower: '源收盘等于下界', touch_both: '源收盘等于重合的上下界', inside: '源收盘位于区间内' };

export function PriceChannel({ query, selected, lookback, onLookbackSelect }: {
  query: Query; selected: Row | null; lookback: number; onLookbackSelect: (value: number) => void;
}) {
  const [report, setReport] = useState<ChannelReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    const parameters = new URLSearchParams({ lookback: String(lookback), mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    jsonRequest<ChannelReport>(`/api/price-channel/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.query_id !== query.query_id || result.lookback !== lookback
        || result.method_id !== 'prior-source-price-channel-v1' || result.qualification !== 'conditional_source_values'
        || !Array.isArray(result.rows) || !Array.isArray(result.unlocated)
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
  return <section className="panel" aria-label="前序日线价格区间">
    <div className="section-heading"><h2>前序日线价格区间</h2><label>历史来源日期数<select value={lookback} onChange={event => onLookbackSelect(Number(event.target.value))}>
      <option value={20}>20日</option><option value={55}>55日</option><option value={10}>10日</option>
    </select></label></div>
    <p className="inline-note amber">条件性源数值比较。跨日价格尺度、复权可比性是假设；日历、覆盖、闭合和历史可得时点未知，尚无预测价值验证。</p>
    <p className="subtle">上界为此前N个可读来源日期的最高值，下界为最低值，排除当前日期。窗口从完整截止历史取得，异常日期不跳过、不补齐；等于边界只计触碰。</p>
    {issue ? <p className="error-banner">{issue}</p> : !current ? <p className="subtle">正在计算…</p> : <>
      {(current.unreadable_date_rows > 0 || current.context_unlocated_rows > 0) && <p className="inline-note amber">上下文有 {current.context_unlocated_rows} 条无法定位记录，其中 {current.unreadable_date_rows} 条日期不可读，历史日期集合完整性未知。</p>}
      {value && focus ? <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号 {focus.ordinal}</strong>{!selected && '（最新所选记录；点击K线可切换）'}</p>
        {value.reason ? <p className="amber">{reasons[value.reason] ?? value.reason}</p> : <>
          <div className="exact-grid"><p>上界 <code>{value.upper}</code></p><p>下界 <code>{value.lower}</code></p><p>区间宽度 <code>{value.width}</code></p></div>
          {value.comparison_reason ? <p className="amber">当前记录比较未定义：{reasons[value.comparison_reason] ?? value.comparison_reason}</p> : <>
            <p>{value.range_relation && ranges[value.range_relation]}；{value.close_relation && closes[value.close_relation]}。</p>
            {(value.touch_upper || value.touch_lower) && <p className="subtle">{value.touch_upper && '最高值触碰上界。'}{value.touch_lower && '最低值触碰下界。'}</p>}
          </>}
        </>}
        <details><summary>完整窗口成员与计算版本</summary>
          {value.members.map(member => <p key={member.date}>{member.date} · 源序号 {member.ordinals.join('、')} · 高 <code>{member.high ?? '∅'}</code> / 低 <code>{member.low ?? '∅'}</code>{member.reason && ` · ${reasons[member.reason] ?? member.reason}`}</p>)}
          <p>历史上下文 <code>{current.context_query_id}</code></p><p>分析版本 <code>{current.channel_id}</code></p>
        </details>
      </> : <p className="subtle">当前选择没有记录。</p>}
    </>}
  </section>;
}
