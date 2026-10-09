import { useEffect, useRef, useState } from 'react';
import { explain, jsonRequest } from './api.ts';

interface Run { run_id: string; status: string; processed: number; pool_sha256: string }
interface CoverageRow {
  symbol: string; status: string; snapshot_id: string | null; raw_sha256: string | null;
  source_rows: number; earliest_source_date: string | null; latest_source_date: string | null;
  invalid_date_rows: number; duplicate_date_rows: number; descending_steps: number;
}
interface Coverage {
  method_id: string; run_ids: string[]; pool_sha256: string;
  counts: { pool: number; processed: number; committed: number; missing: number; failed: number; unprocessed: number; source_rows: number };
  latest_source_date_counts: Record<string, number>; rows: CoverageRow[];
}
const states: Record<string, string> = { committed: '已入库', missing: '缺缓存', failed: '失败', rejected: '未入库', publication_unknown: '入库结果未知', unprocessed: '未处理' };

export function DailyCoverage({ onSelect }: { onSelect: (snapshot: string) => void }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [report, setReport] = useState<Coverage | null>(null);
  const [issue, setIssue] = useState('');
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const [status, setStatus] = useState('all');
  const [end, setEnd] = useState('');
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    jsonRequest<{ runs: Run[] }>('/api/daily-cache-runs', { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setRuns(result.runs);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explain(error)); });
    return () => { controller.abort(); abort.current?.abort(); };
  }, []);

  async function read() {
    if (loading || !selected.length) return;
    const controller = new AbortController(); abort.current = controller;
    setReport(null); setIssue(''); setLoading(true); setPage(0); setEnd('');
    try {
      const result = await jsonRequest<{ coverage: Coverage }>(`/api/daily-cache-coverage?${new URLSearchParams({ run_ids: selected.join(',') })}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (result.coverage.method_id !== 'native-daily-cache-coverage-v1'
        || result.coverage.run_ids.join(',') !== [...selected].sort().join(',') || !Array.isArray(result.coverage.rows)) throw new Error('invalid_response');
      setReport(result.coverage);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  const rows = report?.rows.filter(row => row.symbol.toLowerCase().includes(filter.trim().toLowerCase())
    && (status === 'all' || row.status === status) && (!end || (row.latest_source_date ?? (row.status === 'committed' ? 'unreadable' : '')) === end)) ?? [];
  return <section className="panel detail-panel" aria-label="全市场日线覆盖">
    <h2>全市场日线覆盖</h2>
    <p className="subtle">选择已结束的采集批次，可合并同一来源股票列表的互不重叠部分。当前来源列表不代表历史市场组成；缺缓存与较早的末日期均不自动解释为停牌或未上市。</p>
    {runs.map(run => <label key={run.run_id} className="subtle"><input type="checkbox" checked={selected.includes(run.run_id)} disabled={loading || run.status === 'running'} onChange={event => {
      setSelected(event.target.checked ? [...selected, run.run_id] : selected.filter(id => id !== run.run_id)); setReport(null);
    }} /> 批次 <code>{run.run_id}</code> · {run.status} · 已处理 {run.processed}<br /></label>)}
    {!runs.length && !issue && <p className="subtle">尚无批量日线采集记录。</p>}
    <button className="primary" disabled={loading || !selected.length} onClick={read}>{loading ? '核验原件与日期中…' : '核查所选批次覆盖'}</button>
    {issue && <p className="error-banner">{issue}</p>}
    {report && <>
      <p>源列表 {report.counts.pool} 只 · 已入库 {report.counts.committed} · 缺缓存 {report.counts.missing} · 失败／结果未知 {report.counts.failed} · 未处理 {report.counts.unprocessed} · 源记录 {report.counts.source_rows.toLocaleString()}</p>
      <p className="subtle">末日期取各文件中可读源日期的最大值；不代表数据已完整更新或当日收盘确认。</p>
      <div className="exact-grid">
        <label>代码筛选<input value={filter} onChange={event => { setFilter(event.target.value); setPage(0); }} /></label>
        <label>状态<select value={status} onChange={event => { setStatus(event.target.value); setPage(0); }}><option value="all">全部</option>{Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>末日期<select value={end} onChange={event => { setEnd(event.target.value); setPage(0); }}><option value="">全部</option>{Object.entries(report.latest_source_date_counts).map(([value, count]) => <option key={value} value={value}>{value === 'unreadable' ? '日期不可读' : value} · {count} 只</option>)}</select></label>
      </div>
      <p className="subtle">匹配 {rows.length} 只</p>
      <div className="table-scroll"><table><thead><tr><th>证券</th><th>状态</th><th>最早源日期</th><th>最大源日期</th><th>记录数</th><th>日期异常</th><th>分析</th></tr></thead>
        <tbody>{rows.slice(page*100, (page+1)*100).map(row => <tr key={row.symbol}><td>{row.symbol}</td><td>{states[row.status] ?? row.status}</td><td>{row.earliest_source_date ?? '∅'}</td><td>{row.latest_source_date ?? '∅'}</td><td>{row.source_rows}</td><td>不可读 {row.invalid_date_rows} · 重复 {row.duplicate_date_rows} · 倒序 {row.descending_steps}</td><td>{row.snapshot_id && <button onClick={() => onSelect(row.snapshot_id!)}>打开日线</button>}</td></tr>)}</tbody></table></div>
      {rows.length > 100 && <div className="pagination"><button disabled={page === 0} onClick={() => setPage(page-1)}>上一页</button><span>第 {page+1}／{Math.ceil(rows.length/100)} 页</span><button disabled={(page+1)*100 >= rows.length} onClick={() => setPage(page+1)}>下一页</button></div>}
      <details><summary>源列表哈希</summary><code>{report.pool_sha256}</code></details>
    </>}
  </section>;
}
