import test from 'node:test';
import assert from 'node:assert/strict';
import { createUniverseDraft, prepareUniverseRequest, loadUniverseRequest, UniverseInputError, universeErrorTarget } from '../src/universe-request.ts';
import { ResearchRequestController } from '../src/filter-model.ts';
import { makeFilterFixture, goldenDraftGroups } from './filter-fixtures.mjs';

// Exercises the same request preparation/loader/controller used by the React component.
// It does not simulate browser clicks or hook mounting.
function draftFor(fixture, enabled) {
  return { ...createUniverseDraft(), ids: fixture.expected.snapshotIds, cutoff: fixture.expected.cutoff, lookback: String(fixture.expected.lookback),
    filter: { enabled, groups: structuredClone(goldenDraftGroups) } };
}
function baseEnvelope(reply) {
  return { method_id: 'selected-universe-research-v1', analysis_id: reply.base_analysis_id, inputs: reply.inputs,
    parameters: { cutoff: reply.parameters.cutoff, lookback: reply.parameters.lookback, model: reply.result.universe.parameters },
    mode: 'retrospective', limitations: reply.limitations, result: reply.result.universe };
}
for (const enabled of [false, true]) test(`component request path uses exactly one ${enabled ? 'filter' : 'legacy universe'} endpoint`, async () => {
  const fixture = await makeFilterFixture(); const draft = draftFor(fixture, enabled); const calls = [];
  const previous = globalThis.fetch;
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return Response.json(enabled ? fixture.reply : baseEnvelope(fixture.reply)); };
  try {
    const states = []; const controller = new ResearchRequestController(state => states.push(state));
    await controller.run(() => prepareUniverseRequest(draft, draft.ids), loadUniverseRequest);
    assert.equal(controller.state.status, 'ready'); assert.equal(calls.length, 1);
    assert.match(calls[0][0], enabled ? /^\/api\/research\/universe-filter\?/ : /^\/api\/research\/universe\?/);
    assert.equal(calls[0][1].cache, 'no-store'); assert.equal(calls[0][1].credentials, 'same-origin');
    assert.equal(controller.state.result.kind, enabled ? 'filter' : 'universe');
    assert.deepEqual(controller.state.result.kind === 'filter' ? controller.state.result.report.result.universe : controller.state.result.report.result, fixture.reply.result.universe);
    controller.dispose();
  } finally { globalThis.fetch = previous; }
});

test('submitted copy is stable while display-only name can change without entering request identity', async () => {
  const f = await makeFilterFixture(); const draft = draftFor(f, true);
  const pending = prepareUniverseRequest(draft, draft.ids);
  draft.cutoff = '2026-01-04'; draft.filter.groups[0][0].threshold = '0.9'; draft.groupName = '改名';
  const request = await pending;
  assert.equal(request.request.expected.cutoff, '2026-01-03'); assert.equal(request.request.expected.ruleId, f.expected.ruleId);
  assert.ok(!request.request.path.includes('改名'));
});

test('invalid draft or missing selected source reaches neither endpoint', async () => {
  const f = await makeFilterFixture(); const initial = draftFor(f, true);
  const previous = globalThis.fetch; let calls = 0; globalThis.fetch = async () => { calls++; throw new Error('should_not_fetch'); };
  try {
    for (const change of [d => { d.filter.groups[0][0].threshold = ''; }, d => { d.lookback = '2e1'; }, d => { d.ids.push('e'.repeat(64)); }]) {
      const draft = structuredClone(initial); change(draft); const controller = new ResearchRequestController(() => {});
      await controller.run(() => prepareUniverseRequest(draft, initial.ids), loadUniverseRequest);
      assert.equal(controller.state.status, 'error'); assert.equal(controller.state.result, null); controller.dispose();
    }
    assert.equal(calls, 0); assert.equal(initial.ids.length, 2);
  } finally { globalThis.fetch = previous; }
});

test('local D/N errors identify the actual input, while the same server error code stays at the summary', async () => {
  const f = await makeFilterFixture();
  for (const [input, value] of [['cutoff', '2026-02-30'], ['cutoff', '0000-01-01'], ['lookback', '2e1'], ['lookback', '253']]) {
    const draft = draftFor(f, true); draft[input] = value;
    await assert.rejects(() => prepareUniverseRequest(draft, draft.ids), error => {
      assert.ok(error instanceof UniverseInputError); assert.equal(universeErrorTarget(error), `universe-${input}`); return true;
    });
  }
  assert.equal(universeErrorTarget(new Error('invalid_lookback')), 'universe-error-summary');
  assert.equal(universeErrorTarget(new Error('invalid_cutoff')), 'universe-error-summary');
});

test('error preserves input, requires explicit retry, and never falls back to old results', async () => {
  const f = await makeFilterFixture(); const draft = draftFor(f, true); const before = structuredClone(draft);
  const previous = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? Response.json({ error: 'raw_object_corrupt' }, { status: 409 }) : Response.json(f.reply);
  try {
    const controller = new ResearchRequestController(() => {});
    await controller.run(() => prepareUniverseRequest(draft, draft.ids), loadUniverseRequest);
    assert.equal(calls, 1); assert.equal(controller.state.status, 'error'); assert.equal(controller.state.result, null); assert.deepEqual(draft, before);
    await controller.run(() => prepareUniverseRequest(draft, draft.ids), loadUniverseRequest);
    assert.equal(calls, 2); assert.equal(controller.state.status, 'ready'); controller.dispose();
  } finally { globalThis.fetch = previous; }
});

test('held workspace draft survives controller disposal; restore and invalidation require explicit rerun', async () => {
  const f = await makeFilterFixture(); const heldDraft = draftFor(f, true); const before = structuredClone(heldDraft);
  const previous = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json(f.reply); };
  try {
    const first = new ResearchRequestController(() => {});
    await first.run(() => prepareUniverseRequest(heldDraft, heldDraft.ids), loadUniverseRequest);
    first.dispose();
    const returned = new ResearchRequestController(() => {});
    assert.equal(returned.state.status, 'idle'); assert.equal(returned.state.result, null);
    assert.deepEqual(heldDraft, before); assert.equal(calls, 1);
    await returned.run(() => prepareUniverseRequest(heldDraft, heldDraft.ids), loadUniverseRequest);
    returned.invalidate(); // Same invalidation primitive used by pagehide/pageshow.
    assert.equal(returned.state.status, 'dirty'); assert.equal(returned.state.result, null);
    assert.deepEqual(heldDraft, before); assert.equal(calls, 2);
    assert.deepEqual(createUniverseDraft().ids, []); // A fresh App has no persisted draft.
    returned.dispose();
  } finally { globalThis.fetch = previous; }
});
