import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'vite';
import vm from 'node:vm';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pairSignContextBinding } from '../src/pair-sign-crossproducts.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/group_pair_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:4*1024*1024}));

// Compile the actual component with deterministic hook/adapter doubles. The
// separate ReactDOM acceptance checks real scheduling, binding and DOM actions.
const bundle=await build({configFile:false,logLevel:'silent',plugins:[{
 name:'pair-sign-render-test',enforce:'pre',
 transform(code,id){if(!id.endsWith('/PairSignDetails.tsx'))return;
  return code.replace("import { useEffect, useRef, useState } from 'react';",'const {useEffect,useRef,useState}=globalThis.hooks;')
   .replace("import { buildPairSignAttachment, formatPairSignFraction, pairSignContextBinding } from './pair-sign-crossproducts.ts';",'const {buildPairSignAttachment,formatPairSignFraction,pairSignContextBinding}=globalThis.adapter;')+'\nexport {Calculation};';
 }
}],build:{write:false,minify:false,lib:{entry:fileURLToPath(new URL('../src/PairSignDetails.tsx',import.meta.url)),name:'Subject',formats:['iife']}}});
const code=(Array.isArray(bundle)?bundle[0]:bundle).output.find(x=>x.type==='chunk').code;
function harness(){
 const {reply:report,expected}=structuredClone(fixtures.complete),pair=report.pairs[0];
 const attachment={status:'unavailable'},context={report,expected,left:pair.left_snapshot_id,right:pair.right_snapshot_id,generation:0,binding:pairSignContextBinding(report,expected,pair)};
 let calls=0,index=0,state={...context,attachment},effect,resolve;
 const refs=[{current:context},{current:true}],published=[];
 const sandbox={process:{env:{NODE_ENV:'production'}},AbortController,Blob,URL,console,hooks:{useState:()=>[state,value=>published.push(value)],useRef:()=>refs[index++],useEffect:fn=>{effect=fn;}},adapter:{pairSignContextBinding:()=>{calls++;return pairSignContextBinding(report,expected,pair);},formatPairSignFraction:()=>'',buildPairSignAttachment:()=>new Promise(r=>{resolve=r;})}};
 vm.createContext(sandbox);vm.runInContext(code,sandbox);
 return {render(){index=0;return sandbox.Subject.Calculation({report,expected,pair,onOpen(){},isOpen:()=>true});},get calls(){return calls;},mutate(){report.members[0].endpoints[10].ordinal+=1;},setError(){state={...context,error:'invalid_context'};},start(){effect();},async complete(){resolve({attachment});await Promise.resolve();},published};
}
function button(tree){return tree.props.children.find(child=>child?.type==='button');}
test('059 completed render binds once; a saved export still binds fresh',()=>{
 const h=harness(),tree=h.render();assert.equal(h.calls,1);
 h.mutate();button(tree).props.onClick();assert.equal(h.calls,2);
});
test('059 error render uses the same render binding once',()=>{
 const h=harness();h.setError();const tree=h.render();assert.equal(h.calls,1);
 assert.match(tree.props.children,/数值或资源限制未通过/);
});
test('059 completion checks a fresh binding and rejects intervening mutation',async()=>{
 const h=harness();h.render();h.start();h.mutate();const before=h.calls;
 await h.complete();assert.equal(h.calls,before+1);assert.deepEqual(h.published,[null]);
});
