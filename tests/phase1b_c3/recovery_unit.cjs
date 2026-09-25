/* C3 recovery closure: Node checks of the actual chat-sends.js beyond the reviewer's own
 * (tests/phase1b_c3/review_a8b4e52/test_c3_recovery_unit.cjs, reused unchanged for its
 * harness). Not a browser. Run: node recovery_unit.cjs /path/to/repository
 */
'use strict';
const assert=require('assert/strict');
const {setup,intent,scope,dk,response}=require('./review_a8b4e52/test_c3_recovery_unit.cjs');
const accepted=()=>response(202,{send:{send_id:'send1',operation:{id:'op1'}},operation:{id:'op1'}});
const complete=()=>response(200,{status:'complete',send:{state:'complete',liveness:'quiescent',settled:true},result:{messages:[]}});
const posts=h=>h.calls.filter(c=>c.method==='POST');
const status=(h,p)=>h.api.shown.get(p.client_key)?.text;
const cases=[];
async function test(name,fn){const o={};try{await fn(o);cases.push({name,status:'pass',observation:o});}
  catch(e){cases.push({name,status:'fail',assertion:String(e),observation:o});}}
(async()=>{
 await test('fresh_intent_refused_after_a_401_pause_is_still_not_sent',async o=>{
  // A 401 is answered before any route runs: it keeps the request provably unaccepted.
  let n=0;const h=setup((u,opt)=>opt.method==='POST'?(++n===1?response(401,{error:'bad or missing token'}):response(409,{error:'turn_in_progress'})):response(404,{error:'not_found'}));
  const p=intent();h.api.savePending(scope,p);
  await h.api.drive(scope,p,{freshIntent:true});o.afterPause=status(h,p);
  await h.api.drive(scope,h.api.loadPending(scope));
  o.status=status(h,p);o.pending=h.api.loadPending(scope);o.posts=posts(h).length;
  assert.equal(o.status,'Not sent');assert.equal(o.pending,null);assert.equal(o.posts,2);
 });
 await test('restored_intent_refused_on_replay_adopts_the_send_found_by_key',async o=>{
  const h=setup((u,opt)=>opt.method==='POST'?response(409,{error:'turn_in_progress'}):
    u.includes('/chat/sends?key=')?response(200,{send_id:'send1',operation:{id:'op1'}}):complete());
  const p=intent();h.api.savePending(scope,p);await h.api.drive(scope,p);
  o.pending=h.api.loadPending(scope);o.posts=posts(h).length;o.lookups=h.calls.filter(c=>c.url.includes('?key=')).length;
  assert.equal(o.pending,null,'settled by the receipt of the send the key already names');assert.equal(o.posts,1);assert.equal(o.lookups,1);
 });
 await test('restored_intent_refused_on_replay_without_a_record_stays_unresolved',async o=>{
  const h=setup((u,opt)=>opt.method==='POST'?response(409,{error:'turn_in_progress'}):response(404,{error:'not_found'}));
  const p=intent();h.api.savePending(scope,p);await h.api.drive(scope,p);
  o.status=status(h,p);o.pending=h.api.loadPending(scope);o.lock=h.api.drivers.has(p.client_key);
  assert.equal(o.pending?.client_key,p.client_key);assert.notEqual(o.status,'Not sent');assert.equal(o.lock,false);
  assert.match(o.status,/not confirmed/);assert.doesNotMatch(o.status,/will check again/,'no automatic check is scheduled');
  const keys=new Set(posts(h).map(c=>JSON.parse(c.body).client_key));assert.deepEqual([...keys],[p.client_key]);
 });
 await test('receipt_settled_false_then_null_is_unresolved_not_finished',async o=>{
  let reads=0;const h=setup(u=>u.includes('/operations/')?response(200,{status:'unknown',send:{state:'unknown',settled:false,liveness:'unproven'}}):
    response(200,{state:'unknown',settled:++reads>1?null:false}));
  const p={...intent(),send_id:'send1',operation_id:'op1'};h.api.savePending(scope,p);await h.api.drive(scope,p);
  o.status=status(h,p);o.pending=h.api.loadPending(scope);
  assert.equal(o.pending?.client_key,p.client_key);assert.match(o.status,/unavailable right now/);
 });
 await test('receipt_404_keeps_the_intent_with_accurate_wording',async o=>{
  const h=setup(()=>response(404,{error:'not_found'}));
  const p={...intent(),send_id:'send1',operation_id:'op1'};h.api.savePending(scope,p);await h.api.drive(scope,p);
  o.status=status(h,p);o.pending=h.api.loadPending(scope);
  assert.equal(o.pending?.client_key,p.client_key);assert.match(o.status,/not visible from here/);
 });
 await test('draft_equal_to_the_submission_with_no_edit_is_cleared',async o=>{
  const h=setup((u,opt)=>u.includes('/bootstrap')?response(200,{conversation_id:'conv',generation:'g'}):opt.method==='POST'?accepted():complete());
  h.data.set(dk,'Submitted');await h.api.startIntent(scope,'Submitted',{box:{value:'Submitted'},grow:()=>{}});
  o.draft=h.data.get(dk);assert.equal(o.draft,'');
 });
 const out={scope:'source-executed Node checks, not browser/Hermes certification',cases,
   passed:cases.filter(c=>c.status==='pass').length,failed:cases.filter(c=>c.status==='fail').length};
 console.log(JSON.stringify(out,null,2));process.exitCode=out.failed?1:0;
})().catch(e=>{console.error(e);process.exitCode=2;});
