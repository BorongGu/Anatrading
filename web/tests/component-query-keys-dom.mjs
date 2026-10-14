// Optional external jsdom; actual App/SourceChart, only graphical API adapted.
import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createServer} from 'vite';
import {createElement,act} from 'react';
const {JSDOM}=await import(process.env.ANATRADING_JSDOM_PATH?pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href:'jsdom');
const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
const server=await createServer({resolve:{alias:{'lightweight-charts':fileURLToPath(new URL('./helpers/chart-api-adapter.mjs',import.meta.url))}},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {default:App}=await server.ssrLoadModule('/src/App.tsx');
const {charts}=await server.ssrLoadModule('/tests/helpers/chart-api-adapter.mjs');
const root=createRoot(document.getElementById('root')),originalFetch=globalThis.fetch,originalError=console.error;
let errors=[];console.error=(...args)=>{errors.push(args.map(String).join(' '));originalError(...args);};
after(async()=>{await act(()=>root.unmount());await server.close();dom.window.close();globalThis.fetch=originalFetch;console.error=originalError;});
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/component-query-keys.json',import.meta.url)));
const panel=()=>document.querySelector('[aria-label="日线趋势与历史事件"]');
const ledger=()=>[...(panel()?.querySelectorAll('details')??[])].find(x=>x.firstElementChild?.textContent.startsWith('查看事件记录'));
const change=(el,value)=>act(()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLSelectElement.prototype,'value').set.call(el,value);el.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
const submit=el=>act(()=>el.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
const click=el=>act(()=>el.click());
const live=()=>charts.filter(c=>!c.removed);
function unique(daily){assert.equal(document.querySelectorAll('.chart-panel').length,1);assert.equal(live().length,1);assert.equal(document.querySelectorAll('[aria-label="日线趋势与历史事件"]').length,daily?1:0);}
for(const period of ['1d','1m'])test(period+' first/repeat/advanced/select/reset/unmount without duplicate sibling keys',async()=>{
 errors=[];const f=fixture(),q=f.reply.query;q.metadata.period=period;f.snapshot.metadata.period=period;
 if(period==='1m'){q.rows.forEach(r=>{r.label+=' 09:31';r.source_label=r.label;});}
 const original=JSON.stringify(f);const calls=[];let pending=null,defer=false;
 globalThis.fetch=(url,options={})=>{const path=new URL(url,'http://localhost').pathname;calls.push(path);const ok=x=>Promise.resolve(new Response(JSON.stringify(x)));
 if(path==='/api/config')return ok({csrf_token:'synthetic',formats:['tdx-public-text-v1'],mode:'retrospective',max_query_rows:20000,max_upload_bytes:16777216,capabilities:{tdx_client:false}});
 if(path==='/api/snapshots')return ok({snapshots:[f.snapshot]});if(path==='/api/attempts')return ok({attempts:[]});if(path.startsWith('/api/query/'))return ok(f.reply);
 if(path.startsWith('/api/research/single/')){if(defer)return new Promise(resolve=>pending={resolve,options});return ok(f.report);}
 if(path.startsWith('/api/research/'))return Promise.resolve(new Response(JSON.stringify({error:'synthetic_failure'}),{status:400}));throw Error('Unexpected URL '+url);};
 await act(()=>root.render(createElement(App)));await change(document.getElementById('snapshot'),q.snapshot_id);unique(period==='1d');
 if(period==='1d')assert.ok(ledger(),'valid research accepted');
 for(let i=0;i<2;i++){
  const before=calls.length;await act(()=>live()[0].click({time:i}));assert.ok(document.querySelector('.panel.detail-panel').textContent.includes(q.rows[i].label));unique(period==='1d');assert.equal(calls.length,before);
  await click(document.querySelector('.section-toggle'));unique(period==='1d');assert.equal(document.querySelectorAll('.advanced-analysis').length,1);
  await click(document.querySelector('.section-toggle'));assert.equal(document.querySelector('.advanced-analysis'),null);
  if(period==='1d'){await submit(panel().querySelector('form'));assert.ok(ledger());assert.ok(document.querySelector('.panel.detail-panel'));}
  await submit(document.querySelector('.query-toolbar'));unique(period==='1d');assert.equal(document.querySelector('.panel.detail-panel'),null);
 }
 if(period==='1d'){
  defer=true;await submit(panel().querySelector('form'));const old=pending;await change(document.getElementById('snapshot'),'');assert.ok(old.options.signal.aborted);
  defer=false;await change(document.getElementById('snapshot'),q.snapshot_id);assert.ok(ledger());const text=panel().textContent;
  await act(()=>old.resolve(new Response(JSON.stringify(f.report))));assert.equal(panel().textContent,text);unique(true);
 }
 assert.equal(JSON.stringify(f),original);await change(document.getElementById('snapshot'),'');assert.equal(document.querySelector('.chart-panel'),null);assert.equal(panel(),null);assert.equal(live().length,0);
 await act(()=>root.render(null));assert.deepEqual(errors,[],'React console must remain clean');
});
