/* Keyed workspace sends: the Phase 1B C3 client (PHASE1B_DESIGN.md section 6).

   NOT ACTIVATED. The server references this file only when it is built with
   chat_sends=Options(client=True) (kit/app/server.py), which no shipped entry point
   does, and it is not in release-files.json. The page then carries
   <meta name="tamanitomo-chat-sends" content="keyed">; without that signal this file
   does nothing, and the ordinary workspace keeps sending through POST /api/chat.

   One send is one immutable pending intent, kept in this tab's sessionStorage beside
   (never inside) the editable draft:
     {v, client_key, generation, conversation_id, installation, profile, session,
      message, created_at, send_id?, operation_id?}
   It is written before the POST and is never changed by a transport failure or an
   edited draft; only send_id/operation_id are added once the server confirms. Every
   automatic retry is the identical POST with the same key. Nothing here ever calls
   the unkeyed /api/chat: not on a timeout, a missing route, an expired sign-in or a
   restart. A new key is minted only for an explicit owner intent (Send / Ask again /
   Send again), and after an unknown outcome only with confirmation and a receipt that
   proves the earlier execution is quiescent.

   Reads: the existing keyed routes and operation views, plus, only when a pending send
   is picked up again after a reload or a return to Chat, one GET /api/chat/snapshot
   (Phase 1A) to learn which already-drawn history rows are this send's (by their
   correlation.send_id and source ids, never by text or time). */
(function(){
'use strict';
const signal=document.querySelector('meta[name="tamanitomo-chat-sends"]');
if(!signal||signal.content!=='keyed')return;

const CROCKFORD='0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const BACKOFF=[500,1000,2000,4000,8000];     // then every LATER ms, same key, while the page lives
const LATER=30000,POLL=350,POLL_MAX=5000,POST_TIMEOUT=20000;
// Refusals that prove the request was NOT accepted (PHASE1B_DESIGN.md 5.1, 5.2).
const NOT_ACCEPTED=new Set(['turn_in_progress','installation_busy','ledger_busy','key_conflict','key_expired',
  'send_storage_unsupported','send_supervision_unavailable','send_ledger_lost','invalid_client_key']);
const WORDS={
  sending:'sending…',
  checking:'Checking with the app…',
  replying:'Replying…',
  notSent:'Not sent',
  notConfirmed:'Not confirmed. The app will check again with the same request.',
  failedRecorded:'Your message was recorded; the reply failed',
  failedUnknown:'The reply failed. Whether your message was recorded is unknown.',
  stopped:'Stopped',
  unknown:'The app accepted your request. Whether Hermes recorded it or finished a reply is unknown.',
  reset:'The app’s send records were reset. Whether this message was sent before the reset is unknown.',
  signedOut:'Your sign-in ended. Sign in again, and the app will check this message with the same request.',
  hidden:'This message’s record is not visible from here.',
  otherConversation:'An earlier message belongs to a different conversation record here. It was left untouched.',
  storage:'Not sent: this browser could not keep a safe record of the message. Your draft is kept.',
  duplicate:'This may send your message twice.',
  stillRunning:'The earlier attempt is still running or not yet proven finished. Wait, then try again.',
  wait:'Wait for the current action to finish.',
  onePending:'An earlier message is still being sent.',
};

const boots=new Map();          // scope id -> {conversation_id, generation}
const drivers=new Set();        // client keys with a running driver in this page
const shown=new Map();          // client key -> last painted {text, actions, bad}
let submitting=false;

function scopeNow(){return {installation:INSTALLATION,profile:PROFILE||'default'};}
const scopeId=s=>s.installation+'\u0000'+s.profile;
const isCurrent=s=>s.installation===INSTALLATION&&s.profile===(PROFILE||'default');
const pendingKey=s=>'chat-pending-'+s.installation+'-'+s.profile;
const draftKey=s=>'chat-draft-'+s.installation+'-'+s.profile;
const chatVisible=s=>isCurrent(s)&&current==='chat'&&$('chat-log');

function ulid(){
  const random=new Uint8Array(10);crypto.getRandomValues(random);
  let v=BigInt(Date.now());for(const b of random)v=(v<<8n)|BigInt(b);
  let out='';for(let i=0;i<26;i++){out=CROCKFORD[Number(v&31n)]+out;v>>=5n;}
  return out;
}

/* Every request carries the scope it was captured for, never the page's current one. */
async function call(scope,path,{method='GET',body,timeout=POST_TIMEOUT}={}){
  const u=new URL('/api'+path,location.origin);
  u.searchParams.set('installation',scope.installation);u.searchParams.set('profile',scope.profile);
  const headers={'content-type':'application/json'};
  if(token){headers['x-tamanitomo-token']=token;headers['x-companion-token']=token;}
  const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),timeout);
  try{
    const r=await fetch(u.pathname+u.search,{method,headers,cache:'no-store',signal:ctl.signal,
      body:body===undefined?undefined:JSON.stringify(body)});
    let data=null;try{data=await r.json();}catch(_){data=null;}
    return {status:r.status,data};
  }catch(_){return {status:0,data:null};}
  finally{clearTimeout(timer);}
}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function loadPending(scope){
  try{const raw=sessionStorage.getItem(pendingKey(scope));return raw?JSON.parse(raw):null;}catch(_){return null;}
}
function savePending(scope,p){
  const raw=JSON.stringify(p);
  try{sessionStorage.setItem(pendingKey(scope),raw);return sessionStorage.getItem(pendingKey(scope))===raw;}
  catch(_){return false;}
}
function clearPending(scope,p){
  const stored=loadPending(scope);
  if(stored&&stored.client_key===p.client_key){try{sessionStorage.removeItem(pendingKey(scope));}catch(_){}}
}
/* send_id/operation_id are the only fields ever added; the intent itself never changes. */
function withIds(p,send){
  if(p.send_id&&p.send_id!==send.send_id)throw Error('A different send answered this key.');
  return {...p,send_id:send.send_id,operation_id:send.operation?.id||p.operation_id};
}

