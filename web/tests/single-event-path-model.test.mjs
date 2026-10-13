import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isEventPathPrice } from '../src/single-event-path.ts';
const concepts = JSON.parse(readFileSync(new URL('../../docs/research/056-single-event-six-slot-concepts.json', import.meta.url)));
test('frozen lexical boundaries retain exact decimal domain without arithmetic', () => {
  for (const value of concepts.price_text_cases.accepted) assert.equal(isEventPathPrice(value), true, value);
  for (const value of [...concepts.price_text_cases.rejected, null, 1, false, {}, '1\n', '1\r', '1\r\n']) assert.equal(isEventPathPrice(value), false, String(value));
});

import { acceptEventPath, captureEventPath, eventPathBelongs, eventPathMembership } from '../src/single-event-path.ts';
import { assertResearchReply } from '../src/research-model.ts';
import { fixture, names, context } from './single-event-path-fixtures.mjs';
const accept = f => { assertResearchReply(f.reply, f.expected); return acceptEventPath(f.reply, context(f.query), f.expected); };
for (const name of names) test(`complete synthetic DTO: ${name}`, () => {
  const f = fixture(name), before = structuredClone(f.reply);
  assertResearchReply(f.reply, f.expected);
  if (f.expected.parameters.horizon !== 5) { assert.throws(() => accept(f)); return; }
  const a = accept(f);
  for (let position = Math.max(0, f.reply.result.events.rows.length - 100); position < f.reply.result.events.rows.length; position++) {
    const p = captureEventPath(a, position), e = f.reply.result.events.rows[position];
    assert.equal(p.slots.length, 6); assert.deepEqual(p.event, e);
    for (const slot of p.slots) {
      const row = f.reply.result.series[e.index + slot.offset];
      assert.equal(slot.exists, !!row); assert.equal(slot.close, row?.close ?? null); assert.equal(slot.date, row?.date ?? null); assert.equal(slot.ordinal, row?.ordinal ?? null);
    }
    for (const obj of [p,p.event,p.identity,p.parameters,p.slots,...p.slots]) assert.equal(Object.isFrozen(obj), true);
    assert.notEqual(p.event, e); assert.notEqual(p.parameters, f.reply.parameters);
    assert.equal(Object.isFrozen(f.reply), false); assert.equal(Object.isFrozen(e), false);
  }
  if (name === 'RECENT101') assert.throws(() => captureEventPath(a, 0), /event_path_inconsistent/);
  if (name === 'RECENT0') assert.throws(() => captureEventPath(a, 0), /event_path_inconsistent/);
  assert.deepEqual(f.reply,before);
});
test('same ID and same object acceptance get independent tokens and context is complete', () => {
  const f=fixture(), a=accept(f), b=accept(f); assert.notEqual(a.token,b.token);
  assert.equal(eventPathBelongs(a,f.reply,context(f.query)),true);
  for (const [key,value] of [['ownerQueryId','e'.repeat(64)],['snapshotId','f'.repeat(64)],['cutoff',null],['ordinalStart',2],['ordinalEnd',10]]) assert.equal(eventPathBelongs(a,f.reply,{...context(f.query),[key]:value}),false);
  assert.equal(eventPathBelongs(a,structuredClone(f.reply),context(f.query)),false);
});
test('owned projection keeps exact fields without source aliases or freezing source descriptors', () => {
  const f=fixture(), a=accept(f), source=f.reply.result.series[22], desc=Object.getOwnPropertyDescriptor(source,'close'), p=captureEventPath(a,0);
  assert.throws(()=>{p.slots[2].close='900';},TypeError);
  assert.deepEqual(Object.getOwnPropertyDescriptor(source,'close'),desc);
  source.close='901'; // Deliberate unsupported external mutation: only projection isolation is asserted.
  assert.equal(p.slots[2].close,'95');
});
test('actual displayed partition explains original membership without rewriting state', () => {
  const f=fixture('P5_OTHER_PART'),p=captureEventPath(accept(f),f.eventPosition),before=structuredClone(p);
  assert.match(eventPathMembership(p,'test'),/本条不计入/);assert.match(eventPathMembership(p,'train'),/计入当前训练段/);assert.deepEqual(p,before);
  const x=fixture('P5_OVERLAP');assert.match(eventPathMembership(captureEventPath(accept(x),x.eventPosition),'descriptive'),/未计入/);
});
const malformed = [
 ['start endpoint',f=>f.reply.result.events.rows[0].start_close='99','endpoint'],
 ['end endpoint',f=>f.reply.result.events.rows[0].end_close='99','endpoint'],
 ['unknown label',f=>f.reply.result.events.rows[0].label_status='new','label_state'],
 ['priority',f=>f.reply.result.events.rows[0].selected=false,'evaluation_state'],
 ['wrong partition counts',f=>{f.reply.result.events.partitions.descriptive.counts.raw_events++; f.reply.result.events.partitions.descriptive.counts.selected_events++;f.reply.result.events.partitions.descriptive.counts.immature++;},'partition_counts'],
 ['missing endpoint',f=>delete f.reply.result.events.rows[0].start_close,'endpoint'],
 ['D mismatch',f=>{f.reply.result.events.evaluation_as_of='2026-01-19';for(const e of f.reply.result.events.rows)e.evaluation_as_of='2026-01-19';},'cutoff'],
];
for(const [name,mutate,code] of malformed)test(`deliberately inconsistent acceptance: ${name}`,()=>{
 const f=fixture();mutate(f);assertResearchReply(f.reply,f.expected);const before=structuredClone(f.reply);
 assert.throws(()=>accept(f),e=>e.code===code);assert.deepEqual(f.reply,before);
});
for(const [name,patch,code] of [
 ['nonpositive valid',{close:'0'},'label_state'],['malformed price',{close:'1.0'},'price_text'],['duplicate structure',{reason:'duplicate_date',status:'invalid'},'slot_structure'],
 ['source failure',{reason:'invalid_ohlc',status:'invalid'},'label_state'],['future reason',{reason:'future_reason',status:'invalid'},'label_state'],['computed reason',{reason:'numerical_failure'},'slot_structure'],
])test(`deliberately inconsistent capture: ${name}`,()=>{const f=fixture();Object.assign(f.reply.result.series[22],patch);const a=accept(f),before=structuredClone(f.reply);assert.throws(()=>captureEventPath(a,0),e=>e.code===code);assert.deepEqual(f.reply,before);});
test('existing validator rejects mismatched event links; extra safe fields remain accepted',()=>{
 const f=fixture();f.reply.result.events.rows[0].ordinal++;assert.throws(()=>assertResearchReply(f.reply,f.expected),/invalid_research_response/);
 const g=fixture();g.reply.result.extra={safe:'retained'};assert.doesNotThrow(()=>captureEventPath(accept(g),0));
});
test('graph Q can differ from research Q and request cutoff stays distinct from D',()=>{
 const f=fixture('NULL_CUTOFF');f.query.query_id='b'.repeat(64);
 const p=captureEventPath(accept(f),0);assert.equal(p.identity.ownerQueryId,'b'.repeat(64));assert.equal(p.identity.researchQueryId,'c'.repeat(64));
 assert.equal(p.parameters.requestedCutoff,null);assert.equal(p.parameters.evaluationAsOf,'2026-01-13');
 const g=fixture('EXPLICIT_GAP_CUTOFF'),q=captureEventPath(accept(g),0);assert.equal(q.parameters.evaluationAsOf,'2026-01-20');assert.equal(q.slots[5].date,'2026-01-13');
});
