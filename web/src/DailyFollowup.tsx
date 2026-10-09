import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { checkedFetch, explain } from './api.ts';
import type { ScreenParameters, ScreenWindows } from './DailyScreen.tsx';

interface Ratio { numerator: string; denominator: string; percent_display: string }
interface Endpoint { date: string; ordinals: number[]; close: string | null; reason: string | null }
interface Observation { status: string; reason: string | null; start: Endpoint | null; end: Endpoint | null; change: Ratio | null }
interface Member { symbol: string; status: string; group: string | null; snapshot_id: string | null; analysis: { reason: string | null } | null; observation: Observation }
interface Group {
  selected: number; observed: number; missing: number; coverage: Ratio | null; missing_reasons: Record<string, number>;
  quantiles: Record<'q1' | 'median' | 'q3', Ratio | null>;
  sign_counts: Record<'positive' | 'zero' | 'negative', number>;
  sign_proportions: Record<'positive' | 'zero' | 'negative', Ratio | null>;
}
interface Followup {
  method_id: string; followup_id: string; source_screen_id: string; parameters: ScreenParameters & { evaluation_date: string };
  counts: { pool: number; committed: number; missing: number; unprocessed: number; eligible: number; not_evaluated: number };
  run_ids: string[]; groups: Record<'matched' | 'other_eligible', Group>; rows: Member[];
}
const labels: Record<string, string> = { matched: '筛选日匹配组', other_eligible: '其余可评价组' };
const reasons: Record<string, string> = { end_date_missing: '缺终点日期', duplicate_end_date: '终点日期重复', start_date_missing: '缺起点日期', duplicate_start_date: '起点日期重复', zero_start_close: '起点收盘为零', close_outside_range: '收盘越出有效高低范围', missing_close: '缺有效收盘', screen_not_eligible: '筛选日未入组', date_set_integrity_unknown: '含不可读日期' };
function percent(value: Ratio | null) { return value ? `${value.percent_display}%` : '∅'; }
function fraction(value: Ratio | null) { return value ? `${value.numerator}/${value.denominator}` : undefined; }

