/* Actual client functions + actual app HTTP/ledger + fake Hermes. NOT a browser run.
 * Arguments: repository-for-client-script, base URL, ledger path, lost|known.
 * The only simulated transport fault is dropping the first accepted response in lost mode.
 * The ledger is moved ONLY after a real settled receipt AND an idle operation worker.
 */
'use strict';
const fs=require('fs');
const {setup,intent,scope}=require('./test_c3_recovery_unit.cjs');
const [root,base,ledger,mode]=process.argv.slice(2);const nativeFetch=globalThis.fetch;
const headers={'content-type':'application/json','x-tamanitomo-token':'c3-synthetic-token','x-companion-token':'c3-synthetic-token'};
const realPath=p=>base+'/api'+p+(p.includes('?')?'&':'?')+'installation=existing&profile=nova';
async function real(p){const r=await nativeFetch(realPath(p),{headers});return {status:r.status,data:await r.json()};}
const nap=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const boot=await real('/chat/sends/bootstrap');if(boot.status!==200)throw Error(JSON.stringify(boot));
 const trace=[];let moved=false,accepted=null,settled=null;
 const h=setup(async(u,opt)=>{
  const r=await nativeFetch(base+u,{...opt,headers});const data=await r.json();trace.push({url:u,method:opt.method,status:r.status,error:data.error||null});
  if(!moved&&opt.method==='POST'&&r.status===202){
   accepted=data;const until=Date.now()+60000;
   while(Date.now()<until){
    settled=await real('/chat/sends/'+data.send.send_id);
    const idle=await real('/review-idle');
    if(settled.data.settled&&idle.data.idle)break;
    await nap(30);
   }
   if(!settled?.data.settled)throw Error('Fixture did not settle');
   fs.renameSync(ledger,ledger+'.review-kept');moved=true;
   if(mode==='lost')throw Error('Synthetic lost accepted response');
  }
  return {status:r.status,json:async()=>data};
 });
 const p={...intent(),client_key:h.api.ulid(),generation:boot.data.generation,conversation_id:boot.data.conversation_id};
 h.api.savePending(scope,p);h.ctx.activeOperation='chat-send:'+p.client_key;
 let error=null;try{await h.api.drive(scope,p);}catch(e){error=String(e);}
 const out={mode,scope:'actual app HTTP, actual ledger, fake Hermes, Node-executed client with no DOM',accepted_send_id:accepted?.send?.send_id,
  receipt_before_loss:settled?.data,trace,ledger_moved:moved,client_error:error,
  pending_preserved:h.api.loadPending(scope)?.client_key===p.client_key,status:h.api.shown.get(p.client_key)?.text,
  new_ledger_created:fs.existsSync(ledger),keys_sent:[...new Set(h.calls.filter(c=>c.method==='POST').map(c=>JSON.parse(c.body).client_key))]};
 console.log(JSON.stringify(out,null,2));
 process.exitCode=out.pending_preserved&&out.status!=='Not sent'&&out.client_error===null&&!out.new_ledger_created?0:1;
})().catch(e=>{console.error(e);process.exitCode=2;});
