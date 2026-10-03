import test from 'node:test';
import assert from 'node:assert/strict';
import { SequenceAxis } from '../src/sequence-axis.ts';

test('index zero and duplicate source labels format without Date conversion', () => {
  const labels = ['2020-12-15T09:33', '2020-12-15T09:33', '2020-12-16T09:30'];
  const axis = new SequenceAxis(labels);
  labels[0] = 'mutated outside';
  assert.equal(axis.formatHorzItem(0), '2020-12-15T09:33');
  assert.equal(axis.formatTickmark({ time: 1 }), '2020-12-15T09:33');
  assert.equal(axis.formatHorzItem(-1), '');
  assert.equal(axis.formatHorzItem(3), '');
  assert.equal(axis.key(axis.convertHorzItemToInternal(0)), 0);
  assert.equal(axis.createConverterToInternalObj()(2), 2);
});

test('axis instances cannot expose labels from previous query', () => {
  const oldAxis = new SequenceAxis(['future']);
  const currentAxis = new SequenceAxis([]);
  assert.equal(oldAxis.formatHorzItem(0), 'future');
  assert.equal(currentAxis.formatHorzItem(0), '');
  assert.equal(currentAxis.maxTickMarkWeight([]), 0);
});

test('date boundary weight does not create missing minutes or alter index', () => {
  const axis = new SequenceAxis(['2021-01-04T11:30', '2021-01-04T13:00', '2021-01-05T09:30']);
  const points = [0, 1, 2].map(time => ({ time, timeWeight: 0, originalTime: time }));
  axis.fillWeightsForPoints(points, 0);
  assert.deepEqual(points.map(p => p.time), [0, 1, 2]);
  assert.deepEqual(points.map(p => p.timeWeight), [50, 10, 50]);
});
