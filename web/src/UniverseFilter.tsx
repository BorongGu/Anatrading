import { Fragment, useEffect, useRef, useState } from 'react';
import { formatEstimate, formatPercent, researchReason } from './research-model.ts';
import { thresholdPreview } from './filter-model.ts';
import type { FilterDraft, FilterDraftAtom, FilterEnvelope, FilterField } from './filter-types.ts';
import { Metric } from './ResearchResults.tsx';

const fields: { value: FilterField; label: string; unit: string }[] = [
  { value: 'momentum', label: '收盘变化至少', unit: '%，允许负数' },
  { value: 'volatility', label: '来源区间波动至多', unit: 'log 单位 / 来源区间，不年化' },
  { value: 'max_drawdown', label: '收盘路径最大跌幅不超过', unit: '%，输入正的跌幅上限' },
];
export function FilterEditor({ draft, onChange, inputError }: { draft: FilterDraft; onChange: (next: FilterDraft) => void; inputError?: { groupIndex?: number; atomIndex?: number } }) {
  function changeAtom(groupIndex: number, atomIndex: number, patch: Partial<FilterDraftAtom>) {
    onChange({ ...draft, groups: draft.groups.map((group, gi) => gi !== groupIndex ? group : group.map((atom, ai) => ai !== atomIndex ? atom : { ...atom, ...patch })) });
  }
  const pendingFocus = useRef<string | null>(null);
  function focus(id: string) { pendingFocus.current = id; }
  useEffect(() => {
    if (pendingFocus.current) { document.getElementById(pendingFocus.current)?.focus(); pendingFocus.current = null; }
  }, [draft]);
  return <section className="filter-editor" aria-label="股票价格条件">
    <div className="section-heading"><div><h3>按来源价格条件筛选</h3><p className="subtle">组内同时满足；两组中满足任一组即可。未知条件会保留原因。</p></div>
      <button type="button" className="quiet" onClick={() => onChange({ ...draft, enabled: !draft.enabled })}>{draft.enabled ? '关闭条件' : '添加条件'}</button></div>
    {draft.enabled && <>
      {draft.groups.map((group, gi) => <fieldset key={gi} className="filter-group"><legend>{gi ? '或，满足第 2 组' : '第 1 组'}：同时满足</legend>
        {group.map((atom, ai) => {
          const id = `filter-${gi}-${ai}`; const spec = fields.find(field => field.value === atom.field)!;
          let preview = ''; try { preview = thresholdPreview(atom.field, atom.threshold); } catch { /* Incomplete draft stays editable. */ }
          return <div className="filter-atom" key={ai}><label>条件 {ai + 1}<select id={`${id}-field`} value={atom.field} onChange={event => changeAtom(gi, ai, { field: event.target.value as FilterField, threshold: '' })}>
            {fields.map(field => <option key={field.value} value={field.value} disabled={group.some((other, index) => index !== ai && other.field === field.value)}>{field.label}</option>)}</select></label>
            <label>阈值<input id={`${id}-threshold`} type="text" inputMode={atom.field === 'momentum' ? 'text' : 'decimal'} autoComplete="off" maxLength={24} value={atom.threshold} aria-invalid={inputError?.groupIndex === gi && inputError?.atomIndex === ai ? true : undefined} aria-describedby={`${id}-hint${inputError?.groupIndex === gi && inputError?.atomIndex === ai ? ' universe-error-summary' : ''}`} onChange={event => changeAtom(gi, ai, { threshold: event.target.value })} />
              <small id={`${id}-hint`}>{preview || spec.unit}</small></label>
            <button type="button" className="quiet" aria-label={`删除第 ${gi + 1} 组条件 ${ai + 1}`} disabled={group.length === 1} onClick={() => {
              onChange({ ...draft, groups: draft.groups.map((g, index) => index !== gi ? g : g.filter((_, index) => index !== ai)) });
              focus(`filter-${gi}-${Math.min(ai, group.length - 2)}-field`);
            }}>删除</button></div>;
        })}
        <div className="button-group"><button type="button" className="quiet" id={`filter-add-${gi}`} disabled={group.length === 3} onClick={() => {
          const field = fields.find(field => !group.some(atom => atom.field === field.value))!.value;
          onChange({ ...draft, groups: draft.groups.map((g, index) => index !== gi ? g : [...g, { field, threshold: '' }]) }); focus(`filter-${gi}-${group.length}-field`);
        }}>添加同时满足的条件</button>
          {gi > 0 && <button type="button" className="quiet" onClick={() => { onChange({ ...draft, groups: draft.groups.slice(0, 1) }); focus('filter-add-group'); }}>删除第 2 组</button>}</div>
      </fieldset>)}
      <button type="button" className="quiet" id="filter-add-group" disabled={draft.groups.length === 2} onClick={() => {
        onChange({ ...draft, groups: [...draft.groups, [{ field: 'momentum', threshold: '' }]] }); focus('filter-1-0-field');
      }}>或，再加一组</button>
      <p className="subtle">阈值是你的研究标准。改条件后需重新运行；来源区间不等于交易日。</p>
    </>}
  </section>;
}

