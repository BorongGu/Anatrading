import { groupPercent, groupReason, groupSign } from './group-endpoint-model.ts';
import type { ExactRatio, GroupEndpointReport } from './group-endpoint-model.ts';
const fraction = (v: ExactRatio | null) => v ? `${v.numerator}/${v.denominator}` : '不可算';
export function GroupEndpointResults({report,name,onOpen}:{report:GroupEndpointReport;name:string;onOpen:(id:string,date:string)=>void}) {
  const c=report.counts, p=report.parameters;
  return <section className="panel"><div className="section-heading"><h2>共同端点单组{name ? ` · ${name}` : ''}</h2><span>原组 {c.selected} · 有效 {c.valid} · 不可算 {c.missing}</span></div>
    <p>共同起点 {p.start_date} → 终点 {p.end_date}。源收盘变化 = 终点收盘 / 起点收盘 − 1。</p>
    <p>精确正／零／负：{report.sign_counts.positive}／{report.sign_counts.zero}／{report.sign_counts.negative}，合计为有效 {c.valid} 只。覆盖 {c.valid}/{c.selected}（{groupPercent(report.coverage)}）。</p>
    <p>有效成员中的正／零／负比例：{groupPercent(report.sign_proportions.positive)}／{groupPercent(report.sign_proportions.zero)}／{groupPercent(report.sign_proportions.negative)}。比例分母为有效 {c.valid} 只。</p>
    {c.valid<c.selected&&<p className="inline-note amber" role="status">原组尚有 {c.missing} 只不可算，完整组均值、中位数、Q1、Q3均留空；全部原成员和已核出的原因保留。</p>}
    <div className="table-scroll"><table><thead><tr><th>完整组均值</th><th>中位数</th><th>Q1</th><th>Q3</th></tr></thead><tbody><tr>{(['mean','median','q1','q3'] as const).map(key=><td key={key} title={fraction(report.summary[key])}>{groupPercent(report.summary[key])}</td>)}</tr></tbody></table></div>
    <p className="subtle">完整组分布分母固定为 {c.selected}；分位数采用精确Type7。正负与零按原分数判断，百分比显示保留4位小数。</p>
    <p className="inline-note amber">当前成员的来源价格回顾，A股、CNY、中国日线日期均为范围假设。公司行动覆盖未知，未提供事件附件；复权、历史当时可得性、交易日历和收盘闭合均未核实。日期间隔可跨多个来源日期，不能据此推断相邻交易日收益、行业指数、组合收益或预测优势。</p>
    {report.diagnostic_only&&<p role="status">存在停牌或公司行动诊断，源值与诊断均保留。</p>}
    <div className="table-scroll"><table><thead><tr><th>证券／数据版本</th><th>源收盘变化</th><th>精确符号</th><th>端点与限制</th></tr></thead><tbody>{report.members.map(m=><tr key={m.snapshot_id}>
      <td>{m.symbol??'身份未核实'}<small>{m.snapshot_id.slice(0,8)}</small></td><td>{groupPercent(m.source_change)}</td><td>{groupSign(m.source_change)}</td>
      <td>{m.reasons.map(groupReason).join('；')||'源价格算术，经济语义未认证'}
        {m.evaluation==='not_evaluated'&&<p>来源资格已拒绝，端点和异常尚未检查；仅列首个来源拒绝原因。</p>}
        <details><summary>原始端点与精确分数</summary>
          {m.endpoints?<><p>起点 {m.endpoints.start.date} · 源序号 {m.endpoints.start.ordinal??'未知'} · 精确收盘 {m.endpoints.start.close_exact??'未知'} · 原文 {m.endpoints.start.close_token??'未知'} · {m.endpoints.start.reasons.map(groupReason).join('；')}</p><p>终点 {m.endpoints.end.date} · 源序号 {m.endpoints.end.ordinal??'未知'} · 精确收盘 {m.endpoints.end.close_exact??'未知'} · 原文 {m.endpoints.end.close_token??'未知'} · {m.endpoints.end.reasons.map(groupReason).join('；')}</p></>:<p>端点未检查。</p>}
          <p>精确来源变化（比值）：{fraction(m.source_change)}</p>
          {m.anomalies&&<><p>来源异常 {m.anomalies.total} 条{m.anomalies.truncated?'（列前20例）':''}；{Object.entries(m.anomalies.counts).map(([code,n])=>`${code} ${n}`).join('；')}</p><ul>{m.anomalies.examples.map(a=><li key={a.ordinal}>源序号 {a.ordinal} · {a.scope} · {a.codes.join('；')}</li>)}</ul></>}
          <p>数据版本 {m.snapshot_id}；批次 {m.batch_id}；完整来源查询 {m.query_id}</p>
        </details>
        <button type="button" onClick={()=>onOpen(m.snapshot_id,p.start_date)}>打开此版本至起点日期</button><button type="button" onClick={()=>onOpen(m.snapshot_id,p.end_date)}>打开此版本至终点日期</button>
      </td></tr>)}</tbody></table></div>
    <details><summary>计算身份与回查范围</summary><p>规则 {report.rule_version}；来源资格 {report.source_rule_version}；分析 {report.analysis_id}</p><p>回查打开指定版本至该日期的记录，不自动聚焦源序号。前缀查询与这里的完整来源查询拥有不同查询身份；缺失端点不会用较早记录替代。</p><p>完整组精确统计：均值 {fraction(report.summary.mean)}；中位数 {fraction(report.summary.median)}；Q1 {fraction(report.summary.q1)}；Q3 {fraction(report.summary.q3)}。</p></details>
  </section>;
}
