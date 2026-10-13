import { useEffect, useRef, useState } from 'react';
import { jsonRequest } from './api.ts';
import { Generation } from './model.ts';
import { PairHistory } from './PairHistory.tsx';
import { assertResearchReply, buildResearchRequest, explainResearch, formatEstimate, formatPercent, isDailySnapshot, researchReason, snapshotName } from './research-model.ts';
import { EstimatePlot, Metric, ResearchProvenance } from './ResearchResults.tsx';
import type { Snapshot } from './types.ts';
import { UniverseResearch } from './UniverseResearch.tsx';
import type { UniverseDraft } from './UniverseResearch.tsx';
import type { PairResult, ResearchEnvelope } from './research-types.ts';

type CrossKind = 'pair' | 'universe';
export function CrossResearch({ kind, snapshots, onImport, onOpen, universeDraft, onUniverseDraftChange }: {
  kind: CrossKind; snapshots: Snapshot[]; onImport: () => void; onOpen: (id: string, cutoff: string) => void;
  universeDraft?: UniverseDraft; onUniverseDraftChange?: (next: UniverseDraft) => void;
}) {
  return kind === 'universe' ? <UniverseResearch snapshots={snapshots} onImport={onImport} onOpen={onOpen} draft={universeDraft} onDraftChange={onUniverseDraftChange} />
    : <PairResearch snapshots={snapshots} onImport={onImport} />;
}
function PairResearch({ snapshots, onImport }: { snapshots: Snapshot[]; onImport: () => void }) {
  const daily = snapshots.filter(isDailySnapshot);
  const [left, setLeft] = useState(daily[0]?.snapshot_id ?? '');
  const [right, setRight] = useState(daily[1]?.snapshot_id ?? '');
  const [cutoff, setCutoff] = useState('');
  const [lookback, setLookback] = useState('20');
  const [report, setReport] = useState<ResearchEnvelope<PairResult> | null>(null);
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [issue, setIssue] = useState('');
  const available = daily.some(item => item.snapshot_id === left) && daily.some(item => item.snapshot_id === right);
  const latestAvailable = useRef(available); latestAvailable.current = available;
  const gate = useRef(new Generation()); const abort = useRef<AbortController | null>(null);
  function invalidate() { gate.current.invalidate(); abort.current?.abort(); setReport(null); setIssue(''); setPhase('idle'); }
  useEffect(() => () => { gate.current.invalidate(); abort.current?.abort(); }, []);
  useEffect(() => { if (!available) invalidate(); }, [available]);
  async function load() {
    if (!latestAvailable.current) return;
    invalidate(); const generation = gate.current.current();
    try {
      const request = buildResearchRequest('pair', [left, right], cutoff, Number(lookback));
      const controller = new AbortController(); abort.current = controller; setPhase('loading');
      const result = await jsonRequest<ResearchEnvelope<PairResult>>(request.path, { signal: controller.signal });
      if (!latestAvailable.current || !gate.current.isCurrent(generation)) return;
      assertResearchReply(result, request.expected); setReport(result); setPhase('ready');
    } catch (error) { if (latestAvailable.current && gate.current.isCurrent(generation)) { setIssue(explainResearch(error)); setPhase('error'); } }
  }
  return <>
    <div className="workspace-intro"><span className="eyebrow">关系研究</span><h1>双股对比</h1><p>对齐两只股票的共同日期，观察相对强弱、收益相关与价格偏离。</p></div>
    {daily.length < 2 ? <section className="panel workflow-empty"><div className="empty-step">01</div><h2>先准备至少两份日线行情</h2><p>选择可识别、不同证券的数据版本。分钟数据保留在个股研究中。</p><button className="primary" onClick={onImport}>导入日线数据</button></section> : <>
      <section className="panel research-setup"><div className="section-heading"><h2>选择研究范围</h2><span className="subtle">日线 · 同一截止日期</span></div>
        <form onSubmit={event => { event.preventDefault(); void load(); }}>
          <div className="pair-selectors"><label>左侧股票 A（被解释侧）<select value={left} onChange={event => { setLeft(event.target.value); invalidate(); }} required><option value="">请选择</option>{daily.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{snapshotName(item)} · {item.snapshot_id.slice(0, 6)}</option>)}</select></label>
            <span className="comparison-sign" aria-hidden="true">↔</span><label>右侧股票 B（解释侧）<select value={right} onChange={event => { setRight(event.target.value); invalidate(); }} required><option value="">请选择</option>{daily.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{snapshotName(item)} · {item.snapshot_id.slice(0, 6)}</option>)}</select></label></div>
          <div className="research-controls cross-controls"><label>统一截止日期<input type="date" required value={cutoff} onChange={event => { setCutoff(event.target.value); invalidate(); }} /></label><label>观察窗口<input type="number" min="5" max="252" required value={lookback} onChange={event => { setLookback(event.target.value); invalidate(); }} /><small>来源记录数</small></label><button className="primary" disabled={!available || phase === 'loading'}>{phase === 'loading' ? '核验并计算中…' : '比较两只股票'}</button></div>
        </form><p className="inline-note">仅比较同一市场的不同证券。不填补缺日；坏行与重复日期会中断滚动窗口。</p>
      </section>
      {!available && <p className="inline-note amber">所选数据版本已不可用或不再是日线，请重新选择。</p>}
      {available && issue && <p className="error-banner" role="alert">{issue}</p>}
      {available && phase === 'loading' && <div className="panel research-loading" role="status">正在核验来源并计算，较早的结果已清除。</div>}
      {available && !report && phase === 'idle' && <div className="workflow-hint"><span>接下来</span><p>选好两份日线数据与截止日期，即可查看共同样本和关系指标。</p></div>}
      {available && report && <PairResults report={report} cutoff={cutoff} lookback={Number(lookback)} />}
    </>}
  </>;
}

