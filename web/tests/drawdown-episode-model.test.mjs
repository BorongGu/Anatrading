import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assertDrawdownEpisodes,drawdownEpisodeRequest,verifyDrawdownIdentity} from '../src/drawdown-episode-model.ts';
const fixtures=JSON.parse(readFileSync(new URL('./drawdown-episode-fixtures.json',import.meta.url),'utf8'));
for(const [name,f] of Object.entries(fixtures))test(`API DTO ${name}`,()=>assertDrawdownEpisodes(f.reply,f.expected));
test('reject internally consistent wrong representative, counts, evidence, canonical values and bounds',()=>{
 const f=fixtures.complete;
 const mutations=[r=>{r.members[0].deepest=structuredClone(r.members[0].longest_observed);},
 r=>{r.members[0].longest_observed=structuredClone(r.members[0].deepest);},
 r=>{r.members[0].episode_count++;r.members[0].recovered_count++;},
 r=>{r.members[0].current_open.depth_display='0.0000%';},
 r=>{r.members[0].endpoints[0].close_exact='1e2';},
 r=>{r.members[0].endpoints[0].ordinal='1'.repeat(21);},
 r=>{r.members.pop();},r=>{r.dates[1]='2026-01-02';},
 r=>{r.members[0].deepest.peak_to_recovery_intervals=97;},
 r=>{r.counts.computable--;},r=>{r.parameters.lookback--;},
 r=>{r.members[0].deepest.depth_fraction={numerator:'2',denominator:'10'};}];
 for(const mutate of mutations){const r=structuredClone(f.reply);mutate(r);assert.throws(()=>assertDrawdownEpisodes(r,f.expected));}
 const bad=structuredClone(fixtures.missing.reply);bad.members[0].episode_count=0;assert.throws(()=>assertDrawdownEpisodes(bad,fixtures.missing.expected));
});
test('new request canonicalizes members and rejects invalid inputs',()=>{
 const f=fixtures.complete;const r=drawdownEpisodeRequest({...f.expected,ids:f.expected.ids.toReversed()});
 assert.deepEqual(r.expected,f.expected);assert.match(r.path,/drawdown-episodes/);
 for(const patch of [{lookback:253},{lookback:2.5},{cutoff:'2026-02-30'},{ids:[f.expected.ids[0]]},{ids:[f.expected.ids[0],f.expected.ids[0]]}])assert.throws(()=>drawdownEpisodeRequest({...f.expected,...patch}));
});

test('identity binds all source versions, batches, full queries, actual dates and rule parameters',async()=>{
 for(const f of Object.values(fixtures))await verifyDrawdownIdentity(f.reply);
 for(const mutate of [r=>r.analysis_id='0'.repeat(64),r=>r.members[0].batch_id='1'.repeat(64),r=>r.members[0].query_id='2'.repeat(64),r=>r.members[0].date_array[1]='2026-01-02',r=>r.parameters.lookback=7,r=>r.rule_version+='-changed']){
   const r=structuredClone(fixtures.complete.reply);mutate(r);await assert.rejects(()=>verifyDrawdownIdentity(r));
 }
});

test('global and window anomaly evidence cannot coexist with qualified summaries',()=>{
 const f=fixtures.complete;
 for(const [date,scope,codes] of [['2026-12-31','outside_interval',['source_adjustment','local_source_conflict','global_source_conflict']],
 [null,'unknown',['endpoint_integrity_unknown','unlocated_label']],
 [f.reply.dates[1],'inside_interval',['local_source_conflict']],
 [f.reply.dates[1],'inside_interval',['invalid_price']]]){
 const r=structuredClone(f.reply);r.members[0].anomalies={total:1,counts:Object.fromEntries(codes.map(c=>[c,1])),examples:[{date,ordinal:'999',scope,codes}],examples_truncated:false};
 assert.throws(()=>assertDrawdownEpisodes(r,f.expected));
 }
});

test('removing derived reason tags cannot hide raw global, date or price failures',()=>{
 const f=fixtures.complete;
 for(const [date,scope,codes] of [['2026-12-31','outside_interval',['source_adjustment']],
 [null,'unknown',['unlocated_label']],
 [f.reply.dates[1],'inside_interval',['numeric.close']],
 [f.reply.dates[1],'inside_interval',['label']],
 [f.reply.dates[1],'inside_interval',['duplicate_label']],
 [f.reply.dates[1],'inside_interval',['source_date_range']]]){
 const r=structuredClone(f.reply);r.members[0].anomalies={total:1,counts:Object.fromEntries(codes.map(c=>[c,1])),examples:[{date,ordinal:'999',scope,codes}],examples_truncated:false};
 assert.throws(()=>assertDrawdownEpisodes(r,f.expected));
 }
});
