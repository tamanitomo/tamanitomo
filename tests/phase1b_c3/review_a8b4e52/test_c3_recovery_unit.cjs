/* Reviewer unit tests of the actual submitted script. No browser certification.
 * Only instrumentation is exposing existing closure functions; no function is replaced.
 * Fetch, storage and a detached textarea are controlled test doubles. Run:
 * node test_c3_recovery_unit.cjs /path/to/repository
 */
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert/strict');
const root=process.argv[2]; if(!root)throw Error('Pass the repository root');
const script=fs.readFileSync(path.join(root,'kit/app/static/chat-sends.js'),'utf8');
const anchor='window.KeyedChat={';assert.equal(script.split(anchor).length,2);
const exposed=script.replace(anchor,'window.__review={drive,acquire,follow,startIntent,attach,loadPending,savePending,shown,drivers,ulid};\n'+anchor);
const scope={installation:'existing',profile:'nova'};
const key='01K5VHY8J80000000000000000';
const intent=()=>({v:1,client_key:key,generation:'g',conversation_id:'conv',installation:'existing',profile:'nova',session:null,message:'Synthetic pending message',created_at:Date.now()});
const pk='chat-pending-existing-nova',dk='chat-draft-existing-nova';
function response(status,data){return {status,json:async()=>data};}
function boot(){return response(200,{conversation_id:'conv',generation:'g'});}
function complete(){return response(200,{status:'complete',send:{state:'complete',liveness:'quiescent',settled:true},result:{messages:[]}});}
function accepted(p){return response(202,{send:{send_id:'send1',operation:{id:'op1'}},operation:{id:'op1'}});}
function setup(fetcher){
 const data=new Map(),calls=[],errors=[],timer=new Map();let serial=0;
 const ctx={URL,AbortController,Uint8Array,BigInt,Date,Map,Set,Promise,JSON,Error,crypto:globalThis.crypto,
  INSTALLATION:'existing',PROFILE:'nova',current:'now',activeOperation:null,chatSession:null,token:'synthetic',
  location:{origin:'http://fixture.invalid'},document:{querySelector:()=>({content:'keyed'})},
  sessionStorage:{getItem:k=>data.has(k)?data.get(k):null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k)},
  $:()=>null,showTyping:()=>{},voiceControlsBusy:()=>{},notice:()=>{},chatName:()=> 'Nova',
  console:{error:e=>errors.push(String(e))},
  setTimeout:(fn,ms)=>{const id=++serial;timer.set(id,fn);if(ms<15000)queueMicrotask(()=>{if(timer.has(id)){timer.delete(id);fn();}});return id;},
  clearTimeout:id=>timer.delete(id),
  fetch:async(url,opt)=>{calls.push({url,method:opt.method,body:opt.body});return fetcher(url,opt);}
 };
 ctx.window=ctx;vm.createContext(ctx);vm.runInContext(exposed,ctx,{filename:'chat-sends.js'});
 return {ctx,api:ctx.__review,data,calls,errors};
}
async function driveCaught(h,p,options){try{await h.api.drive(scope,p,options);return null;}catch(e){return String(e);}}
const cases=[];
async function test(name,fn){let observation={};try{await fn(observation);cases.push({name,status:'pass',observation});}catch(e){cases.push({name,status:'fail',assertion:String(e),observation});}}
if(require.main===module)(async()=>{
 await test('initial_401_releases_driver_and_check_now_can_retry',async o=>{
  let signedOut=true;
  const h=setup((u,opt)=>opt.method==='POST'?(signedOut?response(401,{error:'unauthorized'}):accepted()):complete());
  const p=intent();h.api.savePending(scope,p);
  o.firstError=await driveCaught(h,p);o.lockAfter401=h.api.drivers.has(p.client_key);
  signedOut=false;await driveCaught(h,p);o.postCount=h.calls.filter(c=>c.method==='POST').length;o.pending=h.api.loadPending(scope);
  assert.equal(o.firstError,null,'Pausing before acceptance must not throw in finally');
  assert.equal(o.lockAfter401,false,'Paused driver must release its per-key lock');
  assert.equal(o.postCount,2,'Check now must retry the original request');
 });
 await test('uncertain_acceptance_then_ledger_loss_keeps_pending_not_not_sent',async o=>{
  let posts=0;
  const h=setup((u,opt)=>{if(opt.method==='POST'&&++posts===1)throw Error('Server accepted; response lost (transport double)');return response(503,{error:'send_ledger_lost'});});
  const p=intent();h.api.savePending(scope,p);o.error=await driveCaught(h,p);o.lastStatus=h.api.shown.get(p.client_key)?.text;o.pending=h.api.loadPending(scope);o.posts=posts;
  assert.notEqual(o.lastStatus,'Not sent','A later missing ledger cannot prove that the original request was never accepted');
  assert.equal(o.pending?.client_key,p.client_key,'Keep the exact unresolved intent');
 });
 await test('confirmed_send_receipt_outage_keeps_pending',async o=>{
  const h=setup(u=>u.includes('/operations/')?response(404,{error:'not_found'}):response(503,{error:'source_unavailable'}));
  const p={...intent(),send_id:'send1',operation_id:'op1'};h.api.savePending(scope,p);h.ctx.activeOperation='chat-send:'+p.client_key;
  o.error=await driveCaught(h,p);o.pending=h.api.loadPending(scope);o.lastStatus=h.api.shown.get(p.client_key)?.text;o.activeOperation=h.ctx.activeOperation;
  assert.equal(o.pending?.client_key,p.client_key,'A temporarily unreadable receipt must not settle/forget an accepted send');
 });
 await test('unresolved_operation_with_settled_null_keeps_pending',async o=>{
  const h=setup(()=>response(200,{status:'unknown',result:null,error_code:'send_ledger_unavailable',send:{send_id:'send1',state:'unknown',settled:null,ledger:'unavailable'}}));
  const p={...intent(),send_id:'send1',operation_id:'op1'};h.api.savePending(scope,p);h.ctx.activeOperation='chat-send:'+p.client_key;
  o.error=await driveCaught(h,p);o.pending=h.api.loadPending(scope);o.lastStatus=h.api.shown.get(p.client_key)?.text;o.activeOperation=h.ctx.activeOperation;
  assert.equal(o.pending?.client_key,p.client_key,'The real F1 unresolved operation explicitly says settled:null, not true');
 });
 await test('late_bootstrap_does_not_clear_a_newer_draft_from_another_view',async o=>{
  let release;const delayed=new Promise(r=>release=r);
  const h=setup((u,opt)=>u.includes('/bootstrap')?delayed:opt.method==='POST'?accepted():complete());
  const p=intent(),oldBox={value:p.message};h.data.set(dk,p.message);
  const submitted=h.api.startIntent(scope,p.message,{box:oldBox,grow:()=>{}});
  // The original textarea has been detached by navigation. A new view persisted a new draft.
  h.data.set(dk,'A newer draft typed after navigation');release(boot());await submitted;
  for(let i=0;i<12;i++)await Promise.resolve();
  o.draft=h.data.get(dk);o.detachedTextarea=oldBox.value;o.postCount=h.calls.filter(c=>c.method==='POST').length;
  assert.equal(o.draft,'A newer draft typed after navigation','Late bootstrap must not clear the newer saved draft through the detached old textarea');
 });
 await test('control_operation_phase_401_releases_driver',async o=>{
  const h=setup(()=>response(401,{error:'unauthorized'}));const p={...intent(),send_id:'send1',operation_id:'op1'};h.api.savePending(scope,p);
  o.error=await driveCaught(h,p);o.lock=h.api.drivers.has(p.client_key);o.pending=h.api.loadPending(scope);
  assert.equal(o.error,null);assert.equal(o.lock,false);assert.equal(o.pending?.client_key,p.client_key);
 });
 await test('control_brand_new_busy_refusal_is_still_not_sent',async o=>{
  const h=setup((u,opt)=>u.includes('/bootstrap')?boot():response(409,{error:'turn_in_progress'}));
  const p=intent();h.api.savePending(scope,p);o.error=await driveCaught(h,p,{freshIntent:true});
  o.pending=h.api.loadPending(scope);o.posts=h.calls.filter(c=>c.method==='POST').length;
  o.status=[...h.api.shown.values()].at(-1)?.text;
  assert.equal(o.pending,null);assert.equal(o.posts,1);assert.equal(o.status,'Not sent');
 });
 await test('control_connected_send_clears_its_own_pending',async o=>{
  const h=setup((u,opt)=>opt.method==='POST'?accepted():complete());const p=intent();h.api.savePending(scope,p);
  o.error=await driveCaught(h,p);o.pending=h.api.loadPending(scope);o.posts=h.calls.filter(c=>c.method==='POST').length;
  assert.equal(o.error,null);assert.equal(o.pending,null);assert.equal(o.posts,1);
 });
 console.log(JSON.stringify({scope:'source-executed Node unit tests, not browser/Hermes certification',cases,passed:cases.filter(c=>c.status==='pass').length,failed:cases.filter(c=>c.status==='fail').length},null,2));
 process.exitCode=cases.some(c=>c.status==='fail')?1:0;
})().catch(e=>{console.error(e);process.exitCode=2;});

module.exports={setup,intent,scope,pk,dk,response};
