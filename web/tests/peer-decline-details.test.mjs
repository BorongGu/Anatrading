import test from 'node:test';
import assert from 'node:assert/strict';
import { peerDeclineDetails } from '../src/peer-decline-details.ts';
import { assertPeerNeighbors, verifyPeerNeighborIdentity } from '../src/peer-neighbor-model.ts';
import { declineFixture, setSourcePrices, fourStepPrices } from './peer-decline-fixtures.mjs';

function available(fixture) {
  const result = peerDeclineDetails(fixture.report, fixture.peerId);
  assert.equal(result.available, true);
  return result;
}

function cells(window) {
  return Object.values(window.counts);
}

function assertMargins(window) {
  const [dd, dn, nd, nn] = cells(window);
  assert.equal(dd + dn + nd + nn, 60);
  assert.equal(window.total, 60);
  assert.equal(window.targetDown, dd + dn);
  assert.equal(window.targetNonDown, nd + nn);
  assert.equal(window.peerDown, dd + nd);
  assert.equal(window.peerNonDown, dn + nn);
  assert.equal(window.jointDownDates.length, dd);
}

const invalidPrices = [
  null, undefined, 1, '', 'NaN', 'Infinity', '0', '-0', '-1', '+1', '01', '1.0',
  '1.', '.1', ' 1', '1 ', '1e0', '1E-999999999', '1'.repeat(10000),
  '100000000000000000000', '0.0000000000000000001',
];
for (const value of invalidPrices) {
  test(`invalid price closes both windows: ${String(value).slice(0, 50)}`, () => {
    const fixture = declineFixture();
    const peer = fixture.report.members.find(member => member.snapshot_id === fixture.peerId);
    peer.endpoints[120].close_exact = value;
    assert.deepEqual(peerDeclineDetails(fixture.report, fixture.peerId), {
      available: false, reason: 'invalid_source_endpoints',
    });
  });
}

const invalidSources = {
  panelClosed: f => { f.report.source_panel_complete = false; },
  panelReason: f => { f.report.reasons = ['source_panel_unavailable']; },
  anotherMemberClosed: f => { f.report.members.at(-1).panel_complete = false; },
  unqualified: f => { f.report.members[0].source_qualified = false; },
  unassessed: (f, peer) => { peer.evaluation = 'not_evaluated'; },
  memberReason: (f, peer) => { peer.reasons = ['global_source_conflict']; },
  noEndpoints: (f, peer) => { peer.endpoints = null; },
  truncatedEndpoints: (f, peer) => { peer.endpoints.pop(); },
  extraEndpoint: (f, peer) => { peer.endpoints.push(peer.endpoints[120]); },
  missingEndpoint: (f, peer) => { peer.endpoints[60] = null; },
  endpointReason: (f, peer) => { peer.endpoints[60].reasons = ['invalid_price']; },
  missingOrdinal: (f, peer) => { peer.endpoints[60].ordinal = null; },
  duplicateOrdinal: (f, peer) => { peer.endpoints[60].ordinal = peer.endpoints[59].ordinal; },
  wrongDate: (f, peer) => { peer.endpoints[60].date = f.report.used_dates[59]; },
  invalidDate: f => { f.report.used_dates[60] = '2026-02-30'; },
  duplicateDate: f => { f.report.used_dates[60] = f.report.used_dates[59]; },
  missingDate: f => { f.report.used_dates.splice(60, 1); },
  wrongCutoff: f => { f.report.parameters.cutoff = '2026-12-31'; },
  targetInvalid: (f, peer, target) => { target.endpoints[0].close_exact = null; },
};
for (const [name, mutate] of Object.entries(invalidSources)) {
  test(`source failure never becomes non-down: ${name}`, () => {
    const fixture = declineFixture();
    const peer = fixture.report.members.find(member => member.snapshot_id === fixture.peerId);
    const target = fixture.report.members.find(member => member.snapshot_id === fixture.targetId);
    mutate(fixture, peer, target);
    const result = peerDeclineDetails(fixture.report, fixture.peerId);
    assert.equal(result.available, false);
    assert.equal('previous' in result, false);
    assert.equal('current' in result, false);
  });
}

const invalidIdentities = {
  unknownPeer: f => { f.peerId = 'f'.repeat(64); },
  selfPeer: f => { f.peerId = f.targetId; },
  unknownTarget: f => { f.report.parameters.target_snapshot_id = 'f'.repeat(64); },
  wrongTargetRole: f => { f.report.members.find(m => m.snapshot_id === f.targetId).role = 'candidate'; },
  wrongPeerRole: f => { f.report.members.find(m => m.snapshot_id === f.peerId).role = 'target'; },
  duplicateMember: f => { f.report.members.push(f.report.members[0]); },
  missingCandidate: f => { f.report.candidates = f.report.candidates.filter(c => c.snapshot_id !== f.peerId); },
  duplicateCandidate: f => { f.report.candidates.push(f.report.candidates[0]); },
};
for (const [name, mutate] of Object.entries(invalidIdentities)) {
  test(`wrong identity unavailable: ${name}`, () => {
    const fixture = declineFixture();
    mutate(fixture);
    assert.deepEqual(peerDeclineDetails(fixture.report, fixture.peerId), {
      available: false, reason: 'invalid_member_identity',
    });
  });
}

test('qualified constant report passes existing DTO and identity checks, with flat counts despite unavailable rho', async () => {
  const fixture = declineFixture();
  const { report, targetId } = fixture;
  assertPeerNeighbors(report, {
    ids: report.members.map(member => member.snapshot_id),
    target: targetId, cutoff: report.parameters.cutoff,
  });
  await verifyPeerNeighborIdentity(report);
  const before = structuredClone(report);
  for (const window of Object.values(available(fixture)).filter(value => typeof value === 'object')) {
    assert.deepEqual(cells(window), [0, 0, 0, 60]);
    assert.equal(window.targetFlat, 60);
    assert.equal(window.peerFlat, 60);
    assertMargins(window);
  }
  assert.deepEqual(report, before);
});

