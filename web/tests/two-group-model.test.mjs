import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './two-group-fixtures.mjs';
import { assertExplanation, sortExplanation, verifyExplanationIdentity } from '../src/two-group-model.ts';
import { createUniverseDraft, prepareUniverseRequest, loadUniverseRequest } from '../src/universe-request.ts';
import { ResearchRequestController } from '../src/filter-model.ts';
function draftFor(f) {return {...createUniverseDraft(),ids:f.expected.ids,cutoff:f.expected.end,lookback:'broken legacy value',filter:{enabled:true,groups:[]},mode:'explanation',explanation:{start:f.expected.start,roles:Object.fromEntries(f.expected.ids.map((id,i)=>[id,i<2?'A':'B']))}};}
test('third mode bypasses old window/filter and makes exactly one validated request',async()=>{
  const f=fixture(),draft=draftFor(f); const old=globalThis.fetch;let calls=[];
  globalThis.fetch=async(url,options)=>{calls.push([url,options]);return Response.json(f.reply)};
  try {const controller=new ResearchRequestController(()=>{}); await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);assert.equal(controller.state.status,'ready');assert.equal(controller.state.result.kind,'explanation');assert.equal(calls.length,1);assert.match(calls[0][0],/^\/api\/research\/two-group-explanation\?/);assert.doesNotMatch(calls[0][0],/lookback|rule|target/);controller.dispose();}finally{globalThis.fetch=old}
});
test('incomplete roles and invalid current dates never reach the endpoint',async()=>{
  const f=fixture();for(const change of [d=>{delete d.explanation.roles[d.ids[0]]},d=>{d.explanation.roles[d.ids[0]]='B'},d=>{d.explanation.start=d.cutoff},d=>{d.explanation.start='2026-02-30'}]){const d=draftFor(f);change(d);await assert.rejects(()=>prepareUniverseRequest(d,d.ids));}
});
test('DTO rejects altered method, inputs, precision, decomposition and null failures',()=>{
  const f=fixture();assertExplanation(f.reply,f.expected);
  for(const change of [r=>r.method_id='other',r=>r.parameters.current_start='2026-01-01',r=>r.parameters.groups.A.reverse(),r=>r.parameters.rules.decimal_precision=50,r=>r.members[0].snapshot_id='0'.repeat(64),r=>r.members[0].model.explained=Infinity,r=>r.members[0].model.residual=3,r=>r.members[0].model=null,r=>r.counts.model_available=3,r=>r.members[0].source_complete=false,r=>r.training_dates.pop(),r=>r.members[0].model.within_resolution=true,r=>r.status='partial',r=>r.reasons=['source_panel_unavailable'],r=>r.limitations.risk_standardized=true]){const r=structuredClone(f.reply);change(r);assert.throws(()=>assertExplanation(r,f.expected));}
});
test('partial failure remains visible; descriptive sorting puts null last without treating it as zero',()=>{
  const f=fixture();const row=f.reply.members[0];row.model=null;row.reasons=['numerical_unstable'];f.reply.counts.model_available=3;f.reply.status='partial';assertExplanation(f.reply,f.expected);
  assert.equal(sortExplanation(f.reply.members,false),f.reply.members);assert.equal(sortExplanation(f.reply.members,true).at(-1),row);assert.deepEqual(sortExplanation(f.reply.members,true).slice(0,3).map(m=>m.symbol),['600001.SH','600002.SH','600003.SH']);
});
test('changed inputs invalidate and cancellation never resurrects a late response',async()=>{
  const f=fixture(),d=draftFor(f),old=globalThis.fetch;let resolve;
  globalThis.fetch=()=>new Promise(r=>resolve=r);
  try{const c=new ResearchRequestController(()=>{});const pending=c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest);await new Promise(r=>setTimeout(r,0));c.invalidate();resolve(Response.json(f.reply));await pending;assert.equal(c.state.result,null);assert.equal(c.state.status,'dirty');c.dispose();}finally{globalThis.fetch=old}
});

test('source binding, anomaly structure, precision tolerance and limitations reject tampering',async()=>{
 const f=fixture();await verifyExplanationIdentity(f.reply);
 for(const change of [r=>r.members[0].anomalies.counts=null,r=>r.members[0].model.tolerance=1e200,r=>r.members[0].endpoints.start.close_exact=null,r=>r.members[0].query_id=r.members[1].query_id,r=>r.limitations.residuals='independent_anomaly_probability']){const r=structuredClone(f.reply);change(r);assert.throws(()=>assertExplanation(r,f.expected));}
 for(const change of [r=>r.analysis_id='0'.repeat(64),r=>r.members[0].query_id='9'.repeat(64)]){const r=structuredClone(f.reply);change(r);assertExplanation(r,f.expected);await assert.rejects(()=>verifyExplanationIdentity(r));}
});
