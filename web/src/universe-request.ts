import { explanationRequest, fetchExplanation } from './two-group-model.ts';
import type { ExplanationReport } from './two-group-model.ts';
import { jsonRequest } from './api.ts';
import { assertResearchReply, buildResearchRequest } from './research-model.ts';
import { buildFilterRequest, fetchFilter, FilterInputError } from './filter-model.ts';
import type { FilterDraft, FilterEnvelope, FilterRequest } from './filter-types.ts';
import type { ResearchEnvelope, UniverseResult } from './research-types.ts';

export interface UniverseDraft { ids: string[]; cutoff: string; lookback: string; groupName: string; filter: FilterDraft; explanation: { enabled: boolean; start: string; roles: Record<string, 'A' | 'B' | ''> } }
export type UniverseRequestSpec = { kind: 'explanation'; request: ReturnType<typeof explanationRequest> } | { kind: 'filter'; request: FilterRequest } | { kind: 'universe'; request: ReturnType<typeof buildResearchRequest> };
export type UniverseRequestResult = { kind: 'explanation'; report: ExplanationReport } | { kind: 'filter'; report: FilterEnvelope } | { kind: 'universe'; report: ResearchEnvelope<UniverseResult> };
export class UniverseInputError extends Error {
  input: 'cutoff' | 'lookback';
  constructor(input: 'cutoff' | 'lookback') { super(input === 'cutoff' ? 'invalid_cutoff' : 'invalid_lookback'); this.name = 'UniverseInputError'; this.input = input; }
}
export function universeErrorTarget(error: unknown): string {
  if (error instanceof UniverseInputError) return `universe-${error.input}`;
  if (error instanceof FilterInputError && error.groupIndex !== undefined && error.atomIndex !== undefined)
    return `filter-${error.groupIndex}-${error.atomIndex}-threshold`;
  return 'universe-error-summary';
}
function validCutoff(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, date] = value.split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return year > 0 && month >= 1 && month <= 12 && date >= 1 && date <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
export function createUniverseDraft(): UniverseDraft {
  return { ids: [], cutoff: '', lookback: '20', groupName: '', explanation: { enabled: false, start: '', roles: {} }, filter: { enabled: false, groups: [[{ field: 'momentum', threshold: '' }]] } };
}
/** Copies the submitted inputs before asynchronous rule hashing begins. */
export async function prepareUniverseRequest(draft: UniverseDraft, availableIds: readonly string[]): Promise<UniverseRequestSpec> {
  const submitted = structuredClone(draft);
  if (submitted.ids.some(id => !availableIds.includes(id))) throw new Error('snapshot_not_found');
  if (!validCutoff(submitted.cutoff)) throw new UniverseInputError('cutoff');
  if (submitted.explanation.enabled) {
    if (!validCutoff(submitted.explanation.start) || submitted.explanation.start >= submitted.cutoff) throw new Error('invalid_dates');
    return { kind: 'explanation', request: explanationRequest({ ids: submitted.ids, groups: { A: submitted.ids.filter(id => submitted.explanation.roles[id] === 'A'), B: submitted.ids.filter(id => submitted.explanation.roles[id] === 'B') }, start: submitted.explanation.start, end: submitted.cutoff }) };
  }
  if (!/^\d{1,3}$/.test(submitted.lookback) || Number(submitted.lookback) < 2 || Number(submitted.lookback) > 252) throw new UniverseInputError('lookback');
  return submitted.filter.enabled
    ? { kind: 'filter', request: await buildFilterRequest(submitted.ids, submitted.cutoff, Number(submitted.lookback), submitted.filter.groups) }
    : { kind: 'universe', request: buildResearchRequest('universe', submitted.ids, submitted.cutoff, Number(submitted.lookback)) };
}
/** The actual component path: exactly one endpoint supplies each report. */
export async function loadUniverseRequest(spec: UniverseRequestSpec, signal: AbortSignal): Promise<UniverseRequestResult> {
  if (spec.kind === 'explanation') return { kind: 'explanation', report: await fetchExplanation(spec.request, signal) };
  if (spec.kind === 'filter') return { kind: 'filter', report: await fetchFilter(spec.request, signal) };
  const report = await jsonRequest<ResearchEnvelope<UniverseResult>>(spec.request.path, { signal });
  assertResearchReply(report, spec.request.expected);
  return { kind: 'universe', report };
}
