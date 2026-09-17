/* The workspace uses the same API on desktop and on a future paired mobile client. */
const heading=(title,body)=>'';
const options=(rows,selected)=>rows.map(([value,label])=>`<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`).join('');
const post=(path,payload={})=>api(path,{method:'POST',body:JSON.stringify(payload)});
let roster=[],providerRows=[],activeOperation=null,chatSession=null;
const chatKey=kind=>'chat-'+kind+'-'+INSTALLATION+'-'+PROFILE;
const chatName=()=>roster.find(p=>p.id===PROFILE)?.name||'Your companion';
let noticeTimer=null;
function notice(message,bad=false){
  const el=$('operation');if(!el)return;
  if(noticeTimer){clearTimeout(noticeTimer);noticeTimer=null;}
  el.hidden=false;
  el.classList?.remove?.('toast-exit');
  el.classList?.toggle?.('toast-bad',Boolean(bad));
  el.classList?.toggle?.('toast-good',!bad);
  el.innerHTML=`<button class="quiet" id="dismiss-notice">✕</button><span class="${bad?'bad':''}">${esc(message)}</span>`;
  const dismiss=$('dismiss-notice');
  if(dismiss)dismiss.onclick=()=>{el.hidden=true;el.classList?.remove?.('toast-exit');};
  if(!bad&&typeof window!=='undefined'&&window.document&&document.body){
    noticeTimer=setTimeout(()=>{
      el.classList?.add?.('toast-exit');
      setTimeout(()=>{if(el.classList?.contains?.('toast-exit'))el.hidden=true;},220);
    },3200);
  }
}
const operationKey=()=> 'operation-'+INSTALLATION+'-'+(PROFILE||'default');
const operationCallbacks=new Map();
function operationError(error){
  notice(error?.message||String(error),true);
  if(sessionStorage.getItem(operationKey())){
    $('operation').insertAdjacentHTML('beforeend','<button class="quiet" id="retry-operation">Retry status</button>');
    $('retry-operation').onclick=async()=>{try{await followOperation(await api('/operations/'+sessionStorage.getItem(operationKey())));}catch(e){operationError(e);}};
  }
}
window.addEventListener('unhandledrejection',e=>{operationError(e.reason);e.preventDefault();});
async function navigateProfile(profile,tab='now'){if(!await confirmEditorLeave(current)){$('companion-select').value=PROFILE;return;}localStorage.setItem('last-profile-'+INSTALLATION,profile);const u=new URL(location.href);u.searchParams.set('installation',INSTALLATION);u.searchParams.set('profile',profile);u.hash=tab;location.href=u;}
async function installationChanged(value){if(!await confirmEditorLeave(current)){$('installation-select').value=INSTALLATION;return;}const u=new URL(location.href);u.searchParams.set('installation',value);u.searchParams.delete('profile');u.hash='roster';location.href=u;}
async function followOperation(row,onDone){
  if(row.profile!==(PROFILE||'default'))throw Error('This action belongs to another companion. Open that companion to follow it.');
  if(onDone)operationCallbacks.set(row.id,onDone);
  onDone=operationCallbacks.get(row.id);
  activeOperation=row.id;sessionStorage.setItem(operationKey(),row.id);
  try{
    while(true){
      if(row.stream_text&&row.label.startsWith('Chat with ')&&current==='chat'&&$('chat-log')){
        const log=$('chat-log'),follow=log.scrollHeight-log.scrollTop-log.clientHeight<100;
        let live=$('chat-stream');
        if(!live){$('chat-log').insertAdjacentHTML('beforeend','<div class="bubble" id="chat-stream" aria-label="Incoming reply"></div>');live=$('chat-stream');}
        live.textContent=row.stream_text.replace(/<(think|reasoning)>[\s\S]*?(<\/\1>|$)/gi,'');
        $('chat-status').textContent='Replying…';if(follow)log.scrollTop=log.scrollHeight;
      }
      const op=$('operation');
      if(op){
        op.hidden=current==='chat'&&row.label.startsWith('Chat with ')&&['running','complete'].includes(row.status);
        op.classList?.remove?.('toast-exit');
        op.innerHTML=`<button class="quiet" id="dismiss-notice" style="display:none">✕</button><strong>${esc(row.label)}</strong><div class="dim">${esc(row.progress)}</div>`;
      }
      if(row.status!=='running'){
        activeOperation=null;sessionStorage.removeItem(operationKey());operationCallbacks.delete(row.id);
        const result=row.result||{};
        const isBad=row.status==='failed'||Boolean(row.error);
        if(op){
          op.classList?.remove?.('toast-exit');
          op.classList?.toggle?.('toast-bad',isBad);
          op.classList?.toggle?.('toast-good',!isBad);
          op.innerHTML=`<button class="quiet" id="dismiss-notice">✕</button><div class="toast-body"><strong>${esc(row.label)} · ${esc(row.status)}</strong>
            ${row.error?`<p class="bad">${esc(row.error)}</p>`:''}${result.output?`<details><summary>Details</summary><pre>${esc(result.output)}</pre></details>`:''}
            ${result.note?`<p class="dim">${esc(result.note)}</p>`:''}${result.response&&!onDone?`<pre>${esc(result.response)}</pre>`:''}</div>`;
        }
        const dismiss=$('dismiss-notice');
        if(dismiss)dismiss.onclick=()=>{if(op)op.hidden=true;};
        if(!isBad&&typeof window!=='undefined'&&window.document&&document.body){
          if(noticeTimer)clearTimeout(noticeTimer);
          noticeTimer=setTimeout(()=>{
            if(activeOperation===null&&op){
              op.classList?.add?.('toast-exit');
              setTimeout(()=>{if(op.classList?.contains?.('toast-exit'))op.hidden=true;},220);
            }
          },3500);
        }
        if(row.status==='complete'){
          if(onDone)await onDone(result);
          else{
            if(row.label.startsWith('Chat with ')){
              chatSession=result.session||chatSession;sessionStorage.setItem(chatKey('session'),chatSession||'');sessionStorage.removeItem(chatKey('draft'));
            }
            if(!hasEditorChanges())await render(current);
          }
        }
        return row;
      }
      await new Promise(resolve=>setTimeout(resolve,row.label.startsWith('Chat with ')?350:1300));
      row=await api('/operations/'+row.id);
    }
  }finally{
    // A lost status connection must not leave a permanent browser lock. Keep the
    // saved operation ID until its outcome is known; never resubmit it blindly.
    if(activeOperation===row.id)activeOperation=null;
  }
}
async function action(path,payload={},onDone){
  if(activeOperation)throw Error('Wait for the current action to finish.');
  const pending=sessionStorage.getItem(operationKey());
  if(pending){
    await followOperation(await api('/operations/'+pending));
    throw Error('The previous action has been checked. Review its result before starting another action.');
  }
  activeOperation='submitting';
  try{
    const row=await post(path,payload);
    return await followOperation(row,onDone);
  }finally{if(activeOperation==='submitting')activeOperation=null;}
}
function bindAction(id,path,payload={},onDone){const button=$(id);if(button)button.onclick=async()=>{button.disabled=true;try{await action(path,typeof payload==='function'?payload():payload,onDone);}finally{button.disabled=false;}};}

