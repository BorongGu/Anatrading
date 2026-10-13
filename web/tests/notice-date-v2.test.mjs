import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {assertNoticeReference,verifyNoticeReference,matchNoticeDates,buildNoticeDiagnostic,noticeHash,NOTICE_REFERENCE_HASH,NOTICE_REFERENCE_V2_HASH} from '../src/notice-date-model.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/notice_date_fixture_bridge.py',import.meta.url))],{encoding:'utf8'}));
const read=name=>JSON.parse(readFileSync(new URL(`../src/${name}`,import.meta.url),'utf8'));
const v1=read('notice-reference-v1.json'),v2=read('notice-reference-v2.json');
const f=name=>structuredClone(fixtures[name].reply),ref=()=>structuredClone(v2);
test('v2 rejects mixed schemas, incomplete exchange evidence and invalid capture timestamps',()=>{
 for(const change of [r=>r.accepted_facts_sha256='a'.repeat(64),r=>delete r.evidence_by_exchange.SSE,r=>r.evidence_by_exchange.HK=r.evidence_by_exchange.SSE,r=>r.evidence_by_exchange.SSE.review_sha256='bad',r=>r.evidence_by_exchange.SSE.extra=true,r=>r.historical_content_identity='verified',r=>r.known_at='2026-10-13',r=>delete r.notices[0].retrieved_at_utc,r=>r.notices[0].retrieved_at_utc='2026-02-30T10:00:00Z',r=>r.notices[0].retrieved_at_utc='2026-10-13T25:00:00Z',r=>r.notices[0].retrieved_at_utc='2026-10-13T00:00:00+08:00',r=>r.notices[0].url='https://www.szse.cn/wrong-exchange']){
  const r=ref();change(r);assert.throws(()=>assertNoticeReference(r));
 }
 const old=structuredClone(v1);old.notices[0].retrieved_at_utc='2026-10-13T00:00:00Z';assert.throws(()=>assertNoticeReference(old));
});
test('legacy explicit v1 remains replayable with original exported hash and exact attachment identity',async()=>{
 assert.equal(NOTICE_REFERENCE_HASH,'f3ad5c46bde683f3d713259e2aa35166f7469296956d7cc82538734c60a90264');
 await verifyNoticeReference(v1);
 const old=await buildNoticeDiagnostic(f('mixed'),v1,NOTICE_REFERENCE_HASH);
 assert.equal(old.attachment_id,'8cfd32913dbe8cf920cf205516219565453cde0e02ab05afccf36a564fde336a');
 assert.equal(old.exchanges[0].covered_dates,0);assert.deepEqual(old.exchanges[0].dates,[]);
 const current=await buildNoticeDiagnostic(f('mixed'));
 assert.equal(current.reference.schema,'explicit-notice-reference-v2');assert.notEqual(current.attachment_id,old.attachment_id);assert.equal(current.parent_analysis_id,old.parent_analysis_id);
 assert.equal(current.exchanges[0].dates.find(d=>d.date==='2026-01-05').finding,'all_absent');
 await assert.rejects(()=>buildNoticeDiagnostic(f('mixed'),v2,NOTICE_REFERENCE_HASH),/notice_reference_integrity/);
});
test('v2 pins separate accepted source facts and binds provenance into reference identity',async()=>{
 await verifyNoticeReference(v2);assert.equal(await noticeHash(v2),NOTICE_REFERENCE_V2_HASH);
 assert.deepEqual(Object.keys(v2.evidence_by_exchange).sort(),['SSE','SZSE']);
 assert.equal(v2.evidence_by_exchange.SSE.accepted_facts_sha256,'7db3ac48ad6991b9a8302462bbded7f363b0eb4da0d34b87abb3b3555dbd8ba8');
 assert.equal(v2.evidence_by_exchange.SZSE.accepted_facts_sha256,v1.accepted_facts_sha256);
 assert.notEqual(v2.evidence_by_exchange.SSE.review_sha256,v2.evidence_by_exchange.SZSE.review_sha256);
 for(const change of [r=>r.evidence_by_exchange.SSE.accepted_facts_sha256=r.evidence_by_exchange.SZSE.accepted_facts_sha256,r=>r.evidence_by_exchange.SSE.review_sha256='a'.repeat(64),r=>r.notices[0].retrieved_at_utc='2026-10-13T00:00:00Z']){
  const r=ref();change(r);assertNoticeReference(r);await assert.rejects(()=>verifyNoticeReference(r),/notice_reference_integrity/);
 }
});
test('v2 SSE literal notices cover only 72 closures and 13 exact named opens within unchanged scope',()=>{
 const r=f('empty');r.members[0].symbol='600000.SH';r.parameters.cutoff='2026-10-09';const result=matchNoticeDates(r,v2);
 for(const e of result.exchanges){assert.equal(e.closed_dates,72);assert.equal(e.open_dates,13);assert.equal(e.conflict_dates,0);assert.equal(e.uncovered_dates,644);assert.equal(e.covered_dates,85);assert.ok(!e.dates.some(d=>['2024-10-11','2026-01-06','2026-10-09','2026-10-10'].includes(d.date)));}
 const s=result.exchanges[0];assert.deepEqual(s.dates.filter(d=>d.planned==='open').map(d=>d.date),['2025-01-02','2025-02-05','2025-04-07','2025-05-06','2025-06-03','2025-10-09','2026-01-05','2026-02-24','2026-04-07','2026-05-06','2026-06-22','2026-09-28','2026-10-08']);
 const expand=(a,b)=>{const dates=[];for(let t=Date.parse(a+'T00:00:00Z');t<=Date.parse(b+'T00:00:00Z');t+=86400000)dates.push(new Date(t).toISOString().slice(0,10));return dates;};
 const closed=['2024-10-12','2025-01-01','2025-01-26','2025-02-08','2025-04-27','2025-09-28','2025-10-11','2026-01-04','2026-02-14','2026-02-28','2026-05-09','2026-09-20',
 ...[['2025-01-28','2025-02-04'],['2025-04-04','2025-04-06'],['2025-05-01','2025-05-05'],['2025-05-31','2025-06-02'],['2025-10-01','2025-10-08'],['2026-01-01','2026-01-03'],['2026-02-15','2026-02-23'],['2026-04-04','2026-04-06'],['2026-05-01','2026-05-05'],['2026-06-19','2026-06-21'],['2026-09-25','2026-09-27'],['2026-10-01','2026-10-07']].flatMap(([a,b])=>expand(a,b))].sort();
 assert.deepEqual(s.dates.filter(d=>d.planned==='closed').map(d=>d.date),closed);
 assert.ok(s.dates.every(d=>d.evidence.every(id=>id.startsWith('sse-'))));
 for(const old of v1.notices){const n=v2.notices.find(n=>n.id===old.id);const {retrieved_at_utc,...projection}=n;assert.deepEqual(projection,old);assert.ok(retrieved_at_utc);}
});
test('v2 keeps fixed per-exchange and unknown denominators, source failures and immutable original reports',async()=>{
 for(const name of ['mixed','refused','global_identity','empty','cutoff_missing','price','unknown_after_twenty']){
  const r=f(name),before=JSON.stringify(r),d=await buildNoticeDiagnostic(r);
  assert.equal(JSON.stringify(r),before);assert.equal(d.selected,d.exchanges.reduce((n,e)=>n+e.members.length,0)+d.unknown_members.length);
  for(const e of d.exchanges)for(const row of e.dates){assert.equal(row.present.length+row.absent.length+row.unknown.length,e.members.length);assert.ok(row.evidence.every(id=>d.reference.notices.find(n=>n.id===id).exchange===e.exchange));}
  if(['refused','global_identity'].includes(name))assert.equal(d.unknown_members.length,1);
  if(name==='empty')assert.equal(d.status,'not_evaluated');
 }
 const noSse=await buildNoticeDiagnostic(f('complete'));assert.equal(noSse.exchanges[0].members.length,0);assert.ok(noSse.exchanges[0].covered_dates>0);assert.deepEqual(noSse.exchanges[0].dates,[]);
});

test('SSE cutoff uncertainty and unknown identity stay conservative under the same pure adapter',()=>{
 // Isolate exchange-independent adapter rules on a frozen synthetic DTO projection.
 const report=f('cutoff_missing');for(const m of report.members)m.symbol=m.symbol.replace('.SZ','.SH');
 const d=matchNoticeDates(report,v2),sse=d.exchanges[0];
 const uncertain=d.members.find(m=>m.unknown_reasons.includes('cutoff_not_enumerated'));
 assert.ok(uncertain);assert.equal(uncertain.exchange,'SSE');assert.equal(uncertain.absence_span,null);
 assert.ok(sse.dates.every(row=>!row.absent.includes(uncertain.snapshot_id)));
 const refused=f('refused');for(const m of refused.members)if(m.symbol)m.symbol=m.symbol.replace('.SZ','.SH');
 const out=matchNoticeDates(refused,v2);assert.equal(out.unknown_members.length,1);assert.equal(out.exchanges[0].members.length,1);
 for(const row of out.exchanges[0].dates)assert.equal(row.present.length+row.absent.length+row.unknown.length,1);
});