async function bootstrap(scope,fresh=false){
  if(!fresh&&boots.has(scopeId(scope)))return {ok:true,...boots.get(scopeId(scope))};
  const r=await call(scope,'/chat/sends/bootstrap');
  if(r.status===200&&r.data&&r.data.generation){boots.set(scopeId(scope),r.data);return {ok:true,...r.data};}
  return {ok:false,status:r.status,code:r.data?.error};
}

/* ------------------------------------------------------------------ painting */

const ownerId=p=>p.send_id?p.send_id+':owner':'pending-'+p.client_key+':owner';
function ownerEl(p){
  const log=$('chat-log');if(!log)return null;
  return $(ownerId(p))||log.querySelector(`[data-client-key="${CSS.escape(p.client_key)}"]`);
}
function paintOwner(scope,p){
  if(!chatVisible(scope))return null;
  let el=ownerEl(p);
  if(!el){
    const log=$('chat-log');log.querySelector('.chat-welcome')?.remove();
    log.insertAdjacentHTML('beforeend',`<div class="bubble user sending" data-channel="desktop">
      <div class="message-body">${richText(p.message)}</div>
      <small><span class="bubble-status">${esc(WORDS.sending)}</span></small></div>`);
    el=log.lastElementChild;
    log.scrollTo({top:log.scrollHeight,behavior:'smooth'});
  }
  el.dataset.clientKey=p.client_key;el.id=ownerId(p);
  return el;
}
function paintStatus(scope,p,text,{bad=false,sent=false,actions=[]}={}){
  shown.set(p.client_key,{text,bad,sent,actions});
  const el=paintOwner(scope,p);if(!el)return;
  el.classList.toggle('sending',!sent&&!bad);el.classList.toggle('send-error',bad);
  let small=el.querySelector(':scope > small');
  if(!small){el.insertAdjacentHTML('beforeend','<small></small>');small=el.querySelector(':scope > small');}
  small.innerHTML=`<span class="bubble-status">${bad?`<span class="bad">${esc(text)}</span>`:esc(text)}</span>`+
    actions.map((a,i)=>` <button type="button" class="quiet small" data-keyed-action="${i}">${esc(a.label)}</button>`).join('');
  small.querySelectorAll('[data-keyed-action]').forEach(b=>{b.onclick=()=>actions[Number(b.dataset.keyedAction)].run(b);});
}
function paintStream(scope,p,text){
  if(!chatVisible(scope)||!p.send_id||$(p.send_id+':reply:0'))return;   // a reply row is already presented
  const log=$('chat-log'),follow=log.scrollHeight-log.scrollTop-log.clientHeight<100;
  let live=$(p.send_id+':stream');
  if(!live){
    $('chat-typing-indicator')?.remove();
    log.insertAdjacentHTML('beforeend',`<div class="bubble" aria-label="Incoming reply"><div class="message-body"></div></div>`);
    live=log.lastElementChild;live.id=p.send_id+':stream';
  }
  live.querySelector('.message-body').textContent=text;     // a snapshot: replaces, never appends
  if(follow)log.scrollTop=log.scrollHeight;
}
function paintReplies(scope,p,replies,{partial=false}={}){
  if(!chatVisible(scope))return;
  const log=$('chat-log');
  const stream=$(p.send_id+':stream');
  replies.forEach((reply,n)=>{
    const id=p.send_id+':reply:'+n;
    if($(id))return;                                   // already presented (history or earlier paint)
    const {text,extractedMedia}=extractMediaFromContent(reply.content||'');
    if(!text&&!extractedMedia.length)return;
    const html=`<div class="bubble animate-in${partial?' partial':''}" data-channel="desktop">
      <div class="message-body">${richText(text)}</div>${extractedMedia.map(inlineMedia).join('')}
      <small>${partial?'<span class="dim">Partial reply</span> ':''}${esc(new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}</small></div>`;
    if(stream&&n===0){stream.insertAdjacentHTML('afterend',html);stream.nextElementSibling.id=id;}
    else{log.insertAdjacentHTML('beforeend',html);log.lastElementChild.id=id;}
  });
  stream?.remove();
  log.scrollTo({top:log.scrollHeight,behavior:'smooth'});
}
function composer(scope,enabled){
  if(!chatVisible(scope))return;
  const b=$('send-message');if(b)b.disabled=!enabled;
  const box=$('chat-message');if(box)box.readOnly=false;       // drafting never waits for a send
}
function hint(scope,text){if(chatVisible(scope)&&$('chat-status'))$('chat-status').textContent=text;}
/* A message that was definitely not accepted goes back to the box, never over a newer draft. */
function offerBack(scope,message){
  if(!chatVisible(scope))return false;
  const box=$('chat-message');if(!box||box.value.trim())return false;
  box.value=message;try{sessionStorage.setItem(draftKey(scope),message);}catch(_){}
  box.dispatchEvent(new Event('input'));
  return true;
}
function settle(scope,p){
  clearPending(scope,p);
  if(activeOperation==='chat-send:'+p.client_key)activeOperation=null;
  if(chatVisible(scope)){showTyping(false);voiceControlsBusy(false);}
  composer(scope,true);
  hint(scope,'Enter to send · Shift+Enter for a new line');
}

