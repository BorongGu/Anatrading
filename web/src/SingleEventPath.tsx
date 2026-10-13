import { researchReason } from './research-model.ts';
import { eventPathMembership } from './single-event-path.ts';
import type { EventPathProjection } from './single-event-path.ts';

export function SingleEventPath({ projection: p, partition, onClose }: { projection: EventPathProjection; partition: string; onClose: () => void }) {
  const e = p.event;
  return <section className="single-event-path" aria-label="事件日与后5个来源日期组">
    <div className="section-heading"><h4>事件日与后5个来源日期组</h4><button type="button" onClick={onClose}>收起六槽</button></div>
    <p>按本次研究响应的日期组顺序保留6个位置；日期间隔可以不连续，5步不代表5个交易日。</p>
    <dl className="event-path-identity"><dt>数据版本 V</dt><dd>{p.identity.snapshotId}</dd><dt>研究查询 Q</dt><dd>{p.identity.researchQueryId}</dd><dt>analysis_id</dt><dd>{p.identity.analysisId}</dd></dl>
    <details><summary>当前图表查询归属</summary><p className="event-path-identity">{p.identity.ownerQueryId}</p></details>
    <p>lookback：{p.parameters.lookback} · h=5 · test_start：{p.parameters.testStart ?? '未设置'}<br />请求截止：{p.parameters.requestedCutoff ?? '请求未限截止'} · 原评价截止 D：{p.parameters.evaluationAsOf ?? '无来源日期'}<br />事件 index（零基来源槽索引）：{e.index} · 事件日期：{e.date} · 源序号：{e.ordinal}</p>
    <p>原贪心去重 selected：{e.selected ? '是' : '否'}<br />原分段 partition：{e.partition}<br />原标签 label_status：{e.label_status}（{researchReason(e.label_status)}） · 原 label_reason：{e.label_reason === null ? '无' : researchReason(e.label_reason)}<br />原评价 evaluation_status：{e.evaluation_status}（{researchReason(e.evaluation_status)}）<br />原 label_end：{e.label_end ?? '未成熟，终点尚无来源槽'}</p>
    <p className="event-path-membership">{eventPathMembership(p, partition)}</p>
    <p>以上仅指事件样本；全部日期基线另有规则，可能包含该日期。</p>
    <p>已有 {p.slots.filter(slot => slot.exists).length}/6 个来源槽</p>
    <div className="table-scroll"><table><thead><tr><th>位置</th><th>来源日期</th><th>源序号</th><th>规范精确 close</th><th>原系列状态（含估计层）</th></tr></thead><tbody>{p.slots.map(slot => <tr key={slot.offset}>
      <th>t{slot.offset}{slot.offset === 0 ? ' · 事件日' : slot.offset === 5 ? ' · 五步位置' : ''}</th>
      <td>{slot.exists ? slot.date : '未知'}</td><td>{slot.exists ? slot.ordinal ?? '无唯一源序号' : '未知'}</td>
      <td className="event-path-price">{slot.exists ? slot.close ?? '∅（本槽未保留可解析收盘）' : '未知'}</td>
      <td>{slot.exists ? <>{researchReason(slot.status)}{slot.reason ? ` · ${researchReason(slot.reason)}` : ''}<br />响应保留值，不赋予标签资格</> : '原评价截止下尚无此来源槽'}</td>
    </tr>)}</tbody></table></div>
    <p>下列位置属于本次研究响应。当前原图范围可能不同；此处不自动定位原图。</p>
    <p className="inline-note">本表转述原响应及规范收盘值，未重验完整OHLC、复权、公司行动、历史可得性或成交条件。收盘序列不能确定柱内触发先后、可成交收益或未来路径。</p>
  </section>;
}
