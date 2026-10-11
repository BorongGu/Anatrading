import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { assertFilterReply, thresholdToWire, prepareFilterRule, canonicalJson, hashFilterRule,
  FILTER_POLICIES, ResearchRequestController, readFilterJson } from '../src/filter-model.ts';
import { makeFilterFixture, recountFilter, indexReportedTruths, unavailableFact } from './filter-fixtures.mjs';
import { prepareUniverseRequest, createUniverseDraft } from '../src/universe-request.ts';

// Independent adversarial review. Synthetic response scaffolding is shared, but
// every invariant and decimal oracle here is separate from production helpers.
// These tests establish no browser click, hook lifecycle, focus or layout result.
const clone = value => structuredClone(value);
const one = threshold => [[{ field: 'momentum', threshold }]];
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
const tick = () => new Promise(resolve => setImmediate(resolve));
function ratio(text) {
  assert.match(text, /^-?\d+(?:\.\d+)?$/);
  const negative = text.startsWith('-');
  const [whole, tail = ''] = (negative ? text.slice(1) : text).split('.');
  return [BigInt(whole + tail) * (negative ? -1n : 1n), 10n ** BigInt(tail.length)];
}
function addFailedVolatility(reply, index = 0) {
  unavailableFact(reply, index, 'volatility');
  const m = reply.result.members[index];
  m.reasons = [{ id: 'r1', code: 'numerical_failure', scope: 'metric', field: 'volatility',
    count: 1, examples: [], omitted_count: 0 }];
  m.primary_reason = 'numerical_failure';
  return m;
}
function partialOr(reply) {
  const m = addFailedVolatility(reply);
  const v = m.atoms.find(atom => atom.fact_ref === 'volatility');
  v.truth = 'unknown'; v.reason_refs = ['r1'];
  m.groups.find(group => group.atom_ids.includes(v.id)).truth = 'unknown';
  m.evidence_complete = false; m.partial_evidence = true;
  indexReportedTruths(m); recountFilter(reply);
  return m;
}

test('independent integer-ratio oracle preserves all percentage digits and DD polarity', () => {
  const inputs = ['0', '-0.0000', '5.0000000000000001', '-99.9999999999999999',
    '999.9999999999999999', '1000', '-100', '0.0000000000000001'];
  let state = 20261011n;
  for (let i = 0; i < 40; i++) {
    state = (1103515245n * state + 12345n) % 10000000000000000n;
    inputs.push(`${i % 2 ? '-' : ''}${i % 97}.${state.toString().padStart(16, '0')}`);
  }
  for (const input of inputs) {
    const output = thresholdToWire('momentum', input);
    const [n, d] = ratio(input), [wn, wd] = ratio(output);
    assert.equal(wn * d * 100n, n * wd, input);
    assert.ok(!output.includes('e') && !output.endsWith('.'));
  }
  for (const input of ['0', '-0', '0.0000000000000001', '10.0000000000000001', '99.9999999999999999', '100']) {
    const [n, d] = ratio(input), [wn, wd] = ratio(thresholdToWire('max_drawdown', input));
    assert.equal(wn * d * 100n, -n * wd, input);
  }
  for (const input of ['0.000000000000000001', '0.100000000000000001', '1.000000000000000000']) {
    const [n, d] = ratio(input), [wn, wd] = ratio(thresholdToWire('volatility', input));
    assert.equal(wn * d, n * wd, input);
  }
});

test('input grammar never admits whitespace, Unicode lookalikes or an extra precision digit', () => {
  for (const field of ['momentum', 'max_drawdown', 'volatility']) {
    for (const value of ['0\n', '0\r\n', '0\t', '0 ', ' 0', '０', '−0', '1e-2', '0x1', '+0', '.0', '00.0', '0.'])
      assert.throws(() => thresholdToWire(field, value), /invalid_filter_threshold/, `${field}: ${JSON.stringify(value)}`);
  }
  for (const [field, value] of [['momentum', '1000.0000000000000001'], ['momentum', '-100.0000000000000001'],
    ['momentum', '0.00000000000000001'], ['max_drawdown', '100.0000000000000001'], ['volatility', '1.000000000000000001']])
    assert.throws(() => thresholdToWire(field, value), /invalid_filter_threshold/);
});

