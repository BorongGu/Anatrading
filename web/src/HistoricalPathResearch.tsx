import { useEffect, useRef, useState } from 'react';
import { Metric } from './ResearchResults.tsx';
import { emptyHistoricalPathState, explainHistoricalPath, formatPathPercent, HistoricalPathController, pathReason, PATH_METHODS } from './historical-path-model.ts';
import type { HistoricalPathEnvelope, HistoricalPathResult, PathLedgerStatus, PathMethod, PathWindow } from './historical-path-types.ts';
import type { Query } from './types.ts';

const labels: Record<PathMethod, string> = { path: '整段路径最近', endpoint: '终点变化最近', recent: '最近发生的旧区间' };
const notes: Record<PathMethod, string> = {
  path: '按20步相对路径的平方距离排序，保留方向、先后与幅度。',
  endpoint: '只比较首末变化；相同涨跌幅可能掩盖中间路径差异。',
  recent: '从最近的有效旧区间开始，便于比较直接回看的效果。',
};
const pointDate = (result: HistoricalPathResult, window: PathWindow, step: number) => result.groups[window.start_index + step];
const percentagePoints = (value: string) => `${formatPathPercent(value).replace(/%$/, '')} 个百分点`;

export function HistoricalPathResearch({ query }: { query: Query }) {
  // A different chart/source context never receives the preceding context's state.
  return <HistoricalPathResearchPanel key={`${query.snapshot_id}:${query.query_id}`} query={query} />;
}
function HistoricalPathResearchPanel({ query }: { query: Query }) {
  const [cutoff, setCutoff] = useState(query.selection.cutoff?.slice(0, 10) ?? '');
  const [state, setState] = useState(emptyHistoricalPathState);
  const control = useRef<HistoricalPathController | null>(null);
  function controller() { if (!control.current) control.current = new HistoricalPathController(setState); return control.current; }
  useEffect(() => {
    controller();
    const hide = () => control.current?.invalidate();
    const show = (event: PageTransitionEvent) => { if (event.persisted) control.current?.invalidate(); };
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show);
    return () => { window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show); control.current?.dispose(); control.current = null; };
  }, []);
  useEffect(() => {
    if (state.status === 'error') document.getElementById('path-match-error')?.focus();
    if (state.status === 'cancelled') document.getElementById('path-match-run')?.focus();
  }, [state.status]);
  const busy = state.status === 'loading';
  const status = busy ? '正在核验完整来源前缀并检索，较早结果和已选参照已清除。'
    : state.status === 'cancelled' ? '已取消等待，结果已清除。服务端已接受的只读核验可能仍在完成。'
      : state.status === 'dirty' ? '查询条件已变化，请重新检索。'
        : state.report ? `检索完成，请核对下方实际查询窗口。有效旧窗口 ${state.report.result.counts.path.valid} 个，路径栏选出 ${state.report.result.selections.path.length} 段。`
          : '选定精确终点后手动检索；缺少该日期或查询窗口无效时不回退。';
  return <section className="panel research-panel historical-path-panel" aria-label="历史来源路径检索">
    <div className="section-heading"><div><span className="eyebrow">历史参照</span><h2>历史来源路径检索</h2></div><span className="badge">固定20来源步 · 同股同版本</span></div>
    <p>找出可逐点核对的旧区间，也可以不采用任何参照。排名最接近不保证足够相似。</p>
    <form className="historical-path-controls" onSubmit={event => { event.preventDefault(); void controller().run(query.snapshot_id, cutoff); }}>
      <label>查询终点日期<input id="path-match-cutoff" type="date" required value={cutoff} aria-describedby="path-match-window-hint" onChange={event => { controller().invalidate(); setCutoff(event.target.value); }} /></label>
      <div className="button-group"><button id="path-match-run" className="primary" disabled={busy}>{busy ? '核验并检索中…' : state.status === 'error' ? '按当前日期重试' : '检索历史参照'}</button>
        {busy && <button type="button" onClick={() => controller().cancel()}>取消等待</button>}</div>
    </form>
    <p id="path-match-window-hint" className="inline-note">固定20个来源区间、21个观测。检索使用终点前完整历史，旧图的源序号范围不裁剪研究前缀；实际起止与自然日跨度在结果中核对。</p>
    <p className="research-request-status" role="status" aria-live="polite">{status}</p>
    {state.status === 'error' && <p id="path-match-error" className="error-banner" role="alert" tabIndex={-1}>{explainHistoricalPath(state.error)}</p>}
    {state.report && <HistoricalPathResults key={state.report.analysis_id} report={state.report} selected={state.selected} rejected={state.rejected} onSelect={start => controller().select(start)} onReject={() => controller().select(null, true)} />}
  </section>;
}

