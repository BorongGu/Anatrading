import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { explain, jsonRequest } from './api.ts';
import type { Config, ReferenceReport } from './types.ts';

const fields = ['Bonus', 'AllotPrice', 'ShareBonus', 'Allotment'] as const;

export function ReferenceData({ config }: { config: Config | null }) {
  const today = new Date();
  const todayLabel = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const [kind, setKind] = useState<'calendar' | 'actions'>('calendar');
  const [code, setCode] = useState('600059');
  const [market, setMarket] = useState('SH');
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(todayLabel);
  const [report, setReport] = useState<ReferenceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [issue, setIssue] = useState('');
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function read(event: FormEvent) {
    event.preventDefault();
    if (!config || loading) return;
    const controller = new AbortController();
    abort.current = controller;
    setReport(null); setIssue(''); setLoading(true); setPage(0);
    const target = kind === 'calendar' ? 'SH' : `${code}.${market}`;
    const parameters = new URLSearchParams({ kind, target, start, end });
    try {
      const result = await jsonRequest<{ reference: ReferenceReport }>(`/api/read-tdx-reference?${parameters}`, {
        method: 'POST', headers: { 'X-Anatrading-Token': config.csrf_token }, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      const value = result.reference;
      if (value.method_id !== 'tdx-reference-view-v1' || value.kind !== kind || value.target !== target
        || value.selection.start !== start || value.selection.end !== end
        || value.qualification !== 'unverified_source_reference' || !Array.isArray(value.rows)) throw new Error('invalid_response');
      setReport(value);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }

  return <section className="panel detail-panel" aria-label="原始日历与公司行动">
    <h2>原始日历 · 公司行动</h2>
    <form onSubmit={read}>
      <div className="exact-grid">
        <label>参考数据<select value={kind} disabled={loading} onChange={event => { setKind(event.target.value as 'calendar' | 'actions'); setReport(null); }}>
          <option value="calendar">A股日期列表 · SH来源</option><option value="actions">除权除息／股本调整</option>
        </select></label>
        {kind === 'actions' && <><label>证券代码<input value={code} pattern="[0-9]{6}" required disabled={loading} onChange={event => { setCode(event.target.value); setReport(null); }} /></label>
          <label>市场<select value={market} disabled={loading} onChange={event => { setMarket(event.target.value); setReport(null); }}><option>SH</option><option>SZ</option><option>BJ</option></select></label></>}
        <label>开始日期<input type="date" value={start} required disabled={loading} onChange={event => { setStart(event.target.value); setReport(null); }} /></label>
        <label>结束日期<input type="date" value={end} min={start} required disabled={loading} onChange={event => { setEnd(event.target.value); setReport(null); }} /></label>
      </div>
      <button className="primary" disabled={!config || loading}>{loading ? '读取中…' : '从通达信读取参考数据'}</button>
    </form>
    <p className="subtle">{kind === 'calendar' ? '依赖客户端已下载的上证指数999999日线；返回日期缺失不能据此判断休市或个股停牌。' : '保留原始数值字符串；Type1除权除息、11扩缩股、15重新调整。同日多事件保留，单位未核，不计算复权。'}</p>
    {issue && <p className="error-banner">{issue}</p>}
    {report && <>
      <p>来源返回 {report.returned_count} 条 · 本工具按闭区间 {report.selection.start}～{report.selection.end} 选出 {report.selected_count} 条；区间前 {report.before_start} 条、区间后 {report.after_end} 条保留在原始回应中。</p>
      <p className="inline-note amber">这是本次来源记录；完整性与历史可得时点未核。采集时间不代表公告时间或历史首次可用时间。</p>
      {!!report.duplicate_date_rows && <p className="subtle">原数组含 {report.duplicate_date_rows} 条同日额外记录，未合并。</p>}
      <div className="table-scroll"><table><thead><tr><th>源序号</th><th>源日期</th>{report.kind === 'actions' && <><th>源Type</th>{fields.map(field => <th key={field}>源{field}</th>)}</>}</tr></thead>
        <tbody>{report.rows.slice(page * 100, (page + 1) * 100).map(row => <tr key={row.ordinal}><td>{row.ordinal}</td><td>{row.date}</td>
          {report.kind === 'actions' && <><td>{row.source_type} · {row.type_name ?? '未释义'}</td>{fields.map(field => <td key={field}><code>{row.values?.[field] ?? '∅'}</code></td>)}</>}</tr>)}</tbody></table></div>
      {!report.rows.length && <p className="subtle">所选区间未返回记录；不能据此断言没有公司行动或交易日。</p>}
      {report.empty_shape === 'value_only_empty' && <p className="subtle">原始回应仅有空Value，没有Date字段；未生成日期记录。</p>}
      {report.rows.length > 100 && <div className="pagination"><button disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><span>第 {page + 1}／{Math.ceil(report.rows.length / 100)} 页</span><button disabled={(page + 1) * 100 >= report.rows.length} onClick={() => setPage(page + 1)}>下一页</button></div>}
      <details><summary>本次来源与原始回应哈希</summary><p>接口 <code>{report.source_method}</code> · 请求目标 <code>{report.target}</code></p>
        <p>采集时间 {report.captured_at}</p><p>请求 SHA-256 <code>{report.request_sha256}</code></p><p>回应 SHA-256 <code>{report.response_sha256}</code></p>
        <p>采集编号 <code>{report.capture_id}</code></p></details>
    </>}
  </section>;
}
