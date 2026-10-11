import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { assertFilterReply, buildFilterRequest, canonicalJson, checkRuleByteLimit, fetchFilter, FILTER_POLICIES,
  FILTER_RESPONSE_LIMIT, FilterInputError, hashFilterRule, prepareFilterRule, readFilterJson, ResearchRequestController,
  thresholdToWire, thresholdPreview, explainFilter } from '../src/filter-model.ts';
import { goldenDraftGroups, makeFilterFixture, recountFilter, indexReportedTruths, unavailableFact } from './filter-fixtures.mjs';

const one = threshold => [[{ field: 'momentum', threshold }]];
const deferred = () => { let resolve, reject; const promise = new Promise((res, rej) => { resolve = res; reject = rej; }); return { promise, resolve, reject }; };
const tick = () => new Promise(resolve => setImmediate(resolve));
const copy = value => structuredClone(value);

// Synthetic model/stream tests exercise the actual component controller. They
// do not establish browser click bindings, focus, navigation, layout or crypto.
test('text inputs preserve exact percentage conversion, normalized zero, limits and DD sign', () => {
  for (const [field, text, result] of [
    ['momentum', '5.0000000000000001', '0.050000000000000001'], ['momentum', '-100', '-1'],
    ['momentum', '1000', '10'], ['momentum', '-0.0000000000000000', '0'], ['momentum', '0.0000000000000001', '0.000000000000000001'],
    ['max_drawdown', '10.00', '-0.1'], ['max_drawdown', '100', '-1'], ['max_drawdown', '-0', '0'],
    ['volatility', '0.000000000000000001', '0.000000000000000001'], ['volatility', '1.000', '1'],
  ]) assert.equal(thresholdToWire(field, text), result);
  for (const bad of ['', '-', '.', '.5', '1.', ' 1', '1 ', '+1', '01', '1e-3', 'NaN', 'Infinity', '5%', '５', null, 1, true, '0.00000000000000000'])
    assert.throws(() => thresholdToWire('momentum', bad), /invalid_filter_threshold/);
  for (const [field, text] of [['momentum', '-100.0000000000000001'], ['momentum', '1000.0000000000000001'],
    ['max_drawdown', '-0.1'], ['max_drawdown', '100.1'], ['volatility', '-0.1'], ['volatility', '1.000000000000000001'],
    ['volatility', '0.0000000000000000001']]) assert.throws(() => thresholdToWire(field, text), /invalid_filter_threshold/);
  assert.match(thresholdPreview('max_drawdown', '10'), /回撤 ≥ −10%/);
  assert.match(thresholdPreview('volatility', '0.02'), /0.02 log/);
  assert.doesNotMatch(thresholdPreview('volatility', '0.02'), /%/);
  assert.equal(thresholdPreview('max_drawdown', '-0'), '最大跌幅不超过 0%（回撤 ≥ 0%）');
});

test('bounded drafts reject empty/duplicate/unknown fields with local input locations', () => {
  for (const groups of [[], [[]], [...one('0'), ...one('1'), ...one('2')], [[...one('0')[0], ...one('1')[0]]],
    [[...one('0')[0], ...one('1')[0], ...one('2')[0], ...one('3')[0]]], [...one('0'), ...one('-0.00')],
    [[{ field: 'rank', threshold: '0' }]], [[{ field: 'momentum', threshold: '0', op: 'gte' }]], null])
    assert.throws(() => prepareFilterRule(groups), FilterInputError);
  try { prepareFilterRule([[{ field: 'momentum', threshold: '-' }]]); assert.fail(); }
  catch (error) { assert.equal(error.groupIndex, 0); assert.equal(error.atomIndex, 0); }
  assert.doesNotThrow(() => checkRuleByteLimit(' '.repeat(2048)));
  assert.throws(() => checkRuleByteLimit(' '.repeat(2049)), /filter_rule_limit/);
  assert.doesNotThrow(() => checkRuleByteLimit('中'.repeat(682) + 'aa'));
  assert.throws(() => checkRuleByteLimit('中'.repeat(683)), /filter_rule_limit/);
});