export function HistoricalPathResults({ report, selected = null, rejected = false, onSelect, onReject }: {
  report: HistoricalPathEnvelope; selected?: number | null; rejected?: boolean;
  onSelect: (start: number | null) => void; onReject: () => void;
}) {
  const result = report.result, query = result.query, candidate = result.windows.find(window => window.start_index === selected);
  return <div className="historical-path-results">
    <section className="historical-path-window" aria-label="实际查询窗口">
      <div className="section-heading"><h3>先核对所查区间</h3><span className="subtle">{result.identity.symbol} · 截止 {result.cutoff}</span></div>
      <p className="result-statement">{query.start_date} → {query.end_date}</p>
      <p><strong>20来源步 · 21个观测 · 相隔{query.calendar_days}个自然日</strong>。来源步按记录排列，等距显示不代表相同日历间隔；缺交易日仍未知。</p>
      <div className="metric-grid two"><Metric label="查询首末变化" value={formatPathPercent(query.endpoint_change)} detail="末点来源收盘价 ÷ 首点来源收盘价 − 1" />
        <Metric label="查询源路径最大回撤" value={formatPathPercent(query.max_drawdown.value)} detail={`${pointDate(result, query, query.max_drawdown.peak_step)} → ${pointDate(result, query, query.max_drawdown.trough_step)}`} /></div>
      <details className="calculation-note"><summary>核对查询的21个原价与日期</summary><PathPointTable result={result} /></details>
    </section>
    <p className="inline-note amber historical-path-warning">排名最接近也可能不宜参考。三栏分别从同一候选池贪心去重，每栏最多3段；各栏之间可以重复，候选之间不视为独立金融样本。</p>
    {result.counts.path.valid === 0 && <p className="historical-path-empty" role="status">没有有效的旧区间可供参照。历史窗口必须完整早于查询起点，且保留21个连续来源组；没有补点或放宽条件。</p>}
    <div className="historical-path-columns">{PATH_METHODS.map(method => <section key={method} className="historical-path-method" aria-label={labels[method]}>
      <h3>{labels[method]}{method !== 'path' && <small>简单对照</small>}</h3><p className="subtle">{notes[method]}</p>
      <ol>{result.selections[method].map((start, rank) => {
        const item = result.windows.find(window => window.start_index === start)!;
        return <li key={start}><button type="button" className="historical-path-candidate" aria-pressed={selected === start} onClick={() => onSelect(selected === start ? null : start)}>
          <strong>{rank + 1}. {item.start_date} → {item.end_date}</strong><span>相隔{item.calendar_days}个自然日 · 20来源步</span>
          <span>首末变化 {formatPathPercent(item.endpoint_change)}</span><span>路径距离 d²：{item.distance}</span>
          <span>端点差：{percentagePoints(item.endpoint_distance)}</span><span>{selected === start ? '已叠加，点击清除' : '叠加并逐点核对'}</span>
        </button></li>;
      })}</ol>
      {!result.selections[method].length && <p className="subtle">本栏没有可选候选。</p>}
      <p className="historical-path-counts">总候选 {result.counts[method].total} · 有效 {result.counts[method].valid} · 无效 {result.counts[method].invalid}<br />选中 {result.counts[method].selected} · 重叠排除 {result.counts[method].overlap_excluded} · 其余 {result.counts[method].remaining}</p>
    </section>)}</div>
    <p className="inline-note">比例与距离为12位有效数字的舍入显示，按精确值排序。显示相同不表示精确值相同。d²越小仅表示此度量下越近，不能据此推断后续方向。</p>
    <div className="button-group historical-path-decisions"><button type="button" disabled={!candidate} onClick={() => onSelect(null)}>清除叠加</button>
      <button type="button" aria-pressed={rejected} onClick={onReject}>这些参照都不采用</button></div>
    <p className="research-request-status" role="status" aria-live="polite">{rejected ? '已记录本页选择：这些参照都不采用。可继续核对或修改终点重新检索。' : candidate ? `已选参照：${candidate.start_date} → ${candidate.end_date}。` : '尚未选择参照。点选任一候选可叠加与逐点核对。'}</p>
    {candidate && <section className="historical-path-comparison" aria-label="已选路径逐点对照">
      <div className="section-heading"><h3>已选路径对照</h3><span className="subtle">查询与参照的日期分别保留</span></div>
      <p>查询 {query.start_date} → {query.end_date}（{query.calendar_days}天）；参照 {candidate.start_date} → {candidate.end_date}（{candidate.calendar_days}天）。</p>
      <div className="metric-grid two"><Metric label="参照首末变化" value={formatPathPercent(candidate.endpoint_change)} detail={`查询 ${formatPathPercent(query.endpoint_change)}`} />
        <Metric label="参照源路径最大回撤" value={formatPathPercent(candidate.max_drawdown.value)} detail={`${pointDate(result, candidate, candidate.max_drawdown.peak_step)} → ${pointDate(result, candidate, candidate.max_drawdown.trough_step)}；查询 ${formatPathPercent(query.max_drawdown.value)}`} />
        <Metric label="最大逐点差" value={percentagePoints(candidate.max_point_difference.value)} detail={`第${candidate.max_point_difference.step}步：查询 ${pointDate(result, query, candidate.max_point_difference.step)} / 参照 ${pointDate(result, candidate, candidate.max_point_difference.step)}`} />
        <Metric label="路径平方距离 d²" value={candidate.distance} detail="20个非起点差异的平方均值 · 无量纲" /></div>
      <HistoricalPathPlot query={query} candidate={candidate} />
      <PathPointTable result={result} candidate={candidate} />
    </section>}
    <HistoricalPathLedger result={result} />
    <HistoricalPathProvenance report={report} />
  </div>;
}

