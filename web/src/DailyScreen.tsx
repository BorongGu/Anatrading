import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { checkedFetch, explain } from './api.ts';
import type { VolumeFraction } from './types.ts';
import { DailyFollowup } from './DailyFollowup.tsx';

interface Analysis {
  ordinal: number | null; close: string | null; reason: string | null;
  conditions: Record<string, boolean | null>;
  channel: { close_relation: string | null; upper: string | null; lower: string | null; reason: string | null; comparison_reason: string | null } | null;
  volume: { ratio: VolumeFraction | null; reason: string | null } | null;
  efficiency: { efficiency: VolumeFraction | null; direction: string | null; reason: string | null } | null;
}
interface ScreenRow { symbol: string; status: string; snapshot_id: string | null; raw_sha256: string | null; analysis: Analysis | null }
export interface ScreenWindows { channel_lookback: number; volume_lookback: number; efficiency_lookback: number }
export interface ScreenParameters extends ScreenWindows {
  source_date: string; channel_relation: string | null; minimum_volume: string | null;
  minimum_efficiency: string | null; direction: string | null;
}
interface Screen {
  method_id: string; screen_id: string; run_ids: string[]; enabled_conditions: string[];
  parameters: ScreenParameters;
  counts: { pool: number; processed: number; committed: number; missing: number; failed: number; unprocessed: number; target_unique: number; target_missing: number; target_duplicate: number; date_set_unknown: number; eligible: number; matched: number; not_evaluated: number };
  rows: ScreenRow[];
}
const relations: Record<string, string> = { above: '收盘高于上界', below: '收盘低于下界', inside: '收盘在界内', touch_upper: '收盘等于上界', touch_lower: '收盘等于下界', touch_both: '收盘等于两界' };
const states: Record<string, string> = { matched: '满足条件', unmatched: '不满足', not_evaluated: '无法评价', missing: '缺缓存', unprocessed: '未处理', failed: '采集失败', rejected: '未入库', publication_unknown: '入库结果未知' };
const reasons: Record<string, string> = { target_date_missing: '缺目标日', duplicate_target_date: '目标日重复', date_set_integrity_unknown: '含不可读日期', condition_unavailable: '启用条件缺值', history_insufficient: '历史不足', duplicate_date: '历史日期重复', invalid_ohlc: '价格范围无效', zero_baseline: '量均值为零', zero_path_convention: '平坦路径按0约定' };
const conditionNames: Record<string, string> = { channel_relation: '收盘通道', minimum_volume: '源数量比', minimum_efficiency: '路径效率', direction: '净变动方向' };
function ratioText(value: VolumeFraction | null | undefined) { return value ? `${value.display}（${value.numerator}/${value.denominator}）` : '∅'; }