export function PairResults({ report, cutoff, lookback }: { report: ResearchEnvelope<PairResult>; cutoff: string; lookback: number }) {
  const result = report.result; const row = result.series.at(-1); const a = result.alignment;
  return <section className="panel research-panel"><div className="section-heading"><div><span className="eyebrow">研究结果</span><h2>{result.roles.left.symbol} <span className="muted">与</span> {result.roles.right.symbol}</h2></div><span className="badge">截止 {cutoff}</span></div>
    <div className="count-strip"><span>共同日期 {a.common_dates}</span><span>有效共同日期 {a.valid_common_dates}</span><span>仅 A 有记录 {a.left_only_dates}</span><span>仅 B 有记录 {a.right_only_dates}</span></div>
    {row ? <>
      <p className="subtle">最后共同记录：{row.date}{row.date !== cutoff ? '。截止当天没有共同记录，以下只描述这个已标明的历史时点。' : ''}</p>
      <div className="metric-grid four"><Metric label="区间收益相关" value={formatEstimate(row.return_correlation)} detail={`${row.n_returns} 个共同区间 · 含当前区间`} reason={row.correlation_reason} />
        <Metric label="区间收益 β" value={formatEstimate(row.return_beta)} detail="A 对 B · 含当前区间" reason={row.return_beta_reason} />
        <Metric label="价格残差偏离" value={formatEstimate(row.residual_deviation, 2)} detail={`此前 ${row.n_prices} 对价格拟合 · 尺度倍数`} reason={row.deviation_reason} accent />
        <Metric label="相对强弱 A / B" value={formatPercent(row.relative_strength)} detail={`基准 ${result.baseline?.date ?? '不可用'}`} reason={row.relative_strength_reason} /></div>
      <div className="research-columns"><article className="research-subsection"><h3>相对价格路径</h3><EstimatePlot label="A 相对 B 的价格变化" percent series={[{ name: 'A / B 相对强弱', color: '#395a66', points: result.series.map(item => ({ date: item.date, value: item.relative_strength })) }]} /></article>
        <article className="research-subsection"><h3>此前拟合的当期偏离</h3><EstimatePlot label="历史滚动价格残差偏离" series={[{ name: '残差 / 训练残差尺度', color: '#a27f47', points: result.series.map(item => ({ date: item.date, value: item.residual_deviation })) }]} /></article></div>
      <div className="explanation-grid"><div><h3>相关与 β</h3><p>用最近 {lookback} 个共同日期区间的对数收益。相关范围为 −1 到 1；收益 β 为 A 对 B 的协方差除以 B 的收益方差。</p><p className="subtle">实际收益范围：{row.returns_start_date ?? '不可计算'} → {row.returns_end_date ?? '不可计算'}</p></div>
        <div><h3>偏离不等于回归机会</h3><p>以前 {lookback} 对对数价格拟合 A = α + β × B，当期价格不参与拟合。价格 β = {formatEstimate(row.log_price_beta)}，是弹性，不是固定对冲股数。</p><p className="subtle">训练范围：{row.price_start_date ?? '不可计算'} → {row.price_end_date ?? '不可计算'}。未做协整或均值回归检验。</p></div></div>
      {row.reason && <p className="inline-note amber">{researchReason(row.reason)}</p>}{row.coverage_reason && <p className="inline-note amber">{researchReason(row.coverage_reason)}</p>}
    </> : <p className="research-loading">截止范围没有共同日期，不能计算关系。</p>}
    <details className="calculation-note"><summary>对齐与异常记录</summary><div className="table-scroll"><table><thead><tr><th>来源</th><th>源记录</th><th>重复日期</th><th>无效日期</th><th>无法定位</th></tr></thead><tbody>{([['A', a.left], ['B', a.right]] as const).map(([name, side]) => <tr key={name}><th>{name}</th><td>{side.source_rows}</td><td>{side.duplicate_groups}</td><td>{side.invalid_groups}</td><td>{side.unlocated_rows}</td></tr>)}</tbody></table></div></details>
    <PairHistory report={report} lookback={lookback} />
    <ResearchProvenance report={report} />
  </section>;
}

export { UniverseResults } from './UniverseResults.tsx';
