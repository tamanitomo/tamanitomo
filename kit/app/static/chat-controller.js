/* Persistent Chat: one conversation controller for the Chat page, the desktop dock and the
   mobile pill (build plan Phase 2; the first usable UI milestone).

   NOT ACTIVATED. Served only with chat_sends=Options(client=True), which no shipped entry
   point sets (kit/app/server.py). Without it none of these files load, and the Chat page,
   its POST /api/chat send and every other page are exactly as before. Removing the option
   removes the milestone: no data is migrated, and the draft and pending intent keep their
   existing sessionStorage keys.

   What it owns:
   - the keyed send client (chat-sends.js), attached once per page load rather than per
     Chat view, so a reply keeps arriving whichever page is open;
   - reads of the trusted Phase 1A contract (docs/CHAT_CONTRACT.md section 4):
     /api/chat/snapshot for the newest page, /api/chat/history for older pages, through a
     small adapter to the row shape the renderer already draws. Once, then refreshed when
     the Chat page opens with nothing pending. The legacy /api/feed (every non-internal
     source, groups and strangers included) is no longer read by this client;
   - a continuation check when a view opens, so an ineligible saved session is shown as a
     choice before the owner sends (chat-sends.js decides again at send time);
   - which single view is mounted: the Chat page on the Chat tab, otherwise the dock (a
     bottom-right launcher and a user-opened mini chat; on a narrow screen a pill above the
     tab bar and a full-height sheet). It never opens itself and never takes focus when
     something arrives; the launcher only says so.

   Transport is the existing operation polling inside chat-sends.js (Phase 3.1 permits it). */
