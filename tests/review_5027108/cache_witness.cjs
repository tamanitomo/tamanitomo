'use strict';
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert/strict');
const {performance}=require('perf_hooks');
const [repo,base,home,mode]=process.argv.slice(2);
const scope={installation:'existing',profile:'nova'};
const storage=new Map(),calls=[];
const ctx={console,performance,URL,Map,Set,Date,JSON,setTimeout,clearTimeout,queueMicrotask,
  INSTALLATION:'existing',PROFILE:'nova',token:'c3-synthetic-token',current:'chat',
  location:{origin:base},workspaceHandlers:{chat:async()=>{}},
  sessionStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},
  document:{querySelector:()=>({content:'keyed'})},$:()=>null,
  KeyedChat:{words:{},attach:async()=>{},continuation:async()=>null},
  fetch:async(u,opts)=>{const r=await fetch(new URL(u,base),opts);const data=await r.clone().json();
    calls.push({path:new URL(u,base).pathname,status:r.status,error:data.error||null,projection:data.projection_id||null});return r;},
  richText:s=>s,extractMediaFromContent:s=>({text:s,extractedMedia:[]}),
};ctx.window=ctx;vm.createContext(ctx);
for(const name of ['chat-store.js','chat-view.js','chat-controller.js'])vm.runInContext(fs.readFileSync(path.join(repo,'kit/app/static',name),'utf8'),ctx,{filename:name});
(async()=>{
 const S=ctx.ChatStore,P=ctx.PersistentChat;
 await P.loadNewest(scope);
 const marker='Morning! On the train again.';
 assert(S.state(scope).rows.some(r=>r.content===marker),'initial trusted Telegram row must be loaded');
 S.draft.set(scope,'Keep this newer draft');
 const pending={client_key:'witness-key',session:'term',message:'Keep exact pending intent'};
 storage.set('chat-pending-existing-nova',JSON.stringify(pending));
 let moved=false;
 try{
  // Actual name supplied by fixture, not an invented binding path.
  if(mode!=='outage_only')fs.writeFileSync(process.env.WITNESS_BINDING_PATH,JSON.stringify({telegram:[]}));
  if(mode!=='revocation_success'){
   fs.renameSync(path.join(home,'state.db'),path.join(home,'state.db.review-backup'));moved=true;
  }
  if(mode==='invalidated_outage'){
   await P.loadOlder(scope);
   for(let i=0;i<100;i++){if(S.state(scope).stale||S.state(scope).history==='error')break;await new Promise(r=>setTimeout(r,20));}
  }else await P.loadNewest(scope);
  const s=S.state(scope),items=ctx.ChatView.items(s);
  const markerInItems=items.some(i=>i.row?.content===marker);
  console.log(JSON.stringify({mode,calls,initialMarker:true,markerRetainedInStore:s.rows.some(r=>r.content===marker),
    markerStillInRendererItems:markerInItems,history:s.history,stale:s.stale,projection:s.projection,
    pendingPreserved:storage.get('chat-pending-existing-nova')===JSON.stringify(pending),
    draftPreserved:S.draft.get(scope)==='Keep this newer draft'},null,2));
 }finally{if(moved)fs.renameSync(path.join(home,'state.db.review-backup'),path.join(home,'state.db'));}
})().catch(e=>{console.error(e);process.exitCode=1;});