test('477-byte cross-language golden binds canonical ASCII keys and editor group mapping', async () => {
  const { canonicalRule, groupLabels } = prepareFilterRule(goldenDraftGroups);
  const serialized = canonicalJson({ canonical_rule: canonicalRule, policy_versions: FILTER_POLICIES });
  assert.equal(new TextEncoder().encode(serialized).length, 477);
  assert.equal(serialized, '{"canonical_rule":{"any_of":[{"all_of":[{"field":"max_drawdown","op":"gte","threshold":"-0.1"},{"field":"momentum","op":"gte","threshold":"0"}]},{"all_of":[{"field":"momentum","op":"gte","threshold":"0"},{"field":"volatility","op":"lte","threshold":"0.02"}]}]},"policy_versions":{"comparison":"fraction-and-binary64-v1","logic":"strong-kleene-eager-v1","rule_schema":"bounded-price-filter-v1","source_gate":"source-date-locatability-v1","window":"daily-source-date-groups-v1"}}');
  assert.deepEqual(groupLabels, [2, 1]);
  const id = await hashFilterRule(canonicalRule, FILTER_POLICIES, webcrypto.subtle);
  assert.equal(id, 'ed05c4aef00f6130eda8d84f5046cecb2734e9059469be4fd481bb0b4c64272d');
  const reversed = prepareFilterRule(copy(goldenDraftGroups).reverse().map(group => group.reverse()));
  assert.deepEqual(reversed.groupLabels, [1, 2]); assert.equal(await hashFilterRule(reversed.canonicalRule), id);
  const changed = copy(goldenDraftGroups); changed[0][0].threshold = '0.03';
  assert.notEqual(await hashFilterRule(prepareFilterRule(changed).canonicalRule), id);
  assert.notEqual(await hashFilterRule(canonicalRule, { ...FILTER_POLICIES, window: 'another-window' }), id);
  await assert.rejects(hashFilterRule(canonicalRule, FILTER_POLICIES, null), /filter_crypto_unavailable/);
  assert.throws(() => canonicalJson({ text: '非ASCII' }), /invalid_filter_rule/);
});

test('one GET has four parameters, sorted identity and frozen submitted rule, no mutation', async () => {
  const ids = ['b'.repeat(64), 'a'.repeat(64)], groups = copy(goldenDraftGroups);
  const pending = buildFilterRequest(ids, '2026-01-03', 2, groups);
  groups[0][0].threshold = '1'; ids.reverse();
  const request = await pending, url = new URL(request.path, 'http://localhost');
  assert.equal(url.pathname, '/api/research/universe-filter');
  assert.deepEqual([...url.searchParams.keys()].sort(), ['cutoff', 'lookback', 'rule', 'snapshot_ids']);
  assert.equal(url.searchParams.get('snapshot_ids'), ['a'.repeat(64), 'b'.repeat(64)].join(','));
  assert.deepEqual(JSON.parse(url.searchParams.get('rule')), request.expected.canonicalRule);
  assert.equal(request.expected.ruleId, 'ed05c4aef00f6130eda8d84f5046cecb2734e9059469be4fd481bb0b4c64272d');
  for (const args of [[['a'.repeat(64)], '2026-01-03', 2], [ids, '2026-02-30', 2], [ids, '', 2], [ids, '2026-01-03', 1],
    [[ids[0], ids[0]], '2026-01-03', 2], [ids, '2026-01-03', NaN]]) await assert.rejects(buildFilterRequest(...args, goldenDraftGroups), /invalid_research_request/);
});

test('final shared schema accepts scoped IDs, provenance absent/null and differing baseline order', async () => {
  const { reply, expected } = await makeFilterFixture();
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  reply.result.universe.members.reverse();
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  assert.equal(reply.result.conditions.length, 3);
  assert.equal(reply.result.source_contracts.length, 1);
  const semantics = reply.result.source_contracts[0].semantics;
  assert.deepEqual(semantics.adjustment.value, { present: true, value: null });
  assert.deepEqual(semantics.closed.value, { present: false, value: null });
  assert.deepEqual(semantics.price_unit.applicability, { present: true, value: 'unverified' });
});

