import { adjacentSource } from './adjacent-source.ts';
import type { SourceResearchBinding } from './adjacent-source.ts';
import { researchReason } from './research-model.ts';
import type { Query, Row } from './types.ts';

export function AdjacentSourceDetails({ query, row, binding }: { query: Query; row: Row; binding: SourceResearchBinding | null }) {
  const evidence = adjacentSource(query, row, binding);
  return <section className="geometry-details" aria-label="相邻来源变化核对">
    <h3>相邻来源变化核对</h3>
    {evidence.current ? <>
      <div className="exact-grid">{([['前一来源日期组', evidence.previous], ['当前来源记录', evidence.current]] as const).map(([label, item]) => <div key={label}>
        <span className="field-label">{label}</span>{item ? <><code>{item.date} · 源序号 {item.ordinal ?? '不唯一'}</code><code>收盘 {item.close ?? '∅ 缺失 / 非法'}</code></> : <span>无前序来源日期组</span>}
      </div>)}</div>
      {evidence.days !== null && <p className="subtle">两端相隔 {evidence.days} 个自然日；未按天数归一化。</p>}
      <p className="inline-note">相邻记录的对数价格变化（近似值）：<code>{evidence.value === null ? '—' : String(evidence.value)}</code>{evidence.reason && ` · 不可计算：${researchReason(evidence.reason)}`}</p>
    </> : <p className="inline-note">{evidence.reason}</p>}
    <p className="subtle">沿用日线研究结果；极小变化可能因数值精度显示为0。按来源中相邻日期比较，中间有无效记录时不跨过它计算；重新开始后的首条没有变化值。未出现日期不补零；交易日历、覆盖与复权/公司行动未核实，不能认作经济收益或来源纠错依据。</p>
  </section>;
}
