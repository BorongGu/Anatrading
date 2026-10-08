import { fieldNames, fields } from './types.ts';
import type { GeometryRow, Row, SourceContract } from './types.ts';

export function RecordDetails({ row, contract, geometry, compact = false }: { row: Row; contract: SourceContract | undefined; geometry?: GeometryRow; compact?: boolean }) {
  return <div className={compact ? 'record-details compact' : 'record-details'}>
    <div className="record-heading"><strong>{row.label ?? '无法定位'}</strong><span>源序号 {row.ordinal}</span><code>{row.locator}</code></div>
    <div className="exact-grid">
      {fields.map(field => <div key={field}><span className="field-label">{fieldNames[field]}</span><code>{row.values[field] ?? '∅ 缺失 / 非法'}</code></div>)}
    </div>
    <div className="evidence-pills record-qualifications"><UnitEvidence contract={contract} /></div>
    <div className="row-checks">
      {row.checks.filter(check => check.outcome !== 'pass').map((check, i) => <span key={`${check.name}-${i}`} className={check.outcome === 'fail' ? 'check-fail' : 'muted'}>
        {check.outcome === 'fail' ? '未通过' : '未评估'} · {check.name}{check.reason ? `：${check.reason}` : ''}{check.assumption ? `（条件：${check.assumption}）` : ''}
      </span>)}
    </div>
    {!compact && geometry && <GeometryDetails geometry={geometry} unlocated={row.label === null} />}
    {!compact && <details className="raw-tokens"><summary>原字段 / 原始位（纯文本）</summary>
      <dl><dt>原始源标签</dt><dd><code>{row.source_label ?? '∅'}</code></dd>
        {Object.entries(row.tokens).map(([key, value]) => <div className="token-pair" key={key}><dt>{key}</dt><dd><code>{value === null ? '∅' : value === '' ? '（空字符串）' : value}</code></dd></div>)}
      </dl>
    </details>}
  </div>;
}

function GeometryDetails({ geometry: g, unlocated }: { geometry: GeometryRow; unlocated: boolean }) {
  const reasons = { missing_ohlc: 'OHLC 缺失', invalid_price: '价格数值无效', negative_price: '价格为负', invalid_ohlc: 'OHLC 边界不一致' };
  const segments = [['range', '源价差区间'], ['body', '实体'], ['upper_shadow', '上影线'], ['lower_shadow', '下影线']] as const;
  const ratios = [['body', '实体占比'], ['upper_shadow', '上影占比'], ['lower_shadow', '下影占比'], ['close_location', '收盘位置']] as const;
  return <section className="geometry-details" aria-label="单根源K线结构">
    <h3>单根源结构，未检验预测效力</h3>
    <p className="subtle">条件：同根 OHLC 价格尺度相同；源资格与单位限定仍适用。</p>
    {unlocated && <p className="inline-note amber">无法定位：这些结构不能归为某个时点指标。</p>}
    {g.status === 'not_evaluated' ? <p className="inline-note amber">未评估 · {g.reason && reasons[g.reason]}</p> : <>
      <p className="inline-note">本根收相对开：{g.direction === 'up' ? '上' : g.direction === 'down' ? '下' : '相等'}</p>
      <div className="exact-grid">{segments.map(([key, name]) => <div key={key}><span className="field-label">{name}</span><code>{g[key]}</code></div>)}</div>
      {g.ratio_reason === 'zero_range' ? <p className="inline-note">零区间：比例未定义。</p> : <>
        <div className="geometry-ratios">{ratios.map(([key, name]) => <div key={key}><span className="field-label">{name}</span><code>≈{g.ratios[key]?.percent_display}%</code></div>)}</div>
        <p className="subtle">近似显示各自舍入，占比之和可能偏离 100%；收盘位置相对本根高低区间。</p>
        <details><summary>权威分数 · 精确比例</summary><dl className="geometry-fractions">{ratios.map(([key, name]) => <div className="token-pair" key={key}><dt>{name}</dt><dd><code>{g.ratios[key]?.numerator}/{g.ratios[key]?.denominator}</code></dd></div>)}</dl></details>
      </>}
    </>}
  </section>;
}

export function UnitEvidence({ contract }: { contract: SourceContract | undefined }) {
  return <>
    {([['price_unit', '价格定义'], ['volume_unit', '数量定义'], ['amount_unit', '金额定义']] as const).map(([field, label]) => {
      const evidence = contract?.source_semantics?.fields?.[field];
      return <span key={field}>{label} <b>{evidence?.value == null ? '未注明' : String(evidence.value)}</b> · {evidence?.status ?? 'unknown'}
        {evidence?.applicability && <> · 样本适用性 <b>{evidence.applicability}</b></>}
      </span>;
    })}
    <span>规范单位 <b>{contract?.standard_units?.status ?? 'unknown'}</b></span>
  </>;
}