test('wrong binding, schemas, scoped references, finite numbers, text and conservation reject whole report', async () => {
  const fixture = await makeFilterFixture();
  for (const mutate of [
    r => { r.method_id = 'selected-universe-research-v1'; }, r => { r.rule_id = '0'.repeat(64); },
    r => { r.parameters.policy_versions.window = 'future'; }, r => { r.parameters.cutoff = '2026-01-02'; },
    r => { r.parameters.lookback = 3; }, r => { r.parameters.canonical_rule.any_of.reverse(); },
    r => { r.inputs.reverse(); }, r => { r.inputs[1].query_id = r.inputs[0].query_id; },
    r => { r.result.members[0].source_ref = 'f'.repeat(64); }, r => { r.result.sources[0].contract_ref = 'f'.repeat(64); },
    r => { r.result.sources[0].query_id = 'f'.repeat(64); }, r => { r.result.sources[0].identity.qualification = 'certified'; },
    r => { r.result.members[0].window_ref = 'f'.repeat(64); }, r => { r.result.members[0].window.query_id = 'f'.repeat(64); },
    r => { r.result.members[0].window.expected_groups = 4; }, r => { r.result.members[0].window.first.close = 'NaN'; },
    r => { r.result.members[0].window.last.ordinal = -1; }, r => { r.result.members[0].window.drawdown_witness.peak.date = '2027-01-01'; },
    r => { r.result.conditions[0].threshold = '-0.100'; }, r => { r.result.conditions[1].id = 'a1'; },
    r => { r.result.members[0].atoms[0].id = 'a4'; }, r => { r.result.members[0].atoms[0].fact_ref = 'volatility'; },
    r => { r.result.members[0].atoms[0].reason_refs = ['r1']; }, r => { r.result.members[0].atoms[0].threshold = '0'; },
    r => { r.result.members[0].groups[0].atom_ids = ['a1', 'a6']; }, r => { r.result.members[0].groups[0].false_atoms = ['a1']; },
    r => { r.result.members[0].proof_groups = []; }, r => { r.result.members[0].source_gate = 'verified'; },
    r => { r.result.members[0].logical_truth = true; },
    r => { r.result.members[0].selection_state = 'excluded'; recountFilter(r); }, r => { r.result.members[0].selection_state = 'unknown'; },
    r => { r.result.members[0].partial_evidence = true; },
    r => { r.result.members[0].partial_evidence = true; r.result.members[0].evidence_complete = false; recountFilter(r); }, r => { r.result.members[0].facts.momentum.value = Infinity; },
    r => { r.result.members[0].facts.momentum.exact.denominator = '0'; }, r => { r.result.members[0].facts.momentum.exact.numerator = '1e2'; },
    r => { r.result.members[0].facts.volatility.estimate_text = 'Infinity'; },
    r => { r.result.members[0].facts.volatility.estimate_text = '0.9'; },
    r => { r.result.universe.members[0].coverage.coverage_known = false; },
    r => { unavailableFact(r, 0, 'volatility'); recountFilter(r); }, r => { r.result.members[0].facts.volatility.float_hex = '0.0'; },
    r => { r.result.members[0].facts.volatility.exact = { numerator: '0', denominator: '1' }; },
    r => { r.result.counts.selection.selected = 1; }, r => { r.result.counts.atoms.a1.true = 1; },
    r => { r.result.counts.groups.g3 = { true: 2, false: 0, unknown: 0 }; }, r => { r.result.reason_example_fields = ['ordinal', 'date']; },
    r => { r.result.source_contracts[0].semantics.closed.value.value = 'unknown'; }, r => { r.limitations.pop(); },
    r => { r.result.universe.members[0].max_drawdown = 1; }, r => { r.result.universe.parameters.volatility_ddof = 0; },
  ]) {
    const report = copy(fixture.reply); mutate(report);
    assert.throws(() => assertFilterReply(report, fixture.expected), /invalid_filter_response/, mutate.toString());
  }
});

function allUnavailable(reply, index, reason) {
  const m = reply.result.members[index];
  for (const field of ['momentum', 'volatility', 'max_drawdown']) unavailableFact(reply, index, field, reason);
  m.window.drawdown_witness = null;
  m.reasons = [{ id: 'r1', code: reason, scope: 'window', field: null, count: 1, examples: [], omitted_count: 0 }];
  m.primary_reason = reason; m.logical_truth = 'unknown'; m.selection_state = 'undetermined'; m.evidence_complete = false; m.partial_evidence = true;
  m.atoms.forEach(atom => { atom.truth = 'unknown'; atom.reason_refs = ['r1']; });
  m.groups.forEach(group => { group.truth = 'unknown'; }); indexReportedTruths(m); recountFilter(reply);
}

