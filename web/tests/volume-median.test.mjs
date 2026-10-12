import test from 'node:test';
import assert from 'node:assert/strict';
import { historicalVolumeMedian } from '../src/volume-median.ts';
import { volumeFixture } from './volume-median-fixtures.mjs';
const calculate = f => historicalVolumeMedian(f.comparison, f);
const available = exact_text => ({ status: 'available', exact_text });
const invalid = { status: 'invalid', exact_text: null };
const unavailable = { status: 'source_unavailable', exact_text: null };

// Bad inputs are frozen before implementation. Each case must close just the summary.
for (const [name, mutate] of [
  ['unknown comparison field', f => f.comparison.median = '100'],
  ['missing comparison field', f => delete f.comparison.ratio],
  ['null comparison', f => f.comparison = null],
  ['array comparison', f => f.comparison = []],
  ['missing members', f => delete f.comparison.members],
  ['nonarray members', f => f.comparison.members = {}],
  ['null member', f => f.comparison.members[0] = null],
  ['unknown member field', f => f.comparison.members[0].quality = 'good'],
  ['missing member reason', f => delete f.comparison.members[0].reason],
  ['unknown member reason', f => f.comparison.members[0].reason = 'new_reason'],
  ['invalid reason type', f => f.comparison.reason = {}],
  ['missing mean numerator', f => delete f.comparison.baseline_mean.numerator],
  ['unknown mean field', f => f.comparison.baseline_mean.estimate = true],
  ['numeric mean', f => f.comparison.baseline_mean = 100],
  ['bad mean display', f => f.comparison.baseline_mean.display = {}],
  ['zero denominator', f => f.comparison.baseline_mean.denominator = '0'],
  ['overlong denominator', f => f.comparison.baseline_mean.denominator = '1'.repeat(10000)],
  ['overlong numerator', f => f.comparison.baseline_mean.numerator = '1'.repeat(10000)],
  ['wrong sum', f => f.comparison.baseline_sum = '10401'],
  ['wrong mean', f => f.comparison.baseline_mean.numerator = '2081'],
  ['wrong ratio shape', f => f.comparison.ratio = {}],
  ['bad current type', f => f.comparison.current = 200],
  ['missing mean with no reason', f => f.comparison.baseline_mean = null],
  ['unknown dates DTO', f => f.historyDates = {}],
  ['missing history date', f => f.historyDates = f.historyDates.slice(1)],
  ['mismatched date order', f => f.historyDates = [...f.historyDates].reverse()],
  ['duplicate date', f => { f.comparison.members[1].date = f.historyDates[0]; f.historyDates[1] = f.historyDates[0]; }],
  ['nonleap February29', f => { f.comparison.members[0].date = f.historyDates[0] = '2023-02-29'; }],
  ['invalid February30', f => { f.comparison.members[0].date = f.historyDates[0] = '2024-02-30'; }],
  ['invalid April31', f => { f.comparison.members[0].date = f.historyDates[0] = '2024-04-31'; }],
  ['year zero', f => { f.comparison.members[0].date = f.historyDates[0] = '0000-01-01'; }],
  ['same current date', f => f.currentDate = f.historyDates[4]],
  ['future member', f => f.currentDate = '2023-01-01'],
  ['invalid current date', f => f.currentDate = '2025-02-29'],
  ['minute label in date', f => f.currentDate = '2025-01-01T09:31'],
  ['unknown kind', f => f.kind = 'weekly'],
  ['too small N', f => f.lookback = 1],
  ['too large N', f => f.lookback = 253],
  ['fractional N', f => f.lookback = 5.5],
  ['text N', f => f.lookback = '5'],
]) test(`invalid DTO: ${name}`, () => {
  const f = volumeFixture(); mutate(f); const before = structuredClone(f);
  assert.deepEqual(calculate(f), invalid); assert.deepEqual(f, before);
});
for (const value of ['01', '-1', '+1', '1.0', '1e2', ' 1', '1 ', '', '1'.repeat(10000), '9223372036854775808', 100, null]) test(`bad quantity ${String(value).slice(0, 28)}`, () => {
  const f = volumeFixture(); f.comparison.members[0].value = value; assert.deepEqual(calculate(f), invalid);
});
for (const kind of ['daily', 'regular', 'cumulative']) {
  test(`${kind}: N5/M4/K4 and N5/M5/K4 keep original source failure`, () => {
    for (const absent of [true, false]) {
      const f = volumeFixture(undefined, kind);
      if (absent) { f.comparison.members.pop(); f.historyDates.pop(); } else Object.assign(f.comparison.members[2], { value: null, reason: 'missing_quantity' });
      Object.assign(f.comparison, { baseline_sum: null, baseline_mean: null, ratio: null, reason: absent ? 'history_insufficient' : 'missing_quantity' });
      const before = structuredClone(f); assert.deepEqual(calculate(f), unavailable); assert.deepEqual(f, before);
    }
  });
  test(`${kind}: current error inherits the original closed mean gate`, () => {
    const f = volumeFixture(undefined, kind);
    Object.assign(f.comparison, { current: null, baseline_sum: null, baseline_mean: null, ratio: null, reason: 'invalid_quantity' });
    assert.deepEqual(calculate(f), unavailable);
  });
}
for (const [values, expected] of [
  [['1', '2'], '1.5'], [['100', '10000'], '5050'], [['100', '100', '100'], '100'],
  [['100', '100', '100', '100', '10000'], '100'], [['100', '100', '100', '10000', '10000'], '100'],
  [['100', '10000', '10000'], '10000'], [['100', '100', '10000', '10000'], '5050'],
  [['0', '100', '200'], '100'], [['0', '0', '100'], '0'], [['0', '0'], '0'],
  [['9', '100', '10'], '10'], [['9007199254740992', '9007199254740993'], '9007199254740992.5'],
  [['9223372036854775806', '9223372036854775807'], '9223372036854775806.5'],
]) for (const kind of ['daily', 'regular', 'cumulative']) test(`${kind} hand calculation ${values} → ${expected}`, () => {
  const f = volumeFixture(values, kind), before = structuredClone(f);
  Object.freeze(f.comparison.members); f.comparison.members.forEach(Object.freeze);
  assert.deepEqual(calculate(f), available(expected)); assert.deepEqual(f, before);
});
test('cumulative allows 240 signed64 quantities but neither unbounded totals nor narrow-slot overflow', () => {
  const values = ['2213609288845146193679', '2213609288845146193680'];
  assert.deepEqual(calculate(volumeFixture(values, 'cumulative')), available('2213609288845146193679.5'));
  assert.deepEqual(calculate(volumeFixture(values, 'regular')), invalid);
  assert.deepEqual(calculate(volumeFixture(['2213609288845146193680', '2213609288845146193681'], 'cumulative')), invalid);
});
test('maximum252 and minimum2 are accepted without subset or hidden window rewrite', () => {
  assert.deepEqual(calculate(volumeFixture(Array(252).fill('7'))), available('7'));
  const f = volumeFixture(); f.lookback = 4; assert.deepEqual(calculate(f), invalid);
});
test('Gregorian leap centuries are parsed rather than just compared lexically', () => {
  const f = volumeFixture(['1', '2']); f.historyDates[0] = f.comparison.members[0].date = '2000-02-29';
  assert.deepEqual(calculate(f), available('1.5'));
  f.historyDates[0] = f.comparison.members[0].date = '1900-02-29'; assert.deepEqual(calculate(f), invalid);
});
test('cumulative median uses daily cumulative members, not summed slot medians', () => {
  assert.deepEqual(calculate(volumeFixture(['0', '100', '0'])), available('0'));
  assert.deepEqual(calculate(volumeFixture(['100', '0', '0'])), available('0'));
  assert.deepEqual(calculate(volumeFixture(['100', '100', '0'], 'cumulative')), available('100'));
});
test('regular and cumulative completeness are independent', () => {
  const regular = volumeFixture(['0', '100', '0']), cumulative = volumeFixture(['100', '100', '0'], 'cumulative');
  Object.assign(cumulative.comparison.members[0], { value: null, reason: 'missing_slot' });
  Object.assign(cumulative.comparison, { baseline_sum: null, baseline_mean: null, ratio: null, reason: 'missing_slot' });
  assert.deepEqual(calculate(regular), available('0')); assert.deepEqual(calculate(cumulative), unavailable);
});
test('changed valid current quantity, including zero, cannot change history or old ratio', () => {
  for (const current of ['0', '200', '9223372036854775807']) {
    const f = volumeFixture(['0', '0', '100'], 'regular', current), before = structuredClone(f.comparison);
    assert.deepEqual(calculate(f), available('0')); assert.deepEqual(f.comparison, before);
  }
});
test('daily extension fields are known and cannot disagree with the same history_dates', () => {
  const f = volumeFixture(['1', '2'], 'daily'); f.comparison.history_dates = [...f.historyDates].reverse();
  assert.deepEqual(calculate(f), invalid); f.comparison.history_dates = f.historyDates; f.comparison.ordinal = -1;
  assert.deepEqual(calculate(f), invalid); f.comparison.ordinal = 0; assert.deepEqual(calculate(f), invalid);
});
test('hostile local object access is isolated, although HTTP JSON cannot contain getters', () => {
  const f = volumeFixture(); Object.defineProperty(f.comparison, 'members', { get() { throw new Error('bad'); } });
  assert.deepEqual(calculate(f), invalid);
});

test('source failure reasons must agree with the known comparison and member scenarios', () => {
  const f = volumeFixture();
  Object.assign(f.comparison, { baseline_sum: null, baseline_mean: null, ratio: null, reason: 'history_insufficient' });
  assert.deepEqual(calculate(f), invalid);
  Object.assign(f.comparison.members[0], { value: null, reason: 'history_insufficient' });
  assert.deepEqual(calculate(f), invalid);
  Object.assign(f.comparison.members[0], { value: null, reason: 'duplicate_date' });
  f.comparison.reason = 'duplicate_date'; assert.deepEqual(calculate(f), invalid);
  const daily = volumeFixture(['1', '2'], 'daily');
  Object.assign(daily.comparison, { current: null, baseline_sum: null, baseline_mean: null, ratio: null, reason: 'unlocated_label' });
  daily.currentDate = null; assert.deepEqual(calculate(daily), unavailable);
});