export function DailyScreen({ runIds, onSelect }: { runIds: string[]; onSelect: (snapshot: string, sourceDate?: string, windows?: ScreenWindows) => void }) {
  const [sourceDate, setSourceDate] = useState('');
  const [channelWindow, setChannelWindow] = useState('20');
  const [volumeWindow, setVolumeWindow] = useState('20');
  const [efficiencyWindow, setEfficiencyWindow] = useState('10');
  const [relation, setRelation] = useState('');
  const [minimumVolume, setMinimumVolume] = useState('');
  const [minimumEfficiency, setMinimumEfficiency] = useState('');
  const [direction, setDirection] = useState('');
  const [report, setReport] = useState<Screen | null>(null);
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [issue, setIssue] = useState('');
  const [state, setState] = useState('matched');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const runKey = runIds.join(',');
  useEffect(() => { setReport(null); setBody(''); setLoading(false); setIssue(''); return () => abort.current?.abort(); }, [runKey]);

  async function read(event: FormEvent) {
    event.preventDefault(); if (loading) return;
    const controller = new AbortController(); abort.current = controller;
    setReport(null); setBody(''); setIssue(''); setLoading(true); setPage(0);
    const params = new URLSearchParams({ run_ids: runKey, source_date: sourceDate, channel_lookback: channelWindow, volume_lookback: volumeWindow, efficiency_lookback: efficiencyWindow });
    for (const [name, value] of Object.entries({ channel_relation: relation, minimum_volume: minimumVolume, minimum_efficiency: minimumEfficiency, direction })) if (value) params.set(name, value);
    try {
      const response = await checkedFetch(`/api/daily-screen?${params}`, { signal: controller.signal });
      const original = await response.text(); const value = JSON.parse(original).screen as Screen;
      if (controller.signal.aborted) return;
      if (value.method_id !== 'current-pool-daily-screen-v1' || value.parameters.source_date !== sourceDate
        || value.run_ids.join(',') !== [...runIds].sort().join(',') || !Array.isArray(value.rows)) throw new Error('invalid_response');
      setReport(value); setBody(original);
    } catch (error) { if (!controller.signal.aborted) setIssue(explain(error)); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  function download() {
    if (!report || !body) return;
    const url = URL.createObjectURL(new Blob([body], { type: 'application/json;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `daily-screen-${report.screen_id}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const rows = report?.rows.filter(row => (state === 'all' || row.status === state) && row.symbol.toLowerCase().includes(filter.trim().toLowerCase())) ?? [];
  return <div className="detail-panel">
    <h3>当前来源池 · 日线条件筛选</h3>
    <p className="subtle">使用上方所选批次的固定数据版本。按指定来源日期筛选，缺少该日时不使用更早记录替代；条件全部成立才匹配。留空表示不启用，全部留空仅列出无条件数据记录。</p>
    <form onSubmit={read} onChange={() => { setReport(null); setBody(''); }}>
      <fieldset disabled={loading}><div className="exact-grid">
        <label>目标源日期<input type="date" required value={sourceDate} onChange={event => setSourceDate(event.target.value)} /></label>
        <label>通道前N源日期<input type="number" min="2" max="252" required value={channelWindow} onChange={event => setChannelWindow(event.target.value)} /></label>
        <label>量均值前N源日期<input type="number" min="2" max="252" required value={volumeWindow} onChange={event => setVolumeWindow(event.target.value)} /></label>
        <label>ER前N次收盘变化<input type="number" min="2" max="252" required value={efficiencyWindow} onChange={event => setEfficiencyWindow(event.target.value)} /></label>
        <label>收盘相对前期通道<select value={relation} onChange={event => setRelation(event.target.value)}><option value="">不筛选</option>{Object.entries(relations).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>源数量比 ≥<input type="number" min="0" step="any" placeholder="留空不筛选" value={minimumVolume} onChange={event => setMinimumVolume(event.target.value)} /></label>
        <label>路径效率ER ≥<input type="number" min="0" max="1" step="any" placeholder="留空不筛选" value={minimumEfficiency} onChange={event => setMinimumEfficiency(event.target.value)} /></label>
        <label>ER窗口净变动<select value={direction} onChange={event => setDirection(event.target.value)}><option value="">不筛选</option><option value="up">上行</option><option value="down">下行</option><option value="flat">持平</option></select></label>
      </div><button className="primary" disabled={!runIds.length}>{loading ? '读取原件并筛选中…' : '运行条件筛选'}</button></fieldset>
    </form>
    <p className="inline-note amber">当前池历史回顾，复权、数量口径、闭合与历史可得时点未核。ER只描述收盘路径，量比只描述源数量变化；匹配不代表收益或买入建议。</p>
    {issue && <p className="error-banner">{issue}</p>}
    {report && <>
      <p>源池 {report.counts.pool} · 已处理 {report.counts.processed} · 已入库 {report.counts.committed} · 缺缓存 {report.counts.missing} · 未处理 {report.counts.unprocessed} · 采集失败／未知 {report.counts.failed}</p>
      <p>目标日唯一记录 {report.counts.target_unique} · 缺目标日 {report.counts.target_missing} · 目标日重复 {report.counts.target_duplicate} · 日期完整性未知 {report.counts.date_set_unknown} · 可评价 {report.counts.eligible} · {report.enabled_conditions.length ? '满足条件' : '无条件数据记录'} {report.counts.matched}</p>
      <button onClick={download}>导出完整结果 JSON</button>
      <div className="exact-grid"><label>结果状态<select value={state} onChange={event => { setState(event.target.value); setPage(0); }}><option value="all">全部源池记录</option>{Object.entries(states).map(([value,label]) => <option key={value} value={value}>{value === 'matched' && !report.enabled_conditions.length ? '无条件数据记录' : label}</option>)}</select></label>
        <label>代码筛选<input value={filter} onChange={event => { setFilter(event.target.value); setPage(0); }} /></label></div>
      <p className="subtle">显示 {rows.length} 条 · 精确分数参与比较，四位显示仅供阅读。</p>
      <div className="table-scroll"><table><thead><tr><th>证券</th><th>状态</th><th>源收盘</th><th>收盘通道／源上下界</th><th>源数量比</th><th>路径效率／净方向</th><th>条件与缺值</th><th>复查</th></tr></thead><tbody>{rows.slice(page*100,(page+1)*100).map(row => {
        const a = row.analysis; return <tr key={row.symbol}><td>{row.symbol}</td><td>{row.status === 'matched' && !report.enabled_conditions.length ? '无条件记录' : states[row.status] ?? row.status}</td><td>{a?.close ?? '∅'}</td>
          <td>{relations[a?.channel?.close_relation ?? ''] ?? '∅'}<br />{a?.channel?.upper ?? '∅'}／{a?.channel?.lower ?? '∅'}</td><td>{ratioText(a?.volume?.ratio)}</td><td>{ratioText(a?.efficiency?.efficiency)}<br />{({ up: '上行', down: '下行', flat: '持平' } as Record<string,string>)[a?.efficiency?.direction ?? ''] ?? '∅'}</td>
          <td>{a?.reason && <div>{reasons[a.reason] ?? a.reason}</div>}{Object.entries(a?.conditions ?? {}).map(([name,value]) => <div key={name}>{conditionNames[name]}：{value === null ? '无法计算' : value ? '满足' : '不满足'}</div>)}{[a?.channel?.reason,a?.channel?.comparison_reason,a?.volume?.reason,a?.efficiency?.reason].filter(Boolean).map((reason,i) => <div key={i}>{reasons[reason!] ?? reason}</div>)}</td>
          <td>{row.snapshot_id && <button onClick={() => onSelect(row.snapshot_id!,report.parameters.source_date,report.parameters)}>打开日线</button>}</td></tr>;
      })}</tbody></table></div>
      {rows.length > 100 && <div className="pagination"><button disabled={page === 0} onClick={() => setPage(page-1)}>上一页</button><span>第 {page+1}／{Math.ceil(rows.length/100)} 页</span><button disabled={(page+1)*100 >= rows.length} onClick={() => setPage(page+1)}>下一页</button></div>}
      <details><summary>结果编号</summary><code>{report.screen_id}</code><p className="subtle">导出保留全部源池记录、参数、逐项条件、窗口成员、原始哈希和数据版本；更换原件或参数会生成不同的结果编号。</p></details>
      <DailyFollowup parameters={report.parameters} runIds={report.run_ids} screenId={report.screen_id} onSelect={onSelect} />
    </>}
  </div>;
}
