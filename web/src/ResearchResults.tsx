import { formatEstimate, formatPercent, researchReason } from './research-model.ts';
import type { ResearchEnvelope } from './research-types.ts';

export function Metric({ label, value, detail, reason, accent = false }: {
  label: string; value: string; detail?: string; reason?: string | null; accent?: boolean;
}) {
  return <div className={`research-metric${accent ? ' metric-accent' : ''}`}><span>{label}</span><strong>{value}</strong>
    {reason ? <small className="amber">{researchReason(reason)}</small> : detail && <small>{detail}</small>}</div>;
}

export function ResearchProvenance({ report }: { report: ResearchEnvelope<unknown> }) {
  return <details className="research-provenance"><summary>计算方法、数据版本与使用限制</summary>
    <p>基于当前保存的数据版本做历史回顾。逐时点计算只使用当时及此前记录，无法证明这些导出数据在历史当时已经可得。复权口径与缺失交易日按来源说明解释。</p>
    <p>模型估计使用浮点数；原始价格和金额保留精确字符串。计算成功不代表具有预测能力。</p>
    <dl className="metadata-list"><dt>计算方法</dt><dd><code>{report.method_id}</code></dd><dt>结果标识</dt><dd><code>{report.analysis_id}</code></dd>
      <dt>计算参数</dt><dd><code>{JSON.stringify(report.parameters)}</code></dd></dl>
    {report.inputs.map((input, index) => <p key={input.snapshot_id} className="subtle">输入 {index + 1}：<code>{input.snapshot_id}</code><br />查询：<code>{input.query_id}</code></p>)}
    {!!report.limitations.length && <ul className="subtle">{report.limitations.map((item, index) => <li key={index}>{researchReason(item)}</li>)}</ul>}
  </details>;
}

// This chart only lays out estimates already returned by the server. Missing
// estimates break paths; it never fills records or computes a trading signal.
export function EstimatePlot({ series, label, percent = false }: {
  series: { name: string; color: string; points: { date: string; value: number | null; reset?: boolean }[] }[];
  label: string; percent?: boolean;
}) {
  const all = series.flatMap(item => item.points.flatMap(point => typeof point.value === 'number' && Number.isFinite(point.value) ? [point.value] : []));
  if (!all.length) return <p className="plot-empty">尚无可绘制估计，查看相邻的计算状态。</p>;
  let low = Math.min(...all); let high = Math.max(...all);
  if (low === high) { const pad = Math.max(Math.abs(low) * 0.01, 0.001); low -= pad; high += pad; }
  const count = Math.max(...series.map(item => item.points.length));
  const x = (index: number) => 68 + index / Math.max(1, count - 1) * 610;
  const y = (value: number) => 16 + (high - value) / (high - low) * 116;
  const format = percent ? formatPercent : formatEstimate;
  const dates = series[0]?.points ?? [];
  return <figure className="estimate-figure"><figcaption>{series.map(item => <span key={item.name}><i style={{ background: item.color }} />{item.name}</span>)}</figcaption>
    <svg className="estimate-chart" viewBox="0 0 700 164" role="img" aria-label={label}>
      {[high, (low + high) / 2, low].map((value, index) => <g key={index}><line x1="68" x2="678" y1={y(value)} y2={y(value)} stroke="var(--line)" /><text x="58" y={y(value) + 4} textAnchor="end">{format(value)}</text></g>)}
      {series.map(item => {
        let connected = false;
        const path = item.points.map((point, index) => {
          if (point.value === null || !Number.isFinite(point.value)) { connected = false; return ''; }
          const command = connected && !point.reset ? 'L' : 'M'; connected = true;
          return `${command}${x(index).toFixed(2)},${y(point.value).toFixed(2)}`;
        }).join(' ');
        return <path key={item.name} d={path} stroke={item.color} fill="none" strokeWidth="2" />;
      })}
      <text x="68" y="156">{dates[0]?.date}</text><text x="678" y="156" textAnchor="end">{dates.at(-1)?.date}</text>
    </svg><p className="subtle">横轴按来源记录排列；等距显示不代表相同的日历间隔。</p>
  </figure>;
}
