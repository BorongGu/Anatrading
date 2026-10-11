import { formatPercent, researchReason } from './research-model.ts';
import { Metric, ResearchProvenance } from './ResearchResults.tsx';
import type { ResearchEnvelope, UniverseResult } from './research-types.ts';

export function UniverseResults({ report, cutoff, lookback, name, onOpen }: { report: ResearchEnvelope<UniverseResult>; cutoff: string; lookback: number; name: string; onOpen: (id: string, cutoff: string) => void }) {
  const result = report.result; const b = result.breadth;
  return <section className="panel research-panel"><div className="section-heading"><div><span className="eyebrow">所选股票样本</span><h2>{name.trim() || '多股研究结果'}</h2></div><span className="badge">截止 {cutoff}</span></div>
    <div className="metric-grid four"><Metric label="所选证券" value={String(b.selected)} detail={`${b.cutoff_present} 只在截止当日有记录`} /><Metric label="有效期末覆盖" value={`${b.cutoff_valid} / ${b.selected}`} detail="分母为全部所选证券" />
      <Metric label="正动量占比" value={formatPercent(b.positive_momentum_fraction, 1)} detail={`${b.positive} 只为正 / ${b.momentum_valid} 只动量有效`} accent /><Metric label="动量有效覆盖" value={`${b.momentum_valid} / ${b.selected}`} detail={`无结果 ${b.selected - b.momentum_valid} 只`} /></div>
    <div className="section-heading table-heading"><h3>按动量从高到低</h3><span className="subtle">{lookback} 个来源区间 · 并列同名次</span></div>
    <div className="table-scroll universe-table"><table><thead><tr><th>名次</th><th>证券</th><th>动量</th><th>收益波动</th><th>最大回撤</th><th>实际来源区间</th><th>操作</th></tr></thead><tbody>{result.members.map(member => <tr key={member.snapshot_id}>
      <td>{member.rank ?? '—'}</td><th><strong>{member.identity.symbol}</strong><small>{member.identity.market === 'CN_A' ? 'A 股' : member.identity.market} · {researchReason(member.identity.qualification)}</small></th>
      <td><strong>{formatPercent(member.momentum)}</strong>{member.momentum_reason && <small className="amber">{researchReason(member.momentum_reason)}</small>}</td>
      <td>{formatPercent(member.volatility)}{member.volatility_reason && <small className="amber">{researchReason(member.volatility_reason)}</small>}</td>
      <td>{formatPercent(member.max_drawdown)}{member.max_drawdown_reason && <small className="amber">{researchReason(member.max_drawdown_reason)}</small>}</td>
      <td>{member.start_date ?? '—'} → {member.end_date ?? '—'}<small>{member.n_prices} 个价格 · {member.n_returns} 个收益</small></td><td><button className="quiet" onClick={() => onOpen(member.snapshot_id, cutoff)}>查看个股 ↗</button></td>
    </tr>)}</tbody></table></div>
    <div className="explanation-grid"><div><h3>三个原始分项</h3><p>动量 = 当前收盘价 ÷ 前 {lookback} 条记录的收盘价 − 1。波动为这些相邻对数收益的样本标准差，不年化。回撤是窗口内相对此前高点的最大跌幅。</p></div><div><h3>覆盖决定怎样解释广度</h3><p>缺截止当日价不回退到各自末日。各证券的实际窗口起点可能不同。当前所选成员做历史回顾存在选择偏差，不能当作历史全市场或行业指数。</p></div></div>
    <details className="calculation-note"><summary>各指标的有效与缺失数量</summary><div className="table-scroll"><table><thead><tr><th>指标</th><th>有效</th><th>缺失</th><th>无效</th><th>历史不足</th></tr></thead><tbody>{Object.entries(b.metrics).map(([key, metric]) => <tr key={key}><th>{{ momentum: '动量', volatility: '波动', max_drawdown: '回撤' }[key] ?? key}</th><td>{metric.eligible}</td><td>{metric.missing}</td><td>{metric.invalid}</td><td>{metric.short_history}</td></tr>)}</tbody></table></div></details>
    <ResearchProvenance report={report} />
  </section>;
}
