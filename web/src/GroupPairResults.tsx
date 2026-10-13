import { useState } from 'react';
import { groupPairReason } from './group-pair-model.ts';
import type { GroupPair, GroupPairMember, GroupPairReport } from './group-pair-model.ts';
import { peerSign } from './peer-neighbor-model.ts';

const PAGE_SIZE = 50;
const windowLabel = (window: 'previous' | 'current') => window === 'previous' ? '前60区间' : '当前60区间';
const memberLabel = (member: GroupPairMember) => `${member.symbol ?? '身份未核实'}（数据版本 ${member.snapshot_id}）`;
const boundaryLabels = {
  positive_one: '精确为+1', negative_one: '精确为−1', zero: '精确为0',
  none: '非精确边界（精确计算结果不等于0或±1；有限精度估计与显示可能舍入为这些值）',
};
const scopeLabels: Record<string,string> = {
  inside_interval: '候选窗口内', outside_interval: '候选窗口外',
  window_unavailable: '候选窗口未建立', unknown: '日期无法定位',
};
const sourceActions = ['打开前窗起点','打开共享边界','打开当前截止'];
export function groupPairPage(report: GroupPairReport, page: number) {
  const pages = Math.ceil(report.pairs.length / PAGE_SIZE);
  if (!Number.isSafeInteger(page) || page < 0 || page >= pages) throw new Error('invalid_pair_page');
  return { pairs: report.pairs.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE), pages };
}
export function GroupPairPage({ report, window, page, onPage, onSelect }: {
  report: GroupPairReport; window: 'previous' | 'current'; page: number;
  onPage: (page: number) => void; onSelect: (pair: GroupPair) => void;
}) {
  const { pairs, pages } = groupPairPage(report,page);
  const members = new Map(report.members.map(m => [m.snapshot_id,m]));
  return <>
    <p>全部 {report.pairs.length} 对 · 第 {page+1}/{pages} 页 · 每页固定50对，按版本ID排列。</p>
    <div className="button-group">
      <button type="button" aria-label={`上一页：${windowLabel(window)}`} disabled={page === 0} onClick={() => onPage(page-1)}>上一页</button>
      <button type="button" aria-label={`下一页：${windowLabel(window)}`} disabled={page+1 === pages} onClick={() => onPage(page+1)}>下一页</button>
    </div>
    <div className="table-scroll"><table><thead><tr><th>左成员</th><th>右成员</th><th>来源变化相关</th><th>回查</th></tr></thead>
      <tbody>{pairs.map(pair => {
        const cell = pair[window], left = members.get(pair.left_snapshot_id)!, right = members.get(pair.right_snapshot_id)!;
        return <tr key={`${pair.left_snapshot_id}:${pair.right_snapshot_id}`}>
          <th>{left.symbol ?? '身份未核实'}<small title={`数据版本 ${left.snapshot_id}`}>版本 {left.snapshot_id.slice(0,8)}…</small></th>
          <th>{right.symbol ?? '身份未核实'}<small title={`数据版本 ${right.snapshot_id}`}>版本 {right.snapshot_id.slice(0,8)}…</small></th>
          <td><strong>{cell.correlation?.display ?? '不可算'}</strong><small>{peerSign(cell.correlation)}</small>
            {cell.correlation ? <details><summary>估计与精确边界</summary><p>{cell.correlation.estimate}；精确边界 {boundaryLabels[cell.correlation.exact_boundary]}；50位有限小数估计。</p></details> : <>
              <small>{groupPairReason(cell.reason!)}</small>
              {cell.constant_members.map(id => <small key={id}>常量成员 {members.get(id)!.symbol ?? '身份未核实'}</small>)}
            </>}
          </td>
          <td><button type="button" aria-label={`查看双方来源：${windowLabel(window)}，${memberLabel(left)}与${memberLabel(right)}`} onClick={() => onSelect(pair)}>查看双方来源</button></td>
        </tr>;
      })}</tbody>
    </table></div>
  </>;
}
function WindowTable({ report, window, onSelect }: {
  report: GroupPairReport; window: 'previous' | 'current'; onSelect: (pair: GroupPair) => void;
}) {
  const [open,setOpen] = useState(false), [page,setPage] = useState(0);
  const w = report.windows[window];
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{windowLabel(window)}完整成对表 · 可算 {w.available}/{w.total}，不可算 {w.unavailable}</summary>
    <p>{w.start ?? '未建立'} → {w.end ?? '未建立'}。展开读取本次已返回的完整结果，不重新计算。</p>
    {open && <GroupPairPage report={report} window={window} page={page} onPage={setPage} onSelect={onSelect} />}
  </details>;
}
export function GroupPairSource({ member, commonDates, onOpen }: {
  member: GroupPairMember; commonDates: string[]; onOpen: (id: string, date: string) => void;
}) {
  return <section>
    <h4>{member.symbol ?? '身份未核实'}</h4>
    <p>数据版本 {member.snapshot_id}；批次 {member.batch_id}；完整来源查询 {member.query_id}</p>
    <p>{member.reasons.map(groupPairReason).join('；') || '本成员候选窗口核验完整'}</p>
    {!commonDates.length && <p>无共同窗口。以下仅为本成员各自候选日期回查。</p>}
    <div className="button-group">{commonDates.length === 121 && member.endpoints && [0,60,120].map((index,i) =>
      <button key={index} type="button" aria-label={`${sourceActions[i]}：${memberLabel(member)}，${commonDates[index]}`} onClick={() => onOpen(member.snapshot_id,commonDates[index])}>{sourceActions[i]}</button>)}</div>
    {member.endpoints ? <div className="table-scroll"><table>
      <thead><tr><th>来源日期</th><th>源序号</th><th>精确收盘／原文</th><th>限制</th></tr></thead>
      <tbody>{member.endpoints.map(p => <tr key={p.date}>
        <td><button type="button" aria-label={`${p.date}：${memberLabel(member)}`} onClick={() => onOpen(member.snapshot_id,p.date)}>{p.date}</button></td>
        <td>{p.ordinal ?? '未知'}</td><td>{p.close_exact ?? '未知'}<small>原文 {p.close_token ?? '未知'}</small></td>
        <td>{p.reasons.map(groupPairReason).join('；')}</td>
      </tr>)}</tbody>
    </table></div> : <p>来源资格未通过，端点尚未评估。</p>}
    {member.anomalies && <>
      <p>全来源异常 {member.anomalies.total} 条{member.anomalies.truncated ? '，仅列前20例' : ''}；{Object.entries(member.anomalies.counts).map(([code,count]) => `${groupPairReason(code)} ${count}`).join('；')}</p>
      <ul>{member.anomalies.examples.map(e => <li key={e.ordinal}>源序号 {e.ordinal} · {e.date ?? '未知日期'} · {Object.hasOwn(scopeLabels,e.scope) ? scopeLabels[e.scope] : e.scope} · {e.codes.map(groupPairReason).join('；')}</li>)}</ul>
    </>}
  </section>;
}
export function GroupPairResults({ report, name, onOpen }: {
  report: GroupPairReport; name: string; onOpen: (id: string,date: string) => void;
}) {
  const [selected,setSelected] = useState<GroupPair | null>(null);
  const members = new Map(report.members.map(m => [m.snapshot_id,m]));
  return <section className="panel research-panel">
    <h2>全成对双窗相关{name ? ` · ${name}` : ''}</h2>
    <p>原组 {report.counts.selected} 只 · 每窗全部 {report.counts.pairs} 对。简单源收盘变化 =（本价 − 前价）/ 前价；两窗各60变化，共享边界价格。</p>
    <p>各成员独立选取精确截止日及以前最后121个来源日期组，完整数组必须一致。全部成员与不可算对保留。</p>
    <p className="inline-note amber">价格计算只使用截止日及以前的窗口；所选完整数据版本在截止日后出现身份、复权或结构反证，也会关闭本次相关计算。历史当时可得性未核实。</p>
    {!report.source_panel_complete && <p className="inline-note amber" role="status">完整来源面板未齐，全部相关关闭。{report.grid_reasons.map(groupPairReason).join('；')}。不交集、不补齐、不回退。</p>}
    <details><summary>全部成员来源核验</summary><ul>{report.members.map(m => <li key={m.snapshot_id}>
      {m.symbol ?? '身份未核实'} · {m.snapshot_id} · 候选日期 {m.date_array.length} 个 · {m.reasons.map(groupPairReason).join('；') || '本成员核验完整'}
      {m.constant.previous === true && '；前窗变化为常量'}{m.constant.current === true && '；当前窗变化为常量'}
    </li>)}</ul></details>
    <WindowTable report={report} window="previous" onSelect={setSelected} />
    <WindowTable report={report} window="current" onSelect={setSelected} />
    {selected && <section aria-label="选中对来源回查">
      <h3>选中对来源回查</h3>
      <p>日期按钮将打开对应股票的个股研究；每次打开一方。</p><button type="button" onClick={() => setSelected(null)}>关闭回查</button>
      {[selected.left_snapshot_id,selected.right_snapshot_id].map(id => <GroupPairSource key={id} member={members.get(id)!} commonDates={report.used_dates} onOpen={onOpen} />)}
    </section>}
    <p className="inline-note">正相关只描述中心化线性关系，不表示每天同涨同跌；零相关不表示独立。常量变化的相关未定义，包含恒定非零变化。无排名、差值或自动分组。</p>
    <p className="inline-note amber">当前明确成员的来源回顾。交易日历、复权、公司行动、闭合与历史当时可得性未核实；A股/CNY为范围假设。不认证预测、协整、套利或经济收益。性能、实际人效和金融效果未验。</p>
    <details><summary>计算身份与回查边界</summary><p>{report.method_id} · {report.rule_version} · {report.source_rule_version} · {report.analysis_id}</p>
      <p>打开原数据版本至指定日期，不自动聚焦源序号。前缀查询与完整来源查询的query_id不同。哈希只验证响应自洽，前端不独立认证原件或重算Pearson相关。</p>
    </details>
  </section>;
}
