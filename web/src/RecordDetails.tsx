import { fieldNames, fields } from './types.ts';
import type { Row, SourceContract } from './types.ts';

export function RecordDetails({ row, contract, compact = false }: { row: Row; contract: SourceContract | undefined; compact?: boolean }) {
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
    {!compact && <details className="raw-tokens"><summary>原字段 / 原始位（纯文本）</summary>
      <dl><dt>原始源标签</dt><dd><code>{row.source_label ?? '∅'}</code></dd>
        {Object.entries(row.tokens).map(([key, value]) => <div className="token-pair" key={key}><dt>{key}</dt><dd><code>{value === null ? '∅' : value === '' ? '（空字符串）' : value}</code></dd></div>)}
      </dl>
    </details>}
  </div>;
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
