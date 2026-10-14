// 073: optional external jsdom; first-commit correctness, never a timing test.
import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {fixture as eventFixture} from './single-event-path-fixtures.mjs';
import {createServer} from 'vite';
import {createElement,act,Profiler} from 'react';
const {JSDOM}=await import(process.env.ANATRADING_JSDOM_PATH?pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href:'jsdom');
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {SingleResearch}=await server.ssrLoadModule('/src/SingleResearch.tsx');
const {assertResearchReply,buildResearchRequest}=await server.ssrLoadModule('/src/research-model.ts');
const root=createRoot(document.getElementById('root')),originalFetch=globalThis.fetch;
after(async()=>{await act(()=>root.unmount());await server.close();dom.window.close();globalThis.fetch=originalFetch;});
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/component-query-keys.json',import.meta.url)));
const panel=()=>document.querySelector('[aria-label="日线趋势与历史事件"]');
const chart=()=>panel()?.querySelector('svg.estimate-chart');
let requests=[],published=[],commits=[];
const handler=(el,name)=>el[Object.keys(el).find(k=>k.startsWith('__reactProps'))][name];
const snapshot=()=>({chart:!!chart(),columns:!!panel()?.querySelector('.research-columns'),ledger:[...(panel()?.querySelectorAll('summary')??[])].some(e=>e.textContent.startsWith('查看事件记录')),provenance:!!panel()?.querySelector('.research-provenance'),empty:panel()?.textContent.includes('截止范围内没有可研究的日线记录。')??false,text:panel()?.textContent});
const draw=q=>act(()=>root.render(createElement(Profiler,{id:'ownership',onRender(){commits.push(snapshot());}},createElement(SingleResearch,{query:q,onReport:(...v)=>published.push(v)}))));
const settle=(req,reply)=>act(()=>req.resolve({ok:true,json:async()=>reply}));
const submit=()=>act(()=>panel().querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
const edit=(selector,value)=>act(()=>handler(panel().querySelector(selector),'onChange')({target:{value}}));
const singleRequests=()=>requests.filter(r=>r.url.startsWith('/api/research/single/'));
async function mount(f=fixture()){

 await act(()=>root.render(null));requests=[];published=[];commits=[];
 globalThis.fetch=(url,options={})=>new Promise((resolve,reject)=>requests.push({url:String(url),options,resolve,reject}));
 const q=f.reply.query;
 assertResearchReply(f.report,buildResearchRequest('single',[q.snapshot_id],q.selection.cutoff??'',20,f.report.parameters.horizon,f.report.parameters.test_start??'').expected);
 await draw(q);
 if(f.report.parameters.horizon!==5){await edit('select',String(f.report.parameters.horizon));await submit();}
 if(f.report.parameters.test_start){await edit('input[type=date]',f.report.parameters.test_start);await submit();}
 await settle(singleRequests().at(-1),f.report);
 if(f.report.result.series.length)assert.ok(chart(),'legitimate initial acceptance');return f;
}
function assertHidden(label){
 assert.ok(commits.length,label+' produced a commit');
 for(const [i,c] of commits.entries()){
  assert.equal(c.chart,false,label+' SVG at commit '+i);
  assert.equal(c.columns,false,label+' full result block at commit '+i);
  assert.equal(c.ledger,false,label+' ledger at commit '+i);
  assert.equal(c.provenance,false,label+' provenance at commit '+i);
  assert.equal(c.empty,false,label+' empty report at commit '+i);
 }
}
test('snapshot replacement suppresses old SVG at the FIRST React commit',async()=>{
 const f=await mount();commits=[];await draw({...f.reply.query,snapshot_id:'e'.repeat(64)});assertHidden('snapshot');
});
const contexts=[
 ['snapshot',q=>q.snapshot_id='e'.repeat(64)],
 ['batch',q=>q.batch_id='e'.repeat(64)],
 ['cutoff',q=>q.selection.cutoff='2026-02-01'],
 ['ordinal start',q=>q.selection.ordinal_start=2],
 ['ordinal end',q=>q.selection.ordinal_end=20],
 ['period',q=>q.metadata.period='1m'],
 ['qualification',q=>q.manifest.qualification='known_negative_sample'],
 ['known negative',q=>q.batch_checks.push({name:'known_negative_sample',outcome:'fail'})],
];
for(const [name,mutate] of contexts)test(name+' first-commit and A-B-A ownership; explicit reacceptance',async()=>{
 const f=await mount(),q=f.reply.query,b=structuredClone(q),calls=requests.length;
 const before=panel().querySelector('.research-columns').outerHTML;mutate(b);
 commits=[];await draw(b);assertHidden(name);assert.equal(requests.length,calls,'no implicit fetch');
 commits=[];await draw(q);assertHidden(name+' return A');assert.equal(requests.length,calls);
 await submit();await settle(singleRequests().at(-1),f.report);
 assert.equal(panel().querySelector('.research-columns').outerHTML,before,'full accepted result unchanged');
});
test('query-ID replacement hides first commit and uses original automatic-load flow',async()=>{
 const f=await mount(),q={...f.reply.query,query_id:'e'.repeat(64)},calls=singleRequests().length;
 commits=[];await draw(q);assertHidden('query ID');assert.equal(singleRequests().length,calls+1);
 await settle(singleRequests().at(-1),f.report);assert.ok(chart());
});
for(const [selector,value,original] of [['input[type=number]','21','20'],['input[type=date]','2026-01-10',''],['select','1','5'],['input[type=number]','','20']])test('parameter '+selector+' '+JSON.stringify(value)+' immediately invalidates and does not revive',async()=>{
 const f=await mount(),calls=requests.length;commits=[];await edit(selector,value);assertHidden('parameter');
 commits=[];await edit(selector,original);assertHidden('parameter return');assert.equal(requests.length,calls);
 await submit();await settle(singleRequests().at(-1),f.report);assert.ok(chart());
});
for(const mode of ['success','failure'])test('superseded request '+mode+' cannot replace or clear new accepted output',async()=>{
 const f=await mount();await submit();const old=singleRequests().at(-1);
 await submit();const current=singleRequests().at(-1);await settle(current,f.report);
 const before=panel().innerHTML,pubs=published.length,calls=requests.length;commits=[];
 if(mode==='success')await settle(old,f.report);else await act(()=>old.reject(Error('synthetic late failure')));
 assert.equal(panel().innerHTML,before);assert.equal(published.length,pubs);assert.equal(requests.length,calls);assert.ok(chart());
});
for(const [name,mutate] of contexts)test('pending success after '+name+' A-B-A stays revoked',async()=>{
 const f=await mount();await submit();const old=singleRequests().at(-1),b=structuredClone(f.reply.query);mutate(b);
 await draw(b);await draw(f.reply.query);commits=[];await settle(old,f.report);
 assert.equal(chart(),null);assert.equal(snapshot().provenance,false);assert.ok(old.options.signal.aborted);
});
function fromEvents(name){
 const f=eventFixture(name),base=fixture();base.report=f.reply;
 base.reply.query={...base.reply.query,...f.query,selection:{...base.reply.query.selection,...f.query.selection}};
 return base;
}
for(const name of ['H1','H10','H20','KALMAN_ONLY_FAILURE','P4_END_NULL','P4_DUP'])test(name+' retains accepted rendering and read-only full DTO',async()=>{
 const f=fromEvents(name),original=JSON.stringify(f),descriptors=Object.getOwnPropertyDescriptors(f.report.result.series[0]);
 await mount(f);const html=panel().querySelector('.research-columns').outerHTML,calls=requests.length,pubs=published.length;
 await draw(structuredClone(f.reply.query));assert.equal(panel().querySelector('.research-columns').outerHTML,html);
 assert.equal(requests.length,calls);assert.equal(published.length,pubs);assert.equal(JSON.stringify(f),original);
 assert.deepEqual(Object.getOwnPropertyDescriptors(f.report.result.series[0]),descriptors);
});
test('paging and stale callbacks preserve complete plot, statistics, requests, and newly accepted ownership',async()=>{
 const f=await mount(fromEvents('RECENT101')),original=JSON.stringify(f.report),before=panel().querySelector('.research-columns').outerHTML;
 const buttons=()=>[...panel().querySelectorAll('button')],button=t=>buttons().find(b=>b.textContent===t);
 const oldPage=handler(button('较早一页'),'onClick'),oldRow=handler(button('查看后续收盘'),'onClick');
 const calls=requests.length,pubs=published.length;
 await act(()=>button('较早一页').click());await act(()=>button('查看后续收盘').click());
 const oldClose=handler(button('收起明细'),'onClick');await act(()=>oldClose());
 await act(()=>button('较新一页').click());
 assert.equal(panel().querySelector('.research-columns').outerHTML,before);assert.equal(requests.length,calls);assert.equal(published.length,pubs);
 await submit();await settle(singleRequests().at(-1),f.report);const current=panel().innerHTML;
 await act(()=>{oldPage();oldRow({currentTarget:document.createElement('button')});oldClose();});
 assert.equal(panel().innerHTML,current);assert.equal(JSON.stringify(f.report),original);
});
test('six-slot local qualification failure preserves original accepted chart and ledger',async()=>{
 const f=fixture();f.report.result.events.rows[0].start_close='999'; // Deliberate local-link fault, not normal data.
 await mount(f);assert.ok(chart());assert.ok(snapshot().ledger);assert.match(panel().textContent,/原报告保留/);
});
test('empty accepted report is hidden on first mismatching commit',async()=>{
 const f=fromEvents('RECENT0');
 await mount(f);assert.equal(snapshot().empty,true);commits=[];
 await draw({...f.reply.query,snapshot_id:'e'.repeat(64)});assertHidden('empty report');
});

test('same analysis ID and same object explicitly reaccepted redraw changed estimate content',async()=>{
 const f=await mount(),before=chart().outerHTML,id=f.report.analysis_id;
 await submit();assert.equal(chart(),null);
 f.report.result.series.at(-1).kalman_price=4242; // Fixture mutation only after prior acceptance revoked.
 await settle(singleRequests().at(-1),f.report);assert.equal(f.report.analysis_id,id);assert.notEqual(chart().outerHTML,before);
});