window.waitForRestart = function(targetVersion) {
  let backdrop = document.getElementById('update-reconnect-backdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.id = 'update-reconnect-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);backdrop-filter:blur(6px);z-index:99999;display:flex;align-items:center;justify-content:center;';
    backdrop.innerHTML = `
      <div style="background:var(--panel,#18181b);border:1px solid var(--edge-2,#3f3f46);border-radius:16px;padding:32px 28px;max-width:420px;width:90%;text-align:center;color:var(--ink,#fafafa);box-shadow:0 24px 70px rgba(0,0,0,0.85);">
        <div class="spinner" style="margin:0 auto 18px auto;width:38px;height:38px;border:3px solid var(--edge-2,#3f3f46);border-top-color:var(--accent,#818cf8);border-radius:50%;animation:spin 1s linear infinite;"></div>
        <h3 style="margin:0 0 8px 0;font-size:1.25rem;">Restarting Workspace</h3>
        <p style="color:var(--dim,#a1a1aa);margin:0 0 16px 0;font-size:0.95rem;line-height:1.4;">Tamanitomo ${esc(targetVersion ? 'v' + targetVersion.replace(/^v/, '') : '')} has been installed.<br>Reconnecting to your companion...</p>
        <p id="update-reconnect-status" style="color:var(--dim,#71717a);font-size:0.85rem;font-family:monospace;margin:0;">Waiting for service to restart...</p>
      </div>
    `;
    document.body.appendChild(backdrop);
  }

  let attempts = 0;
  const timer = setInterval(async () => {
    attempts++;
    try {
      const res = await fetch(scoped('/api/updates?force=true'), { cache: 'no-store' });
      if (res.ok) {
        clearInterval(timer);
        const st = document.getElementById('update-reconnect-status');
        if (st) st.textContent = 'Service online! Reloading workspace...';
        setTimeout(() => {
          window.location.reload();
        }, 800);
      }
    } catch (_) {
      const st = document.getElementById('update-reconnect-status');
      if (st) st.textContent = `Reconnecting... (attempt ${attempts})`;
    }
  }, 1200);
};

async function boot(){
  // Learn whether there is a face to show before anything draws one: a page
  // that renders first would otherwise show the initial and keep it.
  await refreshPortraitState();
  $('installation-select').value=INSTALLATION;$('installation-select').onchange=e=>installationChanged(e.target.value);
  const data=await api('/profiles');roster=data.profiles;
  if(!PROFILE){const remembered=localStorage.getItem('last-profile-'+INSTALLATION);PROFILE=data.selected_profile&&data.selected_profile!=='default'?data.selected_profile:roster.some(p=>p.id===remembered)?remembered:roster.find(p=>p.installed)?.id||'default';}
  $('companion-select').innerHTML=options([...(roster.some(p=>p.id==='default')?[]:[['default','Default Hermes']]),...roster.map(p=>[p.id,p.name])],PROFILE);
  $('companion-select').onchange=e=>navigateProfile(e.target.value,'now');
  const selected=roster.find(p=>p.id===PROFILE);
  $('who').textContent=selected?.name||'Welcome home';$('sub').textContent=selected?.installed?'A continuing life, together.':'Your companion workspace';
  // Adopt this companion's saved palette and pinned bar before the first page draws.
  if(window.Appearance)await window.Appearance.load();
  let initial=location.hash.slice(1);
  if(!TABS.some(([id])=>id===initial))initial=selected?.installed?'now':'roster';
  showTab(initial);
  const pending=sessionStorage.getItem(operationKey());
  if(pending){try{await followOperation(await api('/operations/'+pending));}catch(e){if(e.status===404||e.status===400)sessionStorage.removeItem(operationKey());operationError(e);}}
}
workspaceHandlers.roster=async()=>{
  const d=await api('/profiles');roster=d.profiles;
  $('roster').innerHTML=heading('A place for your companions','Their conversations, days, and shared memories stay with their Hermes profile. Choose someone to spend time with, or welcome someone new.')+
  `<div class="card onboarding-guide" style="border-left:4px solid var(--accent);margin-bottom:20px">
    <h3>✨ Companion-Kit Setup Guide</h3>
    <p class="dim small">Follow these 4 simple steps to bring your companion to life with Hermes autonomous background routines.</p>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px">
      <div style="padding:10px;border-radius:6px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
        <strong>1. Engine</strong>
        <p class="small dim">${d.runtime.available?'✅ Hermes installed':'⚠️ Hermes needed'}</p>
        ${!d.runtime.available?'<button class="act small" id="guide-install-hermes" style="margin-top:6px">Install Hermes</button>':''}
      </div>
      <div style="padding:10px;border-radius:6px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
        <strong>2. Companion Profile</strong>
        <p class="small dim">${d.profiles.some(p=>p.installed)?`✅ ${d.profiles.filter(p=>p.installed).length} companion(s) active`:'Create your companion’s soul & rhythm'}</p>
        <button class="quiet small" id="guide-create-companion" style="margin-top:6px">Create Companion</button>
      </div>
      <div style="padding:10px;border-radius:6px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
        <strong>3. Inference Presets</strong>
        <p class="small dim">1-click model presets & free fallbacks</p>
        <button class="quiet small" id="guide-goto-env" style="margin-top:6px">Configure Inference</button>
      </div>
      <div style="padding:10px;border-radius:6px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
        <strong>4. Connect & Chat</strong>
        <p class="small dim">Start background life & say hello</p>
        <button class="act small" id="guide-goto-chat" style="margin-top:6px">Open Chat</button>
      </div>
    </div>
  </div>
  <div class="actions"><button class="act" id="create-companion">Create a companion</button>${!d.runtime.available?'<button class="quiet" id="install-hermes">Install Hermes here</button>':''}</div>
  ${!d.runtime.available?`<div class="card"><h2>Set up Hermes</h2><p>${esc(d.runtime.error)}</p><p class="dim">The installer provisions Hermes in this environment. Account setup comes next, in Hermes & providers.</p><code>${esc(d.runtime.root)}</code></div>`:''}
  <div class="grid">${d.profiles.map(p=>`<button class="card profile-card" data-profile="${esc(p.id)}">${faceForProfile(p.id,p.name)}<h3>${esc(p.name)}</h3><span class="pill">${p.installed?esc(p.type||'companion'):'Ready to adopt'}</span><p class="dim small">${esc(p.id)}</p></button>`).join('')||'<div class="card dim">Your first companion starts here.</div>'}</div>
  <div id="onboarding"></div>
  ${d.archives.length?`<div class="card"><h2>Archived profiles</h2>${d.archives.map(a=>`<div class="actions"><span>${esc(a.id)}</span><button class="quiet" data-restore="${esc(a.id)}">Restore</button><button class="quiet" data-purge="${esc(a.id)}">Delete permanently</button></div>`).join('')}</div>`:''}`;
  if($('guide-install-hermes'))bindAction('guide-install-hermes','/install');
  if($('guide-create-companion'))$('guide-create-companion').onclick=()=>onboarding(false);
  if($('guide-goto-env'))$('guide-goto-env').onclick=()=>{aimSettings('hermes-core');navigateProfile(PROFILE||'default','settings');};
  if($('guide-goto-chat'))$('guide-goto-chat').onclick=()=>navigateProfile(PROFILE||'default','now');
  $('create-companion').onclick=()=>onboarding(false);
  bindAction('install-hermes','/install');
  for(const b of $('roster').querySelectorAll('[data-profile]'))b.onclick=()=>{const p=d.profiles.find(p=>p.id===b.dataset.profile);if(p.installed)navigateProfile(p.id,'companion-edit');else{aimSettings('hermes-core');navigateProfile(p.id,'settings');}};
  for(const b of $('roster').querySelectorAll('[data-restore]'))b.onclick=async()=>{const name=prompt('Original profile name:');if(name)await action('/profile/restore',{archive:b.dataset.restore,profile:name},()=>render('roster'));};
  for(const b of $('roster').querySelectorAll('[data-purge]'))b.onclick=async()=>{const name=prompt('Permanently delete this archived profile, including its sessions. The external vault stays intact. Type the full archive name:\n'+b.dataset.purge);if(name===b.dataset.purge)await action('/profile/purge',{archive:name,confirm:name},()=>render('roster'));};
  if(!d.profiles.some(p=>p.installed))setTimeout(()=>onboarding(false),50);
};
/* The create/adopt flow lives in onboarding.js, which defines window.onboarding(). */
/* ---------------------------------------------------------------------- chat

   One conversation. Hermes keeps a session per channel, so a companion talked
   to on Telegram in the morning and here at night had its history split across
   rows that each told only part of it. /api/feed reads across all of them at
   once, so this is the whole thing, in order, however it was said — scheduled
   runs and sub-agents excluded, because those are the companion working rather
   than the companion talking.

   There is no new-conversation control, because the conversation does not end.
   Scrolling up loads what came before until there is nothing before it. */