/* ------------------------------------------------------------------ sending */

async function startIntent(scope,message,{box=null,grow=null}={}){
  if(submitting)return;                                 // a second click or Enter while this one starts
  if(loadPending(scope)){hint(scope,WORDS.onePending);return;}
  if(activeOperation){hint(scope,WORDS.wait);return;}
  submitting=true;composer(scope,false);
  let started=false;
  try{
    const boot=await bootstrap(scope,true);
    if(!isCurrent(scope))return;
    if(!boot.ok){hint(scope,WORDS.notSent+(boot.status===0?': the app could not be reached.':'.')+' Your draft is kept.');return;}
    const p={v:1,client_key:ulid(),generation:boot.generation,conversation_id:boot.conversation_id,
             installation:scope.installation,profile:scope.profile,session:chatSession||null,
             message,created_at:Date.now()};
    if(!savePending(scope,p)){hint(scope,WORDS.storage);return;}
    started=true;
    activeOperation='chat-send:'+p.client_key;
    if(box&&box.value===message){box.value='';try{sessionStorage.setItem(draftKey(scope),'');}catch(_){}grow?.();}
    paintStatus(scope,p,WORDS.sending);
    if(chatVisible(scope))showTyping(true);   // the box stays editable: a newer draft is the owner's
    drive(scope,p);
  }finally{submitting=false;if(!started&&!loadPending(scope))composer(scope,true);}
}