test('missing D actual window remains null although legacy end_date is D; short history retains actual dates', async () => {
  const { reply, expected } = await makeFilterFixture();
  const m = reply.result.members[0], base = reply.result.universe.members[0];
  allUnavailable(reply, 0, 'cutoff_missing');
  Object.assign(base, { cutoff_present: false, cutoff_valid: false, start_date: null, n_prices: 0, n_returns: 0 });
  Object.assign(m.window, { actual_groups: 0, start_date: null, end_date: null, first: null, last: null, n_prices: 0, n_returns: 0 });
  recountFilter(reply);
  assert.equal(base.end_date, expected.cutoff); assert.equal(m.window.end_date, null);
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  const wrong = copy(reply); wrong.result.members[0].window.end_date = expected.cutoff;
  assert.throws(() => assertFilterReply(wrong, expected), /invalid_filter_response/);
  const short = await makeFilterFixture(); allUnavailable(short.reply, 0, 'history_insufficient');
  Object.assign(short.reply.result.universe.members[0], { start_date: '2026-01-02', n_prices: 2, n_returns: 1 });
  Object.assign(short.reply.result.members[0].window, { start_date: '2026-01-02', actual_groups: 2, n_prices: 2, n_returns: 1,
    first: { date: '2026-01-02', ordinal: 1, close: '100' } });
  assert.doesNotThrow(() => assertFilterReply(short.reply, short.expected));
});

test('reported selected/excluded plus partial, F OR U and gate unknown remain distinct', async () => {
  for (const [groupTruths, logical, selection] of [[['true', 'unknown'], 'true', 'selected'], [['false', 'false'], 'false', 'excluded'], [['false', 'unknown'], 'unknown', 'undetermined']]) {
    const { reply, expected } = await makeFilterFixture();
    const m = reply.result.members[0]; unavailableFact(reply, 0, 'volatility');
    m.reasons = [{ id: 'r1', code: 'numerical_failure', scope: 'metric', field: 'volatility', count: 1, examples: [], omitted_count: 0 }];
    m.primary_reason = 'numerical_failure'; m.evidence_complete = false; m.partial_evidence = true;
    m.atoms.find(atom => atom.fact_ref === 'volatility').truth = 'unknown';
    m.atoms.find(atom => atom.fact_ref === 'volatility').reason_refs = ['r1'];
    if (groupTruths[0] === 'false') m.atoms.find(atom => atom.fact_ref === 'max_drawdown').truth = 'false';
    if (groupTruths[1] === 'false') m.atoms.find(atom => atom.fact_ref === 'momentum').truth = 'false';
    m.groups.forEach((group, index) => { group.truth = groupTruths[index]; });
    m.logical_truth = logical; m.selection_state = selection; indexReportedTruths(m); recountFilter(reply);
    assert.doesNotThrow(() => assertFilterReply(reply, expected));
    assert.equal(m.selection_state, selection); assert.equal(m.partial_evidence, true);
  }
  const { reply, expected } = await makeFilterFixture(); const m = reply.result.members[0];
  m.source_gate = 'unknown'; m.logical_truth = 'unknown'; m.selection_state = 'undetermined'; m.evidence_complete = false; m.partial_evidence = true;
  Object.assign(reply.result.universe.members[0].coverage, { source_rows: 4, unlocated_rows: 1, unreadable_date_rows: 1, batch_unlocated_rows: 1, coverage_known: false });
  m.reasons = [{ id: 'r1', code: 'date_set_integrity_unknown', scope: 'source_date', field: null, count: 1, examples: [], omitted_count: 0 }];
  m.primary_reason = 'date_set_integrity_unknown';
  m.atoms.forEach(atom => { atom.truth = 'unknown'; atom.reason_refs = ['r1']; }); m.groups.forEach(group => { group.truth = 'unknown'; });
  indexReportedTruths(m); recountFilter(reply);
  assert.doesNotThrow(() => assertFilterReply(reply, expected)); assert.equal(m.facts.momentum.value, 0);
  for (const mutate of [r => { r.result.members[0].selection_state = 'selected'; },
    r => { r.result.members[0].logical_truth = 'true'; },
    r => { r.result.members[0].atoms[0].truth = 'true'; indexReportedTruths(r.result.members[0]); },
    r => { r.result.members[0].atoms[0].reason_refs = []; }]) {
    const damaged = copy(reply); mutate(damaged); recountFilter(damaged);
    assert.throws(() => assertFilterReply(damaged, expected), /invalid_filter_response/);
  }
});