test('four-step witness maps into fixed windows only by adding flat edges', () => {
  for (const [peerName, expectedFour] of [['a', [1, 1, 0, 2]], ['b', [0, 2, 1, 1]]]) {
    const fixture = declineFixture();
    setSourcePrices(fixture.report, fixture.targetId, fourStepPrices.target);
    setSourcePrices(fixture.report, fixture.peerId, fourStepPrices[peerName]);
    const result = available(fixture);
    const observedFour = cells(result.previous);
    observedFour[3] -= 56;
    assert.deepEqual(observedFour, expectedFour);
    assert.equal(result.previous.targetFlat, 56);
    assert.equal(result.previous.peerFlat, 56);
    assert.deepEqual(result.previous.jointDownDates, peerName === 'a' ? [{
      previousDate: fixture.report.used_dates[1], date: fixture.report.used_dates[2],
    }] : []);
    assert.deepEqual(cells(result.current), [0, 0, 0, 60]);
    assertMargins(result.previous);
    assertMargins(result.current);
    // No Pearson equivalence is asserted for the 60-edge padded paths.
  }
});

test('flat is non-down independently for target and peer, with all four cells and margins', () => {
  const fixture = declineFixture();
  setSourcePrices(fixture.report, fixture.targetId, ['100', '99', '98', '98', '98']);
  setSourcePrices(fixture.report, fixture.peerId, ['100', '99', '99', '98', '98']);
  const window = available(fixture).previous;
  assert.deepEqual(cells(window), [1, 1, 1, 57]);
  assert.equal(window.targetFlat, 58);
  assert.equal(window.peerFlat, 58);
  assertMargins(window);
});

test('max Decimal(38,18), 1e-18 differences, minimum price and lexical traps remain exact', () => {
  const fixture = declineFixture();
  const prices = [
    '99999999999999999999.999999999999999999',
    '99999999999999999999.999999999999999998',
    '10', '9', '0.000000000000000002', '0.000000000000000001',
  ];
  setSourcePrices(fixture.report, fixture.targetId, prices);
  setSourcePrices(fixture.report, fixture.peerId, prices);
  const window = available(fixture).previous;
  assert.deepEqual(cells(window), [5, 0, 0, 55]);
  assert.equal(window.targetFlat, 55);
  assert.equal(window.peerFlat, 55);
  assertMargins(window);
});

test('60+60 uses shared endpoint once in each adjoining edge without duplicate changes', () => {
  const fixture = declineFixture();
  const target = Array.from({ length: 121 }, (_, i) => i < 60 ? '100' : i === 60 ? '99' : '98');
  const peer = Array.from({ length: 121 }, (_, i) => i < 60 ? '100' : i === 60 ? '99' : '101');
  setSourcePrices(fixture.report, fixture.targetId, target);
  setSourcePrices(fixture.report, fixture.peerId, peer);
  const result = available(fixture);
  assert.deepEqual(cells(result.previous), [1, 0, 0, 59]);
  assert.deepEqual(cells(result.current), [0, 1, 0, 59]);
  assert.deepEqual(result.previous.jointDownDates, [{
    previousDate: fixture.report.used_dates[59], date: fixture.report.used_dates[60],
  }]);
  assert.deepEqual(result.current.jointDownDates, []);
  assertMargins(result.previous);
  assertMargins(result.current);
});

test('all 120 falling edges appear exactly once, including current-window start and final edge', () => {
  const fixture = declineFixture();
  const prices = Array.from({ length: 121 }, (_, i) => String(200 - i));
  setSourcePrices(fixture.report, fixture.targetId, prices);
  setSourcePrices(fixture.report, fixture.peerId, prices);
  const result = available(fixture);
  const dates = [...result.previous.jointDownDates, ...result.current.jointDownDates];
  assert.deepEqual(dates, fixture.report.used_dates.slice(1).map((date, i) => ({
    previousDate: fixture.report.used_dates[i], date,
  })));
  assert.equal(new Set(dates.map(event => event.date)).size, 120);
  assert.deepEqual(cells(result.previous), [60, 0, 0, 0]);
  assert.deepEqual(cells(result.current), [60, 0, 0, 0]);
});

test('constant positive source changes can be non-down without being flat', () => {
  const fixture = declineFixture();
  const target = Array.from({ length: 121 }, (_, i) => (2n ** BigInt(Math.min(i, 60))).toString());
  const peer = Array.from({ length: 121 }, (_, i) => String(200 - i));
  setSourcePrices(fixture.report, fixture.targetId, target);
  setSourcePrices(fixture.report, fixture.peerId, peer);
  const result = available(fixture);
  assert.deepEqual(cells(result.previous), [0, 0, 60, 0]);
  assert.equal(result.previous.targetFlat, 0);
  assert.equal(result.current.targetFlat, 60);
  assertMargins(result.previous);
  assertMargins(result.current);
});

test('candidate-only constant correlation failure does not gate source sign counts', () => {
  const fixture = declineFixture();
  setSourcePrices(fixture.report, fixture.targetId, ['100', '99', '100']);
  for (const candidate of fixture.report.candidates) {
    candidate.previous.reason = 'constant_source_change';
    candidate.current.reason = 'constant_source_change';
  }
  fixture.report.windows.previous.target_reason = null;
  fixture.report.windows.current.target_reason = null;
  const result = available(fixture);
  assert.deepEqual(cells(result.previous), [0, 1, 0, 59]);
  assert.equal(result.previous.peerFlat, 60);
  assertMargins(result.previous);
});