async function drive(scope,p){
  if(drivers.has(p.client_key))return;
  drivers.add(p.client_key);
  try{
    if(!p.send_id){p=await acquire(scope,p);if(!p)return;}
    await follow(scope,p);
  }catch(error){
    // A client bug is not an outcome: keep the intent, say nothing untrue.
    paintStatus(scope,p,WORDS.notConfirmed,{actions:[checkAgain(scope,p)]});
    console.error(error);
  }finally{drivers.delete(p.client_key);}
}
const checkAgain=(scope,p)=>({label:'Check now',run:()=>drive(scope,loadPending(scope)||p)});

/* Until the server confirms acceptance: the identical POST, then lookups by the same key. */
async function acquire(scope,p){
  const body={client_key:p.client_key,generation:p.generation,conversation_id:p.conversation_id,
              message:p.message,session:p.session};
  for(let attempt=0;;attempt++){
    if(!isCurrent(scope))return null;
    const r=await call(scope,'/chat/sends',{method:'POST',body});
    const code=r.data?.error;
    if((r.status===202||r.status===200)&&r.data?.send?.send_id)return adopt(scope,p,r.data.send,r.data);
    if(r.status===401){paintStatus(scope,p,WORDS.signedOut,{bad:true,actions:[checkAgain(scope,p)]});return null;}
    if(r.status===409&&code==='generation_changed'){resetOutcome(scope,p);return null;}
    if(r.status===409&&code==='not_bootstrapped'){boots.delete(scopeId(scope));notSent(scope,p);return null;}
    if(NOT_ACCEPTED.has(code)||r.status===400||r.status===422){notSent(scope,p,code);return null;}
    // Uncertain (no answer, a lost or unreadable body, a missing route, a gateway error):
    // ask by the same key. A 404 there is NOT permission for a new key: the POST may be in flight.
    const found=await call(scope,'/chat/sends?key='+encodeURIComponent(p.client_key));
    if(found.status===200&&found.data?.send_id)return adopt(scope,p,found.data,null);
    if(found.status===401){paintStatus(scope,p,WORDS.signedOut,{bad:true,actions:[checkAgain(scope,p)]});return null;}
    const exhausted=attempt>=BACKOFF.length;
    paintStatus(scope,p,exhausted?WORDS.notConfirmed:WORDS.checking,exhausted?{actions:[checkAgain(scope,p)]}:{});
    await sleep(exhausted?LATER:BACKOFF[attempt]);
  }
}

function adopt(scope,p,send,body){
  const q=withIds(p,send);
  savePending(scope,q);          // best effort: the server holds the receipt either way
  paintStatus(scope,q,WORDS.sending);
  if(body&&body.rearm==='expired'){notSent(scope,q,'not_started');return null;}
  return q;
}

