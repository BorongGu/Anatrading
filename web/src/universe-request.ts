import { groupPairRequest, fetchGroupPairs } from './group-pair-model.ts';
import type { GroupPairReport, GroupPairExpected } from './group-pair-model.ts';
import { drawdownEpisodeRequest, fetchDrawdownEpisodes } from './drawdown-episode-model.ts';
import type { DrawdownReport } from './drawdown-episode-model.ts';
import { peerNeighborRequest, fetchPeerNeighbors } from './peer-neighbor-model.ts';
import type { PeerNeighborReport } from './peer-neighbor-model.ts';
import { groupEndpointRequest, fetchGroupEndpoints, validGroupDate } from './group-endpoint-model.ts';
import type { GroupEndpointReport } from './group-endpoint-model.ts';
import { explanationRequest, fetchExplanation } from './two-group-model.ts';
import type { ExplanationReport } from './two-group-model.ts';
import { jsonRequest } from './api.ts';
import { assertResearchReply, buildResearchRequest } from './research-model.ts';
import { buildFilterRequest, fetchFilter, FilterInputError } from './filter-model.ts';
import type { FilterDraft, FilterEnvelope, FilterRequest } from './filter-types.ts';
import type { ResearchEnvelope, UniverseResult } from './research-types.ts';

export interface UniverseDraft { ids: string[]; cutoff: string; lookback: string; groupName: string; filter: FilterDraft; mode: 'group_pairs' | 'drawdown_episodes' | 'existing' | 'explanation' | 'group_endpoints' | 'peer_neighbors'; peerTarget: string; groupStart: string; explanation: { start: string; roles: Record<string, 'A' | 'B' | ''> } }
export type UniverseRequestSpec = { kind: 'group_pairs'; request: ReturnType<typeof groupPairRequest> } | { kind: 'drawdown_episodes'; request: ReturnType<typeof drawdownEpisodeRequest> } | { kind: 'peer_neighbors'; request: ReturnType<typeof peerNeighborRequest> } | { kind: 'group_endpoints'; request: ReturnType<typeof groupEndpointRequest> } | { kind: 'explanation'; request: ReturnType<typeof explanationRequest> } | { kind: 'filter'; request: FilterRequest } | { kind: 'universe'; request: ReturnType<typeof buildResearchRequest> };
export type UniverseRequestResult = { kind: 'group_pairs'; report: GroupPairReport; expected: GroupPairExpected } | { kind: 'drawdown_episodes'; report: DrawdownReport } | { kind: 'peer_neighbors'; report: PeerNeighborReport } | { kind: 'group_endpoints'; report: GroupEndpointReport } | { kind: 'explanation'; report: ExplanationReport } | { kind: 'filter'; report: FilterEnvelope } | { kind: 'universe'; report: ResearchEnvelope<UniverseResult> };
export class UniverseInputError extends Error {
  input: 'cutoff' | 'lookback' | 'group-start';
  constructor(input: 'cutoff' | 'lookback' | 'group-start') { super(input === 'cutoff' ? 'invalid_cutoff' : input === 'group-start' ? 'invalid_dates' : 'invalid_lookback'); this.name = 'UniverseInputError'; this.input = input; }
}
export function universeErrorTarget(error: unknown): string {
  if (error instanceof Error && error.message === 'invalid_target') return 'universe-peer-target';
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
  return { ids: [], cutoff: '', lookback: '20', groupName: '', mode: 'existing', peerTarget: '', groupStart: '', explanation: { start: '', roles: {} }, filter: { enabled: false, groups: [[{ field: 'momentum', threshold: '' }]] } };
}
/** Copies the submitted inputs before asynchronous rule hashing begins. */
export async function prepareUniverseRequest(draft: UniverseDraft, availableIds: readonly string[]): Promise<UniverseRequestSpec> {
  const submitted = structuredClone(draft);
  if (submitted.ids.some(id => !availableIds.includes(id))) throw new Error('snapshot_not_found');
  if (!validCutoff(submitted.cutoff)) throw new UniverseInputError('cutoff');
  if (submitted.mode === 'group_pairs') return { kind: 'group_pairs', request: groupPairRequest({ ids: submitted.ids, cutoff: submitted.cutoff }) };
  if (submitted.mode === 'peer_neighbors') return { kind: 'peer_neighbors', request: peerNeighborRequest({ ids: submitted.ids, target: submitted.peerTarget, cutoff: submitted.cutoff }) };
  if (submitted.mode === 'group_endpoints') {
    if (!validGroupDate(submitted.groupStart) || submitted.groupStart >= submitted.cutoff) throw new UniverseInputError('group-start');
    return { kind: 'group_endpoints', request: groupEndpointRequest({ ids: submitted.ids, start: submitted.groupStart, end: submitted.cutoff }) };
  }
  if (submitted.mode === 'explanation') {
    if (!validCutoff(submitted.explanation.start) || submitted.explanation.start >= submitted.cutoff) throw new Error('invalid_dates');
    return { kind: 'explanation', request: explanationRequest({ ids: submitted.ids, groups: { A: submitted.ids.filter(id => submitted.explanation.roles[id] === 'A'), B: submitted.ids.filter(id => submitted.explanation.roles[id] === 'B') }, start: submitted.explanation.start, end: submitted.cutoff }) };
  }
  if (!/^\d{1,3}$/.test(submitted.lookback) || Number(submitted.lookback) < 2 || Number(submitted.lookback) > 252) throw new UniverseInputError('lookback');
  if (submitted.mode === 'drawdown_episodes') return { kind: 'drawdown_episodes', request: drawdownEpisodeRequest({ ids: submitted.ids, cutoff: submitted.cutoff, lookback: Number(submitted.lookback) }) };
  return submitted.filter.enabled
    ? { kind: 'filter', request: await buildFilterRequest(submitted.ids, submitted.cutoff, Number(submitted.lookback), submitted.filter.groups) }
    : { kind: 'universe', request: buildResearchRequest('universe', submitted.ids, submitted.cutoff, Number(submitted.lookback)) };
}
/** The actual component path: exactly one endpoint supplies each report. */
export async function loadUniverseRequest(spec: UniverseRequestSpec, signal: AbortSignal): Promise<UniverseRequestResult> {
  if (spec.kind === 'group_pairs') {
    const request = structuredClone(spec.request);
    return { kind: 'group_pairs', report: await fetchGroupPairs(request, signal), expected: request.expected };
  }
  if (spec.kind === 'drawdown_episodes') return { kind: 'drawdown_episodes', report: await fetchDrawdownEpisodes(spec.request, signal) };
  if (spec.kind === 'peer_neighbors') return { kind: 'peer_neighbors', report: await fetchPeerNeighbors(spec.request, signal) };
  if (spec.kind === 'group_endpoints') return { kind: 'group_endpoints', report: await fetchGroupEndpoints(spec.request, signal) };
  if (spec.kind === 'explanation') return { kind: 'explanation', report: await fetchExplanation(spec.request, signal) };
  if (spec.kind === 'filter') return { kind: 'filter', report: await fetchFilter(spec.request, signal) };
  const report = await jsonRequest<ResearchEnvelope<UniverseResult>>(spec.request.path, { signal });
  assertResearchReply(report, spec.request.expected);
  return { kind: 'universe', report };
}
