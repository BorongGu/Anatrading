import { Fragment, useEffect, useId, useRef, useState } from 'react';
import { SingleEventPath } from './SingleEventPath.tsx';
import { acceptEventPath, captureEventPath, eventPathBelongs, EventPathError } from './single-event-path.ts';
import type { AcceptedEventPath, EventPathContext, EventPathProjection } from './single-event-path.ts';
import { HistoricalPathResearch } from './HistoricalPathResearch.tsx';
import { jsonRequest } from './api.ts';
import { Generation } from './model.ts';
import { assertResearchReply, buildResearchRequest, explainResearch, formatEstimate, formatPercent, researchReason } from './research-model.ts';
import { EstimatePlot, Metric, ResearchProvenance } from './ResearchResults.tsx';
import type { Query } from './types.ts';
import type { Distribution, ResearchEnvelope, SingleResult } from './research-types.ts';

export function SingleResearch({ query, onReport }: { query: Query; onReport?: (queryId: string, report: ResearchEnvelope<SingleResult> | null) => void }) {
  const [lookback, setLookback] = useState('20');
  const [horizon, setHorizon] = useState('5');
  const [testStart, setTestStart] = useState('');
  const [partition, setPartition] = useState('test');
  const [report, setReport] = useState<ResearchEnvelope<SingleResult> | null>(null);
  const [accepted, setAccepted] = useState<AcceptedEventPath | null>(null);
  const [pathIssue, setPathIssue] = useState('');
  type PathSelection = { token: object; position: number; projection: EventPathProjection | null; issue: string; trigger: HTMLButtonElement };
  const [selection, setSelection] = useState<PathSelection | null>(null);
  const selected = useRef<PathSelection | null>(null);
  function selectPath(next: PathSelection | null) { selected.current = next; setSelection(next); }
  const active = useRef<AcceptedEventPath | null>(null);
  const acceptedGeneration = useRef<number | null>(null);
  const pathId = useId();
  const context: EventPathContext = { ownerQueryId: query.query_id, snapshotId: query.snapshot_id, cutoff: query.selection.cutoff ?? null, ordinalStart: query.selection.ordinal_start ?? null, ordinalEnd: query.selection.ordinal_end ?? null };
  const currentContext = useRef(context); currentContext.current = context;
  const previousContext = useRef(context);
  function closePath() {
    if (!accepted || active.current !== accepted || acceptedGeneration.current === null || !gate.current.isCurrent(acceptedGeneration.current)
      || !eventPathBelongs(accepted, report, currentContext.current) || !selection || selected.current !== selection || selection.token !== accepted.token) return;
    selectPath(null); if (selection.trigger.isConnected) selection.trigger.focus();
  }
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('loading');
  const [issue, setIssue] = useState('');
  const gate = useRef(new Generation()); const abort = useRef<AbortController | null>(null);
  function invalidate() { active.current = null; acceptedGeneration.current = null; setAccepted(null); selectPath(null); setPathIssue(''); gate.current.invalidate(); abort.current?.abort(); setReport(null); onReport?.(query.query_id, null); setIssue(''); setPhase('idle'); }
  async function load() {
    invalidate(); const generation = gate.current.current();
    try {
      const request = buildResearchRequest('single', [query.snapshot_id], query.selection.cutoff ?? '', Number(lookback), Number(horizon), testStart);
      const controller = new AbortController(); abort.current = controller; setPhase('loading');
      const result = await jsonRequest<ResearchEnvelope<SingleResult>>(request.path, { signal: controller.signal });
      if (!gate.current.isCurrent(generation)) return;
      assertResearchReply(result, request.expected);
      // Consumers must treat each published report as read-only. Every complete
      // acceptance is a new ownership generation, even for the same object/ID.
      selectPath(null); active.current = null; setAccepted(null); setPathIssue('');
      if (request.expected.parameters.horizon === 5) {
        try {
          const next = acceptEventPath(result, context, request.expected);
          active.current = next; acceptedGeneration.current = generation; setAccepted(next);
        } catch (error) { setPathIssue(error instanceof EventPathError ? error.code : 'identity'); }
      }
      setReport(result); onReport?.(query.query_id, result); setPhase('ready');
    } catch (error) { if (gate.current.isCurrent(generation)) { setIssue(explainResearch(error)); setPhase('error'); } }
  }
  useEffect(() => {
    const previous = previousContext.current; previousContext.current = context;
    // A normal query-ID replacement is handled by load below. An abnormal
    // same-ID context change still permanently invalidates, with no auto-fetch.
    if (previous.ownerQueryId === context.ownerQueryId && (previous.snapshotId !== context.snapshotId || previous.cutoff !== context.cutoff
      || previous.ordinalStart !== context.ordinalStart || previous.ordinalEnd !== context.ordinalEnd)) invalidate();
  }, [query.query_id, query.snapshot_id, query.selection.cutoff, query.selection.ordinal_start, query.selection.ordinal_end]);
  useEffect(() => { void load(); return () => { active.current = null; acceptedGeneration.current = null; gate.current.invalidate(); abort.current?.abort(); }; }, [query.query_id]);
  const pathAvailable = accepted !== null && active.current === accepted && acceptedGeneration.current !== null
    && gate.current.isCurrent(acceptedGeneration.current) && horizon === '5' && eventPathBelongs(accepted, report, context);
  const shown = pathAvailable && selection?.token === accepted.token ? selection : null;
  function choosePath(position: number, button: HTMLButtonElement) {
    if (!accepted || active.current !== accepted || acceptedGeneration.current === null || !gate.current.isCurrent(acceptedGeneration.current)
      || horizon !== '5' || selected.current !== selection || !eventPathBelongs(accepted, report, currentContext.current)) return;
    if (selection?.token === accepted.token && selection.position === position) { closePath(); return; }
    try { selectPath({ token: accepted.token, position, projection: captureEventPath(accepted, position), issue: '', trigger: button }); }
    catch (error) { selectPath({ token: accepted.token, position, projection: null, issue: error instanceof EventPathError ? error.code : 'event_link', trigger: button }); }
  }
  const result = report?.result; const latest = result?.series.at(-1);
  const evaluation = result?.events;
  const part = evaluation?.partitions[partition] ?? evaluation?.partitions.descriptive ?? evaluation;
  return <><section className="panel research-panel" aria-label="日线趋势与历史事件">
    <div className="section-heading"><div><span className="eyebrow">日线研究</span><h2>趋势与历史事件</h2></div><span className="badge">因果计算 · 描述性统计</span></div>
    <form className="research-controls" onSubmit={event => { event.preventDefault(); void load(); }}>
      <label>突破观察窗<input type="number" min="2" max="252" required value={lookback} onChange={event => { setLookback(event.target.value); invalidate(); }} /><small>此前来源记录数</small></label>
      <label>事件后观察跨度<select value={horizon} onChange={event => { setHorizon(event.target.value); invalidate(); }}>
        {[1, 5, 10, 20].map(value => <option key={value} value={value}>{value} 条来源记录</option>)}</select></label>
      <label>测试段起始日（可选）<input type="date" value={testStart} max={query.selection.cutoff?.slice(0, 10)} onChange={event => { setTestStart(event.target.value); invalidate(); }} /></label>
      <button disabled={phase === 'loading'}>{phase === 'loading' ? '计算中…' : '更新研究'}</button>
    </form>
    <p className="inline-note research-scope">趋势从截止前完整历史初始化；图形的记录序号范围不裁剪研究历史。</p>
    {issue && <p className="error-banner" role="alert">{issue}</p>}
    {!report && !issue && <p className="research-loading" role="status">{phase === 'loading' ? '正在按同一截止日期计算完整历史…' : '参数已变更，请更新研究。'}</p>}
    {report && latest && <>
      <div className="research-columns">
        <article className="research-subsection"><div className="section-heading"><h3>当前趋势</h3><span className="subtle">{latest.date}</span></div>
          <p className="result-statement">{latest.status === 'warming_up' ? '估计预热中' : latest.status === 'invalid' ? '当前记录无法估计' : latest.kalman_slope === null ? '斜率暂无结果' : latest.kalman_slope > 0 ? '估计斜率为正' : latest.kalman_slope < 0 ? '估计斜率为负' : '估计斜率为零'}</p>
          <p className="subtle">{latest.reason ? researchReason(latest.reason) : latest.warmup ? `本段已有 ${latest.segment_observations} 条连续有效记录；前 20 条仅展示估计。` : '局部线性过滤，仅使用当前及此前收盘价。'}{latest.reset_reason && ` 本段重置：${researchReason(latest.reset_reason)}`}</p>
          <div className="metric-grid two">
            <Metric label="趋势估计价格" value={formatEstimate(latest.kalman_price, 4)} detail="与来源价格同尺度 · Kalman" reason={latest.kalman_price_reason ?? latest.reason} />
            <Metric label="简单平滑基线" value={formatEstimate(latest.ema_price, 4)} detail="EMA · 半衰期 10 条记录" reason={latest.ema_price_reason ?? latest.reason} />
            <Metric label="每观测步斜率" value={formatPercent(latest.kalman_slope, 3)} detail="对数价格变化 · 非收益预测" reason={latest.reason} />
            <Metric label="原始收益波动" value={formatPercent(latest.ewma_volatility, 3)} detail="EWMA · 未年化" reason={latest.return_shock_reason && latest.ewma_volatility === null ? latest.return_shock_reason : null} />
          </div>
          <p className="inline-note">标准化模型偏离 {formatEstimate(latest.model_deviation, 2)} · 原始收益冲击 {formatEstimate(latest.return_shock, 2)}{latest.return_shock_reason ? `（${researchReason(latest.return_shock_reason)}）` : ''}。数值为相对历史尺度的倍数，不代表概率。</p>
          <EstimatePlot label="Kalman 与 EMA 历史价格估计" series={[
            { name: '趋势估计', color: '#395a66', points: result!.series.map(row => ({ date: row.date, value: row.kalman_price, reset: row.segment_observations === 1 })) },
            { name: 'EMA 基线', color: '#a27f47', points: result!.series.map(row => ({ date: row.date, value: row.ema_price, reset: row.segment_observations === 1 })) },
          ]} />
          <div className="signal-observation"><strong>{latest.breakout === true ? '本次收盘突破此前高点' : latest.breakout === false ? '本次收盘未突破此前高点' : '本次突破条件不可计算'}</strong><p>{latest.breakout_reason ? researchReason(latest.breakout_reason) : <>比较此前 {evaluation!.lookback} 条记录的最高价 <code>{latest.prior_high}</code>；当前柱不进入基准窗。</>}</p></div>
        </article>
        <article className="research-subsection"><div className="section-heading"><h3>同类事件后来怎样</h3><span className="subtle">观察 {evaluation!.horizon} 条记录</span></div>
          <p className="subtle">固定规则：收盘价超过此前窗口最高价。统计事件后价格变化，未计成交与成本。</p>
          {evaluation?.test_start && <div className="segmented" aria-label="评价分段">{[['train', '训练段'], ['test', '测试段']].map(([value, label]) => <button key={value} aria-pressed={partition === value} onClick={() => setPartition(value)}>{label}</button>)}</div>}
          {part && <>
            <div className="metric-grid two"><Metric label="可评价事件" value={String(part.statistics.count)} detail={`原始 ${part.counts.raw_events} · 重叠排除 ${part.counts.overlap_excluded}`} accent />
              <Metric label="正变化占比" value={formatPercent(part.statistics.positive_fraction, 1)} detail={`${part.statistics.positive_count} 次正变化 / ${part.statistics.count} 次有效事件`} /></div>
            <DistributionTable event={part.statistics} baseline={part.baseline.statistics} />
            <div className="count-strip"><span>未成熟 {part.counts.immature}</span><span>无效标签 {part.counts.invalid}</span><span>跨切点排除 {part.counts.purged}</span></div>
            <p className="inline-note">去重后事件不重叠；全部日期基线仍有重叠依赖，且包含事件日。这里没有独立样本置信度或预测有效性结论。</p>
          </>}
          <details className="calculation-note"><summary>怎样理解这些数字</summary><p>价格变化 = 观察跨度末收盘价 ÷ 事件日收盘价 − 1。只纳入截止日前已成熟、路径有效的标签；不把尚未成熟的事件算成零。</p><p>{evaluation?.test_start ? `测试段从 ${evaluation.test_start} 开始。训练标签跨过切点时排除；切点和规则未经过搜索。` : '尚未指定测试切点；当前为全段描述，不称样本外检验。'}</p><p>基线采用相同时间分区、突破前窗可计算且标签有效的全部日期。它不是随机对照。</p></details>
        </article>
      </div>
      <details className="calculation-note" onToggle={event => { if (!event.currentTarget.open) closePath(); }} onKeyDown={event => { if (event.key === 'Escape' && shown) { event.preventDefault(); event.stopPropagation(); closePath(); } }}>
        <summary>查看事件记录（{evaluation?.rows.length ?? 0}）</summary>
        {horizon !== '5' && <p className="subtle">后续收盘明细仅支持观察跨度5；切换跨度后请更新研究。</p>}
        {pathIssue && <p role="status">后续收盘与事件记录未能对应，暂不提供明细；原报告保留。（{pathIssue}）</p>}
        <div className="table-scroll"><table><thead><tr><th>事件日期</th><th>标签终点</th><th>价格变化</th><th>评价状态</th>{pathAvailable && <th>后续收盘</th>}</tr></thead><tbody>{evaluation?.rows.slice(-100).map((row, offset) => {
          const position = Math.max(0, evaluation.rows.length - 100) + offset, open = shown?.position === position;
          return <Fragment key={`${row.ordinal}-${row.date}`}><tr><th>{row.date}</th><td>{row.label_end ?? '尚未成熟'}</td><td>{formatPercent(row.price_change)}</td><td>{researchReason(row.evaluation_status)}{row.label_reason ? ` · ${researchReason(row.label_reason)}` : ''}</td>
            {pathAvailable && <td><button type="button" aria-expanded={open} aria-controls={`${pathId}-${position}`} onClick={event => choosePath(position, event.currentTarget)}>查看后续收盘</button></td>}</tr>
            {open && shown && <tr><td colSpan={5} id={`${pathId}-${position}`}>{shown.projection
              ? <SingleEventPath projection={shown.projection} partition={evaluation.test_start ? partition : 'descriptive'} onClose={closePath} />
              : <section aria-label="六槽关联错误"><p role="alert">本条后续收盘与事件记录未能对应，暂不展开。原事件和原报告仍保留。</p><details><summary>数据来源与原始状态</summary><p>事件 index {row.index} · {row.date} · 源序号 {row.ordinal} · selected：{row.selected ? '是' : '否'} · partition：{row.partition} · label_status：{row.label_status} · evaluation_status：{row.evaluation_status}</p><p>诊断：event_path_inconsistent / {shown.issue}</p></details><button type="button" onClick={closePath}>收起明细</button></section>}</td></tr>}
          </Fragment>;
        })}</tbody></table></div><p className="subtle">显示最近 100 个事件；上方统计使用完整研究范围。</p>
      </details>
      <ResearchProvenance report={report} />
    </>}
    {report && !latest && <p className="research-loading">截止范围内没有可研究的日线记录。</p>}
  </section><HistoricalPathResearch query={query} /></>;
}

export function DistributionTable({ event, baseline }: { event: Distribution; baseline: Distribution }) {
  return <div className="table-scroll distribution-table"><table><thead><tr><th>事后价格变化</th><th>事件样本</th><th>全部日期基线</th></tr></thead><tbody>
    <tr><th>有效样本</th><td>{event.count}</td><td>{baseline.count}</td></tr>
    {([['均值', 'mean'], ['中位数', 'median'], ['下侧 5% 分位', 'q05'], ['25% 分位', 'q25'], ['75% 分位', 'q75'], ['上侧 95% 分位', 'q95']] as const).map(([label, field]) => <tr key={field}><th>{label}</th><td>{formatPercent(event[field])}</td><td>{formatPercent(baseline[field])}</td></tr>)}
  </tbody></table></div>;
}