/* Polls the existing operation view (a view of the ledger), then the receipt until settled. */
async function follow(scope,p){
  let wait=POLL,view=null;
  while(true){
    if(!isCurrent(scope))return;
    const r=await call(scope,'/operations/'+p.operation_id,{timeout:15000});
    if(r.status===401){paintStatus(scope,p,WORDS.signedOut,{bad:true,actions:[checkAgain(scope,p)]});return;}
    if(r.status===200&&r.data){
      view=r.data;wait=POLL;
      if(view.status==='running'){
        if(view.stream?.available)paintStream(scope,p,view.stream.text);
        paintStatus(scope,p,view.progress==='Replying'?WORDS.replying:WORDS.sending);
        await sleep(POLL);continue;
      }
      break;
    }
    if(r.status===404||r.status===400){view=null;break;}
    await sleep(wait);wait=Math.min(wait*2,POLL_MAX);  // transport or server error: same view, later
  }
  let receipt=view?.send||null;
  if(!view){
    const r=await call(scope,'/chat/sends/'+encodeURIComponent(p.send_id));
    if(r.status===401){paintStatus(scope,p,WORDS.signedOut,{bad:true,actions:[checkAgain(scope,p)]});return;}
    if(r.status!==200){paintStatus(scope,p,WORDS.hidden,{bad:true});settle(scope,p);return;}
    receipt=r.data;
  }
  wait=POLL;
  while(receipt&&receipt.settled===false){             // an outcome while the lease is still held
    paintStatus(scope,p,receipt.state==='unknown'?WORDS.unknown:WORDS.checking);
    await sleep(wait);wait=Math.min(wait*2,POLL_MAX);
    if(!isCurrent(scope))return;
    const r=await call(scope,'/chat/sends/'+encodeURIComponent(p.send_id));
    if(r.status===401){paintStatus(scope,p,WORDS.signedOut,{bad:true,actions:[checkAgain(scope,p)]});return;}
    if(r.status===200)receipt=r.data;
  }
  finish(scope,p,view,receipt||{state:'unknown'});
}

function finish(scope,p,view,receipt){
  const result=view?.result||{};
  const byId=new Map((result.messages||[]).map(m=>[m.message_id,m]));
  let replies=(receipt.reply_message_ids||[]).map(id=>byId.get(id)).filter(Boolean);
  if(!replies.length&&result.response)replies=[{content:result.response}];
  if(result.session&&isCurrent(scope)){chatSession=result.session;try{sessionStorage.setItem(chatKey('session'),chatSession);}catch(_){}}
  const at=new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
  const state=receipt.state;
  settle(scope,p);
  if(receipt.owner_message_id)adoptRow(scope,p,byId.get(receipt.owner_message_id)?.source,'owner');
  (receipt.reply_message_ids||[]).forEach((id,n)=>adoptRow(scope,p,byId.get(id)?.source,'reply:'+n));
  if(state==='complete'){
    paintStatus(scope,p,at,{sent:true});paintReplies(scope,p,replies);
    if(!chatVisible(scope)&&isCurrent(scope))notice('Reply received from '+chatName()+'. Open Chat to read it.');
    if(typeof speakBrowserReply==='function')speakBrowserReply(result);
    return;
  }
  $(p.send_id+':stream')?.remove();
  if(state==='interrupted'){paintStatus(scope,p,WORDS.stopped,{bad:true});paintReplies(scope,p,replies,{partial:true});return;}
  if(state==='failed'){
    if(receipt.owner_turn==='recorded')
      paintStatus(scope,p,WORDS.failedRecorded,{bad:true,actions:[{label:'Ask again',run:()=>startIntent(scope,p.message)}]});
    else paintStatus(scope,p,WORDS.failedUnknown,{bad:true});
    return;
  }
  if(state==='not_started'){notSent(scope,p,'not_started');return;}
  const quiet=['quiescent','none'].includes(receipt.liveness);
  paintStatus(scope,p,WORDS.unknown,{bad:true,actions:quiet?[sendAgain(scope,p,true)]:[]});
}

function notSent(scope,p,code){
  settle(scope,p);
  const back=offerBack(scope,p.message);
  const why=code==='turn_in_progress'?' Another reply is still running.':code==='installation_busy'?' Another action is running.':'';
  paintStatus(scope,p,WORDS.notSent,{bad:true});
  hint(scope,WORDS.notSent+'.'+why+(back?' Your message is back in the box.':' Your newer draft was kept.'));
}

function resetOutcome(scope,p){
  boots.delete(scopeId(scope));
  settle(scope,p);
  paintStatus(scope,p,WORDS.reset,{bad:true,actions:[sendAgain(scope,p,false)]});
}