type Member = FilterEnvelope['result']['members'][number];
type Fact = Member['facts'][FilterField];
type Present = { present: boolean; value: unknown };
const stateNames = { selected: '入选', excluded: '排除', undetermined: '待核' };
const truthNames = { true: '满足', false: '不满足', unknown: '待核' };
const fieldNames = { momentum: '收盘变化', volatility: '来源区间波动', max_drawdown: '收盘路径回撤' };
function displayFact(field: FilterField, fact: Fact) {
  if (fact.value === null) return '—';
  return field === 'volatility' ? `≈ ${formatEstimate(fact.value, 5)} log / 来源区间` : `≈ ${formatPercent(fact.value)}`;
}
function sourceText(value: Present): string {
  if (!value.present) return '来源未提供';
  if (value.value === null) return '明确为空';
  return typeof value.value === 'string' ? value.value : JSON.stringify(value.value);
}
function labelGroup(id: string, labels: readonly number[]) {
  return `第 ${labels[Number(id.slice(1)) - 1]} 组`;
}
function relevantReasons(member: Member) {
  const refs = new Set(member.atoms.flatMap(atom => atom.truth === 'unknown' ? atom.reason_refs : []));
  return member.reasons.filter(reason => refs.has(reason.id));
}
function percentText(text: string): string {
  const negative = text.startsWith('-'); const [whole, fraction = ''] = (negative ? text.slice(1) : text).split('.');
  const padded = fraction.padEnd(2, '0'); const integer = (whole + padded.slice(0, 2)).replace(/^0+(?=\d)/, '');
  const tail = padded.slice(2).replace(/0+$/, '');
  return `${negative && (integer !== '0' || tail) ? '−' : ''}${integer}${tail ? `.${tail}` : ''}%`;
}
function conditionText(field: FilterField, op: string, threshold: string) {
  // Decimal text formatting only; service truth is never recomputed.
  return `${fieldNames[field]} ${op === 'gte' ? '≥' : '≤'} ${field === 'volatility' ? `${threshold} log / 来源区间` : percentText(threshold)}`;
}
function SourceDetails({ member, report }: { member: Member; report: FilterEnvelope }) {
  const source = report.result.sources.find(item => item.id === member.source_ref)!;
  const contract = report.result.source_contracts.find(item => item.id === source.contract_ref)!;
  const semanticLabels: Record<string, string> = { price_unit: '价格单位', adjustment: '复权口径', label_definition: '日期含义', closed: '收盘完整性', known_at: '历史当时可得', first_published_at: '首次发布时间' };
  return <details className="filter-source"><summary>数据版本与来源说明</summary>
    <p>身份：{researchReason(source.identity.qualification)}。源日期可定位性：{member.source_gate === 'pass' ? '可定位；交易日历完整性仍未核' : '存在无法定位日期的记录'}。</p>
    <dl className="metadata-list"><dt>数据版本</dt><dd><code>{source.snapshot_id}</code></dd><dt>完整来源查询</dt><dd><code>{source.query_id}</code></dd>
      <dt>原件哈希</dt><dd><code>{sourceText(source.raw_sha256)}</code></dd><dt>来源格式</dt><dd>{sourceText(contract.format_id)}</dd>
      <dt>来源合同</dt><dd><code>{sourceText(contract.source_contract_id)}</code></dd><dt>合同版本</dt><dd>{sourceText(contract.contract_version)}</dd><dt>解码版本</dt><dd>{sourceText(contract.versions)}</dd>
      <dt>来源说明作用域</dt><dd>{sourceText(contract.semantics_scope)}</dd></dl>
    <p className="subtle">known 表示来源定义的状态，仍需同时看本样本适用性。请求未复权不等于复权口径已核；捕获时间不能充作历史可得时间。</p>
    {Object.entries(contract.semantics).map(([key, semantic]) => <div className="filter-semantic" key={key}><strong>{semanticLabels[key] ?? key}</strong>
      <span>值：{sourceText(semantic.value)}；状态：{sourceText(semantic.status)}</span><span>依据：{sourceText(semantic.reason)}；本样本适用性：{sourceText(semantic.applicability)}</span>
      {key === 'price_unit' && semantic.status.value === 'known' && semantic.applicability.value === 'unverified' && <small>文档定义的单位，本样本适用性未核。</small>}</div>)}
    <details><summary>请求与捕获标记</summary><dl className="metadata-list">{Object.entries(source.metadata).map(([key, value]) => <div className="metadata-entry" key={key}><dt>{key}</dt><dd>{sourceText(value)}</dd></div>)}</dl></details>
  </details>;
}
export function FilterMemberDetails({ member, report, groupLabels, onOpen }: { member: Member; report: FilterEnvelope; groupLabels: readonly number[]; onOpen: (id: string, cutoff: string) => void }) {
  const conditions = new Map(report.result.conditions.map(condition => [condition.id, condition]));
  const window = member.window;
  return <div className="filter-evidence">
    {member.groups.map(group => <section className="filter-proof" key={group.id}><h4>{labelGroup(group.id, groupLabels)}：{truthNames[group.truth]}</h4>
      <ul>{group.atom_ids.map(id => {
        const atom = member.atoms.find(value => value.id === id)!; const condition = conditions.get(id)!; const fact = member.facts[atom.fact_ref];
        return <li key={id}><strong>{truthNames[atom.truth]} · {conditionText(condition.field, condition.op, condition.threshold)}</strong>
          <span>本次值：{displayFact(condition.field, fact)}{member.source_gate === 'unknown' && fact.value !== null ? '，仅作诊断，未用于此次筛选' : ''}</span>
          {fact.exact && <small>精确比例：{fact.exact.numerator} / {fact.exact.denominator}。按精确值判定，显示值已舍入。</small>}
          {condition.field === 'volatility' && <small>float64 估计：{fact.estimate_text ?? '—'}；表示：{fact.float_hex ?? '—'}，不年化。</small>}
          {!!atom.reason_refs.length && <span className="amber">{atom.reason_refs.map(ref => researchReason(member.reasons.find(reason => reason.id === ref)!.code)).join('；')}</span>}
        </li>;
      })}</ul>
    </section>)}
    <section><h4>本次来源窗口</h4><p>请求截止 {window.cutoff}；实际 {window.start_date ?? '—'} → {window.end_date ?? '—'}；{window.actual_groups} / {window.expected_groups} 个来源日期组，{window.n_prices} 个有效价格，{window.n_returns} 个有效相邻区间。</p>
      {window.actual_groups === 0 && member.facts.momentum.reason === 'cutoff_missing' && <p className="amber">缺少截止日期记录，未形成此次窗口。</p>}
      <p>首价 {window.first?.close ?? '—'}（源序号 {window.first?.ordinal ?? '—'}）；末价 {window.last?.close ?? '—'}（源序号 {window.last?.ordinal ?? '—'}）。</p>
      {window.drawdown_witness && <p>回撤峰值 {window.drawdown_witness.peak?.close ?? '—'}（{window.drawdown_witness.peak?.date ?? '—'}，源序号 {window.drawdown_witness.peak?.ordinal ?? '—'}）→ 谷值 {window.drawdown_witness.trough?.close ?? '—'}（{window.drawdown_witness.trough?.date ?? '—'}，源序号 {window.drawdown_witness.trough?.ordinal ?? '—'}）。</p>}
      <small>实际起点可因来源缺日而不同；这里没有填价或删除坏日期槽。</small></section>
    {!!member.reasons.length && <section><h4>原因与定位</h4><ul>{member.reasons.map(reason => <li key={reason.id}><strong>{researchReason(reason.code)}</strong> · {reason.count} {reason.scope === 'window_slot' ? '个日期槽' : '项状态'}
      {!!reason.examples.length && <span>{reason.examples.map(([date, ordinal], index) => <span className="reason-point" key={index}>{date ?? '日期未知'} / {ordinal === null ? '无法唯一定位源序号' : `源序号 ${ordinal}`}</span>)}</span>}
      {reason.omitted_count > 0 && <small>另有 {reason.omitted_count} 个日期槽；按完整来源查询回查。</small>}</li>)}</ul><small>这里保留已归一化的日期槽原因；同槽的其他检查可回查原始记录。</small></section>}
    <SourceDetails member={member} report={report} />
    <button type="button" className="quiet" onClick={() => onOpen(member.snapshot_id, report.parameters.cutoff)}>查看个股与原始记录 ↗</button>
  </div>;
}
export function FilterResults({ report, groupLabels, name, onOpen, view = 'all', onViewChange }: {
  report: FilterEnvelope; groupLabels: readonly number[]; name: string; onOpen: (id: string, cutoff: string) => void;
  view?: 'all' | Member['selection_state']; onViewChange?: (value: 'all' | Member['selection_state']) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const counts = report.result.counts; const members = new Map(report.result.members.map(member => [member.snapshot_id, member]));
  const ordered = report.result.universe.members.map(base => ({ base, member: members.get(base.snapshot_id)! }));
  const visible = ordered.filter(({ member }) => view === 'all' || member.selection_state === view);
  return <section className="panel research-panel filter-results" aria-label="条件筛选结果">
    <div className="section-heading"><div><span className="eyebrow">所选股票样本 · 条件筛选</span><h2>{name.trim() || '多股条件研究'}</h2></div><span className="badge">请求截止 {report.parameters.cutoff}</span></div>
    <p className="inline-note">基于当前所选版本回顾历史；来源价格条件，复权、历史可得性与交易日历仍有未核项。成员身份沿用来源声明。</p>
    <div className="filter-rule-summary">{report.parameters.canonical_rule.any_of.map((group, index) => <p key={index}>{index > 0 && <strong>或 </strong>}第 {groupLabels[index]} 组：{group.all_of.map(condition => conditionText(condition.field, condition.op, condition.threshold)).join('，且 ')}</p>)}</div>
    <div className="metric-grid four"><Metric label="全部所选" value={String(counts.selected_members)} detail="成员始终保留在分母中" />
      <Metric label="入选" value={`${counts.selection.selected} / ${counts.selected_members}`} detail="满足至少一组条件" />
      <Metric label="排除" value={`${counts.selection.excluded} / ${counts.selected_members}`} detail="每组都有已知不满足项" />
      <Metric label="待核" value={`${counts.selection.undetermined} / ${counts.selected_members}`} detail="当前证据尚不能确定" /></div>
    <p className={counts.evidence.partial ? 'inline-note amber' : 'subtle'}>{counts.evidence.partial} 只仍有条件待核，可能已入选或排除；这一数量与上面三类重叠。</p>
    <div className="filter-view" aria-label="显示结果类别">{(['all', 'selected', 'excluded', 'undetermined'] as const).map(value => <button type="button" className="quiet" key={value} aria-pressed={view === value} onClick={() => onViewChange?.(value)}>{value === 'all' ? '全部' : stateNames[value]} {value === 'all' ? counts.selected_members : counts.selection[value]}</button>)}</div>
    <p className="subtle">按原集合收盘变化顺序，保留原名次；{report.parameters.lookback} 个来源区间，每股实际起点可能不同。</p>
    <div className="filter-table"><table><caption className="filter-visually-hidden">所选成员的条件状态、来源价格分项与实际窗口</caption><thead><tr><th>状态</th><th>证券</th><th>收盘变化</th><th>来源区间波动</th><th>收盘路径回撤</th><th>实际起止与证据</th></tr></thead><tbody>{visible.map(({ base, member }) => <Fragment key={member.snapshot_id}><tr>
      <td data-label="状态"><strong className={`selection-state state-${member.selection_state}`}>{stateNames[member.selection_state]}</strong><small>{member.selection_state === 'selected' ? `${member.proof_groups.map(id => labelGroup(id, groupLabels)).join('、')}成立` : member.selection_state === 'excluded' ? '各组均有不满足项' : '尚待核对条件'}</small>{member.partial_evidence && <><small className="amber">仍有条件待核</small><small className="amber">{researchReason(relevantReasons(member)[0]?.code ?? 'unknown')}</small></>}</td>
      <th scope="row" data-label="证券"><strong>{member.identity.symbol}</strong><small>原名次 {base.rank ?? '—'} · {member.identity.market === 'CN_A' ? '沪深北市场分组' : member.identity.market}</small><small>{researchReason(member.identity.qualification)}</small></th>
      {(['momentum', 'volatility', 'max_drawdown'] as const).map(field => <td data-label={fieldNames[field]} key={field}>{displayFact(field, member.facts[field])}{member.facts[field].reason && <small className="amber">{researchReason(member.facts[field].reason)}</small>}{member.source_gate === 'unknown' && member.facts[field].value !== null && <small>仅作诊断，未用于此次筛选</small>}</td>)}
      <td data-label="实际起止与证据"><span>{member.window.start_date ?? '—'} → {member.window.end_date ?? '—'}</span><button type="button" className="quiet filter-row-toggle" aria-expanded={expanded === member.snapshot_id} aria-controls={expanded === member.snapshot_id ? `filter-evidence-${member.snapshot_id}` : undefined} onClick={() => setExpanded(expanded === member.snapshot_id ? null : member.snapshot_id)}>查看 {member.identity.symbol} 的条件与来源</button></td>
    </tr>{expanded === member.snapshot_id && <tr className="filter-detail-row"><td colSpan={6}><div id={`filter-evidence-${member.snapshot_id}`} role="region" aria-label={`${member.identity.symbol} 条件与来源`}><FilterMemberDetails member={member} report={report} groupLabels={groupLabels} onOpen={onOpen} /></div></td></tr>}</Fragment>)}</tbody></table></div>
    {!visible.length && <p className="subtle">当前显示类别为 0 只；全部 {counts.selected_members} 只仍保留在上方统计中。</p>}
    <details className="calculation-note"><summary>原集合覆盖与研究身份</summary><p>截止当日有效 {report.result.universe.breadth.cutoff_valid} / {counts.selected_members}；动量有效 {report.result.universe.breadth.momentum_valid} / {counts.selected_members}。正动量占有效值 {formatPercent(report.result.universe.breadth.positive_momentum_fraction, 1)}，正值指严格大于零。</p>
      <div className="table-scroll"><table><caption>三项原集合指标的有效与失败数量（全部所选为分母）</caption><thead><tr><th>指标</th><th>有效</th><th>缺失</th><th>无效</th><th>历史不足</th></tr></thead><tbody>{(['momentum', 'volatility', 'max_drawdown'] as const).map(field => {
        const metric = report.result.universe.breadth.metrics[field];
        return <tr key={field}><th scope="row">{fieldNames[field]}</th><td>{metric.eligible}</td><td>{metric.missing}</td><td>{metric.invalid}</td><td>{metric.short_history}</td></tr>;
      })}</tbody></table></div>
      <dl className="metadata-list"><dt>规则标识</dt><dd><code>{report.rule_id}</code></dd><dt>研究结果</dt><dd><code>{report.analysis_id}</code></dd><dt>原集合结果</dt><dd><code>{report.base_analysis_id}</code></dd><dt>方法</dt><dd><code>{report.method_id}</code></dd></dl>
      <ul>{report.limitations.map(code => <li key={code}>{code === 'source_identity_not_security_master_verified' ? '证券身份未经证券主数据核验' : researchReason(code)}</li>)}</ul></details>
  </section>;
}
