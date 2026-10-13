import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { acceptDispersion, dispersionContext, readDispersionResponse } from '../src/selected-dispersion.ts';
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/selected-dispersion.json',import.meta.url)));
test('accepts exact full-prefix result owned by an independently clipped chart query',()=>{
 const {query,report}=fixture(); query.query_id='chart'; query.selection.ordinal_start=15;
 const accepted=acceptDispersion(report,dispersionContext(query),null);
 assert.deepEqual(accepted,report); assert.notEqual(accepted,report); assert.equal(Object.isFrozen(accepted.selected),true);
});
for(const mutate of [
 r=>r.identity.snapshot_id='bad',r=>r.identity.batch_id='bad',r=>r.identity.selection.cutoff='2025-01-01',
 r=>r.identity.selection.ordinal_start=1,r=>r.selection.date_requested='2025-01-20',r=>r.selected.window_count=19,
 r=>r.members.pop(),r=>r.members[0].position=2,r=>r.members[0].source_reason='invalid_price',
 r=>r.selected.sigma.display=null,r=>r.selected.mean_exact=1,r=>r.selected.sigma.lower='NaN',
 r=>r.coverage.source_rows=Infinity,r=>r.method_id='other',r=>r.selected.invalid_members.push({}),
 r=>r.qualification='source_rejected',r=>r.identity.raw_sha256='bad',r=>r.identity.source_contract_id='bad',
]) test('rejects mismatched or malformed DTO '+String(mutate),()=>{
 const {query,report}=fixture();mutate(report);assert.throws(()=>acceptDispersion(report,dispersionContext(query),null));
});
test('bounded UTF-8 body handles absent and dishonest content length',async()=>{
 const data=JSON.stringify({x:'中'.repeat(23000)});
 for(const headers of [{},{'content-length':'10'}]) await assert.rejects(readDispersionResponse(new Response(data,{headers})),/dispersion_result_limit/);
 assert.deepEqual(await readDispersionResponse(new Response('{"x":1}')),{x:1});
 await assert.rejects(readDispersionResponse(new Response('not json')),/invalid_query_response/);
 await assert.rejects(readDispersionResponse(new Response('{"x":1e999}')),/invalid_query_response/);
});
for(const mutate of [r=>r.selected.sigma.lower='3',r=>r.selected.dispersion_numerator='1.1',r=>r.selected.sigma.lower='-1',r=>r.members[0].close='0']) test('rejects impossible structural numeric fields '+String(mutate),()=>{
 const {query,report}=fixture();mutate(report);assert.throws(()=>acceptDispersion(report,dispersionContext(query),null));
});
test('stream cancels on chunk that exceeds cap and rejects invalid UTF-8',async()=>{
 let canceled=false;
 const stream=new ReadableStream({start(c){c.enqueue(new Uint8Array(65000));c.enqueue(new Uint8Array(537));},cancel(){canceled=true;}});
 await assert.rejects(readDispersionResponse(new Response(stream)),/dispersion_result_limit/);assert.equal(canceled,true);
 await assert.rejects(readDispersionResponse(new Response(new Uint8Array([255]))),/invalid_query_response/);
});

test('rejects source_rejected with a computed window even if global counts claim all invalid',()=>{
 const {query,report}=fixture();report.qualification='source_rejected';report.coverage.valid_groups=0;report.coverage.invalid_groups=report.coverage.date_groups;
 assert.throws(()=>acceptDispersion(report,dispersionContext(query),null));
});