/* "Send again": a NEW intent (new key, current generation), after the owner confirms the
   duplicate risk and, when there is a receipt, after it still proves quiescence. */
function sendAgain(scope,p,hasReceipt){
  return {label:'Send again',run:button=>{
    const small=button.parentElement;
    small.querySelectorAll('.keyed-confirm').forEach(x=>x.remove());
    small.insertAdjacentHTML('beforeend',`<span class="keyed-confirm"> ${esc(WORDS.duplicate)}
      <button type="button" class="quiet small" data-confirm="yes">Send anyway</button>
      <button type="button" class="quiet small" data-confirm="no">Cancel</button></span>`);
    small.querySelector('[data-confirm="no"]').onclick=()=>small.querySelector('.keyed-confirm')?.remove();
    small.querySelector('[data-confirm="yes"]').onclick=async()=>{
      small.querySelector('.keyed-confirm')?.remove();
      if(hasReceipt){
        const r=await call(scope,'/chat/sends/'+encodeURIComponent(p.send_id));
        if(r.status!==200||r.data.state!=='unknown'||!['quiescent','none'].includes(r.data.liveness)){hint(scope,WORDS.stillRunning);return;}
      }
      startIntent(scope,p.message);
    };
  }};
}

/* ------------------------------------------------------------------ recovery */

/* A history row that is one of this send's rows takes over that part's DOM id, and a
   provisional owner bubble for the same row is removed: one presentation per row. The
   match is by source identity (session + Hermes row id) only, never by text or time. */
function adoptRow(scope,p,source,part){
  if(!chatVisible(scope)||!source)return;
  const el=$('chat-log').querySelector(`[data-source-session="${CSS.escape(String(source.session))}"][data-source-message="${CSS.escape(String(source.message))}"]`);
  if(!el)return;
  if(part==='owner'){
    const mine=ownerEl(p);
    if(mine&&mine!==el)mine.remove();
    el.id=p.send_id+':owner';el.dataset.clientKey=p.client_key;
  }else if(part.startsWith('reply:')){$(p.send_id+':'+part)?.remove();el.id=p.send_id+':'+part;}
}
/* On return to Chat: rows the Phase 1A snapshot already correlates with this send. Links are
   recorded when a send settles (C1), so mid-turn this finds nothing; finish() repeats the
   match from the settled result. */
async function reconcile(scope,p){
  if(!p.send_id||!chatVisible(scope))return;
  const r=await call(scope,'/chat/snapshot?limit=50');
  if(r.status!==200||!chatVisible(scope))return;
  for(const m of r.data?.messages||[])
    if(m.correlation?.send_id===p.send_id)adoptRow(scope,p,m.source,m.correlation.send_part||'');
}

async function attach(){
  const scope=scopeNow();
  const p=loadPending(scope);
  if(!p)return;
  if(p.installation!==scope.installation||p.profile!==scope.profile)return;   // never another scope's
  composer(scope,false);
  activeOperation='chat-send:'+p.client_key;
  const boot=await bootstrap(scope);
  if(boot.ok&&boot.conversation_id!==p.conversation_id){
    activeOperation=null;
    hint(scope,WORDS.otherConversation);
    return;
  }
  let q=p;
  if(!q.send_id&&!drivers.has(q.client_key)){
    const found=await call(scope,'/chat/sends?key='+encodeURIComponent(q.client_key));
    if(found.status===200&&found.data?.send_id){q=withIds(q,found.data);savePending(scope,q);}
  }
  await reconcile(scope,q);
  const last=shown.get(q.client_key);
  paintStatus(scope,q,last?.text||WORDS.checking,last||{});
  if(chatVisible(scope)&&!last?.sent)showTyping(true);
  drive(scope,q);
}

window.KeyedChat={
  submit:(box,grow)=>{const message=box.value;if(!message.trim())return;return startIntent(scopeNow(),message,{box,grow});},
  attach,
};
})();