test('frozen Python golden and independently hashed canonical bytes survive every editor ordering', async () => {
  const draft = [
    [{ field: 'volatility', threshold: '0.0200' }, { field: 'momentum', threshold: '-0.00' }],
    [{ field: 'max_drawdown', threshold: '10.000' }, { field: 'momentum', threshold: '0.00' }],
  ];
  const expected = 'ed05c4aef00f6130eda8d84f5046cecb2734e9059469be4fd481bb0b4c64272d';
  for (const reverseGroups of [false, true]) for (const reverseAtoms of [false, true]) {
    const input = clone(draft);
    if (reverseGroups) input.reverse();
    if (reverseAtoms) input.forEach(group => group.reverse());
    const { canonicalRule, groupLabels } = prepareFilterRule(input);
    const bytes = canonicalJson({ policy_versions: FILTER_POLICIES, canonical_rule: canonicalRule });
    assert.equal(Buffer.byteLength(bytes), 477);
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected);
    assert.equal(await hashFilterRule(canonicalRule), expected);
    assert.deepEqual(groupLabels, reverseGroups ? [1, 2] : [2, 1]);
    groupLabels.forEach((label, index) => assert.deepEqual(prepareFilterRule([input[label - 1]]).canonicalRule.any_of[0], canonicalRule.any_of[index]));
  }
});

test('duplicate groups are detected after unit conversion and zero/tail normalization', () => {
  assert.throws(() => prepareFilterRule([
    [{ field: 'momentum', threshold: '-0.000' }, { field: 'max_drawdown', threshold: '10.00' }],
    [{ field: 'max_drawdown', threshold: '10' }, { field: 'momentum', threshold: '0' }],
  ]), /duplicate_filter_group/);
});

test('returned date gate must agree with the already-reported source coverage', async () => {
  const { reply, expected } = await makeFilterFixture();
  Object.assign(reply.result.universe.members[0].coverage, {
    source_rows: 4, unlocated_rows: 1, unreadable_date_rows: 1, batch_unlocated_rows: 1, coverage_known: false,
  });
  // Keep all totals internally consistent: disagreement is in the binding itself.
  recountFilter(reply);
  assert.throws(() => assertFilterReply(reply, expected), /invalid_filter_response/);
});

test('a failed enabled fact cannot silently remain true and erase partial evidence', async () => {
  const { reply, expected } = await makeFilterFixture();
  addFailedVolatility(reply); recountFilter(reply);
  assert.equal(reply.result.members[0].evidence_complete, true);
  assert.throws(() => assertFilterReply(reply, expected), /invalid_filter_response/);
  const good = await makeFilterFixture(); partialOr(good.reply);
  assert.equal(good.reply.result.members[0].selection_state, 'selected');
  assert.doesNotThrow(() => assertFilterReply(good.reply, good.expected));
});

test('unknown reason references bind to the same field, not another local numerical failure', async () => {
  const { reply, expected } = await makeFilterFixture();
  const m = partialOr(reply);
  // r2 exists locally, but belongs to a different failed metric.
  m.reasons.push({ id: 'r2', code: 'numerical_failure', scope: 'metric', field: 'momentum',
    count: 1, examples: [], omitted_count: 0 });
  m.atoms.find(atom => atom.fact_ref === 'volatility').reason_refs = ['r2'];
  recountFilter(reply);
  assert.throws(() => assertFilterReply(reply, expected), /invalid_filter_response/);
});

test('explicit logical/selection enums cannot contradict one another with repaired totals', async () => {
  const { reply, expected } = await makeFilterFixture();
  reply.result.members[0].selection_state = 'excluded';
  recountFilter(reply);
  assert.throws(() => assertFilterReply(reply, expected), /invalid_filter_response/);
});

test('volatility decimal evidence must represent the same reported estimate', async () => {
  for (const text of ['0.9', '1e-300', '-0.5']) {
    const { reply, expected } = await makeFilterFixture();
    reply.result.members[0].facts.volatility.estimate_text = text;
    assert.throws(() => assertFilterReply(reply, expected), /invalid_filter_response/, text);
  }
});

