import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { scanCloseReversals, parseThresholdBps, captureReversalSource, buildReversalReport } from '../src/close-reversal.ts';
import { fixture, context } from './single-event-path-fixtures.mjs';
const cases=JSON.parse(readFileSync(new URL('./close-reversal-fixtures.json',import.meta.url))).cases;
const oracles=JSON.parse(readFileSync(new URL('./close-reversal-oracles.json',import.meta.url)));
const options={yieldControl:async()=>{}};
const points=closes=>closes.map((close_exact,index)=>({index,date:new Date(Date.UTC(2020,0,index+1)).toISOString().slice(0,10),ordinal:String(index*19+2),close_exact,close_token:null,token_status:'unavailable_in_parent_report'}));
const oracleEvent=({anchor,confirmation,...rest})=>rest;
for(const c of cases)test(`independent exact oracle and prefixes ${c.id}`,async()=>{
 const input=points(c.closes),result=await scanCloseReversals(input,600,options);
 for(const mode of ['up','down']){
  const expected=oracles.find(o=>o.case===c.id&&o.initial_mode===mode);
  assert.deepEqual(result[mode].events.map(oracleEvent),expected.events);
  const {extreme,last_observation,...terminal}=result[mode].terminal;
  assert.deepEqual(terminal,expected.terminal);
  for(let n=1;n<=input.length;n++){
   const prefix=await scanCloseReversals(input.slice(0,n),600,options);
   assert.deepEqual(prefix[mode].events,result[mode].events.filter(e=>e.confirmation_index<n));
  }
 }
});
test('strict basis-point parser rejects coerced values',()=>{
 for(const v of [1,9999,600,'1','9999','600'])assert.equal(parseThresholdBps(v),Number(v));
 for(const v of [false,true,null,undefined,0,10000,-1,1.1,'',' 600','600 ','6e2','600.0','0600','1\n',[],{}])assert.throws(()=>parseThresholdBps(v));
});
test('whole sequence lexical errors never skip points; tiny exact arithmetic',async()=>{
 for(const bad of ['0','-1','1e2','1.0','01','NaN','0.0000000000000000001','100000000000000000000'])await assert.rejects(scanCloseReversals(points(['100',bad,'120']),600,options));
 const r=await scanCloseReversals(points(['0.0000000000000001','0.000000000000000094']),600,options);
 assert.equal(r.up.events.length,1);assert.deepEqual(r.up.events[0].magnitude,{numerator:'3',denominator:'50'});
 await assert.rejects(scanCloseReversals(points([]),600,options));
 assert.equal((await scanCloseReversals(points(['100']),600,options)).up.count,0);
});
function source(){const f=fixture();return {f,context:{...context(f.query),batchId:'b'.repeat(64)}};}
test('source coverage and model failures remain distinct',async()=>{
 const {f,context:c}=source();f.reply.result.series[0].reason='numerical_failure';f.reply.result.series[0].status='invalid';
 const s=captureReversalSource(f.reply,c,f.expected);assert.equal((await buildReversalReport(s,600,options)).status,'complete');
 for(const key of ['invalid_groups','duplicate_groups','unlocated_rows','unreadable_date_rows','batch_unlocated_rows']){
  const {f,context:c}=source();f.reply.result.coverage[key]=1;
  if(key==='invalid_groups')f.reply.result.coverage.valid_groups--;
  const s=captureReversalSource(f.reply,c,f.expected);const r=await buildReversalReport(s,600,options);
  assert.equal(r.status,'unavailable');assert.equal(r.modes.up.events,null);assert.equal(r.modes.down.terminal,null);
 }
});
test('cancel and output bound',async()=>{
 const controller=new AbortController();controller.abort();await assert.rejects(scanCloseReversals(points(['100','90']),600,{signal:controller.signal}));
 const p=points(Array.from({length:20000},(_,i)=>i%2?'90':'100'));
 const r=await scanCloseReversals(p,600,options);assert.equal(r.up.count+r.down.count,39997);
});
test('omitted source rows and inherited reason keys cannot qualify',async()=>{
 for(const mutation of [f=>{f.reply.result.coverage.source_rows+=2;},f=>{f.reply.result.qualification='__proto__';},f=>{f.reply.result.series[0].reason='__proto__';},f=>{f.reply.result.series[0].reason='constructor';}]){
  const {f,context:c}=source();mutation(f);const r=await buildReversalReport(captureReversalSource(f.reply,c,f.expected),600,options);assert.equal(r.status,'unavailable');assert.equal(r.source.rejected_observations.length,f.reply.result.series.length);assert.ok(Object.values(r.source.reasons).every(Number.isSafeInteger));
 }
});
test('accepted immutable evidence cannot be exported from mutated parent',async()=>{
 const {f,context:c}=source(),s=captureReversalSource(f.reply,c,f.expected);f.reply.result.series[0].close='123';await assert.rejects(buildReversalReport(s,600,options),/cancelled/);
});