export function HistoricalPathPlot({ query, candidate }: { query: PathWindow; candidate: PathWindow }) {
  const series = [{ name: '查询路径', color: '#395a66', window: query }, { name: '历史参照', color: '#a27f47', window: candidate }];
  const all = series.flatMap(item => item.window.relative_path.map(Number));
  let low = Math.min(...all), high = Math.max(...all);
  if (low === high) { const pad = Math.max(Math.abs(low) * 0.01, 0.001); low -= pad; high += pad; }
  const x = (step: number) => 94 + step / 20 * 570, y = (value: number) => 18 + (high - value) / (high - low) * 150;
  const tick = (value: number) => `${(value * 100).toLocaleString('zh-CN', { maximumSignificantDigits: 5 })}%`;
  return <figure className="estimate-figure historical-path-figure"><figcaption>{series.map(item => <span key={item.name}><i style={{ background: item.color }} />{item.name}：{item.window.start_date} → {item.window.end_date}</span>)}</figcaption>
    <svg className="estimate-chart" viewBox="0 0 700 220" role="img" aria-label="按第0至20来源步对齐的查询与历史参照相对路径，真实日期分别列示">
      {[high, (low + high) / 2, low].map((value, index) => <g key={index}><line x1="94" x2="664" y1={y(value)} y2={y(value)} stroke="var(--line)" /><text x="84" y={y(value) + 4} textAnchor="end">{tick(value)}</text></g>)}
      {series.map((item, index) => <path key={item.name} d={item.window.relative_path.map((value, step) => `${step ? 'L' : 'M'}${x(step).toFixed(2)},${y(Number(value)).toFixed(2)}`).join(' ')} stroke={item.color} strokeDasharray={index ? '6 4' : undefined} fill="none" strokeWidth="2" />)}
      {[0, 5, 10, 15, 20].map(step => <text key={step} x={x(step)} y="191" textAnchor="middle">{step}</text>)}<text x="380" y="213" textAnchor="middle">查询第0…20来源步</text>
    </svg><p className="subtle">纵轴为各段来源收盘价 ÷ 各自首价 − 1。SVG仅用显示值布点；精确原价见表。源路径回撤未含分红，窗内除权或错价可改变整段对照。</p>
  </figure>;
}

export function PathPointTable({ result, candidate }: { result: HistoricalPathResult; candidate?: PathWindow }) {
  const query = result.query;
  return <div className="table-scroll historical-path-point-table" tabIndex={0} role="region" aria-label={candidate ? '查询与参照21点原价差异表，可横向滚动' : '查询21点原价表，可横向滚动'}><table><thead><tr><th>来源步</th><th>查询日期 / 源序号</th><th>查询收盘原价</th><th>查询相对路径</th>{candidate && <><th>参照日期 / 源序号</th><th>参照收盘原价</th><th>参照相对路径</th><th>差异（查询−参照）</th></>}</tr></thead><tbody>
    {query.prices.map((price, step) => <tr key={step} className={candidate?.max_point_difference.step === step ? 'historical-path-largest' : undefined}><th>{step}{candidate?.max_point_difference.step === step && <small>首个最大差异</small>}</th>
      <td>{pointDate(result, query, step)}<small>源序号 {query.ordinals[step]}</small></td><td><code>{price}</code></td><td>{formatPathPercent(query.relative_path[step])}</td>
      {candidate && <><td>{pointDate(result, candidate, step)}<small>源序号 {candidate.ordinals[step]}</small></td><td><code>{candidate.prices[step]}</code></td><td>{formatPathPercent(candidate.relative_path[step])}</td><td>{percentagePoints(candidate.differences[step])}</td></>}</tr>)}
  </tbody></table></div>;
}

