import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assertGroupEndpoints,verifyGroupEndpointIdentity,groupEndpointRequest,groupPercent,groupSign,validGroupDate} from '../src/group-endpoint-model.ts';
import {createUniverseDraft,prepareUniverseRequest,loadUniverseRequest,universeErrorTarget} from '../src/universe-request.ts';
import {ResearchRequestController} from '../src/filter-model.ts';
const fixtures=JSON.parse(readFileSync(new URL('./group-endpoint-fixtures.json',import.meta.url),'utf8'));
const fixture=(name='complete')=>structuredClone(fixtures[name]);
const draftFor=f=>({...createUniverseDraft(),mode:'group_endpoints',ids:f.expected.ids,cutoff:f.expected.end,groupStart:f.expected.start,lookback:'old invalid value',filter:{enabled:true,groups:[]},explanation:{start:'old start',roles:{}}});
for(const name of Object.keys(fixtures))test(`Python synthetic golden ${name} validates exact ratios and identity`,async()=>{
 const f=fixture(name);assertGroupEndpoints(f.reply,f.expected);await verifyGroupEndpointIdentity(f.reply);
 assertGroupEndpoints(f.reply,{...f.expected,ids:[...f.expected.ids].reverse()});
});
const mutations={
 method:r=>r.method_id='old', rule:r=>r.rule_version='old', sourceRule:r=>r.source_rule_version='old',
 start:r=>r.parameters.start_date='2026-09-27', missingMember:r=>r.members.pop(), order:r=>r.members.reverse(),
 snapshot:r=>r.members[0].snapshot_id='0'.repeat(64), query:r=>r.members[0].query_id='not-a-hash',
 ordinal:r=>r.members[0].endpoints.start.ordinal=2**53, endpointDate:r=>r.members[0].endpoints.end.date='2026-09-29',
 close:r=>r.members[0].endpoints.end.close_exact='1e2', noncanonical:r=>r.members[0].endpoints.end.close_exact='101.00',
 priceRange:r=>r.members[0].endpoints.end.close_exact='1'+'0'.repeat(20), priceScale:r=>r.members[0].endpoints.end.close_exact='0.'+'0'.repeat(18)+'1',
 ratio:r=>r.members[0].source_change.numerator='999', oversized:r=>r.members[0].source_change.numerator='9'.repeat(4097),
 denominator:r=>r.members[0].source_change.denominator='0', nonreduced:r=>{const v=r.members[0].source_change;v.numerator=String(BigInt(v.numerator)*2n);v.denominator=String(BigInt(v.denominator)*2n);},
 counts:r=>r.counts.valid=1, sign:r=>r.sign_counts.positive=0, coverage:r=>r.coverage.numerator='0', proportion:r=>r.sign_proportions.positive.numerator='0',
 mean:r=>r.summary.mean.numerator='0', median:r=>r.summary.median.numerator='0', q1:r=>r.summary.q1.numerator='0', q3:r=>r.summary.q3.numerator='0',
 reason:r=>r.summary_reason='incomplete_group', status:r=>r.status='partial', diag:r=>r.diagnostic_only=true,
 events:r=>r.events.push({}), scope:r=>r.scope.price_currency.value='USD', limits:r=>r.limitations.economic_return_qualified=true,
 unknown:r=>r.extra='x', memberReason:r=>r.members[0].reasons=['unknown'], endpointReason:r=>r.members[0].endpoints.start.reasons=['unknown'],
 anomalies:r=>r.members[0].anomalies.total=1, token:r=>r.members[0].endpoints.start.close_token='x'.repeat(129),
};
for(const [name,mutate]of Object.entries(mutations))test(`rejects DTO or internal math mismatch: ${name}`,()=>{const f=fixture();mutate(f.reply);assert.throws(()=>assertGroupEndpoints(f.reply,f.expected),/invalid_group_endpoint_response/);});
test('incomplete and unevaluated are distinct; partial summaries never use K',()=>{
 const f=fixture('partial');f.reply.summary.mean=fixture().reply.summary.mean;assert.throws(()=>assertGroupEndpoints(f.reply,f.expected));
 for(const mutation of [m=>m.endpoints=fixture().reply.members[0].endpoints,m=>m.anomalies={total:0,counts:{},examples:[],truncated:false},m=>m.symbol='600000.SH']){
  const g=fixture('rejected');mutation(g.reply.members.find(m=>m.evaluation==='not_evaluated'));assert.throws(()=>assertGroupEndpoints(g.reply,g.expected));
 }
});
test('source tokens stay opaque; well-shaped provenance is trusted Store responsibility',async()=>{
 const f=fixture('near_zero');const m=f.reply.members.find(m=>m.endpoints.start.close_token==='1e0');assert.ok(m);m.endpoints.start.close_token='0001e0';
 assertGroupEndpoints(f.reply,f.expected);await verifyGroupEndpointIdentity(f.reply);
 const changed=fixture();changed.reply.analysis_id='0'.repeat(64);await assert.rejects(()=>verifyGroupEndpointIdentity(changed.reply),/invalid_group_endpoint_response/);
});
test('percentage half-even and exact near-zero signs remain separate',()=>{
 const r=(n,d)=>({numerator:n,denominator:d,unit:'ratio'});
 assert.equal(groupPercent(r('1','2000000')),'0.0000%（正，显示舍入）');
 assert.equal(groupPercent(r('-1','2000000')),'0.0000%（负，显示舍入）');
 assert.equal(groupPercent(r('3','2000000')),'0.0002%');assert.equal(groupPercent(r('-3','2000000')),'-0.0002%');
 assert.equal(groupPercent(r('0','1')),'0.0000%');assert.equal(groupSign(r('1','1000000000000000000')),'正');assert.equal(groupPercent(null),'不可算');
});
test('strict dates, bounds and copied request; invalid old controls do not affect new mode',async()=>{
 const f=fixture(),draft=draftFor(f),before=structuredClone(draft);const spec=await prepareUniverseRequest(draft,draft.ids);
 assert.equal(spec.kind,'group_endpoints');assert.match(spec.request.path,/^\/api\/research\/group-endpoints\?/);assert.deepEqual(draft,before);
 const request=groupEndpointRequest(f.expected);f.expected.ids.reverse();assert.deepEqual(request.expected.ids,[...f.expected.ids].sort());
 for(const date of ['0000-01-01','2026-02-29','2026-01-32','2026-1-01'])assert.equal(validGroupDate(date),false);
 for(const patch of [{groupStart:'2026-02-30'},{groupStart:f.expected.end}])await assert.rejects(()=>prepareUniverseRequest({...draft,...patch},draft.ids),e=>universeErrorTarget(e)==='universe-group-start');
 for(const ids of [draft.ids.slice(0,3),[...draft.ids,draft.ids[0]]])assert.throws(()=>groupEndpointRequest({...f.expected,ids}));
});
test('actual new-mode component path uses one endpoint, rejects failures and retries explicitly',async()=>{
 const f=fixture(),draft=draftFor(f),old=globalThis.fetch,calls=[];let fail=true;
 globalThis.fetch=async(url,options)=>{calls.push([url,options]);return fail?Response.json({error:'raw_object_corrupt'},{status:409}):Response.json(f.reply);};
 const controller=new ResearchRequestController(()=>{});
 try{
  await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);assert.equal(controller.state.status,'error');assert.equal(controller.state.result,null);assert.equal(calls.length,1);
  fail=false;await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);assert.equal(controller.state.status,'ready');assert.equal(calls.length,2);
  assert.ok(calls.every(([path])=>path.startsWith('/api/research/group-endpoints?')));assert.equal(calls[1][1].cache,'no-store');assert.equal(calls[1][1].credentials,'same-origin');
 }finally{controller.dispose();globalThis.fetch=old;}
});
test('duplicate submit, cancel and late success cannot restore stale group report',async()=>{
 const f=fixture(),draft=draftFor(f),old=globalThis.fetch;let release,called;const entered=new Promise(r=>called=r);globalThis.fetch=()=>{called();return new Promise(r=>release=r);};
 const controller=new ResearchRequestController(()=>{});
 try{const task=controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);await entered;
  assert.equal(await controller.run(()=>{throw Error('duplicate');},loadUniverseRequest),false);controller.cancel();release(Response.json(f.reply));await task;assert.equal(controller.state.status,'cancelled');assert.equal(controller.state.result,null);
 }finally{controller.dispose();globalThis.fetch=old;}
});
test('hash completion cannot overwrite edited or unmounted state',async()=>{
 const f=fixture(),draft=draftFor(f),old=globalThis.fetch,oldDigest=crypto.subtle.digest;
 let release,entered;const waiting=new Promise(r=>entered=r);globalThis.fetch=async()=>Response.json(f.reply);
 crypto.subtle.digest=async function(...args){entered();await new Promise(r=>release=r);return oldDigest.apply(this,args);};
 const controller=new ResearchRequestController(()=>{});
 try{const task=controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);await waiting;controller.invalidate();controller.dispose();release();await task;assert.equal(controller.state.result,null);assert.equal(controller.state.status,'cancelled');}
 finally{globalThis.fetch=old;crypto.subtle.digest=oldDigest;}
});
test('out-of-scope normalized identities remain visible only in source-rejected rows',()=>{
 for(const symbol of ['AAPL.NASDAQ','00700.HK','BRK.B.NYSE']){
  const f=fixture('rejected'),m=f.reply.members.find(m=>m.evaluation==='not_evaluated');m.symbol=symbol;m.reasons=['scope_conflict'];
  assertGroupEndpoints(f.reply,f.expected);
  const complete=fixture();complete.reply.members[0].symbol=symbol;assert.throws(()=>assertGroupEndpoints(complete.reply,complete.expected));
 }
});
test('DTO-internal ordinal, blocking-anomaly and anomaly-count contradictions are rejected',()=>{
 for(const mutate of [
  m=>m.endpoints.end.ordinal=m.endpoints.start.ordinal,
  m=>m.anomalies={total:1,counts:{local_source_conflict:1},examples:[{ordinal:1,scope:'inside_interval',codes:['local_source_conflict']}],truncated:false},
  m=>m.anomalies={total:2,counts:{'numeric.volume':1},examples:[{ordinal:1,scope:'outside_interval',codes:['numeric.volume']},{ordinal:2,scope:'outside_interval',codes:['numeric.volume']}],truncated:false},
 ]){const f=fixture();mutate(f.reply.members[0]);assert.throws(()=>assertGroupEndpoints(f.reply,f.expected),/invalid_group_endpoint_response/);}
});
test('display-only name changes preserve the submitted identity and require no second fetch',async()=>{
 const f=fixture(),draft=draftFor(f),before=await prepareUniverseRequest(draft,draft.ids),old=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return Response.json(f.reply);};const controller=new ResearchRequestController(()=>{});
 try{await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);const report=controller.state.result;
  draft.groupName='另一个显示名';const after=await prepareUniverseRequest(draft,draft.ids);assert.deepEqual(after,before);assert.strictEqual(controller.state.result,report);assert.equal(calls,1);
 }finally{controller.dispose();globalThis.fetch=old;}
});
test('late error after cancellation cannot replace a newer successful group response',async()=>{
 const f=fixture(),draft=draftFor(f),old=globalThis.fetch;let reject,entered,calls=0;const waiting=new Promise(r=>entered=r);
 globalThis.fetch=()=>++calls===1?(entered(),new Promise((_,r)=>reject=r)):Promise.resolve(Response.json(f.reply));const controller=new ResearchRequestController(()=>{});
 try{const first=controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);await waiting;controller.cancel();
  await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);const current=controller.state.result;reject(new Error('old network failure'));await first;
  assert.equal(controller.state.status,'ready');assert.strictEqual(controller.state.result,current);assert.equal(calls,2);
 }finally{controller.dispose();globalThis.fetch=old;}
});
test('switching back to prior modes retains their independent drafts and invalidates only through the shared controller',async()=>{
 const f=fixture(),draft=draftFor(f);draft.groupName='显示组';draft.explanation={start:'2026-09-01',roles:{[draft.ids[0]]:'A'}};
 const saved=structuredClone(draft);await prepareUniverseRequest(draft,draft.ids);draft.mode='existing';assert.equal(draft.lookback,saved.lookback);assert.deepEqual(draft.filter,saved.filter);
 draft.mode='explanation';assert.deepEqual(draft.explanation,saved.explanation);draft.mode='group_endpoints';assert.equal(draft.groupStart,saved.groupStart);assert.equal(draft.groupName,saved.groupName);
});
test('unknown anomaly labels retain Unicode and prototype names without changing source eligibility',()=>{
 for(const code of ['__proto__','constructor','toString','未知核验']){
  const f=fixture(),m=f.reply.members[0];
  m.anomalies={total:1,counts:JSON.parse(JSON.stringify({[code]:1,unclassified_source_failure:1})),examples:[{ordinal:99,scope:'outside_interval',codes:[code,'unclassified_source_failure']}],truncated:false};
  assertGroupEndpoints(f.reply,f.expected);
 }
});
