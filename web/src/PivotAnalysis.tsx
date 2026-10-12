import { useEffect, useRef, useState } from 'react';
import { checkedFetch } from './api.ts';
import { explainAnalysisError } from './analysis-errors.ts';
import { assertPivotReport } from './model.ts';
import type { PivotReport, Query, Row } from './types.ts';

const reasons: Record<string, string> = { history_insufficient: '左侧来源窗口不足', pending_right_window: '右侧来源窗口尚未齐备',
  duplicate_label: '来源标签有重复记录', missing_ohlc: 'OHLC缺失', invalid_price: '价格无效', negative_price: '存在负价格',
  invalid_ohlc: 'OHLC包含关系不成立', unlocated_label: '标签无法定位', unsupported_period: '仅支持日线和1分钟',
  context_row_unavailable: '上下文没有对应源行', not_high: '存在更高的源值', not_low: '存在更低的源值',
  tied_not_strict: '并列窗口极值，未选为严格极值' };

export function PivotAnalysis({ query, selected, onChoose, radius, onRadiusSelect, report, onReport }: {
  query: Query; selected: Row | null; onChoose: (row: Row) => void; radius: number;
  onRadiusSelect: (value: number) => void; report: PivotReport | null; onReport: (value: PivotReport | null) => void;
}) {
  const [body, setBody] = useState('');
  const [issue, setIssue] = useState('');
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    onReport(null); setBody(''); setIssue(''); setLoading(false); setPage(0);
    return () => abort.current?.abort();
  }, [query, radius, onReport]);

  async function read() {
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    onReport(null); setBody(''); setIssue(''); setLoading(true); setPage(0);
    const parameters = new URLSearchParams({ query_id: query.query_id, mode: query.selection.mode, radius: String(radius) });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    try {
      const response = await checkedFetch(`/api/source-pivots/${query.snapshot_id}?${parameters}`, { signal: controller.signal });
      const text = await response.text();
      if (controller.signal.aborted) return;
      const value = JSON.parse(text) as PivotReport;
      assertPivotReport(query, value, radius);
      onReport(value); setBody(text);
    } catch (error) { if (!controller.signal.aborted) setIssue(explainAnalysisError(error, 'current_version')); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  const current = report?.query_id === query.query_id && report.radius === radius ? report : null;
  const focus = selected ?? query.rows.at(-1);
  const value = current && focus ? [...current.rows, ...current.unlocated].find(row => row.ordinal === focus.ordinal) : null;
  const members = new Map(current?.members.map(member => [member.label, member]) ?? []);
  function sourceLink(ordinal: number, label: string) {
    const row = query.rows.find(row => row.ordinal === ordinal);
    return row ? <button onClick={() => onChoose(row)}>{label} · 源序号{ordinal}</button> : <span>{label} · 上下文源序号{ordinal}</span>;
  }
  function download() {
    if (!current || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `source-pivots-${current.pivots_id}.json`;
    link.click(); URL.revokeObjectURL(url);
  }
  return <section className="panel" aria-label="严格局部高低点与来源窗口确认">
    <div className="section-heading"><h2>局部高低点 · 来源窗确认</h2><label>左右每侧来源标签数<select value={radius} onChange={event => onRadiusSelect(Number(event.target.value))}>
      <option value={2}>2</option><option value={5}>5</option><option value={10}>10</option></select></label></div>
    <p className="subtle">中心高价严格大于、低价严格小于左右各N个源标签内的对应值；并列不选。图标位于右窗齐备的确认源柱，中心位置与确认位置分别记录。</p>
    <button className="primary" disabled={loading} onClick={() => void read()}>{loading ? '计算中…' : '计算当前窗口并标记确认柱'}</button>
    <p className="inline-note amber">来源窗口齐备仅是基于当前数据版本的回顾判断；闭合、当时可得及复权可比性未核。N个源标签不等同N个交易日／分钟，尚未验证去噪效果或预测价值。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {current && <>
      <p>截至 {current.as_of_label ?? '无可定位记录'}：所选中心形成 {current.events.filter(e => e.kind === 'high').length} 个严格高点、{current.events.filter(e => e.kind === 'low').length} 个严格低点；同中心可同时成立。</p>
      {current.coverage_reason && <p className="amber">上下文有 {current.context_unlocated_rows} 条无法定位记录，来源窗口的完整覆盖未知。</p>}
      {focus && value && <>
        <p><strong>{focus.label ?? '无法定位'} · 源序号{focus.ordinal}</strong>作为中心：{value.reason ? reasons[value.reason] ?? value.reason
          : <>高点 {value.high.is_pivot ? '成立' : reasons[value.high.reason!] ?? value.high.reason}；低点 {value.low.is_pivot ? '成立' : reasons[value.low.reason!] ?? value.low.reason}。来源窗齐于 {value.confirmation_label}。</>}</p>
        {current.events.filter(e => e.confirmation_ordinal === focus.ordinal).map(event => <p key={event.pivot_id}>在当前标签确认{event.kind === 'high' ? '高点' : '低点'}，极值中心为 {sourceLink(event.anchor_ordinal, event.anchor_label)}，源价 <code>{event.price}</code>。</p>)}
        <details><summary>当前中心的固定来源窗口（左{value.left_count}／右{value.right_count}）</summary>
          {value.window_labels.map(label => { const member = members.get(label); return <p key={label}>{label} · 源序号{member?.ordinals.join('、')} · 高 <code>{member?.high ?? '∅'}</code>／低 <code>{member?.low ?? '∅'}</code>{member?.reason && ` · ${reasons[member.reason] ?? member.reason}`}</p>; })}
        </details>
      </>}
      <div className="table-scroll"><table><thead><tr><th>中心记录</th><th>类型／精确源价</th><th>来源窗口确认记录</th><th>确认延迟</th></tr></thead>
        <tbody>{current.events.slice(page * 100, (page + 1) * 100).map(event => <tr key={event.pivot_id}>
          <td>{sourceLink(event.anchor_ordinal, event.anchor_label)}</td><td>{event.kind === 'high' ? '严格高点' : '严格低点'} · <code>{event.price}</code></td>
          <td>{sourceLink(event.confirmation_ordinal, event.confirmation_label)}</td><td>{event.delay_source_labels} 个来源标签</td></tr>)}</tbody></table></div>
      {!current.events.length && <p className="subtle">当前所选中心没有已经齐备且符合严格条件的极值；窗口不足与异常行仍保留在JSON中。</p>}
      {current.events.length > 100 && <div className="pagination"><button disabled={!page} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1}／{Math.ceil(current.events.length / 100)}</span><button disabled={(page + 1) * 100 >= current.events.length} onClick={() => setPage(page + 1)}>下一页</button></div>}
      <button onClick={download}>导出极值、确认和窗口 JSON</button>
      <details><summary>算法版本与范围</summary><p>局部点不强制交替，不连接柱内轨迹；同柱高低事件不代表先后。仅在固定数据版本和对应来源窗口内比较，来源修订后另存版本。</p>
        <p>上下文 <code>{current.context_query_id}</code></p><p>分析版本 <code>{current.pivots_id}</code></p></details>
    </>}
  </section>;
}
