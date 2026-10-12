import { peerReason, peerSign } from './peer-neighbor-model.ts';
import type { PeerNeighborReport, PeerCell, PeerMember } from './peer-neighbor-model.ts';

interface PeerNeighborResultsProps {
  report: PeerNeighborReport;
  name: string;
  onOpen: (id: string, date: string) => void;
}

export function PeerNeighborResults({ report, name, onOpen }: PeerNeighborResultsProps) {
  const members = new Map(report.members.map(member => [member.snapshot_id, member]));
  const candidates = new Map(report.candidates.map(candidate => [candidate.snapshot_id, candidate]));
  const target = members.get(report.parameters.target_snapshot_id)!;
  const sameCoverage = report.candidates.every(candidate =>
    (candidate.previous.correlation !== null) === (candidate.current.correlation !== null),
  );

  function source(member: PeerMember) {
    return <details>
      <summary>原始端点与来源核对</summary>
      <p>数据版本 {member.snapshot_id}；批次 {member.batch_id}；完整来源查询 {member.query_id}</p>
      {!member.source_qualified &&
        <p>来源资格拒绝，端点与异常尚未评估；保留首个拒绝原因。</p>}
      {member.endpoints ? <>
        <p>共 {member.endpoints.length} 个使用端点。点击日期打开此版本至该日期。</p>
        <div className="button-group">
          {[0, 60, 120].map((index, boundary) =>
            <button
              type="button"
              key={index}
              onClick={() => onOpen(member.snapshot_id, report.used_dates[index])}
            >
              {['打开前窗起点', '打开共享边界', '打开当前截止'][boundary]}
            </button>,
          )}
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr>
              <th>来源日期</th><th>源序号</th><th>精确收盘／原文</th><th>限制</th>
            </tr></thead>
            <tbody>
              {member.endpoints.map(endpoint => <tr key={endpoint.date}>
                <td>
                  <button
                    type="button"
                    className="quiet"
                    onClick={() => onOpen(member.snapshot_id, endpoint.date)}
                  >{endpoint.date}</button>
                </td>
                <td>{endpoint.ordinal ?? '未知'}</td>
                <td>
                  <code>{endpoint.close_exact ?? '未知'}</code>
                  <small>原文 {endpoint.close_token ?? '未知'}</small>
                </td>
                <td>{endpoint.reasons.map(peerReason).join('；')}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </> : <p>使用窗口或来源未通过，端点尚未评估。</p>}
      {member.date_mismatch && <p>
        缺失日期 {member.date_mismatch.missing_count}：
        {member.date_mismatch.missing_examples.join('、') || '无'}；
        额外日期 {member.date_mismatch.extra_count}：
        {member.date_mismatch.extra_examples.join('、') || '无'}
        {member.date_mismatch.truncated ? '（各列前20例）' : ''}。
      </p>}
      {member.anomalies && <>
        <p>
          已扫来源异常 {member.anomalies.total} 条
          {member.anomalies.truncated ? '，列前20例' : ''}；
          {Object.entries(member.anomalies.counts).map(([code, count]) => `${code} ${count}`).join('；')}
        </p>
        <ul>
          {member.anomalies.examples.map(anomaly => <li key={anomaly.ordinal}>
            源序号{anomaly.ordinal} · {anomaly.date ?? '日期未知'} · {anomaly.scope} ·
            {' '}{anomaly.codes.map(peerReason).join('；')}
          </li>)}
        </ul>
      </>}
    </details>;
  }

  function cell(value: PeerCell, window: 'previous' | 'current') {
    if (!value.correlation) {
      return <>
        <strong>不可算</strong>
        <small>{peerReason(value.reason ?? 'source_panel_unavailable')}</small>
      </>;
    }
    const correlation = value.correlation;
    const sameDisplay = report.candidates.some(other =>
      other[window].correlation?.display === correlation.display && other[window].rank !== value.rank,
    );
    const boundaryLabels = {
      none: '非零且绝对值小于1',
      zero: '零',
      positive_one: '+1',
      negative_one: '−1',
    };
    return <>
      <strong>{correlation.display}</strong>
      <small>
        {peerSign(correlation)} · 第{value.rank}位
        {value.tie_size! > 1 ? `，${value.tie_size}项精确并列` : ''}
      </small>
      {sameDisplay && <small>显示值相同，精确位次不同</small>}
      <details>
        <summary>相关估计细节</summary>
        <code>{correlation.estimate}</code>
        <p>50位有限小数估计；精确边界：{boundaryLabels[correlation.exact_boundary]}。</p>
      </details>
    </>;
  }

  return <section className="panel research-panel">
    <div className="section-heading">
      <h2>双窗有符号相关{name ? ` · ${name}` : ''}</h2>
      <span>目标 {target.symbol ?? target.snapshot_id.slice(0, 8)}</span>
    </div>
    <p>简单源收盘变化 =（本端点收盘 − 前端点收盘）/ 前端点收盘。与既有双股对数变化相关口径不同，数值和排名可能不同。</p>
    <p>
      原组 {report.counts.selected} 只（含目标），候选 {report.counts.candidates} 只；
      初始来源资格通过 {report.counts.source_qualified}，121点完整 {report.counts.panel_complete}。全部原成员保留。
    </p>
    <p>
      前窗 {report.windows.previous.start ?? '未建立'} → {report.windows.previous.end ?? '未建立'}；
      当前窗 {report.windows.current.start ?? '未建立'} → {report.windows.current.end ?? '未建立'}。
      各60个来源区间，两窗共享边界价格，未共享变化行。
    </p>
    <p>
      前窗可算 {report.windows.previous.available}/{report.counts.candidates}，
      当前可算 {report.windows.current.available}/{report.counts.candidates}；
      位次分别只针对该窗可算候选。按当前精确有符号相关从高到低展示，精确并列同位次。
    </p>
    {!report.source_panel_complete && <p className="inline-note amber" role="status">
      完整组来源面板未齐，两窗均未计算。请核对下方每个原成员的具体缺失、额外日期或资格原因；
      没有自动删除成员或前移日期。{report.anchor.reasons.map(peerReason).join('；')}。
    </p>}
    {!sameCoverage && <p className="inline-note amber">
      两窗可算候选集合不同，请连同各窗分母核对位次；未生成名次升降摘要。
    </p>}
    {!!report.anchor.reasons.length && <p>
      目标截止前可定位日期数 {report.anchor.located_dates}；末日期 {report.anchor.last_date ?? '未知'}；
      最近日期例：{report.anchor.examples.join('、') || '无'}。
    </p>}
    <section>
      <h3>目标原始来源</h3>
      <p>{target.symbol ?? '身份未核实'} · {target.reasons.map(peerReason).join('；') || '121点来源核对完整'}</p>
      {source(target)}
    </section>
    <div className="table-scroll">
      <table>
        <thead><tr>
          <th>全部候选</th><th>当前60区间相关／位次</th><th>前60区间相关／位次</th>
          <th>相关变化</th><th>来源与回查</th>
        </tr></thead>
        <tbody>
          {report.windows.current.order.map(id => {
            const candidate = candidates.get(id)!;
            const member = members.get(id)!;
            const difference = candidate.difference;
            return <tr key={id}>
              <th>{member.symbol ?? '身份未核实'}<small>{id.slice(0, 8)}</small></th>
              <td>{cell(candidate.current, 'current')}</td>
              <td>{cell(candidate.previous, 'previous')}</td>
              <td>
                {difference ? <>
                  <strong>{difference.display}</strong>
                  <small>
                    {{ increased: '增加', decreased: '减少', equal: '精确相等' }[difference.direction]}
                    {difference.direction !== 'equal' && difference.display === '0.0000' ? '，显示未分辨' : ''}
                  </small>
                  <small>Δρ近似 {difference.estimate}</small>
                </> : '不可算'}
              </td>
              <td>
                <p>{member.reasons.map(peerReason).join('；') ||
                  (report.source_panel_complete ? '来源面板完整' : '本成员已核，整组面板未齐')}</p>
                {source(member)}
              </td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
    <p className="inline-note amber">当前明确自选组的来源回顾。A股、CNY与中国日线日期为范围假设；未接事件附件，公司行动与停牌覆盖、复权、交易日历、闭合及历史当时可得性均未核实。不自动认证行业、同伴、未来稳定、预测、套利或经济收益；实际省时与判断改善未验。</p>
    <details>
      <summary>回查与计算身份</summary>
      <p>打开指定数据版本至该日期，不自动聚焦源序号；前缀查询与本报告完整查询拥有不同query_id，缺失记录不以较早价替代。</p>
      <p>
        规则 {report.rule_version}；来源资格 {report.source_rule_version}；分析 {report.analysis_id}。
        符号、位次、并列、边界和增减由精确算术决定，小数仅显示估计；
        前端核对格式与请求身份，不独立认证原件或重算精确相关。
      </p>
    </details>
  </section>;
}