(function(){
'use strict';
if(!window.ChatStore||!window.ChatView||!window.KeyedChat)return;
const S=window.ChatStore;

let started=false,pageView=null,dockView=null,dockOpen=false,focusPage=false;

/* Reads carry the scope they were captured for, never the page's current one. */
async function read(scope,path){
  const u=new URL('/api'+path,location.origin);
  u.searchParams.set('installation',scope.installation);u.searchParams.set('profile',scope.profile);
  const headers={};
  if(token){headers['x-tamanitomo-token']=token;headers['x-companion-token']=token;}
  const r=await fetch(u.pathname+u.search,{headers,cache:'no-store'});
  const d=await r.json().catch(()=>({}));
  // The app's own PIN lock, as api() raises it (index.html).
  if(r.status===401&&d.pin_required&&typeof showPinModal==='function'){initPinModal();showPinModal();}
  if(!r.ok){
    const e=Error(UNREADABLE[d.error]||d.detail||d.error||('Request failed: '+r.status));
    e.status=r.status;e.code=d.error;throw e;
  }
  return d;
}
const UNREADABLE={
  source_unavailable:'The conversation cannot be read right now (its source is unavailable). Nothing was changed; it will be read again when Chat reopens.',
};

/* The trusted read contract, adapted to the renderer's row shape. The opaque message_id is
   the row's identity; source ids are kept only to reconcile a send's parts. Channel labels
   follow the projection's source kind (a workspace session is drawn as the app's own, as
   the ordinary page draws a session it started). Deleted messages are never on a page. */
const CHANNEL={workspace:'tamanitomo',terminal:'terminal',telegram:'telegram'};
function adapt(page){
  const rows=(page.messages||[]).filter(m=>m&&m.message_id&&m.content!=null&&m.status!=='deleted').map(m=>({
    message_id:m.message_id,role:m.role,content:m.content,timestamp:m.occurred_at,
    attachments:m.attachments||[],correlation:m.correlation||null,
    session:m.source?.session??null,source_message:m.source?.message??null,
    source:CHANNEL[m.source?.kind]||m.source?.kind||''}));
  return {messages:rows,next_cursor:page.history?.before||null,projection:page.projection_id||null};
}
function pending(scope){
  try{if(sessionStorage.getItem('chat-pending-'+scope.installation+'-'+scope.profile))return true;}catch(_){}
  return [...S.state(scope).intents.values()].some(it=>!it.settled);
}

async function loadNewest(scope,{reset=false}={}){
  const s=S.state(scope),gen=++s.gen,since=performance.now();
  if(s.history!=='ready')S.set(scope,{history:'loading'});
  try{
    const d=adapt(await read(scope,'/chat/snapshot?limit=60'));
    if(gen!==S.state(scope).gen||!S.isCurrent(scope))return;
    S.present.signedIn(scope);
    S.newest(scope,{...d,reset},since);
  }catch(error){
    if(gen!==S.state(scope).gen||!S.isCurrent(scope))return;
    if(error.status===401)S.present.signedOut(scope);
    // A failed read is "unavailable", never an empty conversation: rows already read stay,
    // marked as read earlier.
    if(S.state(scope).history!=='ready')S.set(scope,{history:'error',historyError:error.message});
    else S.set(scope,{stale:error.message});
  }
}
async function loadOlder(scope){
  const s=S.state(scope);
  if(s.history!=='ready'||s.older==='loading'||!s.cursor)return;
  const cursor=s.cursor,gen=s.gen;
  S.set(scope,{older:'loading'});
  try{
    const d=adapt(await read(scope,'/chat/history?limit=60&before='+encodeURIComponent(cursor)));
    const now=S.state(scope);
    if(now.gen!==gen||now.cursor!==cursor||!S.isCurrent(scope)||d.projection!==now.projection){S.set(scope,{older:'idle'});return;}
    now.older='idle';
    S.older(scope,d);
  }catch(error){
    if(error.status===401)S.present.signedOut(scope);
    const now=S.state(scope);
    // The cursor is no longer valid (a rebuilt projection or an expired window): one fresh
    // snapshot replaces the rows. Drafts and pending intents are not part of this state.
    if(now.gen===gen&&S.isCurrent(scope)&&(error.code==='resync_required'||error.code==='invalid_cursor')){
      S.set(scope,{older:'idle'});
      loadNewest(scope,{reset:true});
      return;
    }
    S.set(scope,{older:'error'});
  }
}
/* Which session the next message would continue, shown before sending (an ineligible saved
   one becomes a choice; a new profile says that its first message starts a session). */
async function checkContinuation(scope){
  if(pending(scope))return;
  const pick=await KeyedChat.continuation().catch(()=>null);
  if(!pick||!S.isCurrent(scope)||pending(scope))return;
  if(pick.ok&&pick.fresh)S.present.hint(scope,KeyedChat.words.newSession);
}
function ensureHistory(scope){if(S.state(scope).history==='idle')loadNewest(scope);}

/* Once per page load: pick up this scope's pending send (after a reload) and follow it. */
function start(){
  if(started||!INSTALLATION)return;
  started=true;
  S.subscribe(syncLauncher);
  KeyedChat.attach().catch(e=>console.error(e));
}

/* ------------------------------------------------------------------ the page */

const prior=workspaceHandlers.chat;          // the ordinary handler; unused in this build
workspaceHandlers.chat=async()=>{
  start();
  const scope=S.now();
  pageView?.unmount();pageView=null;
  hideDock();
  const s=S.state(scope);
  // The shell and composer first; nothing here waits for history, feelings or portraits.
  $('chat').innerHTML=`
    <div class="chat-room">
      <div class="chat-peek" id="chat-peek">
        ${faceHtml(chatName(),'chat-peek-avatar')}
        <div class="chat-peek-copy">
          <strong>${esc(chatName())}</strong>
          <span class="dim small" id="chat-presence"> </span>
        </div>
      </div>
      <div id="chat-log" class="chat-log" role="log" aria-live="polite"></div>
      <form id="chat-form" class="chat-composer">
        <label class="sr-only" for="chat-message">Your message</label>
        <textarea rows="1" id="chat-message" placeholder="Message ${esc(chatName())}" required maxlength="30000"></textarea>
        <button class="chat-send" id="send-message" aria-label="Send">${icon('arrow_right')}</button>
      </form>
      <span class="dim small chat-hint" id="chat-status" role="status">${esc(s.hint)}</span>
    </div>`;
  pageView=new ChatView.View({kind:'page',log:$('chat-log'),form:$('chat-form'),box:$('chat-message'),
    send:$('send-message'),status:$('chat-status'),ids:true,limit:0,
    visible:()=>current==='chat',after:presence}).mount();
  pageView.watchTop(()=>loadOlder(scope));
  if(typeof mountBrowserVoice==='function')mountBrowserVoice();
  if(s.history==='idle'||!pending(scope))loadNewest(scope);
  checkContinuation(scope);
  mood(scope);
  if(focusPage){focusPage=false;$('chat-message')?.focus();}
};

/* The header says what is actually happening with a send, or the recorded mood: no
   percentages, no invented presence. */
let moodText='';
function turnText(s){
  if(s.auth==='expired')return 'Sign in again to continue';
  const live=[...s.intents.values()].filter(it=>!it.settled).at(-1);
  if(!live)return '';
  if(live.stream)return KeyedChat.words.replying;
  return live.status&&!live.status.bad?live.status.text:'';
}
function presence(s){
  const el=$('chat-presence');if(!el)return;
  const text=turnText(s)||moodText||' ';
  if(el.textContent!==text)el.textContent=text;
  el.onclick=!turnText(s)&&moodText?()=>showTab('relationship'):null;
}
async function mood(scope){
  try{
    const d=await read(scope,'/feelings');
    moodText=d?.state?.mood?String(d.state.mood):'';
  }catch(_){moodText='';}
  if(S.isCurrent(scope))presence(S.state(scope));
}

/* ------------------------------------------------------------------ the dock */

function dock(){
  let el=$('chat-dock');
  if(el)return el;
  document.body.insertAdjacentHTML('beforeend',`
    <div id="chat-dock" class="chat-dock" hidden>
      <button type="button" class="chat-dock-launcher" id="chat-dock-launcher" aria-expanded="false" aria-controls="chat-dock-panel">
        <span class="chat-dock-face"></span>
        <span class="chat-dock-copy"><strong class="chat-dock-name"></strong><span class="chat-dock-preview dim small"></span></span>
        <span class="chat-dock-dot" hidden>New reply</span>
      </button>
      <section class="chat-dock-panel" id="chat-dock-panel" role="region" hidden>
        <div class="chat-dock-bar">
          <span class="chat-dock-face"></span>
          <span class="chat-dock-copy"><strong class="chat-dock-name"></strong><span class="chat-dock-state dim small" role="status"></span></span>
          <button type="button" class="icon-button chat-dock-button" id="chat-dock-maximise" aria-label="Open the full conversation" title="Open the full conversation">⤢</button>
          <button type="button" class="icon-button chat-dock-button" id="chat-dock-minimise" aria-label="Minimise chat" title="Minimise (Esc)">–</button>
        </div>
        <div class="chat-log chat-dock-log" id="chat-dock-log" role="log" aria-live="polite"></div>
        <form class="chat-composer chat-dock-composer" id="chat-dock-form">
          <label class="sr-only" for="chat-dock-message">Your message</label>
          <textarea rows="1" id="chat-dock-message" required maxlength="30000"></textarea>
          <button class="chat-send" id="chat-dock-send" aria-label="Send">${icon('arrow_right')}</button>
        </form>
        <span class="dim small chat-dock-status" id="chat-dock-status" role="status"></span>
      </section>
    </div>`);
  el=$('chat-dock');
  $('chat-dock-launcher').onclick=()=>openDock();
  $('chat-dock-minimise').onclick=()=>minimise();
  $('chat-dock-maximise').onclick=()=>maximise();
  $('chat-dock-panel').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();minimise();}});
  return el;
}
function available(){
  return started&&current!=='chat'&&Boolean(roster.find(p=>p.id===PROFILE)?.installed);
}
function syncDock(){
  const el=dock();
  if(!available()){hideDock();return;}
  el.hidden=false;
  syncLauncher();
}
function hideDock(){
  const el=$('chat-dock');if(!el)return;
  if(dockView){dockView.unmount();dockView=null;}
  dockOpen=false;
  el.hidden=true;el.dataset.state='collapsed';
  $('chat-dock-panel').hidden=true;$('chat-dock-launcher').hidden=false;
  $('chat-dock-launcher').setAttribute('aria-expanded','false');
}
function openDock(){
  if(!available())return;
  const scope=S.now();
  dockOpen=true;
  const el=dock();el.dataset.state='open';
  $('chat-dock-panel').hidden=false;$('chat-dock-launcher').hidden=true;
  $('chat-dock-launcher').setAttribute('aria-expanded','true');
  $('chat-dock-panel').setAttribute('aria-label','Chat with '+chatName());
  $('chat-dock-message').placeholder='Message '+chatName();
  dockView?.unmount();
  dockView=new ChatView.View({kind:'dock',log:$('chat-dock-log'),form:$('chat-dock-form'),box:$('chat-dock-message'),
    send:$('chat-dock-send'),status:$('chat-dock-status'),ids:false,limit:40,
    visible:()=>dockOpen&&current!=='chat',after:syncLauncher}).mount();
  ensureHistory(scope);
  if(S.state(scope).session.state==='unknown')checkContinuation(scope);
  $('chat-dock-message').focus();       // the owner opened it
}
function minimise(){
  if(dockView){dockView.unmount();dockView=null;}
  dockOpen=false;
  const el=dock();el.dataset.state='collapsed';
  $('chat-dock-panel').hidden=true;$('chat-dock-launcher').hidden=false;
  $('chat-dock-launcher').setAttribute('aria-expanded','false');
  syncLauncher();
  $('chat-dock-launcher').focus();
}
/* The page's own leave guard (an unsaved note) may keep the owner where they are; then the
   dock stays exactly as it was. Otherwise navigation hides it and the page takes over. */
