import { GroupSourcePath } from './GroupSourcePath.tsx';
import type { DrawdownReport, DrawdownEpisode, DrawdownPoint, DrawdownExpected } from './drawdown-episode-model.ts';

const reasonLabels: Record<string, string> = {
  cutoff_missing: '缺少精确截止日',
  history_insufficient: '窗口历史不足',
  date_grid_mismatch: '成员的完整来源日期数组不一致',
  endpoint_integrity_unknown: '存在无法可靠定位日期的记录',
  global_source_conflict: '来源存在全局身份、调整或结构反证',
  local_source_conflict: '窗口内存在来源反证',
  unclassified_source_failure: '存在尚未归类的来源失败',
  duplicate_endpoint: '窗口内日期重复',
  unlocated_endpoint: '窗口内日期标签未通过核验',
  missing_endpoint: '缺少端点',
  missing_ohlc: '缺少完整开高低收',
  invalid_price: '原价无效',
  invalid_ohlc: '开高低收关系无效',
  endpoint_price_check_failed: '原价核对未通过',
  known_negative_source: '已知负来源样本',
  source_identity_conflict: '来源身份冲突',
  source_adjustment_conflict: '来源调整声明冲突',
  source_structure_failed: '来源结构核验未通过',
  unsupported_source_check: '来源核验范围未支持',
  scope_conflict: '来源范围不符',
  unsupported_source: '来源格式尚未支持',
  unsupported_period: '仅支持日线来源',
};

function Point({ name, point }: { name: string; point: DrawdownPoint | null }) {
  return (
    <li>
      <strong>{name}</strong>{' '}
      {point ? <>
        {point.date} · 窗口位置 {point.index} · 源序号 <code>{point.ordinal}</code>
        {' · 原收盘价 '}<code>{point.close_exact}</code>
      </> : '截至截止尚未恢复'}
    </li>
  );
}

function Episode({ title, episode, onOpen }: {
  title: string;
  episode: DrawdownEpisode | null;
  onOpen: (day: string) => void;
}) {
  return (
    <section>
      <h4>{title}</h4>
      {episode ? <>
        <p><strong>{episode.depth_display}</strong> · 已观察 {episode.observed_intervals} 个来源区间</p>
        {episode.observed_is_lower_bound ? (
          <p className="inline-note amber">
            截至截止尚未恢复，峰后已观察 {episode.observed_intervals} 个来源区间；完整恢复跨度未知。这是已观察下界。
          </p>
        ) : (
          <p>峰至恢复 {episode.peak_to_recovery_intervals} 个来源区间；谷至恢复 {episode.valley_to_recovery_intervals} 个来源区间。</p>
        )}
        <details>
          <summary>查看该段自己的原价证据与精确跌幅</summary>
          <ul>
            <Point name="窗口内峰" point={episode.peak} />
            <Point name="首次谷" point={episode.valley} />
            <Point name="首次恢复" point={episode.recovery} />
            <Point name="已观察终点" point={episode.observed_end} />
          </ul>
          <p>
            精确跌幅 {episode.depth_fraction.numerator}/{episode.depth_fraction.denominator}；百分数显示舍入至4位小数。
            峰至谷 {episode.peak_to_valley_intervals} 个来源区间；严格低于该峰的来源观测 {episode.underwater_observations} 个。
          </p>
        </details>
        <button type="button" className="quiet" onClick={() => onOpen(episode.observed_end.date)}>
          打开此版本至该段已观察终点
        </button>
      </> : <p>{title === '截止未恢复段' ? '截止没有未恢复段' : '窗口内无回撤'}</p>}
    </section>
  );
}

