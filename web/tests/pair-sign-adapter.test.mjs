import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {buildPairSignAttachment,pairSignParentHash} from '../src/pair-sign-crossproducts.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/group_pair_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:4*1024*1024}));
const options={yieldControl:async()=>{}};
for(const name of Object.keys(fixtures))test(`059 adapter full original 051 ${name}`,async()=>{
 const f=structuredClone(fixtures[name]),before=JSON.stringify(f.reply),pair=f.reply.pairs[0];const {parent,attachment:a}=await buildPairSignAttachment(f.reply,f.expected,pair,options);
 assert.equal(JSON.stringify(parent),before);assert.equal(JSON.stringify(f.reply),before);assert.equal(a.parent_content_hash,await pairSignParentHash(f.reply));assert.ok(Object.isFrozen(parent));assert.ok(Object.isFrozen(a));
 assert.deepEqual(Object.keys(a.pair).sort(),['left_snapshot_id','right_snapshot_id']);
 assert.equal(a.status,f.reply.source_panel_complete?'complete':'unavailable');
 for(const key of ['previous','current'])if(f.reply.source_panel_complete){assert.deepEqual(a.windows[key].parent_correlation_state,pair[key]);assert.equal(a.windows[key].rows.length,60);}else assert.equal(a.windows[key],null);
 assert.deepEqual(a.source_refs.left.endpoints?.map(({index,...p})=>p)??null,f.reply.members.find(m=>m.snapshot_id===pair.left_snapshot_id).endpoints);
});
test('059 parent bytes and expected independent, whole group tamper cannot be salvaged',async()=>{
 for(const modify of [f=>f.expected.ids.pop(),f=>f.expected.cutoff='2026-01-01',f=>f.reply.members.at(-1).query_id='0'.repeat(64)]){const f=structuredClone(fixtures.complete);modify(f);await assert.rejects(buildPairSignAttachment(f.reply,f.expected,f.reply.pairs[0],options),/invalid_context/);}
 const f=structuredClone(fixtures.complete);f.reply.members[0].endpoints[0].close_token='x'.repeat(2*1024*1024);await assert.rejects(buildPairSignAttachment(f.reply,f.expected,f.reply.pairs[0],options),/resource_limit/);
});
test('059 full parent hashes price ordinal and Unicode token changes; mutable inputs cannot publish',async()=>{
 const f=structuredClone(fixtures.complete),hash=await pairSignParentHash(f.reply);
 for(const mutate of [r=>r.members[0].endpoints[1].close_exact='123',r=>r.members[0].endpoints[1].ordinal=12345,r=>r.members[0].endpoints[1].close_token='汉字']){const r=structuredClone(f.reply);mutate(r);assert.notEqual(await pairSignParentHash(r),hash);}
 await assert.rejects(buildPairSignAttachment(f.reply,f.expected,f.reply.pairs[0],{yieldControl:async()=>{f.reply.members[0].endpoints[0].close_token='changed';}}),/cancelled/);
});