test('all-unknown and all-excluded still retain the full member denominator', async () => {
  const unknown = await makeFilterFixture();
  for (const index of [0, 1]) {
    allUnavailable(unknown.reply, index, 'cutoff_missing');
    Object.assign(unknown.reply.result.universe.members[index], { cutoff_present: false, cutoff_valid: false, start_date: null, n_prices: 0, n_returns: 0 });
    Object.assign(unknown.reply.result.members[index].window, { actual_groups: 0, start_date: null, end_date: null, first: null, last: null, n_prices: 0, n_returns: 0 });
  } recountFilter(unknown.reply);
  assert.doesNotThrow(() => assertFilterReply(unknown.reply, unknown.expected));
  assert.deepEqual(unknown.reply.result.counts.selection, { selected: 0, excluded: 0, undetermined: 2 });
  const excluded = await makeFilterFixture();
  excluded.reply.result.members.forEach((m, i) => {
    for (const [field, value, numerator, denominator] of [['momentum', -0.1, '-1', '10'], ['max_drawdown', -0.2, '-1', '5']]) {
      m.facts[field].value = value; m.facts[field].exact = { numerator, denominator };
      excluded.reply.result.universe.members[i][field] = value;
    }
    m.facts.volatility.value = 0.5; m.facts.volatility.estimate_text = '0.5'; m.facts.volatility.float_hex = '0x1.0000000000000p-1';
    excluded.reply.result.universe.members[i].volatility = 0.5;
    m.atoms.forEach(atom => { atom.truth = 'false'; }); m.groups.forEach(group => { group.truth = 'false'; });
    m.logical_truth = 'false'; m.selection_state = 'excluded'; indexReportedTruths(m);
  }); recountFilter(excluded.reply);
  assert.doesNotThrow(() => assertFilterReply(excluded.reply, excluded.expected));
  assert.deepEqual(excluded.reply.result.counts.selection, { selected: 0, excluded: 2, undetermined: 0 });
  assert.equal(excluded.reply.result.counts.selected_members, 2);
});

test('unenabled V failure stays in baseline and does not force partial or a false result', async () => {
  const { reply, expected } = await makeFilterFixture({ groups: one('0') });
  unavailableFact(reply, 0, 'volatility');
  reply.result.members[0].reasons = [{ id: 'r1', code: 'numerical_failure', scope: 'metric', field: 'volatility', count: 1, examples: [], omitted_count: 0 }];
  reply.result.members[0].primary_reason = 'numerical_failure'; recountFilter(reply);
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  assert.equal(reply.result.members[0].partial_evidence, false); assert.deepEqual(reply.result.members[0].atoms[0].reason_refs, []);
});

test('equal rounded 5.00% display keeps server Fraction decisions without numerical recomputation', async () => {
  const { reply, expected } = await makeFilterFixture({ groups: one('5') });
  reply.result.members.forEach((m, i) => {
    const base = reply.result.universe.members[i], truth = i ? 'true' : 'false';
    m.facts.momentum = { value: 0.05, reason: null, comparison_type: 'source_fraction', exact: { numerator: i ? '500000000000000001' : '499999999999999999', denominator: '10000000000000000000' } };
    base.momentum = 0.05; m.atoms[0].truth = truth; m.groups[0].truth = truth; m.logical_truth = truth;
    m.selection_state = i ? 'selected' : 'excluded'; indexReportedTruths(m);
  }); recountFilter(reply);
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  assert.equal(reply.result.members[0].facts.momentum.value, reply.result.members[1].facts.momentum.value);
  assert.notEqual(reply.result.members[0].atoms[0].truth, reply.result.members[1].atoms[0].truth);
});

