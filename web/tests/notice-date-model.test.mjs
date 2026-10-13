import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {assertGroupPairs,verifyGroupPairIdentity} from '../src/group-pair-model.ts';
import {assertNoticeReference,verifyNoticeReference,adaptNoticeMembers,matchNoticeDates,buildNoticeDiagnostic,noticeCanonical,noticeHash,NOTICE_REFERENCE_HASH} from '../src/notice-date-model.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/notice_date_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:8*1024*1024}));
const reference=JSON.parse(readFileSync(new URL('../src/notice-reference-v1.json',import.meta.url),'utf8'));
const f=(name='complete')=>structuredClone(fixtures[name].reply),ref=()=>structuredClone(reference);
const member=name=>adaptNoticeMembers(f(name)).find(m=>m.symbol==='000001.SZ');
const run=(name='complete',r=ref())=>matchNoticeDates(f(name),r);
const cell=(r,day,exchange='SZSE')=>r.exchanges.find(e=>e.exchange===exchange).dates.find(d=>d.date===day);
for(const [name,x]of Object.entries(fixtures))test(`notice input ${name} is actual valid 051 DTO`,async()=>{assertGroupPairs(x.reply,x.expected);await verifyGroupPairIdentity(x.reply);});
test('production pins accepted facts, local manifest and exactly72/13 dates',async()=>{
 assertNoticeReference(reference);await verifyNoticeReference(reference);assert.equal(await noticeHash(reference),NOTICE_REFERENCE_HASH);
 assert.equal(reference.accepted_facts_sha256,'d667d14bd1c6a761aef53a8a6ecf9c412e996211b45518eb58a967f815ccc541');
 const report=f();report.members.forEach(m=>m.date_array=[]);report.parameters.cutoff='2026-10-09';
 const r=matchNoticeDates(report,ref()),sz=r.exchanges.find(e=>e.exchange==='SZSE');assert.equal(sz.closed_dates,72);assert.equal(sz.open_dates,13);assert.equal(r.exchanges[0].covered_dates,0);
 const changed=ref();changed.version+='-changed';assertNoticeReference(changed);await assert.rejects(()=>verifyNoticeReference(changed),/notice_reference_integrity/);
});
test('malformed, over-budget and unsafe reference rejected before expansion',()=>{
 for(const change of [r=>r.extra=true,r=>r.scope=['2026-01-01','2025-01-01'],r=>r.scope[0]='2026-02-30',r=>r.scope[0]='x'.repeat(1000),r=>r.scope=['2020-01-01','2026-10-09'],r=>r.notices[0].url='javascript:alert(1)',r=>r.notices[0].exchange='HK',r=>r.notices[0].closed_ranges=[['2025-01-01','2025-02-02']],r=>r.notices=Array(17).fill(r.notices[0]),r=>r.notices[0].reopen_dates=Array(129).fill('2026-01-05'),r=>r.notices[0].closed_dates=['2026-10-10'],r=>r.notices[0].publication_date='2025-2-30']){const r=ref();change(r);assert.throws(()=>assertNoticeReference(r));}
});
test('bad-price and duplicate presence survives; original full report stays unchanged',async()=>{
 for(const name of ['price','duplicate']){const r=f(name),before=JSON.stringify(r),m=member(name);assert.ok(m.present.includes('2026-01-05'));assert.deepEqual(m.absence_span,[r.members.find(x=>x.symbol===m.symbol).date_array[0],r.parameters.cutoff]);assert.ok(r.members.find(x=>x.symbol===m.symbol).reasons.length);await buildNoticeDiagnostic(r);assert.equal(JSON.stringify(r),before);}
});
test('refused fallback symbol/future identity conflict remain unknown, denominator retained',()=>{
 for(const name of ['refused','global_identity']){const m=member(name);assert.equal(m.exchange,null);assert.deepEqual(m.present,[]);assert.equal(m.absence_span,null);const r=run(name);assert.equal(r.unknown_members.length,1);assert.equal(r.selected,2);assert.equal(r.exchanges.reduce((n,e)=>n+e.members.length,0)+r.unknown_members.length,2);}
});
test('full counts beyond20 examples disable absence; independent known dates remain',()=>{
 const raw=f('unknown_after_twenty').members.find(m=>m.symbol==='000001.SZ');assert.equal(raw.anomalies.truncated,true);assert.ok(!raw.anomalies.examples.some(e=>e.date===null));
 const m=member('unknown_after_twenty');assert.equal(m.absence_span,null);assert.ok(m.present.includes('2026-01-05'));
 for(const name of ['unlocated_known','label_mismatch']){assert.equal(member(name).absence_span,null);assert.ok(!member(name).present.includes('2026-01-05'));}
 for(const name of ['local_conflict','unclassified']){assert.equal(member(name).absence_span,null);assert.deepEqual(member(name).present,[]);}
});
test('all internal missing explicit open gives candidate without replacing original121 points',async()=>{
 const r=f('missing_all'),before=JSON.stringify(r);assert.ok(r.members.every(m=>m.date_array.length===121));const result=await buildNoticeDiagnostic(r),d=cell(result,'2026-01-05');assert.equal(d.finding,'all_absent');assert.equal(d.absent.length,2);assert.equal(JSON.stringify(r),before);assert.equal(cell(run('missing_one'),'2026-01-05').finding,'some_absent');
});
test('before own first, missing cutoff and empty arrays cannot manufacture absence',()=>{
 const d=cell(run('short'),'2026-01-05');assert.equal(d.unknown.length,1);assert.equal(d.present.length,1);assert.equal(d.finding,null);assert.equal(member('cutoff_missing').absence_span,null);
 const r=run('empty');assert.equal(r.status,'not_evaluated');assert.ok(r.members.every(m=>m.absence_span===null));assert.ok(r.exchanges.flatMap(e=>e.dates).every(d=>!d.absent.length));
});
test('only explicit dates, inclusive closed endpoints, no following inferred open',()=>{
 const r=run();assert.equal(cell(r,'2026-01-05').planned,'open');assert.equal(cell(r,'2026-01-06'),undefined);for(const d of ['2026-02-15','2026-02-23'])assert.equal(cell(r,d).planned,'closed');assert.equal(cell(r,'2026-02-24').planned,'open');assert.equal(cell(r,'2026-02-25'),undefined);
});
test('same-direction deduplicates and opposing evidence conflicts regardless of later publication',()=>{
 const r=ref(),n=structuredClone(r.notices[2]);n.id='synthetic-second';n.publication_date='2026-10-01';r.notices.push(n);assertNoticeReference(r);assert.equal(cell(run('complete',r),'2026-01-05').evidence.length,2);
 n.closed_dates.push('2026-01-05');const d=cell(run('complete',r),'2026-01-05');assert.equal(d.planned,'conflict');assert.equal(d.finding,null);assert.equal(d.present.length+d.absent.length+d.unknown.length,2);
});
test('independent exchange denominators, absent reference and zero/single members',()=>{
 const r=run('mixed');assert.equal(r.exchanges.find(e=>e.exchange==='SSE').covered_dates,0);assert.equal(r.exchanges.find(e=>e.exchange==='SZSE').members.length,1);
 const sr=ref(),n=structuredClone(sr.notices[2]);n.exchange='SSE';n.id='synthetic-sse';n.url='https://www.sse.com.cn/synthetic';sr.notices.push(n);
 const result=run('mixed',sr);assert.equal(cell(result,'2026-01-05','SSE').finding,'all_absent');assert.equal(cell(result,'2026-01-05').finding,null);assert.equal(run().exchanges.find(e=>e.exchange==='SSE').dates.length,0);
});
test('P+A+U conserved; permutation/future lawful price stable; empty evidence not success',async()=>{
 const r=run();for(const e of r.exchanges)for(const d of e.dates)assert.equal(d.present.length+d.absent.length+d.unknown.length,e.members.length);assert.deepEqual(run('reversed'),r);
 const empty=ref();empty.notices=[];assert.equal(run('complete',empty).status,'not_evaluated');const a=await buildNoticeDiagnostic(f()),b=await buildNoticeDiagnostic(f('future_price'));assert.equal(a.attachment_id,b.attachment_id);
 const bad=f();bad.members[0].reasons=['invalid_price'];await assert.rejects(()=>buildNoticeDiagnostic(bad));
});
test('ID binds reliability and reference version beyond original analysis_id',async()=>{
 const a=await buildNoticeDiagnostic(f()),b=await buildNoticeDiagnostic(f('price'));assert.equal(a.parent_analysis_id,b.parent_analysis_id);assert.notEqual(a.attachment_id,b.attachment_id);
 const r=ref();r.version+='-synthetic';const c=await buildNoticeDiagnostic(f(),r,await noticeHash(r));assert.notEqual(a.attachment_id,c.attachment_id);assert.equal(a.mode,'retrospective');assert.equal(a.historical_availability,'unknown');assert.equal(noticeCanonical({文:'字',a:1}),'{"a":1,"文":"字"}');
});
test('independent handwritten date oracle matches all production explicit dates',()=>{
 const report=f('empty');report.parameters.cutoff='2026-10-09';const result=matchNoticeDates(report,ref()),sz=result.exchanges.find(e=>e.exchange==='SZSE');
 const expand=(a,b)=>{const result=[];for(let t=Date.parse(a+'T00:00:00Z');t<=Date.parse(b+'T00:00:00Z');t+=86400000)result.push(new Date(t).toISOString().slice(0,10));return result;};
 const closed=['2024-10-12','2025-01-01','2025-01-26','2025-02-08','2025-04-27','2025-09-28','2025-10-11','2026-01-04','2026-02-14','2026-02-28','2026-05-09','2026-09-20',
 ...[['2025-01-28','2025-02-04'],['2025-04-04','2025-04-06'],['2025-05-01','2025-05-05'],['2025-05-31','2025-06-02'],['2025-10-01','2025-10-08'],['2026-01-01','2026-01-03'],['2026-02-15','2026-02-23'],['2026-04-04','2026-04-06'],['2026-05-01','2026-05-05'],['2026-06-19','2026-06-21'],['2026-09-25','2026-09-27'],['2026-10-01','2026-10-07']].flatMap(([a,b])=>expand(a,b))].sort();
 const open=['2025-01-02','2025-02-05','2025-04-07','2025-05-06','2025-06-03','2025-10-09','2026-01-05','2026-02-24','2026-04-07','2026-05-06','2026-06-22','2026-09-28','2026-10-08'];
 assert.deepEqual(sz.dates.filter(d=>d.planned==='closed').map(d=>d.date),closed);assert.deepEqual(sz.dates.filter(d=>d.planned==='open').map(d=>d.date),open);
 assert.ok(!sz.dates.some(d=>d.date==='2026-10-10'));assert.equal(sz.open_dates+sz.closed_dates+sz.conflict_dates+sz.uncovered_dates,729);
});
test('raw prototype diagnostic names do not imply unrelated date/identity conflicts',()=>{
 const r=f(),m=r.members[0];m.anomalies.counts=JSON.parse('{"constructor":1,"__proto__":1,"toString":1}');
 const adapted=adaptNoticeMembers(r).find(x=>x.snapshot_id===m.snapshot_id);assert.equal(adapted.exchange,'SZSE');assert.ok(adapted.absence_span);
 // Own global/local/unknown counters are still acted on independently of example truncation.
 m.anomalies.counts.global_source_conflict=1;assert.equal(adaptNoticeMembers(r).find(x=>x.snapshot_id===m.snapshot_id).exchange,null);
});
test('out-of-window additions do not alter W results, no-overlap is not success',()=>{
 const r=ref();r.notices[0].closed_dates.push('2026-10-09');assert.deepEqual(run('complete',r),run());
 const report=f();report.parameters.cutoff='2024-01-01';const result=matchNoticeDates(report,ref());assert.equal(result.status,'no_overlap');assert.equal(result.window,null);assert.equal(result.differences,0);
});
test('source/date, range and fact count budgets reject rather than truncate',()=>{
 const r=f();r.members=Array(51).fill(r.members[0]);assert.throws(()=>matchNoticeDates(r,ref()),/notice_member_limit/);
 const s=f();s.members[0].date_array=Array(122).fill('2026-01-01');assert.throws(()=>matchNoticeDates(s,ref()),/notice_member_limit/);
 const n=ref();n.notices[0].closed_ranges=[['2025-01-02','2025-01-01']];assert.throws(()=>assertNoticeReference(n));
 const leap=ref();leap.scope=['2024-02-28','2024-03-01'];leap.notices=[{...leap.notices[0],closed_ranges:[['2024-02-28','2024-03-01']],closed_dates:[],reopen_dates:[]}];assertNoticeReference(leap);
 leap.notices[0].closed_dates=['2025-02-29'];assert.throws(()=>assertNoticeReference(leap));
});
test('async build freezes source/reference inputs before first SHA yield',async()=>{
 const r=f(),original=JSON.stringify(r),reference=ref();const pending=buildNoticeDiagnostic(r,reference);r.members[0].date_array=[];reference.version='changed-after-call';const result=await pending;
 assert.equal(result.reference.version,'szse-explicit-20261013-v1');assert.equal(result.members[0].source_span[0],JSON.parse(original).members[0].date_array[0]);
});
