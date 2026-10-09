import { useEffect, useRef, useState } from 'react';
import { checkedFetch, explain } from './api.ts';
import { assertGapReport } from './model.ts';
import type { GapEvent, GapReport, Query, Row } from './types.ts';

const reasons: Record<string, string> = { no_previous_source_bar: '没有前序可定位源柱',
  duplicate_label: '同一标签存在重复记录', previous_bar_unavailable: '前序源柱无法计算',
  missing_ohlc: 'OHLC缺失', invalid_price: '价格无效', negative_price: '存在负价格',
  invalid_ohlc: 'OHLC包含关系不成立', unlocated_label: '源标签无法定位',
  unsupported_period: '仅支持日线和1分钟', context_row_unavailable: '上下文没有对应源行' };
const states = { far_boundary_observed: '已见远端达到', near_boundary_observed: '已见近端达到；未见远端',
  observation_interrupted: '首次观察已中断', not_observed_before_asof: '截至终点未见近端达到' };

export function GapAnalysis({ query, selected, onChoose }: { query: Query; selected: Row | null; onChoose: (row: Row) => void }) {
  const [report, setReport] = useState<GapReport | null>(null);
  const [body, setBody] = useState('');
  const [issue, setIssue] = useState('');
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    setReport(null); setBody(''); setIssue(''); setLoading(false); setPage(0);
    return () => abort.current?.abort();
  }, [query]);

  async function read() {
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    setReport(null); setBody(''); setIssue(''); setLoading(true); setPage(0);
    const parameters = new URLSearchParams({ query_id: query.query_id, mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    try {
      const response = await checkedFetch(`/api/source-gaps/${query.snapshot_id}?${parameters}`, { signal: controller.signal });
      const text = await response.text();
      if (controller.signal.aborted) return;
      const value = JSON.parse(text) as GapReport;
      assertGapReport(query, value);
      setReport(value); setBody(text);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  const current = report?.query_id === query.query_id ? report : null;
  const origins = current?.rows.filter(row => row.gap) ?? [];
  const focus = selected ?? query.rows.at(-1);
  const value = focus && current ? [...current.rows, ...current.unlocated].find(row => row.ordinal === focus.ordinal) : null;
  function sourceLink(ordinal: number, label: string | null) {
    const row = query.rows.find(row => row.ordinal === ordinal);
    return row ? <button onClick={() => onChoose(row)}>{label} · 源序号{ordinal}</button>
      : <span>{label} · 上下文源序号{ordinal}</span>;
  }
  function eventCell(event: GapEvent | null) {
    return event ? <>{sourceLink(event.ordinal, event.label)}<p>源极值 <code>{event.extreme}</code>（{event.relation === 'equal' ? '等于' : '越过'}）</p>
      <p className="subtle">{event.range_relation === 'passed_without_overlap' ? '整柱跳过区间，无范围重叠' : event.contains_boundary ? '源价域包含该边界' : '源极值越过阈值，价域未包含边界'}</p></> : '未观察到';
  }
  function download() {
    if (!current || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `source-gaps-${current.gaps_id}.json`;
    link.click(); URL.revokeObjectURL(url);
  }
  return <section className="panel" aria-label="源K线缺口与边界观察">
    <h2>源 K 线缺口 · 边界观察</h2>
    <p className="subtle">整柱价域严格分离才形成正宽缺口；开盘相对前收盘差另列。仅分析所选记录的缺口形成，后续观察使用完整源上下文，止于所选最大标签与查询截止点。</p>
    <button className="primary" disabled={loading} onClick={() => void read()}>{loading ? '计算中…' : '分析当前窗口'}</button>
    <p className="inline-note amber">相邻可定位源柱与所见首次极值。价格尺度、复权可比性是假设，覆盖与闭合未知；边界达到不证明逐价成交，也不提供回补预测。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {current && <>
      <p>观察终点 {current.as_of_label ?? '无可定位记录'}；所选记录形成 {origins.length} 个正宽缺口，{current.rows.filter(row => row.reason).length + current.unlocated.length} 条记录未计算。</p>
      {current.coverage_reason && <p className="amber">上下文有 {current.context_unlocated_rows} 条无法定位记录；相邻关系与首次观察的完整覆盖未知。</p>}
      {value && <p>{focus?.label ?? '无法定位'} · 源序号{value.ordinal}：{value.reason ? reasons[value.reason] ?? value.reason : <>开盘相对前收盘差 <code>{value.open_close_change}</code>；{value.gap ? states[value.gap.state] : '未形成严格正宽价域缺口'}。前序标签 {value.previous_label}，源序号{value.previous_ordinals.join('、')}。</>}</p>}
      <div className="table-scroll"><table><thead><tr><th>形成记录／前序源柱</th><th>方向／精确源边界</th><th>所见首次近端达到</th><th>所见首次远端达到</th><th>截至终点状态</th></tr></thead>
        <tbody>{origins.slice(page * 100, (page + 1) * 100).map(row => {
          const gap = row.gap!;
          return <tr key={gap.gap_id}><td>{sourceLink(row.ordinal, row.label)}<p className="subtle">前序 {row.previous_label} · 源序号{row.previous_ordinals.join('、')}</p></td>
            <td>{gap.direction === 'up' ? '向上' : '向下'}<p><code>{gap.lower}</code>～<code>{gap.upper}</code></p><p>宽度 <code>{gap.width}</code></p></td>
            <td>{eventCell(gap.near_event)}</td><td>{eventCell(gap.far_event)}</td><td>{states[gap.state]}
              {gap.interrupted_at && <p className="amber">{gap.interrupted_at.label} · 源序号{gap.interrupted_at.ordinals.join('、')}：{reasons[gap.interrupted_at.reason] ?? gap.interrupted_at.reason}。尚未发生的首次观察不再续接。</p>}</td></tr>;
        })}</tbody></table></div>
      {!origins.length && <p className="subtle">当前所选记录未识别出正宽缺口；窗口外形成的缺口不在本表中。</p>}
      {origins.length > 100 && <div className="pagination"><button disabled={!page} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1}／{Math.ceil(origins.length / 100)}</span><button disabled={(page + 1) * 100 >= origins.length} onClick={() => setPage(page + 1)}>下一页</button></div>}
      <button onClick={download}>导出缺口与观察 JSON</button>
      <details><summary>观察范围与版本</summary><p>形成柱不参与后续观察。近远端可在同一源柱出现，先后与准确触及时刻未知。公司行动可能影响跨柱比较，可在公司行动区间工具另行核对。</p>
        <p>上下文 <code>{current.context_query_id}</code></p><p>分析版本 <code>{current.gaps_id}</code></p></details>
    </>}
  </section>;
}
