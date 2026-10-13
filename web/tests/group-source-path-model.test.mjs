import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {buildGroupSourcePath, groupPathFraction, formatGroupPathPercent, checkGroupPathBudgets} from '../src/group-source-path-model.ts';
const old=JSON.parse(readFileSync(new URL('./drawdown-episode-fixtures.json',import.meta.url),'utf8'));
test('abnormal parent responses, missing request context and mismatch cannot create attachment',async()=>{
 const f=old.complete;
 for(const mutate of [r=>r.members.pop(),r=>r.members[0].endpoints[0].close_exact='0',r=>r.members[0].endpoints[0].ordinal='0',r=>r.dates[1]=r.dates[0],r=>r.members[0].source_qualified=false,r=>r.analysis_id='0'.repeat(64)]){
  const r=structuredClone(f.reply);mutate(r);await assert.rejects(()=>buildGroupSourcePath(r,f.expected));
 }
 await assert.rejects(()=>buildGroupSourcePath(f.reply));
 for(const patch of [{cutoff:'2026-12-31'},{lookback:1},{lookback:253},{ids:f.expected.ids.slice(0,1)}])await assert.rejects(()=>buildGroupSourcePath(f.reply,{...f.expected,...patch}));
});
test('unavailable is never a zero drawdown or a survivor subset; all old source nulls survive',async()=>{
 for(const f of Object.values(old).filter(f=>!f.reply.comparison_available)){
  const before=structuredClone(f.reply),{parent,attachment:a}=await buildGroupSourcePath(f.reply,f.expected);
  assert.equal(a.status,'unavailable');assert.equal(a.selected,f.reply.members.length);
  for(const k of ['denominator','sums','depth','peak_index','trough_index','contributions'])assert.equal(a[k],null,k);
  assert.deepEqual(f.reply,before);assert.deepEqual(parent,before);assert.ok(Object.isFrozen(parent.members[0]));
 }
});
test('pre-abort and in-flight input mutation reject without publication',async()=>{
 const f=old.complete,abort=new AbortController();abort.abort();
 await assert.rejects(()=>buildGroupSourcePath(f.reply,f.expected,{signal:abort.signal}),e=>e.name==='AbortError');
 const r=structuredClone(f.reply);let release;const paused=new Promise(resolve=>release=resolve);
 const task=buildGroupSourcePath(r,f.expected,{yieldControl:()=>paused});r.members[0].endpoints[0].ordinal='999';release();
 await assert.rejects(()=>task,/group_path_input_changed/);
});
test('signed exact display cannot hide microscopic offsets and limits reject growth',()=>{
 assert.equal(formatGroupPathPercent('-1','1000000000000000000',true),'负值（绝对值小于0.0001个百分点）');
 assert.equal(formatGroupPathPercent('1','1000000000000000000',true),'正值（小于0.0001个百分点）');
 assert.equal(formatGroupPathPercent('0','1',true),'0.0000个百分点');
 assert.deepEqual(groupPathFraction('-2','42'),{numerator:'-1',denominator:'21'});
 assert.throws(()=>groupPathFraction('1','0'));
 assert.throws(()=>groupPathFraction((1n<<6400n).toString(),'1'),/group_path_integer_limit/);
 assert.throws(()=>checkGroupPathBudgets({extra:'汉'.repeat(5500)}),/group_path_metadata_limit/);
 assert.throws(()=>checkGroupPathBudgets({sums:['9'.repeat(2*1024*1024)]}),/group_path_result_limit/);
});