const CHANNELS={
  telegram:{label:'Telegram',mark:'✈'},
  discord:{label:'Discord',mark:'◉'},
  signal:{label:'Signal',mark:'△'},
  whatsapp:{label:'WhatsApp',mark:'●'},
  sms:{label:'SMS',mark:'✉'},
  email:{label:'Email',mark:'✉'},
  tamanitomo:{label:'Tamanitomo',mark:'◈'},
  cli:{label:'Terminal',mark:'⌫'},
  terminal:{label:'Terminal',mark:'⌫'},
  tui:{label:'Terminal',mark:'⌫'},
  desktop:{label:'Here',mark:''},
  web:{label:'Here',mark:''}
};
const channelOf=source=>{
  const key=String(source||'desktop').toLowerCase();
  return {key,...(CHANNELS[key]||{label:source||'Elsewhere',mark:'○'})};
};

let chatPageGeneration=0,chatFeedCursor=null,chatFeedLoading=false,chatLastDay='',chatFeedReady=false;
let chatTopWatcher=null;

workspaceHandlers.chat=async()=>{
  const pageGeneration=++chatPageGeneration;
  const alive=()=>current==='chat'&&pageGeneration===chatPageGeneration;
  const emotions=await api('/feelings').catch(()=>null);
  if(!alive())return;
  const moodLabel=emotions?.intimacy?`${emotions.intimacy.stage_badge} · ${emotions.intimacy.score}%`
    :(emotions?.state?.mood||'');
  $('chat').innerHTML=`
    <div class="chat-room">
      <div class="chat-peek" id="chat-peek">
        ${faceHtml(chatName(),"chat-peek-avatar")}
        <div class="chat-peek-copy">
          <strong>${esc(chatName())}</strong>
          <span class="dim small" id="chat-presence">${moodLabel?esc(moodLabel):' '}</span>
        </div>
      </div>
      <div id="chat-log" class="chat-log" role="log" aria-live="polite">
        <p class="dim small chat-loading" role="status">Reading the conversation…</p>
      </div>
      <form id="chat-form" class="chat-composer">
        <label class="sr-only" for="chat-message">Your message</label>
        <textarea rows="1" id="chat-message" placeholder="Message ${esc(chatName())}" required maxlength="30000"></textarea>
        <button class="chat-send" id="send-message" aria-label="Send">${icon('arrow_right')}</button>
      </form>
      <span class="dim small chat-hint" id="chat-status" role="status">Enter to send · Shift+Enter for a new line</span>
    </div>`;
  if(moodLabel&&$('chat-presence'))$('chat-presence').onclick=()=>showTab('relationship');

  const log=$('chat-log');
  chatFeedCursor=null;chatLastDay='';chatFeedReady=false;

  await loadFeed(pageGeneration);
  mountBrowserVoice();
  voiceControlsBusy(Boolean(activeOperation));

  const box=$('chat-message');
  box.value=sessionStorage.getItem(chatKey('draft'))||'';
  const grow=()=>{box.style.height='auto';box.style.height=Math.min(box.scrollHeight,200)+'px';};
  grow();
  box.oninput=()=>{sessionStorage.setItem(chatKey('draft'),box.value);grow();};
  box.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('send-message').disabled)$('chat-form').requestSubmit();}};

  $('chat-form').onsubmit=async e=>{
    e.preventDefault();
    const message=box.value;
    if(!message.trim())return;
    if(activeOperation)throw Error('Wait for the current action to finish.');
    sessionStorage.setItem(chatKey('draft'),message);
    $('send-message').disabled=true;box.readOnly=true;
    log.querySelector('.chat-welcome')?.remove();
    const tempId='turn-'+Date.now();
    log.insertAdjacentHTML('beforeend',
      `<div class="bubble user sending" id="${tempId}" data-channel="desktop">
        <div class="message-body">${richText(message)}</div>
        <small><span class="bubble-status">sending…</span></small></div>`);
    showTyping(true);
    log.scrollTo({top:log.scrollHeight,behavior:'smooth'});
    box.value='';grow();
    try{
      const result=await action('/chat',{message,session:chatSession},async r=>{
        showTyping(false);
        $('chat-stream')?.remove();
        const pending=$(tempId);
        if(pending){
          pending.classList.remove('sending');
          const status=pending.querySelector('.bubble-status');
          if(status)status.textContent=new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
        }
        chatSession=r.session||chatSession;
        sessionStorage.setItem(chatKey('session'),chatSession||'');
        sessionStorage.removeItem(chatKey('draft'));
        if(current!=='chat'){notice('Reply received from '+chatName()+'. Open Chat to read it.');return;}
        const replyObj=(r.messages||[]).filter(m=>m.role==='assistant').at(-1);
        const {text:replyText,extractedMedia}=extractMediaFromContent(replyObj?.content||r.response||'');
        const attachments=[...(replyObj?.attachments||[]),...extractedMedia];
        if(replyText||attachments.length){
          log.insertAdjacentHTML('beforeend',
            `<div class="bubble animate-in" data-channel="desktop">
              <div class="message-body">${richText(replyText)}</div>
              ${attachments.map(inlineMedia).join('')}
              <small>${esc(new Date().toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}</small></div>`);
        }
        log.scrollTo({top:log.scrollHeight,behavior:'smooth'});
        $('send-message').disabled=false;box.readOnly=false;
        if($('chat-status'))$('chat-status').textContent='Enter to send · Shift+Enter for a new line';
        box.focus();
        await speakBrowserReply(r);
      });
      if(result.status!=='complete')throw Error(result.error||'Message could not be completed. Your draft is saved.');
    }catch(error){
      showTyping(false);
      $('chat-stream')?.remove();
      voiceReplyRequested=false;
      const pending=$(tempId);
      if(pending){
        pending.classList.remove('sending');pending.classList.add('send-error');
        const status=pending.querySelector('.bubble-status');
        if(status)status.innerHTML='<span class="bad">Failed to send</span>';
      }
      box.value=message;grow();
      if($('chat-status'))$('chat-status').textContent='Could not finish. Your draft is saved; you can retry.';
      $('send-message').disabled=false;box.readOnly=false;
      throw error;
    }
  };
};

/* A marker pinned to the head of the log. When it scrolls into view there is
   history to fetch. An observer fires on layout, so this also covers a log too
   short to scroll and a flick that outruns its own scroll events. */
function watchTopOfLog(log,generation){
  chatTopWatcher?.disconnect();chatTopWatcher=null;
  const sentinel=document.createElement('div');
  sentinel.className='chat-top-sentinel';
  log.insertBefore(sentinel,log.firstChild);
  if(typeof IntersectionObserver!=='function'){
    log.onscroll=()=>{if(chatFeedReady&&log.scrollTop<140)loadOlder(generation);};
    return;
  }
  chatTopWatcher=new IntersectionObserver(entries=>{
    if(chatFeedReady&&entries.some(entry=>entry.isIntersecting))loadOlder(generation);
  },{root:log,rootMargin:'200px 0px 0px 0px'});
  chatTopWatcher.observe(sentinel);
}

/* Land on the newest message without animating down the whole history, and only
   start watching for the top of the log once we are there. Pictures resolve
   their height late, so the foot is held for a couple of frames. */
