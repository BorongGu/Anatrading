import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assertPeerNeighbors,verifyPeerNeighborIdentity,peerNeighborRequest,peerDisplay,peerSign} from '../src/peer-neighbor-model.ts';
import {createUniverseDraft,prepareUniverseRequest,loadUniverseRequest,universeErrorTarget} from '../src/universe-request.ts';
import {ResearchRequestController} from '../src/filter-model.ts';
const fixtures=JSON.parse(readFileSync(new URL('./peer-neighbor-fixtures.json',import.meta.url),'utf8'));
const fixture=(name='complete')=>structuredClone(fixtures[name]);
const draftFor=f=>({...createUniverseDraft(),mode:'peer_neighbors',ids:f.expected.ids,peerTarget:f.expected.target,cutoff:f.expected.cutoff,lookback:'not used',groupStart:'not used',filter:{enabled:true,groups:[]},explanation:{start:'not used',roles:{}}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
for(const name of Object.keys(fixtures))test(`actual Python ${name} DTO, source and analysis identity`,async()=>{const f=fixture(name);assertPeerNeighbors(f.reply,f.expected);await verifyPeerNeighborIdentity(f.reply);});
const mutations={
 target:r=>r.parameters.target_snapshot_id='0'.repeat(64),rule:r=>r.parameters.rules.transform='source_log_change',
 date:r=>r.used_dates[60]=r.used_dates[59],truncated_window:r=>r.used_dates.pop(),count:r=>r.counts.candidates++,
 candidate_missing:r=>r.candidates.pop(),candidate_duplicate:r=>r.candidates[1].snapshot_id=r.candidates[0].snapshot_id,
 order:r=>r.windows.current.order[1]=r.windows.current.order[0],rank:r=>r.candidates.find(c=>c.current.correlation).current.rank=49,
 tie:r=>r.candidates.find(c=>c.current.correlation).current.tie_size=49,
 sign:r=>r.candidates.find(c=>c.current.correlation?.sign==='positive').current.correlation.sign='negative',
 display:r=>r.candidates.find(c=>c.current.correlation).current.correlation.display='NaN',
 magnitude:r=>r.candidates.find(c=>c.current.correlation).current.correlation.estimate='2E+0',
 coefficient:r=>r.candidates.find(c=>c.current.correlation).current.correlation.estimate='1.'+'9'.repeat(100)+'E-2',
 exponent:r=>r.candidates.find(c=>c.current.correlation).current.correlation.estimate='1E-10001',
 rho_zero:r=>r.candidates.find(c=>c.current.correlation?.sign==='positive').current.correlation.estimate='0',
 boundary:r=>r.candidates.find(c=>c.current.correlation?.sign==='zero').current.correlation.exact_boundary='none',
 difference_range:r=>r.candidates.find(c=>c.difference).difference.estimate='3E+0',
 panel:r=>r.source_panel_complete=false,scope:r=>r.scope.price_currency.evidence_status='certified',
 events:r=>r.events=[{}],member:r=>r.members.pop(),ordinal:r=>r.members[0].endpoints[1].ordinal=r.members[0].endpoints[0].ordinal,
 endpoint_count:r=>r.members[0].endpoints.pop(),source_ids:r=>r.members[0].query_id='?'
};
for(const [name,mutate]of Object.entries(mutations))test(`reject inconsistent peer DTO: ${name}`,()=>{const f=fixture();mutate(f.reply);assert.throws(()=>assertPeerNeighbors(f.reply,f.expected),/invalid_peer_neighbor_response/);});
test('reject analysis hash change independently of shape',async()=>{const f=fixture();f.reply.analysis_id='0'.repeat(64);await assert.rejects(()=>verifyPeerNeighborIdentity(f.reply),/invalid_peer_neighbor_response/);});
test('decimal display stays signed without Number underflow or giant exponent powers',()=>{
 assert.equal(peerDisplay('1E-4566'),'0.0000');assert.equal(peerDisplay('-1E-4566'),'0.0000');
 assert.equal(peerDisplay('1.23445E-1'),'0.1234');assert.equal(peerDisplay('1.23455E-1'),'0.1235');
 assert.equal(peerDisplay('2E+0',2),'2.0000');assert.equal(peerDisplay('-2E+0',2),'-2.0000');
 assert.match(peerSign({estimate:'-1E-4566',display:'0.0000',sign:'negative',exact_boundary:'none'}),/反向，显示舍入/);
});
test('bounded request copies members and ignores all three unrelated mode drafts',async()=>{
 const f=fixture(),draft=draftFor(f),before=structuredClone(draft);const spec=await prepareUniverseRequest(draft,draft.ids);
 assert.equal(spec.kind,'peer_neighbors');assert.deepEqual(draft,before);assert.match(spec.request.path,/^\/api\/research\/peer-neighbors\?/);assert.doesNotMatch(spec.request.path,/lookback|group_a|start_date|events/);
 draft.ids.reverse();assert.deepEqual(spec.request.expected.ids,[...f.expected.ids].sort());
 await assert.rejects(()=>prepareUniverseRequest({...draft,peerTarget:''},draft.ids),e=>universeErrorTarget(e)==='universe-peer-target');
 await assert.rejects(()=>prepareUniverseRequest({...draft,cutoff:'2026-02-30'},draft.ids),e=>universeErrorTarget(e)==='universe-cutoff');
 for(const ids of [draft.ids.slice(0,1),[...draft.ids,draft.ids[0]]])assert.throws(()=>peerNeighborRequest({...f.expected,ids}));
});
test('real prepare/load/controller sends one peer endpoint and no-store, preserves latest generation',async()=>{
 const f=fixture(),draft=draftFor(f),old=globalThis.fetch,calls=[];globalThis.fetch=async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify(f.reply));};
 try{const control=new ResearchRequestController(()=>{});await control.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);assert.equal(control.state.status,'ready');assert.equal(control.state.result.kind,'peer_neighbors');assert.equal(calls.length,1);assert.equal(calls[0][1].cache,'no-store');assert.equal(calls[0][1].credentials,'same-origin');control.dispose();}finally{globalThis.fetch=old;}
});
for(const action of ['cancel','invalidate','dispose'])test(`late success/error cannot revive after ${action}`,async()=>{
 for(const failure of [false,true]){const f=fixture(),old=globalThis.fetch,waiting=[];globalThis.fetch=(path,options)=>new Promise((resolve,reject)=>waiting.push({path,options,resolve,reject}));
 try{const control=new ResearchRequestController(()=>{}),prepare=()=>prepareUniverseRequest(draftFor(f),f.expected.ids);const work=control.run(prepare,loadUniverseRequest);await tick();assert.equal(waiting.length,1);assert.equal(await control.run(prepare,loadUniverseRequest),false);control[action]();assert.equal(waiting[0].options.signal.aborted,true);
 failure?waiting[0].reject(new Error('late_error')):waiting[0].resolve(new Response(JSON.stringify(f.reply)));await work;assert.equal(control.state.result,null);assert.equal(control.state.error,null);control.dispose();}finally{globalThis.fetch=old;}}
});
test('newer target request survives older late completion and supports explicit retry',async()=>{
 const f=fixture(),old=globalThis.fetch,waiting=[];globalThis.fetch=(path,options)=>new Promise((resolve,reject)=>waiting.push({path,options,resolve,reject}));
 try{const c=new ResearchRequestController(()=>{}),prepare=()=>prepareUniverseRequest(draftFor(f),f.expected.ids);
 const first=c.run(prepare,loadUniverseRequest);await tick();c.invalidate();const second=c.run(prepare,loadUniverseRequest);await tick();waiting[0].reject(new Error('stale'));await first;assert.equal(c.state.status,'loading');
 waiting[1].reject(new Error('raw_object_missing'));await second;assert.equal(c.state.status,'error');assert.equal(c.state.result,null);
 const retry=c.run(prepare,loadUniverseRequest);await tick();waiting[2].resolve(new Response(JSON.stringify(f.reply)));await retry;assert.equal(c.state.status,'ready');c.dispose();}finally{globalThis.fetch=old;}
});
test('editing during asynchronous preparation admits no stale fetch',async()=>{const f=fixture(),c=new ResearchRequestController(()=>{});let resolve,calls=0;const work=c.run(()=>new Promise(r=>resolve=r),async()=>{calls++;});c.invalidate();resolve(await prepareUniverseRequest(draftFor(f),f.expected.ids));await work;assert.equal(calls,0);assert.equal(c.state.result,null);c.dispose();});