// The bridge contains no candidate kernel: synthetic parent generation + Fraction all-pairs.
const {fixtures}=await import('./group-source-path-fixtures.mjs');
const fast={yieldControl:async()=>{}};
for(const [name,f] of Object.entries(fixtures))test(`independent Fraction and source controls: ${name}`,async()=>{
 const original=structuredClone(f.reply),{parent,attachment:a}=await buildGroupSourcePath(f.reply,f.expected,fast),want=f.oracle;
 assert.deepEqual(parent,original);assert.deepEqual(f.reply,original);
 assert.equal(a.selected,parent.members.length);
 if(!want){assert.equal(a.status,'unavailable');assert.equal(a.sums,null);assert.equal(a.depth,null);return;}
 assert.equal(a.status,want.peak===null?'no_drawdown':'drawdown');
 assert.deepEqual(a.depth,want.depth);assert.equal(a.peak_index,want.peak);assert.equal(a.trough_index,want.trough);
 assert.deepEqual(a.sums.map(s=>groupPathFraction(s,a.denominator)),want.curve);
 assert.deepEqual(a.contributions?.map(w=>groupPathFraction(w,a.sums[a.peak_index]))??null,want.contributions);
 if(a.contributions)assert.equal(a.contributions.reduce((x,w)=>x+BigInt(w),0n),BigInt(a.sums[a.peak_index])-BigInt(a.sums[a.trough_index]));
 assert.ok(Object.isFrozen(a));assert.ok(Object.isFrozen(a.sums));assert.ok(Object.isFrozen(parent.members[0].endpoints[0]));
 assert.throws(()=>{parent.members[0].endpoints[0].close_exact='1';});
 if(name==='full_bound'){
  assert.equal(a.sums.length,253);assert.equal(a.contributions.length,50);
  assert.ok(BigInt(a.denominator).toString(2).length>256);assert.ok(BigInt(a.denominator).toString(2).length<=6318);
  assert.ok(new TextEncoder().encode(JSON.stringify(a)).length<599353);
  for(const s of a.sums)assert.ok(BigInt(s).toString(2).length<=6318);
 }
});
test('T1/T2/T3 manual oracle and original anchor semantics stay explicit',async()=>{
 const a=(await buildGroupSourcePath(fixtures.T2.reply,fixtures.T2.expected,fast)).attachment;
 assert.deepEqual(a.depth,{numerator:'2',denominator:'21'});assert.equal(a.peak_index,1);assert.equal(a.trough_index,2);
 assert.deepEqual(fixtures.T1.oracle.depth,{numerator:'0',denominator:'1'});
 assert.equal(fixtures.T3.oracle.peak,1);assert.equal(fixtures.T3.oracle.trough,2);
 // Reanchoring at shared peak answers a different question (5/72); one interval is not admitted.
 assert.notDeepEqual(a.depth,{numerator:'5',denominator:'72'});
 await assert.rejects(()=>buildGroupSourcePath(fixtures.T2.reply,{...fixtures.T2.expected,lookback:1},fast));
});
test('same analysis identity cannot conceal changed price, ordinal or qualification',async()=>{
 const f=fixtures.T2,first=await buildGroupSourcePath(f.reply,f.expected,fast);
 for(const kind of ['price','ordinal','qualification']){
  const changed=fixtures['same_id_'+kind];assert.equal(changed.reply.analysis_id,f.reply.analysis_id);
  const next=await buildGroupSourcePath(changed.reply,changed.expected,fast);
  assert.notEqual(next.attachment.parent_content_hash,first.attachment.parent_content_hash);
  assert.notEqual(next.attachment.attachment_id,first.attachment.attachment_id);
 }
 const mutable=structuredClone(f.reply),old=await buildGroupSourcePath(mutable,f.expected,fast),before=structuredClone(old);
 mutable.members[0].endpoints[0].ordinal='999';assert.deepEqual(old,before);
});
test('all exact output fields and parent canonical contents are covered by SHA256',async()=>{
 const {groupPathCanonical:canonicalJson}=await import('../src/group-source-path-model.ts');
 const hash=async v=>Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonicalJson(v)))).toString('hex');
 const f=fixtures.T2,{attachment:a,parent}=await buildGroupSourcePath(f.reply,f.expected,fast);
 assert.equal(a.parent_content_hash,await hash(parent));const {attachment_id,...identity}=a;assert.equal(attachment_id,await hash(identity));
 const changed={...identity,contributions:[...identity.contributions]};changed.contributions[0]='0';assert.notEqual(attachment_id,await hash(changed));
});
test('cooperative batches yield every eight dates and cancellation never returns partials',async()=>{
 const f=fixtures.full_bound;let calls=0;
 await buildGroupSourcePath(f.reply,f.expected,{yieldControl:async()=>{calls++;}});
 assert.equal(calls,1+Math.floor((f.reply.dates.length-1)/8));
 const control=new AbortController();calls=0;
 await assert.rejects(()=>buildGroupSourcePath(f.reply,f.expected,{signal:control.signal,yieldControl:async()=>{if(++calls===2)control.abort();}}),e=>e.name==='AbortError');
 assert.equal(calls,2);
});
test('full canonical JSON preserves legitimate Unicode and key-order identity without widening050 fields',async()=>{
 const {groupPathCanonical}=await import('../src/group-source-path-model.ts');
 const a={z:'小于0.0001%',a:[true,1,null]},b={a:[true,1,null],z:'小于0.0001%'};
 assert.equal(groupPathCanonical(a),groupPathCanonical(b));
 assert.notEqual(groupPathCanonical(a),groupPathCanonical({...a,z:'文字改变'}));
 for(const value of [NaN,Infinity,1n,undefined,new Date()])assert.throws(()=>groupPathCanonical(value));
 const f=fixtures.near_depth;assert.ok(JSON.stringify(f.reply).includes('小于0.0001%'));
 const first=await buildGroupSourcePath(f.reply,f.expected,fast);
 const reverseKeys=v=>Array.isArray(v)?v.map(reverseKeys):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).reverse().map(k=>[k,reverseKeys(v[k])])):v;
 const second=await buildGroupSourcePath(reverseKeys(f.reply),f.expected,fast);assert.equal(first.attachment.attachment_id,second.attachment.attachment_id);
 const invalid=structuredClone(fixtures.failure_zero.reply);invalid.members[0].reasons.push('未知原因');await assert.rejects(()=>buildGroupSourcePath(invalid,fixtures.failure_zero.expected,fast));
});
test('metadata and final UTF8 byte budgets accept the exact boundary and reject one byte beyond',()=>{
 const metadataOverhead=new TextEncoder().encode(JSON.stringify({label:''})).length;
 checkGroupPathBudgets({label:'x'.repeat(16384-metadataOverhead)});
 assert.throws(()=>checkGroupPathBudgets({label:'x'.repeat(16385-metadataOverhead)}),/group_path_metadata_limit/);
 const numericOverhead=new TextEncoder().encode(JSON.stringify({sums:['']})).length;
 checkGroupPathBudgets({sums:['1'.repeat(2*1024*1024-numericOverhead)]});
 assert.throws(()=>checkGroupPathBudgets({sums:['1'.repeat(2*1024*1024-numericOverhead+1)]}),/group_path_result_limit/);
 assert.equal(formatGroupPathPercent('1','2000000'),'小于0.0001%');
 assert.equal(formatGroupPathPercent('3','2000000'),'0.0002%');
 assert.equal(formatGroupPathPercent('-3','2000000',true),'−0.0002个百分点');
});
