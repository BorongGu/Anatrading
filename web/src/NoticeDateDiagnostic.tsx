import { useEffect, useState } from 'react';
import { buildNoticeDiagnostic, noticeReferenceExchanges } from './notice-date-model.ts';
import type { NoticeDate, NoticeDiagnostic, NoticeExchangeResult, NoticeMember } from './notice-date-model.ts';
import type { GroupPairReport } from './group-pair-model.ts';
import { groupPairReason } from './group-pair-model.ts';

const PAGE_SIZE = 50;
const exchangeLabel = { SSE:'上交所', SZSE:'深交所' };
// Optional reference metadata must never take down the original 051 readout.
// Null means invalid/unavailable; the empty string means valid but no listed facts.
function coverageNames(reference?: unknown): string | null {
  try { return noticeReferenceExchanges(reference).map(e=>exchangeLabel[e]).join('、'); }
  catch { return null; }
}

const unknownLabels: Record<string,string> = {
  exchange_claim_unverified:'来源交易所声明未核实', endpoint_date_unverified:'存在未可靠定位的端点日期',
  date_array_empty:'来源日期数组为空', cutoff_not_enumerated:'日期数组未包含原截止日',
};
function findingLabel(row: NoticeDate, n: number) {
  if (row.finding === 'closed_present') return '来源日期与已核休市计划不一致';
  if (row.finding === 'all_absent') return n === 1 ? '该成员在公告计划开市日无来源日期（候选）' : '该所声明已核的全部成员无来源日期（候选）';
  if (row.finding === 'some_absent') return '部分成员无来源日期；不认定全部缺席';
  return row.planned === 'conflict' ? '公告事实冲突，未判定' : row.unknown.length ? '含未判定成员' : '本日未发现相应差异';
}
export function noticeDatePage(dates: NoticeDate[], page: number) {
  const pages = Math.max(1,Math.ceil(dates.length/PAGE_SIZE));
  if (!Number.isSafeInteger(page) || page<0 || page>=pages) throw new Error('invalid_notice_page');
  return {rows:dates.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE),pages};
}
function MemberDateLinks({ids,members,date,onOpen,kind}: {
  ids:string[];members:Map<string,NoticeMember>;date:string;onOpen:(id:string,date:string)=>void;kind:'present'|'absent'|'unknown';
}) {
  if (!ids.length) return null;
  const label = {present:'有可靠日期',absent:'范围内无日期',unknown:'未判定'}[kind];
  return <details><summary>{label} {ids.length} 个成员</summary>
    {kind==='absent' && <p>该日期无已定位标签；截至该日的回查可能结束于更早来源日。</p>}
    <ul>{ids.map(id=><li key={id}>{members.get(id)?.symbol ?? '身份未核实'} · 数据版本 {id}
      {kind!=='unknown' && <button type="button" onClick={()=>onOpen(id,date)} aria-label={`打开该版本截至此日：${id}，${date}`}>打开该版本截至此日</button>}
    </li>)}</ul>
  </details>;
}
export function NoticeExchangeTable({result,diagnostic,page,onPage,onOpen}: {
  result:NoticeExchangeResult;diagnostic:NoticeDiagnostic;page:number;onPage:(page:number)=>void;onOpen:(id:string,date:string)=>void;
}) {
  const {rows,pages}=noticeDatePage(result.dates,page),members=new Map(diagnostic.members.map(m=>[m.snapshot_id,m]));
  return <>
    <p>完整 {result.dates.length} 个已列日期 · 第 {page+1}/{pages} 页 · 每页50行。分页不删成员或差异。</p>
    <div className="button-group">
      <button type="button" disabled={page===0} onClick={()=>onPage(page-1)} aria-label={`${exchangeLabel[result.exchange]}公告日期上一页`}>上一页</button>
      <button type="button" disabled={page+1===pages} onClick={()=>onPage(page+1)} aria-label={`${exchangeLabel[result.exchange]}公告日期下一页`}>下一页</button>
    </div>
    <div className="table-scroll"><table><thead><tr><th>公告日期</th><th>计划与核对</th><th>固定成员分母</th><th>依据与原版本回查</th></tr></thead>
      <tbody>{rows.map(row=><tr key={row.date}>
        <th>{row.date}</th><td>{row.planned==='closed'?'明示计划闭市':row.planned==='open'?'命名恢复开市日':'事实冲突'}<small>{findingLabel(row,result.members.length)}</small></td>
        <td>交易所声明已核为{result.exchange}的 {result.members.length} 个成员<small>有日期 {row.present.length} · 无日期 {row.absent.length} · 未判定 {row.unknown.length}</small></td>
        <td>{row.evidence.map(id=>{const n=diagnostic.reference.notices.find(n=>n.id===id)!;return <p key={id}><a href={n.url} target="_blank" rel="noopener noreferrer">{n.document_id}</a> · 声明发布 {n.publication_date}</p>;})}
          {(['present','absent','unknown'] as const).map(kind=><MemberDateLinks key={kind} ids={row[kind]} members={members} date={row.date} onOpen={onOpen} kind={kind}/>)}
        </td>
      </tr>)}</tbody></table></div>
  </>;
}
function ExchangeReadout({result,diagnostic,onOpen}: {result:NoticeExchangeResult;diagnostic:NoticeDiagnostic;onOpen:(id:string,date:string)=>void}) {
  const [page,setPage]=useState(0);
  return <section aria-label={`${exchangeLabel[result.exchange]}有限公告日期`}>
    <h4>{exchangeLabel[result.exchange]} · 交易所声明已核为{result.exchange}的 {result.members.length} 个成员</h4>
    <p>明示闭市 {result.closed_dates} 日 · 命名开市 {result.open_dates} 日 · 冲突 {result.conflict_dates} 日 · 本范围未覆盖 {result.uncovered_dates} 个自然日。</p>
    {!result.members.length && <p>未选择该所声明已核的成员，不运行比较。</p>}
    {!result.covered_dates && <p>该所日期计划本包未覆盖，未作通过判断。</p>}
    {!!result.members.length && !!result.covered_dates && <>
      <p>成员日期状态：有可靠日期 {result.present} · 范围内无日期 {result.absent} · 未判定 {result.unknown}。冲突日期另列，不计入上述状态量。</p>
      <NoticeExchangeTable result={result} diagnostic={diagnostic} page={page} onPage={setPage} onOpen={onOpen}/>
    </>}
  </section>;
}
export function NoticeDateReadout({diagnostic:d,onOpen}: {diagnostic:NoticeDiagnostic;onOpen:(id:string,date:string)=>void}) {
  const coverage=coverageNames(d.reference);
  return <section aria-label="有限公告日期核对结果">
    <p>按本次公告参考回顾 · {d.window ? `${d.window[0]} → ${d.window[1]}` : '与参考范围无交叠'}。原选 {d.selected} 个成员，交易所声明未核实 {d.unknown_members.length} 个。</p>
    <p className="inline-note amber">仅按来源声明的交易所和现有A股/日期基准假设核对；未认证证券主数据身份、实际交易、个股应有行情或历史当时可得性。候选只覆盖各所声明已核的成员，未核身份成员不能算入“全部缺席”。</p>
    <p>{d.status==='no_overlap'?'原来源窗口与本包范围无交叠，未评估。':d.status==='not_evaluated'?'没有可比较的成员日期单元，未评估。':d.differences?`本次有 ${d.differences} 个所内公告日期值得回查；保留全部成员和原失败。`:'本次已核公告日期内未发现相应差异；覆盖与未判定状态见下。'}</p>
    {d.exchanges.map(e=><ExchangeReadout key={`${d.attachment_id}:${e.exchange}`} result={e} diagnostic={d} onOpen={onOpen}/>)}
    <details><summary>全部成员日期证据与未判定原因</summary><ul>{d.members.map(m=><li key={m.snapshot_id}>
      {m.symbol ?? '身份未知'} · 数据版本 {m.snapshot_id} · 交易所声明 {m.exchange ?? '未核实'}
      <p>原候选范围 {m.source_span?.join(' → ') ?? '未建立'}；可判缺席范围 {m.absence_span?.join(' → ') ?? '未建立'}；可靠日期 {m.present.length} 个。</p>
      <p>{m.unknown_reasons.map(r=>unknownLabels[r] ?? groupPairReason(r)).join('；') || '本成员内部日期枚举可核对；原价格资格保持原状'}</p>
    </li>)}</ul></details>
    <details><summary>公告参考与独立附件身份</summary>
      <p>{d.reference.version} · 静态参考范围 {d.reference.scope.join(' → ')} · Asia/Shanghai · 归档复核 {d.reference.reviewed_on}</p>
      <p>临时事件与更正全集未知；命名恢复开市仅核对该单日。公告计划不保证实际全日开市或个股成交。</p>
      <p>仅校验本地派生参考内容hash；原件hash记录归档时字节身份，本次没有重新读取或认证官方原件。</p>
      <p>{coverage===null?'公告参考覆盖信息暂不可用。':coverage?`本参考含${coverage}有限公告日期；其它日期仍未覆盖。`:'本参考未列出交易所公告日期。'}</p>
      <p>附件 {d.attachment_id}；原报告 {d.parent_analysis_id}；参考 {d.reference_hash}</p>
      {d.reference.schema==='explicit-notice-reference-v1' ? <p>已核事实 {d.reference.accepted_facts_sha256}（v1归档参考）</p> : <>
        <p>原件历史内容身份与known_at未知；获取时间不表示历史当时可得。审查hash仅标识归档审查记录，本包未附审查全文，也未实时核验官方来源。</p>
        <ul>{Object.entries(d.reference.evidence_by_exchange).map(([exchange,evidence])=><li key={exchange}>{exchange} · 已核事实 {evidence.accepted_facts_sha256} · 归档审查 {evidence.review_sha256}</li>)}</ul>
      </>}
      <ul>{d.reference.notices.map(n=><li key={n.id}><a href={n.url} target="_blank" rel="noopener noreferrer">{n.document_id}</a> · {n.exchange} · 声明发布 {n.publication_date} · 归档原字节 SHA256 {n.original_sha256}{'retrieved_at_utc' in n && <> · 获取时间 {String(n.retrieved_at_utc)}</>}</li>)}</ul>
    </details>
  </section>;
}
function Calculation({report,onOpen}: {report:GroupPairReport;onOpen:(id:string,date:string)=>void}) {
  const [attempt,setAttempt]=useState(0);
  const [state,setState]=useState<{report:GroupPairReport;diagnostic?:NoticeDiagnostic;error?:string}|null>(null);
  useEffect(()=>{
    let active=true;
    void buildNoticeDiagnostic(report).then(diagnostic=>{if(active)setState({report,diagnostic});},error=>{
      if(active)setState({report,error:error instanceof Error?error.message:'notice_diagnostic_failed'});
    });
    return ()=>{active=false;};
  },[report,attempt]);
  if (state?.report!==report) return <p role="status">正在核对本地参考与日期身份…</p>;
  if (state.error) return <div role="alert"><p>公告日期附件未生成：{state.error}。原报告保持可用；未输出零差异结论。</p><button type="button" onClick={()=>{setState(null);setAttempt(a=>a+1);}}>重试本地核对</button></div>;
  return state.diagnostic ? <NoticeDateReadout diagnostic={state.diagnostic} onOpen={onOpen}/> : null;
}
export function NoticeDateDiagnostic({report,onOpen}: {report:GroupPairReport;onOpen:(id:string,date:string)=>void}) {
  const [open,setOpen]=useState(false);
  const coverage=coverageNames();
  return <details onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>已核公告日期核对（回顾）</summary>
    <p>{coverage===null?'公告参考覆盖信息暂不可用；展开后可查看核对失败原因并重试。':coverage?`本包仅含${coverage}有限公告日期，其它日期未覆盖。`:'本包未列出交易所公告日期。'}不生成完整交易日历，不改原窗口或来源资格。</p>
    {open && <Calculation report={report} onOpen={onOpen}/>}
  </details>;
}
