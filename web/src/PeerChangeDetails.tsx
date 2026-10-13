import { useState } from 'react';
import type { SyntheticEvent } from 'react';
import type { PeerNeighborReport } from './peer-neighbor-model.ts';
import { validatePeerSourcePair } from './peer-source-pair.ts';
import type { PeerSourcePair } from './peer-source-pair.ts';
import { peerChangeWindow, changeDisplay, changeSign } from './peer-change-details.ts';

interface Props { report: PeerNeighborReport; peerId: string; onOpen: (id: string, date: string) => void }
type Pair = Extract<PeerSourcePair, { available: true }>;
interface WindowProps extends Props { pair: Pair; offset: 0 | 60 }
export function syncDetailsOpen(event: SyntheticEvent<HTMLDetailsElement>, setOpen: (open: boolean) => void) {
  if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
}
/** The closed entry does not even inspect source properties. */
export function PeerChangeDetails(props: Props) {
  const [open, setOpen] = useState(false);
  return <details className="peer-change-details" onToggle={event => syncDetailsOpen(event, setOpen)}>
    <summary>变化差异</summary>
    {open && <PeerChangeContent {...props} />}
  </details>;
}
export function PeerChangeContent(props: Props) {
  const pair = validatePeerSourcePair(props.report, props.peerId);
  if (!pair.available) return <p>{{
    source_panel_unavailable: '完整组来源未齐，变化差异不可用。',
    invalid_member_identity: '目标或同伴身份未通过核对，变化差异不可用。',
    invalid_source_endpoints: '121个同日精确端点未通过核对，变化差异不可用。',
  }[pair.reason]}</p>;
  return <>
    <p>按同期源收盘价变化对比，差值为目标减同伴。差异大小不表示排名原因。</p>
    {([0, 60] as const).map(offset => <PeerChangeWindow key={offset} {...props} pair={pair} offset={offset} />)}
  </>;
}
function PeerChangeWindow(props: WindowProps) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => syncDetailsOpen(event, setOpen)}>
    <summary>{props.offset === 0 ? '前60区间' : '当前60区间'}：{props.pair.dates[props.offset]} → {props.pair.dates[props.offset + 60]}</summary>
    {open && <PeerChangeRows {...props} />}
  </details>;
}
/** Pure content is separately testable; it is mounted only for an open window. */
export function PeerChangeRows({ report, peerId, pair, offset, onOpen }: WindowProps) {
  const rows = peerChangeWindow(pair, offset);
  const targetId = report.parameters.target_snapshot_id;
  const target = report.members.find(member => member.snapshot_id === targetId)!;
  const peer = report.members.find(member => member.snapshot_id === peerId)!;
  return <>
    <p>按绝对差从大到小列出全部60区间，同值按日期排列；显示值已舍入，精确值可展开核对。</p>
    <div className="table-scroll"><table><thead><tr>
      <th>前日期 → 结束日期</th><th>目标简单变化（%）</th><th>同伴简单变化（%）</th><th>目标减同伴（百分点）</th><th>来源与精确计算</th>
    </tr></thead><tbody>{rows.map(row => <tr key={row.date}>
      <td>{row.previousDate} → {row.date}</td>
      {([['target', '%'], ['peer', '%'], ['difference', '百分点']] as const).map(([field, unit]) =>
        <td key={field}>{changeDisplay(row[field], unit)}<small>{changeSign(row[field])}</small></td>)}
      <td>
        <button type="button" onClick={() => onOpen(targetId, row.date)}>打开目标至{row.date}</button>
        <button type="button" onClick={() => onOpen(peerId, row.date)}>打开同伴至{row.date}</button>
        <details><summary>精确计算</summary>
          <p>规范源收盘：目标 {target.endpoints![row.index - 1].close_exact} → {target.endpoints![row.index].close_exact}；同伴 {peer.endpoints![row.index - 1].close_exact} → {peer.endpoints![row.index].close_exact}</p>
          <p>以下为精确比值分数（未约分）；百分比与百分点显示均为对应分数乘100后舍入。</p>
          <ul>{([['target', '目标变化'], ['peer', '同伴变化'], ['difference', '目标减同伴']] as const).map(([field, label]) =>
            <li key={field}>{label}：<code>{row[field].numerator.toString()} / {row[field].denominator.toString()}</code></li>)}</ul>
        </details>
      </td>
    </tr>)}</tbody></table></div>
  </>;
}
