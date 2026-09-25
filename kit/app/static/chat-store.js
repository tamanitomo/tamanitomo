/* Persistent Chat: the conversation's state, kept outside any view (build plan Phase 2.1).

   NOT ACTIVATED. Served only with chat_sends=Options(client=True), like chat-sends.js; the
   ordinary page never loads it. Load order: chat-store.js, chat-sends.js, chat-view.js,
   chat-controller.js.

   One state per installation/profile scope: history rows (from the trusted Phase 1A
   /api/chat/snapshot and /api/chat/history, keyed by their opaque message_id), the keyed
   sends' presentation (status, stream snapshot, replies), source-identity links (a history
   row is one of a send's parts only by its session + Hermes row id, or the read's own
   correlation.send_id, never by text), typing/can-send/hint, an in-session "new reply"
   flag, each view kind's scroll anchor, and which session a new message continues. The
   editable draft stays where it always was: this tab's sessionStorage.

   Views (chat-view.js) subscribe and render; chat-sends.js publishes through `present`.
   Nothing here fetches. */
(function(){
'use strict';
if(!document.querySelector('meta[name="tamanitomo-chat-sends"][content="keyed"]'))return;

const HINT='Enter to send · Shift+Enter for a new line';
const scopeId=s=>s.installation+'\u0000'+s.profile;
const sourceKey=(session,message)=>String(session)+'\u0000'+String(message);
const states=new Map();
const listeners=new Set();
let view=null;                   // the one mounted view: {kind, scope, composer(), visible()}

function blank(scope){
  return {scope,gen:0,rows:[],cursor:null,history:'idle',older:'idle',start:false,
    links:new Map(),intents:new Map(),typing:false,canSend:true,hint:HINT,unseen:false,
    auth:'ok',scroll:{},seq:0,projection:null,stale:null,
    // Which session a NEW message continues: 'unknown' until checked, then 'current' (an
    // eligible session), 'new' (the first message starts one), 'ineligible' (the saved one
    // can no longer be continued; the owner chooses) or 'unavailable' (not checked).
    session:{state:'unknown',id:null,suggestion:null}};
}
function state(scope){
  let s=states.get(scopeId(scope));
  if(!s){s=blank(scope);states.set(scopeId(scope),s);}
  return s;
}
const now=()=>({installation:INSTALLATION,profile:PROFILE||'default'});
const isCurrent=s=>s.installation===INSTALLATION&&s.profile===(PROFILE||'default');

/* Notifications are batched to one per task: a burst of updates is one render. */
let queued=false;
function changed(scope){
  state(scope).seq++;
  if(queued)return;
  queued=true;
  queueMicrotask(()=>{queued=false;for(const fn of [...listeners]){try{fn();}catch(e){console.error(e);}}});
}
function subscribe(fn){listeners.add(fn);return ()=>listeners.delete(fn);}

/* ------------------------------------------------------------------ drafts */
const draftKey=s=>'chat-draft-'+s.installation+'-'+s.profile;
const draft={
  get(scope){try{return sessionStorage.getItem(draftKey(scope))||'';}catch(_){return '';}},
  set(scope,text){try{sessionStorage.setItem(draftKey(scope),text);}catch(_){}},
};

/* ---------------------------------------------------------- continuation */
/* The tab's saved choice, per scope: {session: id|null, fresh: bool}. `fresh` records the
   owner's explicit "Start a new session"; no saved entry means nothing was chosen yet. */
const selectionKey=s=>'chat-continuation-'+s.installation+'-'+s.profile;
const selection={
  get(scope){try{const v=JSON.parse(sessionStorage.getItem(selectionKey(scope))||'null');
    return v&&typeof v==='object'?{session:typeof v.session==='string'&&v.session?v.session:null,fresh:v.fresh===true}:null;}
    catch(_){return null;}},
  set(scope,v){try{sessionStorage.setItem(selectionKey(scope),JSON.stringify({session:v.session||null,fresh:v.fresh===true}));}catch(_){}},
};

/* ------------------------------------------------------------------ history */
/* View identity is the read's opaque message_id; equal text is never merged. Source
   identity (session + Hermes row id) is kept beside it only to reconcile a send's parts. */
const rowKey=m=>'m:'+m.message_id;
const sourceOf=r=>r.session!=null&&r.source_message!=null?sourceKey(r.session,r.source_message):null;

function normalise(rows){
  return (rows||[]).filter(m=>m&&m.message_id).map(m=>({...m,_key:rowKey(m)}));
}
/* A row the read itself correlates with a send this page knows (correlation.send_id,
   computed on the server under the current binding) is linked like a settled result. */
function linkCorrelated(s,rows){
  for(const r of rows){
    const c=r.correlation,src=sourceOf(r);
    if(!c||!c.send_id||!src||s.links.has(src))continue;
    const it=[...s.intents.values()].find(i=>i.sendId===c.send_id);
    if(it)s.links.set(src,{sendId:c.send_id,key:it.key,part:c.send_part||''});
  }
}
/* The newest page, read from `since` (performance.now() when its request started). The
   first load takes it as is; a later one replaces the loaded tail from its oldest row on
   (edits, deletions and new rows in that window), or everything when it does not reach
   back to what is loaded. Sends that had settled before the read began are retired: the
   recorded history is the conversation again, exactly as a fresh Chat page used to show
   it. A send still pending is never retired; if its own source ids do not yet name its
   row, the page may already hold that row, so it is presented as the labelled request
   status (the C3 B1 treatment) until it settles; nothing is matched by text. */
function newest(scope,page,since=Infinity){
  const s=state(scope);
  const rows=normalise(page.messages);
  // A different projection (rebuilt: new ids, old cursors refused) or a resync replaces all.
  const whole=s.history!=='ready'||page.reset||page.projection!==s.projection;
  const at=!whole&&rows.length?s.rows.findIndex(r=>r._key===rows[0]._key):-1;
  if(whole||at<0){s.rows=rows;s.cursor=page.next_cursor||null;s.start=!s.cursor;}
  else s.rows=[...s.rows.slice(0,at),...rows];
  s.projection=page.projection;
  linkCorrelated(s,rows);
  s.stale=null;
  for(const [key,it] of s.intents){
    if(it.settled&&it.settledAt<=since)s.intents.delete(key);
    else if(!it.settled&&rows.length&&!linkedRow(s,it.sendId,'owner'))it.request=true;
  }
  s.history='ready';
  changed(scope);
}
function older(scope,page){
  const s=state(scope);
  const known=new Set(s.rows.map(r=>r._key));
  const rows=normalise(page.messages).filter(r=>!known.has(r._key));
  s.rows=[...rows,...s.rows];
  s.cursor=page.next_cursor||null;s.start=!s.cursor;
  linkCorrelated(s,rows);
  changed(scope);
}
/* Cached server content is usable only within its read generation. Invalidating it
   preserves the owner's editable draft and exact pending intent, not fetched replies. */
function invalidateHistory(scope){
  const s=state(scope);
  s.rows=[];s.links.clear();s.cursor=null;s.projection=null;s.start=false;
  s.history='loading';s.older='idle';s.stale=null;
  for(const [key,it] of s.intents){
    if(it.settled)s.intents.delete(key);
    else{it.stream=null;it.replies=null;it.request=true;}
  }
  changed(scope);
}
function set(scope,values){Object.assign(state(scope),values);changed(scope);}

/* ------------------------------------------------ what chat-sends.js publishes */
function intent(scope,p){
  const s=state(scope);
  let it=s.intents.get(p.client_key);
  if(!it){
    it={key:p.client_key,sendId:null,message:p.message,status:null,request:false,stream:null,
        replies:null,partial:false,confirm:null,at:null,settled:false};
    s.intents.set(p.client_key,it);
  }
  if(p.send_id)it.sendId=p.send_id;
  return it;
}
/* The loaded history row that is this send's `part`, if any (source identity only). */
function linkedRow(s,sendId,part){
  if(!sendId)return null;
  for(const r of s.rows){const l=s.links.get(sourceOf(r));if(l&&l.sendId===sendId&&l.part===part)return r;}
  return null;
}
const mounted=scope=>view&&isCurrent(scope)&&scopeId(view.scope)===scopeId(scope)?view:null;

const present={
  status(scope,p,st){const it=intent(scope,p);it.status=st;it.confirm=null;changed(scope);},
  stream(scope,p,text){
    const s=state(scope),it=intent(scope,p);
    if(!p.send_id||it.replies||linkedRow(s,p.send_id,'reply:0'))return;   // a reply is already presented
    if(it.stream===text)return;
    it.stream=text;changed(scope);
  },
  dropStream(scope,p){const it=intent(scope,p);if(it.stream!==null){it.stream=null;changed(scope);}},
  replies(scope,p,replies,{partial=false}={}){
    const it=intent(scope,p);
    it.replies=replies.map(r=>({content:r.content||'',attachments:r.attachments||[]}));
    it.partial=partial;it.stream=null;it.at=new Date();
    changed(scope);
  },
  typing(scope,on){const s=state(scope);if(s.typing!==!!on){s.typing=!!on;changed(scope);}},
  canSend(scope,on){const s=state(scope);if(s.canSend!==!!on){s.canSend=!!on;changed(scope);}},
  hint(scope,text){const s=state(scope);s.hint=text;s.hintSeq=(s.hintSeq||0)+1;changed(scope);},  // said again = shown again
  confirm(scope,p,value){intent(scope,p).confirm=value;changed(scope);},
  request(scope,p){intent(scope,p).request=true;changed(scope);},
  promote(scope,p){const it=state(scope).intents.get(p.client_key);if(it&&it.request){it.request=false;changed(scope);}},
  settled(scope,p){const it=state(scope).intents.get(p.client_key);if(it){it.settled=true;it.settledAt=performance.now();}},
  link(scope,p,source,part){
    if(!source||source.session==null||source.message==null||!p.send_id)return;
    state(scope).links.set(sourceKey(source.session,source.message),{sendId:p.send_id,key:p.client_key,part});
    changed(scope);
  },
  /* Whether this intent already has an owner presentation in this page: its own, or the
     history row its source ids name. A restored one that has neither is a request status. */
  ownerPresented(scope,p){
    const s=state(scope);
    return s.intents.has(p.client_key)||Boolean(linkedRow(s,p.send_id,'owner'));
  },
  composer(scope){return mounted(scope)?.composer()||null;},
  /* A message that was definitely not accepted goes back to the draft, never over a newer one. */
  offerDraft(scope,message){
    if(!isCurrent(scope))return false;
    const box=present.composer(scope);
    if(box?box.value.trim():draft.get(scope).trim())return false;
    draft.set(scope,message);
    if(box){box.value=message;box.dispatchEvent(new Event('input'));}
    return true;
  },
  /* A reply that arrived while no view showed this conversation. */
  arrived(scope){
    if(mounted(scope)?.visible())return;
    const s=state(scope);if(!s.unseen){s.unseen=true;changed(scope);}
  },
  signedOut(scope){set(scope,{auth:'expired'});},
  signedIn(scope){if(state(scope).auth!=='ok')set(scope,{auth:'ok'});},
  /* Continuation (chosen before an intent exists; a pending intent's session never changes). */
  selection(scope){return selection.get(scope);},
  choose(scope,v){selection.set(scope,v);},
  session(scope,v){set(scope,{session:{state:v.state,id:v.id||null,suggestion:v.suggestion||null}});},
  /* A completed keyed send's session becomes the tab's current selection. */
  continued(scope,session){
    if(!session)return;
    selection.set(scope,{session});
    set(scope,{session:{state:'current',id:session,suggestion:null}});
  },
  /* Acceptance refused the session as unauthorised: the saved choice is no longer eligible.
     Nothing switches by itself; the owner chooses (chat-view.js renders the choice). */
  sessionRefused(scope,session){
    const saved=selection.get(scope);
    if(session&&saved&&saved.session===session)set(scope,{session:{state:'ineligible',id:session,suggestion:null}});
  },
};

/* The owner's choice after an ineligible saved session: a new session, or a suggested one. */
function chooseSession(scope,which){
  const s=state(scope);
  if(which==='new'){
    selection.set(scope,{session:null,fresh:true});
    s.session={state:'new',id:null,suggestion:null};
    s.hint='Your next message starts a new session.';s.hintSeq=(s.hintSeq||0)+1;
  }else if(which==='suggested'&&s.session.suggestion){
    selection.set(scope,{session:s.session.suggestion.session});
    s.session={state:'current',id:s.session.suggestion.session,suggestion:null};
    s.hint=HINT;s.hintSeq=(s.hintSeq||0)+1;
  }else return;
  changed(scope);
}

window.ChatStore={HINT,state,now,isCurrent,subscribe,changed,draft,newest,older,set,present,linkedRow,sourceKey,sourceOf,
  selection,chooseSession,invalidateHistory,
  mount(v){view=v;},unmount(v){if(view===v)view=null;},get view(){return view;}};
})();