export function HistoricalPathLedger({ result }: { result: HistoricalPathResult }) {
  const [page, setPage] = useState(0), size = 50, pages = Math.max(1, Math.ceil(result.ledger.length / size));
  const status = (value: PathLedgerStatus) => value === null ? '无效' : value[0] !== null ? `选中第${value[0]}段` : value[1] !== null ? `与${result.groups[value[1]]}起的已选段重叠` : '其余';
  return <details className="calculation-note historical-path-ledger"><summary>查看候选资格与去重账本（{result.ledger.length}个）</summary>
    <p className="subtle">保留原来源组位置。无效窗列出首个失败日期；各栏重叠状态指向第一段相交的已选结果。分页仅影响展示。</p>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="候选账本，可横向滚动"><table><thead><tr><th>起止日期</th><th>资格 / 首个失败</th><th>路径距离 d²</th><th>端点差</th>{PATH_METHODS.map(method => <th key={method}>{labels[method]}</th>)}</tr></thead><tbody>
      {result.ledger.slice(page * size, (page + 1) * size).map(row => <tr key={row[0]}><th>{result.groups[row[0]]} → {result.groups[row[0] + 20]}</th><td>{row[1] === null ? '有效' : <>{pathReason(row[1])}<br />{row[7] === null ? '日期未知' : result.groups[row[7]]}</>}</td><td>{row[2] ?? '—'}</td><td>{row[3] === null ? '—' : percentagePoints(row[3])}</td>{[row[4], row[5], row[6]].map((item, i) => <td key={i}>{status(item)}</td>)}</tr>)}
    </tbody></table></div>
    <div className="button-group"><button type="button" disabled={page === 0} onClick={() => setPage(value => value - 1)}>上一页</button><span>第{page + 1} / {pages}页，每页最多50个候选</span><button type="button" disabled={page + 1 >= pages} onClick={() => setPage(value => value + 1)}>下一页</button></div>
  </details>;
}

export function HistoricalPathProvenance({ report }: { report: HistoricalPathEnvelope }) {
  return <details className="research-provenance historical-path-provenance"><summary>计算方法、数据版本与使用限制</summary>
    <p>基于当前保存的同一股票、同一数据版本回顾历史。先按所选终点截取完整来源前缀，历史窗口末点严格早于查询首点；查询与参照没有共享来源组。</p>
    <p>用精确整数与有理数比较路径平方距离，原价保留精确字符串。比例和距离按12位有效数字、半偶舍入显示；图形用显示值绘制，不参与排序。各栏取最多3个互不重叠的窗口，为贪心结果，未求全局最优组合。</p>
    <p>复权、公司行动、交易日历完整性、收盘闭合与历史当时可得性继续按来源保留未知。来源路径无法区分拆股与真实价格下跌。计算成功不代表可预测或可成交，页面没有候选的后续路径。</p>
    {!!Object.keys(report.result.nonprice_check_failures ?? {}).length && <details className="calculation-note"><summary>查看数量、金额或单位相关的来源检查失败</summary>
      <p>以下检查失败仍保留；本次只检索来源收盘路径，不把数量、金额或单位核验视为已通过。</p>
      <ul>{Object.entries(report.result.nonprice_check_failures ?? {}).map(([name, count]) => <li key={name}><code>{name}</code>：{count}项</li>)}</ul>
    </details>}
    <dl className="metadata-list"><dt>计算方法</dt><dd><code>{report.method_id}</code></dd><dt>结果标识</dt><dd><code>{report.analysis_id}</code></dd><dt>数据版本</dt><dd><code>{report.inputs[0].snapshot_id}</code></dd><dt>完整前缀查询标识</dt><dd><code>{report.inputs[0].query_id}</code></dd><dt>固定规则</dt><dd><code>{JSON.stringify(report.parameters)}</code></dd></dl>
    <ul className="subtle">{report.limitations.map((item, i) => <li key={i}>{pathReason(item)}</li>)}</ul>
  </details>;
}