export function DailyFollowup({ parameters, runIds, screenId, onSelect }: {
  parameters: ScreenParameters; runIds: string[]; screenId: string; onSelect: (snapshot: string, sourceDate?: string, windows?: ScreenWindows) => void;
}) {
  const [end, setEnd] = useState('');
  const [report, setReport] = useState<Followup | null>(null);
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [issue, setIssue] = useState('');
  const [group, setGroup] = useState('matched');
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function read(event: FormEvent) {
    event.preventDefault(); if (loading || end <= parameters.source_date) return;
    const controller = new AbortController(); abort.current = controller;
    setLoading(true); setReport(null); setBody(''); setIssue(''); setPage(0);
    const params = new URLSearchParams({ run_ids: runIds.join(','), evaluation_date: end, screen_id: screenId });
    for (const [key, value] of Object.entries(parameters)) if (value !== null) params.set(key, String(value));
    try {
      const response = await checkedFetch(`/api/daily-followup?${params}`, { signal: controller.signal });
      const original = await response.text(); const value = JSON.parse(original).followup as Followup;
      if (controller.signal.aborted) return;
      if (value.method_id !== 'current-pool-daily-followup-v1' || value.source_screen_id !== screenId || value.parameters.evaluation_date !== end
        || value.parameters.source_date !== parameters.source_date || value.run_ids.join(',') !== [...runIds].sort().join(',')) throw new Error('invalid_response');
      setReport(value); setBody(original);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  function download() {
    if (!report || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `daily-followup-${report.followup_id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const members = report?.rows.filter(row => group === 'all' || (group === 'ungrouped' ? row.group === null : row.group === group)) ?? [];
  const groupNames = [parameters.channel_relation, parameters.minimum_volume, parameters.minimum_efficiency, parameters.direction].some(value => value !== null)
    ? labels : { ...labels, matched: '无条件数据记录组' };
  return <div className="detail-panel">
    <h3>后续区间观察 · 源收盘变化</h3>
    <p className="subtle">沿用上方已固定的 {parameters.source_date} 筛选成员与参数。终点缺失不删除原成员、不替换较早日期。变化为两日源收盘之比减1；统计以可观察成员为分母。</p>
    <form onSubmit={read}><label>观察终点日期<input type="date" min={parameters.source_date} required disabled={loading} value={end} onChange={event => { setEnd(event.target.value); setReport(null); setBody(''); }} /></label>
      <button className="primary" disabled={loading || end <= parameters.source_date}>{loading ? '按固定条件核查后续观察中…' : '观察后续区间'}</button></form>
    <p className="inline-note amber">后续列为事后观察，不进入原日筛选。公司行动与复权未核；两组并非随机分配，分布差异尚不能解释为交易收益或预测优势。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {report && <>
      <p>源池 {report.counts.pool} · 已入库 {report.counts.committed} · 缺缓存 {report.counts.missing} · 未处理 {report.counts.unprocessed} · 筛选日可评价 {report.counts.eligible} · 已入库未评价 {report.counts.not_evaluated}</p>
      <p>{report.parameters.source_date} → {report.parameters.evaluation_date} · 所有分位数采用精确Type7线性插值，正负分类按原分数。</p>
      <div className="table-scroll"><table><thead><tr><th>分组</th><th>原成员</th><th>可观察／缺失</th><th>覆盖率</th><th>Q1</th><th>中位数</th><th>Q3</th><th>正／零／负数量</th><th>正变化占可观察成员</th></tr></thead><tbody>
        {Object.entries(report.groups).map(([name, data]) => <tr key={name}><th>{groupNames[name]}</th><td>{data.selected}</td><td>{data.observed}／{data.missing}</td><td title={fraction(data.coverage)}>{percent(data.coverage)}</td>{(['q1', 'median', 'q3'] as const).map(key => <td key={key} title={fraction(data.quantiles[key])}>{percent(data.quantiles[key])}</td>)}<td>{data.sign_counts.positive}／{data.sign_counts.zero}／{data.sign_counts.negative}</td><td title={fraction(data.sign_proportions.positive)}>{percent(data.sign_proportions.positive)}</td></tr>)}
      </tbody></table></div>
      {Object.entries(report.groups).map(([name, data]) => data.missing > 0 && <p key={name} className="subtle">{groupNames[name]}缺失：{Object.entries(data.missing_reasons).map(([reason, count]) => `${reasons[reason] ?? reason} ${count}`).join(' · ')}</p>)}
      <button onClick={download}>导出全部成员与精确分数 JSON</button>
      <label>成员分组<select value={group} onChange={event => { setGroup(event.target.value); setPage(0); }}><option value="matched">{groupNames.matched}</option><option value="other_eligible">其余可评价组</option><option value="ungrouped">筛选日未入组</option><option value="all">全部源池</option></select></label>
      <p className="subtle">{members.length} 个原成员；缺失行保留在表内。</p>
      <div className="table-scroll"><table><thead><tr><th>证券</th><th>原分组</th><th>起点源收盘</th><th>终点源收盘</th><th>源收盘变化</th><th>观察状态</th><th>复查</th></tr></thead><tbody>{members.slice(page*100,(page+1)*100).map(row => <tr key={row.symbol}>
        <td>{row.symbol}</td><td>{groupNames[row.group ?? ''] ?? '未入组'}</td><td>{row.observation.start?.close ?? '∅'}</td><td>{row.observation.end?.close ?? '∅'}</td><td title={fraction(row.observation.change)}>{percent(row.observation.change)}</td><td>{row.observation.status === 'computed' ? '已观察' : reasons[row.observation.reason ?? ''] ?? row.observation.reason}</td>
        <td>{row.snapshot_id && <><button onClick={() => onSelect(row.snapshot_id!,report.parameters.source_date,report.parameters)}>查看筛选日</button><button disabled={!row.observation.end?.close} onClick={() => onSelect(row.snapshot_id!,report.parameters.evaluation_date,report.parameters)}>查看终点</button></>}</td>
      </tr>)}</tbody></table></div>
      {members.length > 100 && <div className="pagination"><button disabled={page === 0} onClick={() => setPage(page-1)}>上一页</button><span>第 {page+1}／{Math.ceil(members.length/100)} 页</span><button disabled={(page+1)*100 >= members.length} onClick={() => setPage(page+1)}>下一页</button></div>}
      <details><summary>固定观察身份</summary><code>{report.followup_id}</code></details>
    </>}
  </div>;
}