function jumpToNewest(log){
  chatFeedReady=false;
  const settle=()=>{log.style.scrollBehavior='auto';log.scrollTop=log.scrollHeight;log.style.scrollBehavior='';};
  settle();
  requestAnimationFrame(settle);
  setTimeout(settle,60);
  setTimeout(()=>{settle();chatFeedReady=true;},300);
  for(const img of log.querySelectorAll('img'))
    img.addEventListener('load',()=>{if(!chatFeedReady)settle();},{once:true});
}

/* The three dots, while they are composing a reply. */
function showTyping(on){
  const log=$('chat-log');if(!log)return;
  $('chat-typing-indicator')?.remove();
  if($('chat-presence'))$('chat-presence').classList.toggle('is-typing',!!on);
  if(!on)return;
  log.insertAdjacentHTML('beforeend',
    `<div class="bubble typing" id="chat-typing-indicator" aria-label="${esc(chatName())} is typing">
      <span class="typing-dots"><i></i><i></i><i></i></span></div>`);
  log.scrollTo({top:log.scrollHeight,behavior:'smooth'});
}

async function loadFeed(generation){
  const log=$('chat-log');
  try{
    const d=await api('/feed?limit=60');
    if(current!=='chat'||generation!==chatPageGeneration||!$('chat-log'))return;
    chatFeedCursor=d.next_cursor;
    chatSession=d.session||chatSession;
    if(chatSession)sessionStorage.setItem(chatKey('session'),chatSession);
    log.innerHTML=chatMessagesHtml(d.messages)||`
      <div class="chat-welcome">
        ${faceHtml(chatName())}
        <h2>The beginning</h2>
        <p>Whatever you say here, and on any channel ${esc(chatName())} is reachable on, collects in this one place.</p>
      </div>`;
    watchTopOfLog(log,generation);
    jumpToNewest(log);
  }catch(error){
    if(current==='chat'&&generation===chatPageGeneration&&$('chat-log'))
      log.innerHTML=`<p class="bad">${esc(error.message)}</p>`;
    chatFeedReady=true;
  }
}

async function loadOlder(generation){
  if(chatFeedLoading||!chatFeedCursor)return;
  chatFeedLoading=true;
  const log=$('chat-log');
  // Everything lands just after the sentinel, so the sentinel stays the head of
  // the log and one observer keeps working across every page.
  const sentinel=log.querySelector('.chat-top-sentinel');
  const place=html=>sentinel?sentinel.insertAdjacentHTML('afterend',html):log.insertAdjacentHTML('afterbegin',html);
  place('<p class="dim small chat-older" id="chat-older" role="status">Reading earlier…</p>');
  try{
    const page=await api('/feed?limit=60&before='+encodeURIComponent(chatFeedCursor));
    if(current!=='chat'||generation!==chatPageGeneration||!$('chat-log'))return;
    const height=log.scrollHeight,top=log.scrollTop;
    $('chat-older')?.remove();
    // The oldest message on screen is no longer the first of its day.
    chatLastDay='';
    place(chatMessagesHtml(page.messages));
    // Hold the reader's place: the content above them just grew.
    log.scrollTop=top+log.scrollHeight-height;
    chatFeedCursor=page.next_cursor;
    if(!chatFeedCursor){
      chatTopWatcher?.disconnect();chatTopWatcher=null;
      place('<p class="dim small chat-older">The beginning of the conversation.</p>');
    }
  }catch(error){
    if($('chat-older'))$('chat-older').innerHTML=`<span class="bad">${esc(error.message)}</span>`;
  }finally{chatFeedLoading=false;}
}
function extractMediaFromContent(content){
  let text=String(content||'');
  const mediaMatches=[];
  text=text.replace(/(?:^|\n)MEDIA:([^\n]+)(?:\n|$)/g,(match,path)=>{
    const cleanPath=path.trim();
    if(/\.(png|jpe?g|webp|gif)$/i.test(cleanPath)){
      mediaMatches.push({kind:'image',path:cleanPath,url:'/content/file?path='+encodeURIComponent(cleanPath),title:cleanPath.split('/').pop()});
      return '\n';
    }
    if(/\.(wav|ogg|mp3|m4a|flac|aac)$/i.test(cleanPath)){
      mediaMatches.push({kind:'audio',path:cleanPath,url:'/content/file?path='+encodeURIComponent(cleanPath),title:cleanPath.split('/').pop()});
      return '\n';
    }
    return match;
  });
  text=text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g,(match,alt,url)=>{
    const cleanUrl=url.trim();
    const resolvedUrl=cleanUrl.startsWith('/api/')?cleanUrl.slice(4):(cleanUrl.startsWith('http')?cleanUrl:'/content/file?path='+encodeURIComponent(cleanUrl));
    mediaMatches.push({kind:'image',path:cleanUrl,url:resolvedUrl,title:alt||'Shared photo'});
    return '';
  });
  return {text:text.trim(),extractedMedia:mediaMatches};
}
function chatMessagesHtml(messages){
  const GROUP_WINDOW=5*60;
  return messages.map((m,i)=>{
    const at=new Date((m.timestamp||0)*1000),day=at.toLocaleDateString();
    const divider=day!==chatLastDay?`<div class="chat-day">${esc(day)}</div>`:'';
    const newDay=day!==chatLastDay;
    chatLastDay=day;
    const channel=channelOf(m.source);
    const prev=messages[i-1],next=messages[i+1];
    const sameRun=(a,b)=>a&&b&&a.role===b.role&&String(a.source||'')===String(b.source||'')
      &&Math.abs((b.timestamp||0)-(a.timestamp||0))<=GROUP_WINDOW;
    const startsRun=newDay||!sameRun(prev,m);
    const endsRun=!sameRun(m,next)||
      (next&&new Date((next.timestamp||0)*1000).toLocaleDateString()!==day);
    const {text,extractedMedia}=extractMediaFromContent(m.content);
    const attachments=[...(m.attachments||[]),...extractedMedia];
    // "Here" needs no badge; any other channel is worth knowing about.
    const badge=channel.key==='desktop'||channel.key==='web'?''
      :`<span class="bubble-channel">${channel.mark?channel.mark+' ':''}${esc(channel.label)}</span>`;
    const meta=endsRun
      ?`<small>${badge}<span>${esc(at.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}</span></small>`:'';
    const shape=[startsRun?'starts-run':'',endsRun?'ends-run':''].filter(Boolean).join(' ');
    const face=m.role!=='user'&&endsRun?faceHtml(chatName(),'bubble-face'):'';
    return divider+`<div class="bubble ${m.role==='user'?'user':''} ${shape}" data-channel="${esc(channel.key)}">
      ${face}
      <div class="message-body">${richText(text)}</div>
      ${attachments.map(inlineMedia).join('')}
      ${meta}
    </div>`;}).join('');
}

function inlineMedia(item){const url=mediaUrl(item.url);const p=item.path?` data-photo-path="${esc(item.path)}"`:'';const u=` data-photo-url="${esc(item.url)}"`;if(item.kind==='image'&&item.blur)return `<details class="media-reveal"><summary><img class="chat-media concealed-media" src="${url}" alt="Concealed image"><span>Reveal sensitive or unreviewed image</span></summary><div class="chat-media-card" onclick="openChatPhoto(this.querySelector('img'))"${p}${u}><img class="chat-media" src="${url}" alt="${esc(item.title)}" loading="lazy"></div></details>`;return item.kind==='image'?`<div class="chat-media-card" onclick="openChatPhoto(this.querySelector('img'))"${p}${u}><img class="chat-media" src="${url}" alt="${esc(item.title)}" loading="lazy"><div class="chat-media-bar"><span class="chat-media-caption">${esc(item.title||'Photo')}</span><button type="button" class="chat-media-zoom">Zoom 🔍</button></div></div>`:item.kind==='audio'?`<div class="chat-audio-card"><audio class="chat-media" controls preload="metadata" src="${url}"></audio><div class="chat-audio-caption">🎵 ${esc(item.title||'Voice note')}</div></div>`:item.kind==='video'?`<video class="chat-media" controls preload="none" src="${url}"></video>`:'';}
function openChatPhoto(imgEl){if(!imgEl)return;const card=imgEl.closest('.chat-media-card');const path=card?.dataset.photoPath||'';const url=card?.dataset.photoUrl||imgEl.src;const title=imgEl.alt||'Photo';if(typeof openPhotoViewer==='function'){openPhotoViewer({url,path,title,at:new Date().toISOString()});}else{window.open(url,'_blank');}}
/* How things are between you, in one card.

   This was two: an "Emotional Atmosphere" card with five meters and a mood, and
   a "Relationship & Connection Dynamic" card with the stage ladder — both
   answering the same question, one above the other, with the stage name printed
   twice inside the second. The meters live on Home as well, so the page was the
   third place to read the same numbers. One card now: where you are, how it
   feels, and what governs it. */
