import { useState } from 'react';
import { explainReason, sortExplanation } from './two-group-model.ts';
import type { ExplanationReport } from './two-group-model.ts';
const number = (value: number | null | undefined) => value === null || value === undefined ? '不可算' : value.toPrecision(10);
export function TwoGroupResults({ report, onOpen }: { report: ExplanationReport; onOpen: (id: string, cutoff: string) => void }) {
  const [sort, setSort] = useState(false);
  return <section className="panel"><div className="section-heading"><h2>个股与参考组</h2><span>所选 {report.counts.selected} · 来源完整 {report.counts.source_complete} · 模型可算 {report.counts.model_available}</span></div>
    <p>用前60个来源区间的关系，解释当前变化；本次不会重新拟合。</p>
    <p>当前 {report.parameters.current_start} 至 {report.parameters.current_end}；训练 {report.training_dates[0] ?? '未知'} 至 {report.training_dates.at(-1) ?? '未知'}，要求60个所选源区间。单位：源价log变化（估计）。</p>
    <p className="inline-note amber">这是来源价格的回顾解释，不能据此判断新闻、噪声或买卖时机。</p>
    <details><summary>适用范围与解释限制</summary><p>历史当时可得性、交易日历、公司行动覆盖及价格经济语义未核实。所有成员共同漏日仍无法发现。各股未解释部分相互依赖，不能当作独立异常概率，也没有验证预测能力。</p></details>
    {report.reasons.length > 0 && <p role="status">{report.reasons.map(explainReason).join('；')}</p>}
    <label>显示顺序<select value={sort ? 'residual' : 'input'} onChange={e => setSort(e.target.value === 'residual')}><option value="input">输入顺序</option><option value="residual">绝对未解释变化降序</option></select></label><p>描述排序，未按波动风险标准化；不可算行保留在末尾。</p>
    <div className="table-scroll"><table><thead><tr><th>股票 / 参考组</th><th>价格变化（对数）</th><th>模型解释部分</th><th>未解释部分</th><th>限制与来源</th></tr></thead><tbody>{sortExplanation(report.members, sort).map(m => <tr key={m.snapshot_id}><td>{m.symbol} / {m.group}</td><td>{number(m.raw_change)}</td><td>{number(m.model?.explained)}</td><td>{number(m.model?.residual)}{m.model?.within_resolution && <small>数值分辨范围内（保留原值）</small>}</td><td>{m.reasons.map(explainReason).join('；') || '源价解释，经济语义未认证'}<details><summary>原始端点与拟合限制</summary><p>起点 {m.endpoints.start.date}，源序号 {m.endpoints.start.ordinal ?? '未知'}，收盘 {m.endpoints.start.close_exact ?? '未知'}；终点 {m.endpoints.end.date}，源序号 {m.endpoints.end.ordinal ?? '未知'}，收盘 {m.endpoints.end.close_exact ?? '未知'}</p>
      {m.model && <><p>原始变化 = 训练目标基线 {number(m.model.baseline)} + A相对训练均值贡献 {number(m.model.contributions[0])} + B相对训练均值贡献 {number(m.model.contributions[1])} + 未解释变化 {number(m.model.residual)}</p><p>训练标准差 A/B：{m.model.factor_sd.map(number).join(' / ')}；当前标准因子 A/B：{m.model.current_z.map(number).join(' / ')}；秩比 {number(m.model.rank_ratio)}；核对容差 {number(m.model.tolerance)}</p><p>留一当前组均值 A/B：{m.model.current_factor.map(number).join(' / ')}；冻结标准化系数 A/B：{m.model.gamma.map(number).join(' / ')}</p></>}
      <p>来源异常 {m.anomalies.total} 条{m.anomalies.truncated ? '（仅展示前20例）' : ''}；{Object.entries(m.anomalies.counts).map(([code, n]) => `${explainReason(code)} ${n}`).join('；')}</p><ul>{m.anomalies.examples.map(a => <li key={a.ordinal}>源序号 {a.ordinal} · {a.date ?? '日期未知'} · {a.scope} · {a.codes.map(explainReason).join('；')}</li>)}</ul><details><summary>训练及当前来源定位</summary><ol>{m.training_endpoints.map((p, i) => <li key={`${p.date}-${i}`}>{p.date} · 源序号 {p.ordinal ?? '未知'} · 收盘 {p.close_exact ?? '未知'} · {p.reasons.map(explainReason).join('；')}</li>)}</ol></details><p>计算规则 {report.rule_version}；数据版本 {m.snapshot_id}；查询 {m.query_id}</p></details><button type="button" onClick={() => onOpen(m.snapshot_id, report.parameters.current_end)}>打开原始记录</button></td></tr>)}</tbody></table></div>
  </section>;
}