test('eight tuple examples preserve null ordinal and omitted slots; every reason reference is member-local', async () => {
  const { reply, expected } = await makeFilterFixture({ lookback: 19, cutoff: '2026-01-20' });
  allUnavailable(reply, 0, 'invalid_price'); const m = reply.result.members[0];
  Object.assign(reply.result.universe.members[0], { cutoff_valid: false, n_prices: 0, n_returns: 0 });
  Object.assign(reply.result.universe.members[0].coverage, { valid_groups: 0, invalid_groups: 20 });
  Object.assign(m.window, { n_prices: 0, n_returns: 0 }); m.window.first.close = '0'; m.window.last.close = '0';
  recountFilter(reply);
  m.reasons = [{ id: 'r1', code: 'invalid_price', scope: 'window_slot', field: null, count: 20,
    examples: Array.from({ length: 8 }, (_, i) => [`2026-01-${String(i + 1).padStart(2, '0')}`, i === 0 ? null : i + 1]), omitted_count: 12 }];
  assert.doesNotThrow(() => assertFilterReply(reply, expected));
  for (const mutate of [r => { r.result.members[0].reasons[0].omitted_count = 11; },
    r => { r.result.members[0].reasons[0].examples[0] = { date: '2026-01-01', ordinal: null }; },
    r => { r.result.members[0].reasons[0].examples.push(['2026-01-09', 9]); },
    r => { r.result.members[1].atoms[0].reason_refs = ['r1']; }]) {
    const bad = copy(reply); mutate(bad); assert.throws(() => assertFilterReply(bad, expected), /invalid_filter_response/);
  }
  allUnavailable(reply, 1, 'history_insufficient');
  assert.doesNotThrow(() => assertFilterReply(reply, expected)); // r1 can mean a different reason in another member.
});

function responseStream(bytes, status = 200, onCancel = () => {}) {
  let offset = 0;
  return new Response(new ReadableStream({ pull(controller) {
    if (offset === bytes.length) { controller.close(); return; }
    const next = Math.min(offset + 4093, bytes.length); controller.enqueue(bytes.slice(offset, next)); offset = next;
  }, cancel: onCancel }), { status, headers: { 'Content-Length': '1' } });
}

test('512 KiB inclusive cap counts actual decoded-body bytes on success and HTTP errors', async () => {
  for (const status of [200, 409]) {
    const text = '{"error":"raw_object_corrupt"}', encode = size => new TextEncoder().encode(text + ' '.repeat(size - text.length));
    assert.deepEqual(await readFilterJson(responseStream(encode(FILTER_RESPONSE_LIMIT), status)), { error: 'raw_object_corrupt' });
    let cancelled = false;
    await assert.rejects(readFilterJson(responseStream(encode(FILTER_RESPONSE_LIMIT + 1), status, () => { cancelled = true; })), /filter_response_limit/);
    assert.equal(cancelled, true);
  }
  // Multibyte input and hostile Content-Length cannot evade byte accounting.
  await assert.rejects(readFilterJson(responseStream(new TextEncoder().encode('"' + '中'.repeat(180000) + '"'))), /filter_response_limit/);
  await assert.rejects(readFilterJson(new Response(new Uint8Array([255]))), /invalid_filter_response/);
  await assert.rejects(readFilterJson(new Response('not JSON')), /invalid_filter_response/);
});

test('transport uses one GET, no-store, same-origin, signal and safe bounded errors with no retries', async () => {
  const { request, reply } = await makeFilterFixture(), signal = new AbortController().signal;
  let calls = 0;
  const result = await fetchFilter(request, signal, async (path, options) => {
    calls++; assert.equal(path, request.path); assert.deepEqual(options, { method: 'GET', signal, cache: 'no-store', credentials: 'same-origin' });
    return new Response(JSON.stringify(reply));
  }); assert.equal(calls, 1); assert.deepEqual(result, reply);
  for (const [status, body, code] of [[404, '{"error":"snapshot_not_found"}', 'snapshot_not_found'],
    [409, '{"error":"raw_object_corrupt"}', 'raw_object_corrupt'], [500, '{"error":"/private/path"}', 'invalid_filter_response']]) {
    let count = 0;
    await assert.rejects(fetchFilter(request, signal, async () => { count++; return new Response(body, { status }); }), new RegExp(code));
    assert.equal(count, 1);
  }
  await assert.rejects(fetchFilter(request, signal, async () => new Response(' '.repeat(FILTER_RESPONSE_LIMIT + 1), { status: 500 })), /filter_response_limit/);
  assert.doesNotMatch(explainFilter(new Error('/private/path')), /private/);
  for (const code of ['invalid_filter_rule', 'filter_rule_limit', 'unsupported_filter_field', 'invalid_filter_operator', 'invalid_filter_threshold',
    'duplicate_filter_field', 'duplicate_filter_group', 'filter_crypto_unavailable', 'filter_response_limit', 'invalid_filter_response'])
    assert.match(explainFilter(new Error(code)), /[\u4e00-\u9fff]/);
});