export function DrawdownEpisodeResults({ report, name, onOpen, expected }: {
  report: DrawdownReport;
  expected?: DrawdownExpected;
  name: string;
  onOpen: (id: string, cutoff: string) => void;
}) {
  const counts = report.counts;
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>{name || '所选成员'} · 回撤持续与恢复</h2>
        <span>日线来源价格描述</span>
      </div>
      <p>
        原组 {counts.selected}；来源有效 {counts.source_qualified}/{counts.selected}；
        自身窗口有效 {counts.window_qualified}/{counts.selected}；摘要可算 {counts.computable}/{counts.selected}。
      </p>
      <p>
        截止 {report.parameters.cutoff} · {report.parameters.lookback} 个来源区间。
        最深回撤段、已观察跨度最长段、截止未恢复段分别保留自身证据，可能指向同一段。
      </p>
      <p className="inline-note">
        范围假设为A股、CNY及中国日线来源日期。窗口前更高峰及开始时刻未知。
        相同来源日期无法证明交易日历完整；复权语义、公司行动与停牌覆盖、历史可得性尚未核实。
        当前成员回顾不代表历史行业。跌幅是来源价格描述，未提供经济收益或恢复预测。
      </p>
      <p>
        截止未恢复段的跌幅指该段至今最深跌幅；其完整恢复跨度未知。跨度按窗口位置计数，源序号仅供回查。
        最深按精确跌幅、最长按已观察跨度，各自真并列取较早峰；峰平台取下跌前最后一次峰，谷价并列取首次。
      </p>
      {!report.comparison_available && (
        <p className="inline-note amber">整组尚不可计算。保留全部成员及已核事实，各段摘要和段数均留空。</p>
      )}
      {report.members.map(member => (
        <article key={member.snapshot_id} className="drawdown-member">
          <h3>{member.symbol || '身份待核'} · 数据版本 <code>{member.snapshot_id.slice(0, 12)}</code></h3>
          <p>
            来源{member.source_qualified ? '已核' : '未通过'}；自身窗口{member.window_qualified ? '已核' : '未通过'}；
            实际窗口长度 {member.window_length === null ? '未评估' : `${member.window_length} 个来源观测`}；
            精确截止日{member.cutoff_present === null ? '未评估' : member.cutoff_present ? '存在' : '缺失'}。
          </p>
          {member.reasons.length > 0 && (
            <ul>{member.reasons.map(code => <li key={code}>{reasonLabels[code] ?? code} <code>{code}</code></li>)}</ul>
          )}
          {!report.comparison_available && member.window_qualified && (
            <p>本成员已核，整组日期与来源尚未齐全。下列日期及原价仅为本成员的来源证据。</p>
          )}
          {report.comparison_available ? <>
            <p>已开始 {member.episode_count} 段；已恢复 {member.recovered_count} 段；尚未恢复 {member.open_count} 段。</p>
            <div className="research-metrics">
              {([
                ['最深回撤段', member.deepest],
                ['已观察跨度最长段', member.longest_observed],
                ['截止未恢复段', member.current_open],
              ] as const).map(([title, episode]) => (
                <Episode
                  key={title}
                  title={title}
                  episode={episode}
                  onOpen={day => onOpen(member.snapshot_id, day)}
                />
              ))}
            </div>
          </> : <p>最深回撤段、已观察跨度最长段、截止未恢复段：待全组核验。</p>}
          <details>
            <summary>成员来源与核验事实</summary>
            <p>
              数据版本 <code>{member.snapshot_id}</code> · 批次 <code>{member.batch_id}</code> · 查询 <code>{member.query_id}</code>
            </p>
            <p>完整有界来源日期：{member.date_array === null ? '未评估' : member.date_array.join('、') || '无可定位窗口日期'}</p>
            {!report.comparison_available && member.endpoints && (
              <ul>
                <Point name="本成员窗口起点" point={member.endpoints[0]} />
                <Point name="本成员窗口终点" point={member.endpoints[member.endpoints.length - 1]} />
              </ul>
            )}
            {member.anomalies === null ? <p>来源早停，端点和异常计数尚未评估。</p> : <>
              <p>
                已核异常记录 {member.anomalies.total} 条；异常原因计数：
                {Object.entries(member.anomalies.counts).map(([code, count]) => `${code} ${count}`).join('、') || '无'}。
              </p>
              <ul>{member.anomalies.examples.map(example => (
                <li key={example.ordinal}>
                  日期 {example.date ?? '无法定位'} · 源序号 {example.ordinal} · {example.codes.join('、')}
                </li>
              ))}</ul>
              {member.anomalies.examples_truncated && <p>只展示前20条异常例，完整异常计数保留。</p>}
            </>}
          </details>
        </article>
      ))}
      {expected ? <GroupSourcePath report={report} expected={expected} onOpen={onOpen}/> : <details>
        <summary>组来源平均路径与共同最深段（回顾）</summary>
        <p>缺少本次已核请求，附件不可计算。原回撤结果保留。</p>
      </details>}
      <details>
        <summary>分析标识</summary>
        <code>{report.analysis_id}</code>
        <p>{report.method_id} · {report.rule_version}</p>
      </details>
    </section>
  );
}