function relationshipNow(bars,intimacy,companionName){
  const feelings=bars&&bars.feelings;
  if(!feelings&&!intimacy)return '';
  const stages=['Just Met','Friends','Chemistry','Intimacy','Bonded'];
  const stage=intimacy?(intimacy.stage||0):0;
  const score=intimacy?(intimacy.score||0):0;
  const paceLabel=intimacy?({slow:'Gradual',natural:'Natural',quick:'Quick'}[intimacy.pace]||intimacy.pace):'';

  // Real state, kept. Boundaries that have actually been crossed are not a detail.
  const standing=intimacy&&intimacy.permanent_friend?
    `<div class="notice-strip rel-standing is-firm"><p><strong>Friendship established.</strong>
      After repeated boundary violations, ${esc(companionName)} has stepped back to friendship. This does not reopen.</p></div>`
    :intimacy&&intimacy.nsfw_revoked?
    `<div class="notice-strip rel-standing"><p><strong>Stepped back to friendship.</strong>
      Your relationship is rooted in friendship and affectionate companionship.</p></div>`:'';

  const facts=[
    intimacy?['Stage',esc(intimacy.stage_name||stages[stage]||'Just Met')]:null,
    intimacy?['Pace',esc(paceLabel)]:null,
    feelings?['Temperament',esc(feelings.personality||'—')]:null,
    feelings&&feelings.mood?['Mood',esc(feelings.mood)+(feelings.mood_at?` · ${esc(ago(feelings.mood_at))}`:'')]:null,
    intimacy&&intimacy.violations_count?['Boundary violations',String(intimacy.violations_count)]:null,
  ].filter(Boolean);

  return `<div class="card rel-now">
    <div class="section-heading" style="margin-top:0">
      <h2>How things are between you</h2>
      ${intimacy?`<span class="pill ${stage>=3?'status-good':''}">${esc(intimacy.stage_name||stages[stage])} · ${score}%</span>`:''}
    </div>
    ${intimacy&&intimacy.description?`<p class="dim">${esc(intimacy.description)}</p>`:''}
    ${intimacy?`<div class="rel-ladder">
      <div class="rel-ladder-track"><div class="rel-ladder-fill" style="width:${score}%"></div></div>
      <div class="rel-ladder-labels">${stages.map((name,i)=>
        `<span class="${stage>=i?'is-reached':''}">${name}</span>`).join('')}</div>
    </div>`:''}
    ${standing}
    ${feelings?feelingMeters(feelings.meters):''}
    ${facts.length?`<dl class="fact-list">${facts.map(([k,v])=>
      `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`:''}
    <details class="rel-explainer">
      <summary class="small dim">How closeness works here</summary>
      <p class="dim small">Companions banter, tease and reciprocate affection as mutual trust deepens; at Bonded, warmth is expressed freely and naturally.</p>
      <p class="dim small">${esc(companionName)} holds genuine agency. Mutual respect is the condition of all of it — repeated boundary violations step the relationship back to friendship permanently.</p>
    </details>
  </div>`;
}
workspaceHandlers.relationship=async()=>{
  const d=await api('/relationship');const s=d.settings;
  const companionName=chatName()||'Your companion';
  $('relationship').innerHTML=heading('Your story together','Small firsts, familiar rituals, and jokes that only make sense between you. A shared history grows through experience.')+
  relationshipNow(d.bars,d.intimacy,companionName)+
  (s.relationship_progression==='milestones'?`
  <div class="card">
    <div class="section-heading" style="margin-top:0">
      <h2>Milestones</h2>
      <span class="pill">${d.milestones?d.milestones.filter(m=>m.earned).length:0} of ${d.milestones.length} earned</span>
    </div>
    <div class="milestone-badge-grid">
      ${d.milestones.map(m=>`
        <div class="milestone-card ${m.earned?'is-earned':''}">
          <span class="milestone-icon">${m.earned?'✦':'○'}</span>
          <div style="min-width:0">
            <div style="font-size:13px;font-weight:600">${esc(m.label)}</div>
            <div class="dim small">${m.earned?'Achieved':'In progress'}</div>
          </div>
        </div>`).join('')}
    </div>
  </div>`:'')+
  '<div id="feelings-controls"></div>'+
  `<div class="card">
    <div class="section-heading" style="margin-top:0">
      <h2>Moments</h2>
      <span class="pill">${d.moments.length} recorded</span>
    </div>
    <p class="dim">Things worth keeping, written down as they happened.</p>
    <div class="moment-timeline">
      ${d.moments.length?d.moments.slice().reverse().map(m=>`
        <div class="moment-card">
          <div class="moment-card-meta">
            <span class="pill">${esc(d.kinds[m.moment]||m.moment)}</span>
            <span class="dim small">📅 ${esc(m.happened_on||m.recorded_at.slice(0,10))}</span>
            <div style="flex:1"></div>
            ${m.status==='active'?`<button class="quiet small-btn" data-retire="${esc(m.id)}">Retire</button>`:'<span class="dim small">Retired</span>'}
          </div>
          <p style="margin:0;font-size:13.5px;line-height:1.5;color:var(--ink)">${esc(m.text)}</p>
        </div>`).join(''):'<p class="dim small" style="padding:20px;text-align:center">There is room here for your firsts. Meaningful shared moments will be preserved authentically as you interact together.</p>'}
    </div>
  </div>`;
  for(const b of $('relationship').querySelectorAll('[data-retire]'))b.onclick=async()=>{if(!await confirmEditorLeave('relationship'))return;await post('/relationship/'+encodeURIComponent(b.dataset.retire)+'/retire');notice('Moment retired.');await render('relationship');};
  await mountFeelings();
};
let vaultPath='',openNote=null;
workspaceHandlers.vault=async()=>{
  $('vault').innerHTML=heading('Your vault','Browse the vault, follow links between notes, and write in your own notebook. The files stay ordinary Markdown and JSON, ready for Obsidian too.')+
  `<div class="actions"><button class="quiet" id="vault-up">Parent folder</button><button class="quiet" id="vault-home">Vault root</button><button class="act" id="new-note">New note</button><a class="quiet" href="${mediaUrl('/api/vault/export')}" download>Export vault</a><span class="dim small" id="vault-path"></span></div><form id="vault-search-form" class="actions"><input id="vault-query" placeholder="Search your vault…" minlength="2" required style="max-width:420px"><button class="quiet">Search</button></form><div class="split"><div class="card files" id="vault-files"></div><div class="card" id="vault-document"><p class="dim">Choose a file to explore.</p></div></div>`;
  $('vault-up').onclick=()=>listVault(vaultPath.split('/').slice(0,-1).join('/'));$('vault-home').onclick=()=>listVault('');
  $('new-note').onclick=()=>{const name=prompt('Note name (letters, numbers, spaces, or hyphens):');if(!name||! /^[\p{L}\p{N} _-]{1,100}$/u.test(name))return;openNote={path:'notes/'+name+'.md',text:'# '+name+'\n',revision:'',editable:true};showNote(openNote,true);};
  $('vault-search-form').onsubmit=async e=>{e.preventDefault();const d=await api('/vault/search?q='+encodeURIComponent($('vault-query').value));$('vault-files').innerHTML=d.matches.map(m=>`<button class="quiet" data-result="${esc(m.path)}"><strong>${esc(m.path)}</strong><p class="dim small">${esc(m.excerpt)}</p></button>`).join('')||'<p class="dim">No matches in the scanned files.</p>';for(const b of $('vault-files').querySelectorAll('[data-result]'))b.onclick=()=>readNote(b.dataset.result);};
  await listVault(vaultPath);
};
async function listVault(path){const d=await api('/vault?path='+encodeURIComponent(path));vaultPath=path;$('vault-path').textContent=path||d.root;$('vault-files').innerHTML=d.entries.map(f=>`<button class="quiet" data-path="${esc(f.path)}" data-dir="${f.directory}">${f.directory?'▸':'·'} ${esc(f.name)}</button>`).join('')||'<p class="dim">This folder is empty.</p>';for(const b of $('vault-files').children)if(b.dataset.path)b.onclick=()=>b.dataset.dir==='true'?listVault(b.dataset.path):readNote(b.dataset.path);}
async function readNote(path){try{openNote=await api('/vault/file?path='+encodeURIComponent(path));showNote(openNote);}catch(e){$('vault-document').innerHTML=`<h2>${esc(path)}</h2><p class="dim">${esc(e.message)}</p><a href="${mediaUrl('/api/vault/download?path='+encodeURIComponent(path))}" download>Download file</a>`;}}
function markdown(source){return source.split('\n').map(line=>{const heading=line.match(/^(#{1,3}) (.*)$/);if(heading)return `<h${heading[1].length}>${esc(heading[2])}</h${heading[1].length}>`;let out='',at=0;for(const match of line.matchAll(/\[\[([^\]]+)\]\]/g)){out+=esc(line.slice(at,match.index))+`<button class="quiet wiki-link" data-link="${esc(match[1])}">${esc(match[1])}</button>`;at=match.index+match[0].length;}return out+esc(line.slice(at));}).join('\n');}
function showNote(note,edit=false){
  const body=edit?`<textarea id="note-text" style="height:55vh">${esc(note.text)}</textarea><div class="actions"><button class="act" id="save-note">Save note</button><button class="quiet" id="preview-note">Preview</button></div>`:`<div class="document">${markdown(note.text)}</div>${note.editable?'<div class="actions"><button class="quiet" id="edit-note">Edit note</button></div>':'<p class="dim small">Companion-owned record. Use Identity or Memory for supported changes.</p>'}`;
  $('vault-document').innerHTML=`<h2>${esc(note.path)}</h2>`+body;
  if($('edit-note'))$('edit-note').onclick=()=>showNote(note,true);
  if($('preview-note'))$('preview-note').onclick=()=>showNote({...note,text:$('note-text').value});
  if($('save-note'))$('save-note').onclick=async()=>{const d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path:note.path,text:$('note-text').value,revision:note.revision})});openNote=d;showNote(d);await listVault(vaultPath);notice('Note saved.');};
  for(const b of $('vault-document').querySelectorAll('.wiki-link'))b.onclick=()=>{const target=b.dataset.link;const base=note.path.split('/').slice(0,-1).join('/');return readNote((base?base+'/':'')+target+(target.endsWith('.md')?'':'.md'));};
}
let envState=null;
/* The Hermes environment, drawn into whichever container asks for it. The
   unified Settings page hosts it as several of its panels; nothing below
   knows or cares which page it landed on. */
async function renderHermesInto(host){
  const d=await api('/environment');envState=d;
  const gateway=await api('/gateway');
  const known=roster.find(p=>p.id===PROFILE);
  host.innerHTML=heading('Hermes settings','Manage the Hermes environment behind this companion. Providers, backups, and scheduled routines all live in Hermes’s own configuration.')+
  `<div class="card" data-hermes-card="installation"><h2>Installation</h2><p><span class="pill">${d.runtime.managed?'Kit-managed':'Existing Hermes'}</span> <span class="dim small">${esc(d.runtime.root)}</span></p>
  <div class="actions">${!d.runtime.available?'<button class="act" id="env-install">Install Hermes</button>':'<button class="quiet" id="check-version">Check version</button><button class="quiet" id="update-hermes">Update Hermes</button>'}
  ${known&&!known.installed?'<button class="act" id="adopt-companion">Adopt as a companion</button>':''}</div><p class="dim small">The vault lives outside Hermes’s code checkout. Updates are handled by Hermes; run Health checks afterwards.</p></div>
  <div class="card" data-hermes-card="stack"><h2>Local companion stack</h2><p>Install a local conversation model on the Hermes host, then choose image and voice engines for this companion.</p><div class="actions"><button class="act" id="open-local-models">Local models</button><button class="quiet" id="env-stack-images">Image studio</button><button class="quiet" id="env-stack-voice">Voice studio</button></div></div>
  ${d.runtime.available?`<div class="card" data-hermes-card="presets"><h2>Inference presets & Free Cascades</h2><p class="dim small">One-click model cascades. Automatically sets your primary model and ordered fallbacks for zero downtime.</p><div id="inference-presets" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:10px"></div></div>
  <div class="card" data-hermes-card="models"><h2>Models and fallbacks</h2><p class="dim small">Choose a model available to your account. A configured model is not yet a tested response.</p><datalist id="provider-ids"></datalist>
  <form id="models-form"><div class="form-grid"><label>Primary provider<input id="primary-provider" list="provider-ids" value="${esc(d.model.provider)}" placeholder="openrouter"></label><label>Primary model<input id="primary-model" value="${esc(d.model.default)}" placeholder="provider/model-name" required></label><label class="wide">Custom base URL (optional)<input id="primary-url" type="url" value="${esc(d.model.base_url)}" placeholder="http://localhost:11434/v1"></label></div>
  <details open><summary>Ordered fallback providers</summary><p class="dim small">Hermes tries this chain when the primary is unavailable. No provider chain can cover a complete network outage.</p><div id="fallbacks"></div><button class="quiet" id="add-fallback" type="button">Add a fallback</button></details>
  <details><summary>Models for background jobs</summary><div class="form-grid">${['loops','reflection'].map(t=>`<label>${t} provider<input id="tier-${t}-provider" list="provider-ids" value="${esc(d.tiers[t]?.provider||'')}"></label><label>${t} model<input id="tier-${t}-model" value="${esc(d.tiers[t]?.model||'')}" placeholder="Follow profile default"></label><label>${t} reasoning<select id="tier-${t}-effort">${options([['','Hermes default'],['none','None'],['low','Low'],['medium','Medium'],['high','High']],d.tiers[t]?.reasoning_effort||'')}</select></label>`).join('')}</div></details>
  <div class="actions"><button class="act">Save model configuration</button><button class="quiet" id="test-model" type="button">Test saved model chain</button><button class="quiet" id="apply-models" type="button">Apply job models</button></div></form><p class="dim small">${esc(d.restart_note)}</p></div>
  <div class="card" data-hermes-card="accounts"><h2>Accounts and credentials</h2><p class="dim">For ChatGPT or Grok account sign-in, choose Account sign-in / OAuth and select the provider in Hermes’s menu. The available login methods come from your installed Hermes version. You can also use an API key below. Stored keys are never sent back to this page.</p>
  <form id="credentials-form"><div class="form-grid"><label>Credential<select id="credential-name"><option>Loading provider catalog…</option></select></label><label>Value (blank removes it)<input id="credential-value" type="password" autocomplete="new-password"></label></div><div class="actions"><button class="act">Save credential</button></div></form><div id="credential-status" class="dim small"></div>
  <div class="actions"><button class="quiet native-console" data-console="models">Account sign-in / OAuth</button><button class="quiet native-console" data-console="messaging">Telegram & messaging</button><button class="quiet native-console" data-console="tools">Tools, voice, images & MCP</button><button class="quiet native-console" data-console="setup">Full Hermes setup</button><button class="quiet" id="advanced-config">All Hermes settings</button></div><div id="native-console"></div></div>
  <div class="card" data-hermes-card="gateway" id="gateway-controls"><h2>Gateway & background life</h2><p class="dim">Closing this app leaves an independently running Hermes gateway and its enabled jobs running. The host must stay awake; photos require an enabled schedule and working image provider.</p><div class="grid">${Object.entries(gateway.preflight.checks).map(([key,value])=>`<div><span class="pill ${value?'status-good':'status-warn'}">${value?'Verified':'Not verified'}</span><p class="small">${esc(key.replaceAll('_',' '))}</p></div>`).join('')}</div><p class="small dim">Gateway owner: ${esc(gateway.preflight.owner_home)}</p>${gateway.preflight.notes.map(n=>`<p class="small warn">${esc(n)}</p>`).join('')}<p class="dim">Review the hooks once, verify the provider, then start the gateway and activate the routine. Model-free maintenance remains active when the routine is paused.</p>
  <div class="actions"><button class="quiet" id="review-hooks">Review & approve hooks</button><button class="quiet" id="repair-companion">Install / repair jobs</button><button class="act" id="activate-routine">Activate routine</button><button class="quiet" id="pause-routine">Pause routine</button><button class="quiet" id="doctor-companion">Check installation</button></div><div id="hook-review"></div>
  <details open><summary>Gateway service controls</summary><div class="actions">${['status','install','start','stop','restart','uninstall','restart-root'].map(a=>`<button class="quiet gateway-action" data-action="${a}">${a[0].toUpperCase()+a.slice(1)}</button>`).join('')}</div>
  <label>Gateway ownership<select id="gateway-mode"><option value="">Keep current ownership</option><option value="shared">Use the shared root gateway</option><option value="dedicated">Use this profile’s own gateway</option></select></label><button class="quiet" id="save-gateway-mode">Apply ownership</button><p class="dim small">Changing ownership can require restarting the root gateway. A shared gateway restart affects all profiles it serves.</p></details></div>
  ${PROFILE&&PROFILE!=='default'?`<div class="card" data-hermes-card="lifecycle"><h2>Profile lifecycle</h2><p class="dim">Archive this profile to remove it from the roster. Its external vault stays intact, and you can restore the profile later.</p><button class="quiet" id="archive-profile">Archive ${esc(PROFILE)}</button></div>`:''}`:''}
  <div id="environment-onboarding"></div>`;
  $('open-local-models').onclick=()=>showTab('local-models');$('env-stack-images').onclick=()=>showTab('image-studio');$('env-stack-voice').onclick=()=>showTab('voice');
  bindAction('env-install','/install');bindAction('check-version','/maintenance/version');
  if($('update-hermes'))$('update-hermes').onclick=()=>{if(confirm('Let Hermes update this installation? Active gateway workers may need a restart afterwards.'))return action('/maintenance/update');};
  if($('adopt-companion'))$('adopt-companion').onclick=()=>onboarding(true);
  if(!d.runtime.available)return;
  d.fallbacks.forEach(addFallback);
  $('add-fallback').onclick=()=>{if($('fallbacks').children.length<8)addFallback({});};
  $('models-form').onsubmit=async e=>{
    e.preventDefault();const fallbacks=[...$('fallbacks').children].map(row=>({provider:row.querySelector('.fallback-provider').value,model:row.querySelector('.fallback-model').value}));
    const tiers={};for(const t of ['loops','reflection']){const model=$('tier-'+t+'-model').value,provider=$('tier-'+t+'-provider').value,reasoning_effort=$('tier-'+t+'-effort').value;if(model||reasoning_effort)tiers[t]={model,provider,reasoning_effort};}
    const model={provider:$('primary-provider').value,model:$('primary-model').value};if($('primary-url').value)model.base_url=$('primary-url').value;
    await post('/environment',{model,fallbacks,tiers});notice('Model settings saved. Apply job models, then restart the gateway to reload persistent workers.');
  };
  bindAction('test-model','/models/probe');bindAction('apply-models','/jobs/apply-models');
  bindAction('repair-companion','/maintenance/repair');bindAction('activate-routine','/maintenance/activate');bindAction('pause-routine','/maintenance/pause');bindAction('doctor-companion','/maintenance/doctor');
  $('credentials-form').onsubmit=async e=>{e.preventDefault();await post('/credentials',{name:$('credential-name').value,value:$('credential-value').value});$('credential-value').value='';notice('Credential saved. It will not be shown again.');};
  $('review-hooks').onclick=async()=>{const h=await api('/hooks');$('hook-review').innerHTML=`<details open><summary>Commands Hermes will run</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(h.hooks,null,2))}</pre><p class="dim">${esc(h.note)}</p><label>First message<input id="hook-message" value="Hello."></label><button class="act" id="approve-hooks">Approve these hooks and send my first message</button></details>`;bindAction('approve-hooks','/hooks/approve',()=>({digest:h.digest,message:$('hook-message').value}));};
  for(const b of host.querySelectorAll('.gateway-action'))b.onclick=async()=>{const affects=['stop','restart','uninstall','restart-root'].includes(b.dataset.action);if(affects&&!confirm('This can affect every profile served by the owning gateway. Continue?'))return;await action('/gateway/'+b.dataset.action,{affects_all_profiles:affects,root_restarted:false});};
  $('save-gateway-mode').onclick=()=>{if($('gateway-mode').value)return action('/gateway/'+$('gateway-mode').value);};
  if($('archive-profile'))$('archive-profile').onclick=async()=>{const name=prompt('Type '+PROFILE+' to archive it. Stop its gateway first.');if(name===PROFILE)await action('/profile/archive',{confirm:name},()=>navigateProfile('default','roster'));};
  for(const b of host.querySelectorAll('.native-console'))b.onclick=()=>openConsole(b.dataset.console);
  $('advanced-config').onclick=async()=>{
    const data=await api('/config'),entries=[];
    const flatten=(value,prefix='')=>{for(const [key,item] of Object.entries(value)){const path=prefix?prefix+'.'+key:key;if(item==='[configured]')continue;if(item&&typeof item==='object'&&!Array.isArray(item))flatten(item,path);else entries.push([path,item]);}};flatten(data.config);
    $('native-console').innerHTML=`<h3>All Hermes settings</h3><p>Choose a setting to inspect or change. Secret values stay in Accounts and credentials.</p><form id="config-value-form"><label>Find a setting<input id="setting-search" type="search" placeholder="Search settings…"></label><label>Setting<select id="setting-select"></select></label><label id="custom-key-label" hidden>New setting key<input id="config-key" placeholder="terminal.backend"></label><label>Value<div id="setting-value"></div></label><button class="act">Save setting</button></form><details><summary>View complete configuration</summary><pre>${esc(JSON.stringify(data.config,null,2))}</pre></details>`;
    const choices=()=>{$('setting-select').innerHTML=options(entries.filter(([key])=>key.includes($('setting-search').value.toLowerCase())).map(([key])=>[key,key]),'')+'<option value="__custom__">Add another setting…</option>';value();};
    const value=()=>{const key=$('setting-select').value,item=entries.find(([k])=>k===key)?.[1],custom=key==='__custom__';$('custom-key-label').hidden=!custom;$('config-key').required=custom;$('setting-value').innerHTML=typeof item==='boolean'?`<select id="config-value">${options([['true','Enabled'],['false','Disabled']],String(item))}</select>`:typeof item==='number'?`<input id="config-value" type="number" step="any" value="${item}">`:`<textarea id="config-value">${esc(custom?'':typeof item==='string'?item:JSON.stringify(item))}</textarea>`;};
    $('setting-search').oninput=choices;$('setting-select').onchange=value;choices();
    $('config-value-form').onsubmit=async e=>{e.preventDefault();const key=$('setting-select').value==='__custom__'?$('config-key').value:$('setting-select').value;let value=$('config-value').value;const previous=entries.find(([k])=>k===key)?.[1];if(typeof previous!=='string'){try{value=JSON.parse(value);}catch{}}await action('/config',{key,value});};
  };
  // Catalog discovery runs separately so a slow Hermes import doesn't block the workspace.
  api('/providers').then(p=>{if(!host.isConnected||!$('provider-ids'))return;providerRows=p.providers;$('provider-ids').innerHTML=p.providers.map(x=>`<option value="${esc(x.slug)}">${esc(x.label)}</option>`).join('');
    const keys=new Map();for(const row of p.providers)for(const key of row.api_key_env_vars||[])keys.set(key,row.label+' · '+key);
    for(const key of ['TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USERS','DISCORD_BOT_TOKEN','DISCORD_ALLOWED_USERS'])keys.set(key,key);
    $('credential-name').innerHTML=options([...keys],'');$('credential-status').textContent=p.providers.filter(p=>p.credential_configured).map(p=>p.label+' configured').join(' · ')||'No API key detected. OAuth accounts can be managed through Provider sign-in.';
  }).catch(e=>{if($('credential-status'))$('credential-status').textContent=e.message;});
  api('/inference/presets').then(res=>{
    const c=$('inference-presets');
    if(!c||!host.isConnected||!res.presets)return;
    c.innerHTML=res.presets.map(p=>`
      <div style="border:1px solid var(--border);border-radius:8px;padding:12px;background:color-mix(in srgb,var(--ink) 2%,transparent);display:flex;flex-direction:column;justify-content:space-between">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <strong>${esc(p.name)}</strong>
            <span class="pill ${p.ready?'status-good':'status-warn'}" style="font-size:10px">${p.ready?'Key ready':'Key needed'}</span>
          </div>
          <p class="small dim" style="margin-bottom:8px">${esc(p.description)}</p>
          <div class="small dim" style="margin-bottom:8px;font-family:monospace;font-size:11px">
            Primary: <strong>${esc(p.primary.model)}</strong><br>
            Fallbacks: ${p.fallbacks.map(f=>esc(f.model.split('/').pop())).join(' → ')}
          </div>
        </div>
        <button class="act small apply-preset-btn" data-preset-id="${esc(p.id)}" type="button" style="margin-top:8px">Apply Preset</button>
      </div>
    `).join('');
    for(const b of c.querySelectorAll('.apply-preset-btn')){
      b.onclick=async()=>{
        b.disabled=true;b.textContent='Applying…';
        try{
          const r=await post('/inference/apply-preset',{id:b.dataset.presetId});
          notice(r.note||'Preset applied.');
          renderHermesInto(host);
        }catch(err){
          b.disabled=false;b.textContent='Apply Preset';
          notice('Failed to apply preset: '+err.message);
        }
      };
    }
  }).catch(()=>{});
}
function addFallback(row){const el=document.createElement('div');el.className='row';el.style.marginBottom='10px';el.innerHTML=`<label>Provider<input class="fallback-provider" list="provider-ids" value="${esc(row.provider||'')}"></label><label>Model<input class="fallback-model" value="${esc(row.model||'')}" required></label><button class="quiet" type="button" style="flex:0 0 auto;align-self:center">Remove</button>`;el.querySelector('button').onclick=()=>el.remove();$('fallbacks').append(el);}
let consoleId=null,consolePoll=null;
async function openConsole(which){
  const d=await post('/terminal',{action:which});consoleId=d.id;sessionStorage.setItem('console-'+INSTALLATION+'-'+PROFILE,d.id);
  $('native-console').innerHTML=`<h3>Hermes · ${esc(which)}</h3><p class="dim small">Hermes’s own setup, running for this profile. Use the arrow buttons and Enter for menus. Paste a login URL into your browser when Hermes asks. Input is sent directly to Hermes.</p>
  <pre id="terminal-screen" tabindex="0" role="textbox" aria-label="Hermes console" style="background:var(--bg);padding:12px;overflow:auto;font:12px/1.4 monospace;min-height:300px;outline:none"></pre>
  <div class="actions"><button class="quiet term-key" data-key="up">↑</button><button class="quiet term-key" data-key="down">↓</button><button class="quiet term-key" data-key="tab">Tab</button><button class="quiet term-key" data-key="enter">Enter</button><button class="quiet term-key" data-key="escape">Esc</button><button class="quiet term-key" data-key="interrupt">Ctrl-C</button><button class="quiet" id="close-console">Close console</button></div>
  <form id="terminal-input-form"><label>Type or paste a value<input type="password" id="terminal-input" autocomplete="off" placeholder="Input is hidden here; Hermes controls whether it echoes"></label><button class="act">Send input + Enter</button></form>`;
  const keys={up:'\x1b[A',down:'\x1b[B',tab:'\t',enter:'\r',escape:'\x1b',interrupt:'\x03'};
  const send=data=>post('/terminal/'+consoleId+'/input',{data});
  for(const b of $('native-console').querySelectorAll('.term-key'))b.onclick=()=>send(keys[b.dataset.key]);
  $('terminal-input-form').onsubmit=async e=>{e.preventDefault();const v=$('terminal-input').value;$('terminal-input').value='';await send(v+'\r');};
  $('terminal-screen').onkeydown=e=>{const map={ArrowUp:keys.up,ArrowDown:keys.down,ArrowLeft:'\x1b[D',ArrowRight:'\x1b[C',Enter:'\r',Backspace:'\x7f',Tab:'\t',Escape:'\x1b'};const v=map[e.key]||(e.ctrlKey&&e.key==='c'?'\x03':e.key.length===1&&!e.ctrlKey&&!e.metaKey?e.key:null);if(v){e.preventDefault();send(v);}};
  $('close-console').onclick=async()=>{clearTimeout(consolePoll);await post('/terminal/'+consoleId+'/close');sessionStorage.removeItem('console-'+INSTALLATION+'-'+PROFILE);$('native-console').innerHTML='';consoleId=null;};
  async function poll(){if(!consoleId||!$('terminal-screen'))return;const state=await api('/terminal/'+consoleId);$('terminal-screen').textContent=state.screen;if(state.finished){sessionStorage.removeItem('console-'+INSTALLATION+'-'+PROFILE);notice('Hermes console finished. Refresh the page to see updated settings.');return;}consolePoll=setTimeout(poll,350);}
  clearTimeout(consolePoll);await poll();$('native-console').scrollIntoView({behavior:'smooth'});
}
const imageTimeline=renderTimeline;
workspaceHandlers.timeline=async()=>{await imageTimeline();const d=await api('/life');$('timeline').insertAdjacentHTML('afterbegin',heading('A continuing life','Their recorded days, alongside the images you choose to keep.')+`<div class="card"><h2>Recent lived state</h2>${d.events.map(e=>`<div style="padding:12px 0;border-bottom:1px solid var(--edge)"><span class="dim small">${esc(new Date(e.recorded_at).toLocaleString())}</span> <span class="pill">${e.state.confirmed===false?'Carried forward · unconfirmed':'Recorded by companion'}</span><p>${esc(e.state.activity)} · ${esc(e.state.location)}</p><span class="dim">${esc(e.state.mood)}</span></div>`).join('')||'<p class="dim">No lived state yet. After setup, the background routine starts recording their day.</p>'}</div>`);};