async function maximise(){
  focusPage=true;
  await showTab('chat');
  if(current!=='chat')focusPage=false;
}
/* The collapsed launcher: who, what is happening now, and an in-session "new reply". A
   message preview is shown only while signed in. */
function syncLauncher(){
  const el=$('chat-dock');if(!el||el.hidden)return;
  const s=S.state(S.now());
  for(const face of el.querySelectorAll('.chat-dock-face')){
    const want=faceHtml(chatName(),'chat-dock-avatar');if(face.innerHTML!==want)face.innerHTML=want;
  }
  for(const n of el.querySelectorAll('.chat-dock-name'))n.textContent=chatName();
  const live=[...s.intents.values()].filter(it=>!it.settled).at(-1);
  const preview=s.auth==='expired'?'Sign in again to continue':
    live?.stream?live.stream.replace(/\s+/g,' ').trim().slice(-90):
    live?(live.status?.text||KeyedChat.words.sending):s.unseen?'Replied':'Chat';
  el.querySelector('.chat-dock-preview').textContent=preview;
  el.querySelector('.chat-dock-state').textContent=turnText(s);
  el.querySelector('.chat-dock-dot').hidden=!s.unseen;
  el.classList.toggle('is-active',Boolean(live));
  $('chat-dock-launcher').setAttribute('aria-label','Chat with '+chatName()+(s.unseen?', new reply':'')+(live?', '+(turnText(s)||'sending'):''));
}

/* Navigation: leaving Chat disposes the page view (not the conversation); the dock takes
   over on every other page. */
const navigate=window.productNavigate;
window.productNavigate=name=>{
  navigate?.(name);
  start();
  if(name!=='chat'&&pageView){pageView.unmount();pageView=null;$('chat').innerHTML='';}
  syncDock();
};

window.PersistentChat={loadNewest,loadOlder,adapt,openDock,minimise,maximise,get pageView(){return pageView;},get dockView(){return dockView;},prior};
})();