test('source/member scopes reject cross-wiring and retain distinct shared-contract presence states', async () => {
  const f = await makeFilterFixture();
  for (const mutate of [
    r => { r.result.members[0].source_ref = r.result.sources[1].id; },
    r => { r.result.members[0].window.query_id = r.result.sources[1].query_id; },
    r => { r.result.sources[0].contract_ref = 'e'.repeat(64); },
    r => { r.result.source_contracts[0].semantics.closed.value = { present: false, value: 'verified' }; },
  ]) {
    const r = clone(f.reply); mutate(r);
    assert.throws(() => assertFilterReply(r, f.expected), /invalid_filter_response/);
  }
  const r = clone(f.reply), distinct = clone(r.result.source_contracts[0]);
  distinct.id = 'e'.repeat(64);
  distinct.semantics.closed.value = { present: true, value: null };
  r.result.source_contracts.push(distinct); r.result.sources[1].contract_ref = distinct.id;
  const before = clone(r);
  assert.doesNotThrow(() => assertFilterReply(r, f.expected));
  assert.deepEqual(r, before); // Validation must not fill absent values or collapse nulls.
});

test('different member-local r1 references remain separate and an unenabled V failure stays complete', async () => {
  const { reply, expected } = await makeFilterFixture({ groups: one('0') });
  addFailedVolatility(reply, 0);
  addFailedVolatility(reply, 1);
  recountFilter(reply);
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  assert.ok(reply.result.members.every(m => m.evidence_complete && !m.partial_evidence && m.atoms[0].reason_refs.length === 0));
});

test('delayed prepare failure cannot overwrite or unlock a newer request', async () => {
  const a = deferred(), b = deferred(), published = [];
  const c = new ResearchRequestController(state => published.push(state));
  const old = c.run(() => a.promise, async () => assert.fail('stale prepare must never load'));
  c.invalidate();
  const fresh = c.run(() => 'B', () => b.promise); await tick();
  a.reject(new Error('invalid_filter_threshold')); await old;
  assert.equal(c.state.status, 'loading');
  assert.equal(await c.run(() => 'duplicate', async () => assert.fail('locked')), false);
  b.resolve('bound response'); await fresh;
  assert.equal(c.state.result, 'bound response');
  assert.deepEqual(published.filter(state => state.status === 'error'), []);
});

test('cancelled response-body reads and disposed controllers cannot publish an old success', async () => {
  const body = deferred(), states = [], c = new ResearchRequestController(state => states.push(state));
  let signal;
  const run = c.run(() => 'A', async (_, supplied) => { signal = supplied; return body.promise; }); await tick();
  c.cancel(); assert.equal(signal.aborted, true);
  await c.run(() => 'B', async () => 'current');
  body.resolve('old body'); await run;
  assert.equal(c.state.result, 'current');
  const length = states.length; c.dispose();
  assert.equal(states.length, length);
  assert.equal(await c.run(() => 'resurrect', async () => assert.fail('disposed')), false);
});

test('actual component preparation snapshots draft before hashing and never drops unavailable IDs', async () => {
  const f = await makeFilterFixture();
  const draft = { ...createUniverseDraft(), ids: [...f.expected.snapshotIds], cutoff: f.expected.cutoff, lookback: '2',
    filter: { enabled: true, groups: one('5.0000000000000001') } };
  const submitted = prepareUniverseRequest(draft, [...draft.ids]);
  draft.ids.pop(); draft.cutoff = '2027-01-01'; draft.filter.groups[0][0].threshold = '10';
  const request = await submitted;
  assert.equal(request.request.expected.snapshotIds.length, 2);
  assert.equal(request.request.expected.cutoff, '2026-01-03');
  assert.equal(request.request.expected.canonicalRule.any_of[0].all_of[0].threshold, '0.050000000000000001');
  await assert.rejects(prepareUniverseRequest({ ...draft, ids: ['a'.repeat(64), 'f'.repeat(64)] }, f.expected.snapshotIds), /snapshot_not_found/);
});

test('truncated multibyte JSON and stream errors fail safely without accepting a partial body', async () => {
  const prefix = new TextEncoder().encode('{"说明":"中');
  await assert.rejects(readFilterJson(new Response(prefix.slice(0, -1))), /invalid_filter_response/);
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode('{"ok":'));
    controller.error(new Error('connection interrupted'));
  } });
  await assert.rejects(readFilterJson(new Response(stream)), /connection interrupted/);
});