test('synchronous admission blocks double submit and Enter during hash; edit during hash prevents fetch', async () => {
  const hash = deferred(), states = [], controller = new ResearchRequestController(state => states.push(state));
  let loads = 0;
  const first = controller.run(() => hash.promise, async () => { loads++; return 'A'; });
  assert.equal(controller.state.status, 'loading');
  assert.equal(await controller.run(() => 'duplicate', async () => { loads++; }), false);
  controller.invalidate(); hash.resolve('A'); await first;
  assert.equal(loads, 0); assert.equal(controller.state.status, 'dirty'); assert.equal(controller.state.result, null);
  assert.equal(await controller.run(() => 'B', async () => 'fresh'), true);
  assert.equal(controller.state.result, 'fresh'); assert.equal(states.filter(state => state.status === 'ready').length, 1);
});

test('A→B→A and stale success/error/finally cannot publish or unlock the current request', async () => {
  for (const staleOutcome of ['success', 'failure']) {
    const a = deferred(), b = deferred(), states = [], c = new ResearchRequestController(state => states.push(state));
    let signalA;
    const first = c.run(() => 'A', async (_, signal) => { signalA = signal; return a.promise; }); await tick();
    c.invalidate(); assert.equal(signalA.aborted, true);
    const second = c.run(() => 'B', () => b.promise); await tick();
    if (staleOutcome === 'success') a.resolve('stale'); else a.reject(new Error('raw_object_corrupt'));
    await first;
    assert.equal(c.state.status, 'loading'); assert.equal(await c.run(() => 'A', async () => 'blocked'), false);
    b.resolve('B response'); await second; assert.equal(c.state.result, 'B response');
    c.invalidate(); await c.run(() => 'A', async () => 'fresh A');
    assert.deepEqual(states.filter(state => state.status === 'ready').map(state => state.result), ['B response', 'fresh A']);
  }
});

test('cancel/unmount preserve no report and stale responses or hash errors remain silent', async () => {
  for (const action of ['cancel', 'dispose']) for (const stage of ['hash', 'fetch']) for (const outcome of ['resolve', 'reject']) {
    const pending = deferred(), states = [], c = new ResearchRequestController(state => states.push(state));
    const run = c.run(() => stage === 'hash' ? pending.promise : 'spec', () => pending.promise); await tick();
    c[action](); const count = states.length;
    if (outcome === 'resolve') pending.resolve('old'); else pending.reject(new Error('snapshot_not_found'));
    await run; assert.equal(states.length, count); assert.equal(c.state.result, null); assert.equal(c.state.error, null);
    if (action === 'dispose') assert.equal(await c.run(() => 'again', async () => 'no'), false);
    else { await c.run(() => 'retry', async () => 'done'); assert.equal(c.state.result, 'done'); }
  }
});

test('current error clears report, preserves request snapshot and allows explicit retry only', async () => {
  const c = new ResearchRequestController(() => {}), spec = { ids: ['a', 'b'], cutoff: '2026-01-03', rules: 'A' };
  await c.run(() => spec, async () => 'ready');
  let attempts = 0;
  await c.run(() => spec, async () => { attempts++; throw new Error('raw_object_corrupt'); });
  assert.equal(c.state.status, 'error'); assert.equal(c.state.result, null); assert.deepEqual(c.state.spec, spec); assert.equal(attempts, 1);
  await c.run(() => spec, async () => { attempts++; return 'rechecked'; });
  assert.equal(attempts, 2); assert.equal(c.state.status, 'ready'); assert.equal(c.state.result, 'rechecked');
  c.invalidate(); assert.equal(c.state.result, null); assert.equal(c.state.status, 'dirty');
});
