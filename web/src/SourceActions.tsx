import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { checkedFetch, explain, jsonRequest } from './api.ts';
import type { ActionCapture, ActionWindow, Query, Row } from './types.ts';

const fields = ['Bonus', 'AllotPrice', 'ShareBonus', 'Allotment'] as const;
const links: Record<string, string> = { outside_query_cutoff: '晚于当前查询截止日期',
  not_returned_by_query: '当前查询未返回同日记录', duplicate_query_date: '当前查询有同日重复记录',
  unlocated_query_label: '对应源标签无法定位' };

export function SourceActions({ query, onChoose }: { query: Query; onChoose: (row: Row) => void }) {
  const [captures, setCaptures] = useState<ActionCapture[]>([]);
  const [captureId, setCaptureId] = useState('');
  const [start, setStart] = useState(query.rows.at(0)?.label?.slice(0, 10) ?? '');
  const [end, setEnd] = useState(query.rows.at(-1)?.label?.slice(0, 10) ?? '');
  const [report, setReport] = useState<ActionWindow | null>(null);
  const [body, setBody] = useState('');
  const [issue, setIssue] = useState('');
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const listing = useRef<AbortController | null>(null);

  async function refresh() {
    listing.current?.abort();
    const controller = new AbortController(); listing.current = controller;
    try {
      const result = await jsonRequest<{ captures: ActionCapture[] }>('/api/action-captures', { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.captures)) throw new Error('invalid_response');
      setCaptures(result.captures);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
  }
  useEffect(() => { void refresh(); return () => { listing.current?.abort(); abort.current?.abort(); }; }, []);
  useEffect(() => {
    abort.current?.abort(); setReport(null); setBody(''); setLoading(false); setIssue(''); setPage(0);
  }, [query.query_id, captureId, start, end]);

  async function read(event: FormEvent) {
    event.preventDefault(); if (!captureId || loading || !start || end <= start) return;
    const controller = new AbortController(); abort.current = controller;
    setReport(null); setBody(''); setIssue(''); setLoading(true); setPage(0);
    const parameters = new URLSearchParams({ capture_id: captureId, query_id: query.query_id, start, end, mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    try {
      const response = await checkedFetch(`/api/action-window/${query.snapshot_id}?${parameters}`, { signal: controller.signal });
      const text = await response.text();
      if (controller.signal.aborted) return;
      const value = JSON.parse(text) as ActionWindow;
      const ordinals = new Set([...query.rows, ...query.unlocated].map(row => row.ordinal));
      if (value.method_id !== 'source-action-window-v1' || value.query_id !== query.query_id || value.capture_id !== captureId
        || value.start_exclusive !== start || value.end_inclusive !== end || value.qualification !== 'retrospective_source_records'
        || value.coverage !== 'unverified' || value.historical_available_at !== null || !Array.isArray(value.rows)
        || value.rows.some(row => row.date <= start || row.date > end || !Array.isArray(row.query_ordinals)
          || row.query_ordinals.some(ordinal => !ordinals.has(ordinal)))) throw new Error('invalid_query_response');
      setReport(value); setBody(text);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }

  const current = report?.query_id === query.query_id && report.capture_id === captureId
    && report.start_exclusive === start && report.end_inclusive === end ? report : null;
  function download() {
    if (!current || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `action-window-${current.action_window_id}.json`;
    link.click(); URL.revokeObjectURL(url);
  }
  return <section className="panel" aria-label="公司行动源记录区间标记">
    <h2>公司行动 · 源记录区间标记</h2>
    <p className="subtle">先在下方“原始日历 · 公司行动”读取所需证券，再刷新原件列表。选择已保存原件及两日期，查看起点之后、终点当日及以前返回的源记录。</p>
    <button className="quiet" onClick={() => void refresh()}>刷新原件列表</button>
    <form onSubmit={read}><div className="exact-grid">
      <label>已保存权息原件<select value={captureId} disabled={loading} onChange={event => setCaptureId(event.target.value)}>
        <option value="">请选择对应证券原件</option>
        {captures.map(item => <option key={item.capture_id} value={item.capture_id} disabled={item.status !== 'received'}>
          {item.target ?? '原件不可用'} · {item.captured_at ?? item.error_code} · {item.capture_id.slice(0, 8)}
        </option>)}
      </select></label>
      <label>起点日期（排除）<input type="date" value={start} required disabled={loading} onChange={event => setStart(event.target.value)} /></label>
      <label>终点日期（包含）<input type="date" value={end} min={start} required disabled={loading} onChange={event => setEnd(event.target.value)} /></label>
    </div><button className="primary" disabled={loading || !captureId || !start || end <= start}>{loading ? '关联原始记录中…' : '查看区间源记录'}</button></form>
    <p className="inline-note amber">事后原件回顾；完整性、单位及历史可得时点未核。Type11/15的经济含义和日期解释仍未验证。标记不会调整价量或计算总回报。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {current && <>
      <p>原回应返回 {current.returned_count} 条；本区间选出 {current.selected_count} 条源记录，同日额外记录 {current.duplicate_selected_date_rows} 条。</p>
      {current.request_range_status === 'range_not_requested' && <p className="amber">该区间超出原采集请求 {current.capture_selection.start}～{current.capture_selection.end}；仅展示原件中找到的记录，覆盖未知。</p>}
      {!!current.unreadable_query_date_ordinals.length && <p className="amber">日线日期归属未知的源序号：{current.unreadable_query_date_ordinals.join('、')}。</p>}
      {!current.rows.length && <p className="subtle">该响应未返回区间记录，不能据此确认没有公司行动。</p>}
      <div className="table-scroll"><table><thead><tr><th>权息源序号</th><th>源日期／类型</th>{fields.map(field => <th key={field}>源{field}</th>)}<th>当前日线记录</th></tr></thead>
        <tbody>{current.rows.slice(page * 100, (page + 1) * 100).map(row => <tr key={row.ordinal}><td>{row.ordinal}</td>
          <td>{row.date} · Type{row.source_type} · {row.type_name ?? '未释义'}</td>{fields.map(field => <td key={field}><code>{row.values?.[field] ?? '∅'}</code></td>)}
          <td>{row.query_ordinals.map(ordinal => <button key={ordinal} onClick={() => {
            const source = [...query.rows, ...query.unlocated].find(item => item.ordinal === ordinal);
            if (source) onChoose(source);
          }}>查看源序号{ordinal}</button>)}{row.link_reason && <p className="subtle">{links[row.link_reason] ?? row.link_reason}</p>}</td>
        </tr>)}</tbody></table></div>
      {current.rows.length > 100 && <div className="pagination"><button disabled={!page} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1}／{Math.ceil(current.rows.length / 100)}</span><button disabled={(page + 1) * 100 >= current.rows.length} onClick={() => setPage(page + 1)}>下一页</button></div>}
      <button onClick={download}>导出源记录与关联 JSON</button>
      <details><summary>固定原件与窗口身份</summary><p>采集时间 {current.captured_at}；请求证券声明 {current.target}。</p>
        <p>回应 SHA-256 <code>{current.response_sha256}</code></p><p>窗口版本 <code>{current.action_window_id}</code></p></details>
    </>}
  </section>;
}
