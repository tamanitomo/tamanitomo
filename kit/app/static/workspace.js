/* The workspace uses the same API on desktop and on a future paired mobile client. */
const heading=(title,body)=>`<h2 class="page-title">${esc(title)}</h2><p class="intro">${esc(body)}</p>`;
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
async function boot(){
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
  <div class="grid">${d.profiles.map(p=>`<button class="card profile-card" data-profile="${esc(p.id)}"><div class="avatar">${esc(p.name.slice(0,1))}</div><h3>${esc(p.name)}</h3><span class="pill">${p.installed?esc(p.type||'companion'):'Ready to adopt'}</span><p class="dim small">${esc(p.id)}</p></button>`).join('')||'<div class="card dim">Your first companion starts here.</div>'}</div>
  <div id="onboarding"></div>
  ${d.archives.length?`<div class="card"><h2>Archived profiles</h2>${d.archives.map(a=>`<div class="actions"><span>${esc(a.id)}</span><button class="quiet" data-restore="${esc(a.id)}">Restore</button><button class="quiet" data-purge="${esc(a.id)}">Delete permanently</button></div>`).join('')}</div>`:''}`;
  if($('guide-install-hermes'))bindAction('guide-install-hermes','/install');
  if($('guide-create-companion'))$('guide-create-companion').onclick=()=>onboarding(false);
  if($('guide-goto-env'))$('guide-goto-env').onclick=()=>navigateProfile(PROFILE||'default','environment');
  if($('guide-goto-chat'))$('guide-goto-chat').onclick=()=>navigateProfile(PROFILE||'default','now');
  $('create-companion').onclick=()=>onboarding(false);
  bindAction('install-hermes','/install');
  for(const b of $('roster').querySelectorAll('[data-profile]'))b.onclick=()=>{const p=d.profiles.find(p=>p.id===b.dataset.profile);if(p.installed)navigateProfile(p.id,'companion-edit');else navigateProfile(p.id,'environment');};
  for(const b of $('roster').querySelectorAll('[data-restore]'))b.onclick=async()=>{const name=prompt('Original profile name:');if(name)await action('/profile/restore',{archive:b.dataset.restore,profile:name},()=>render('roster'));};
  for(const b of $('roster').querySelectorAll('[data-purge]'))b.onclick=async()=>{const name=prompt('Permanently delete this archived profile, including its sessions. The external vault stays intact. Type the full archive name:\n'+b.dataset.purge);if(name===b.dataset.purge)await action('/profile/purge',{archive:name,confirm:name},()=>render('roster'));};
};
/* The create/adopt flow lives in onboarding.js, which defines window.onboarding(). */
let chatPageGeneration=0;
workspaceHandlers.chat=async()=>{
  const pageGeneration=++chatPageGeneration;
  const [d,emotions]=await Promise.all([api('/sessions'),api('/feelings').catch(()=>null)]);
  if(current!=='chat'||pageGeneration!==chatPageGeneration)return;
  chatSession=chatSession||sessionStorage.getItem(chatKey('session'));
  if(chatSession&&!d.sessions.some(s=>s.id===chatSession))d.sessions.push({id:chatSession,title:'Saved conversation',source:'history'});
  const moodLabel=emotions?.intimacy?`${emotions.intimacy.stage_badge} · ${emotions.intimacy.score}%`:(emotions?.state?.mood||'How things feel');
  const channelIcons={telegram:'📱 Telegram',discord:'💬 Discord',cli:'💻 Terminal',terminal:'💻 Terminal',desktop:'🌐 Web',history:'📜 History'};
  const sessionLabel=s=>(channelIcons[s.source]||('💬 '+(s.source||'Web')))+' — '+(s.title||(s.id?s.id.slice(0,14):'Conversation'));
  $('chat').innerHTML=
  `<div class="card conversation-card"><div class="conversation-header"><div class="avatar">${esc(chatName().slice(0,1))}</div><div><strong>${esc(chatName())}</strong><div class="dim small">${emotions?.state?.enabled||emotions?.intimacy?`<button type="button" class="link-button small" id="chat-feeling" title="View intimacy escalation, feelings, and routines">${esc(moodLabel)}</button>`:'Your shared conversation'}</div></div><button class="quiet" id="new-chat">New chat</button></div><details class="conversation-history"><summary>Conversations & channels</summary><label>Conversation<select id="session-select"><option value="">✨ New conversation</option>${options(d.sessions.map(s=>[s.id,sessionLabel(s)]),chatSession)}</select></label><button type="button" class="quiet" id="older-sessions" ${d.next_cursor?'':'hidden'}>Load older conversations</button></details>
  <div class="chat-archive-controls" id="chat-archive-controls" hidden><button type="button" class="quiet" id="older-messages">Load older messages</button><span class="dim small" id="history-status" role="status"></span></div>
  <div id="chat-log" class="chat-log" role="log" aria-live="polite"></div>
  <form id="chat-form"><label class="sr-only" for="chat-message">Your message</label><textarea rows="1" id="chat-message" placeholder="What’s on your mind?" required maxlength="30000"></textarea><div class="actions"><button class="act" id="send-message">Send</button><span class="dim small" id="chat-status" role="status">Enter to send · Shift+Enter for a new line</span></div></form></div>`;
  if($('chat-feeling'))$('chat-feeling').onclick=()=>showTab('relationship');
  let sessionsCursor=d.next_cursor;
  $('older-sessions').onclick=async()=>{
    const button=$('older-sessions');button.disabled=true;button.textContent='Loading conversations…';
    try{
      const page=await api('/sessions?before='+encodeURIComponent(sessionsCursor));
      if(current!=='chat'||pageGeneration!==chatPageGeneration)return;
      const select=$('session-select');
      for(const row of page.sessions){const existing=[...select.options].find(o=>o.value===row.id);const label=sessionLabel(row);if(existing)existing.textContent=label;else select.insertAdjacentHTML('beforeend',options([[row.id,label]],chatSession));}
      sessionsCursor=page.next_cursor;button.hidden=!sessionsCursor;
    }finally{button.disabled=false;button.textContent='Load older conversations';}
  };
  $('session-select').onchange=async e=>{chatSession=e.target.value||null;sessionStorage.setItem(chatKey('session'),chatSession||'');await loadChat();};
  $('new-chat').onclick=()=>{stopBrowserVoice();chatSession=null;sessionStorage.removeItem(chatKey('session'));workspaceHandlers.chat();};
  await loadChat();
  mountBrowserVoice();
  voiceControlsBusy(Boolean(activeOperation));
  $('chat-message').value=sessionStorage.getItem(chatKey('draft'))||'';
  $('chat-message').oninput=e=>{sessionStorage.setItem(chatKey('draft'),e.target.value);e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,220)+'px';};
  $('chat-message').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('send-message').disabled)$('chat-form').requestSubmit();}};
  $('chat-form').onsubmit=async e=>{
    e.preventDefault();const message=$('chat-message').value;
    if(!message.trim())return;
    if(activeOperation)throw Error('Wait for the current action to finish.');
    sessionStorage.setItem(chatKey('draft'),message);
    $('send-message').disabled=true;$('session-select').disabled=true;$('new-chat').disabled=true;$('chat-message').readOnly=true;
    if($('chat-status'))$('chat-status').textContent='Waiting for '+chatName()+'…';
    const box=$('chat-log');box.querySelector('.chat-welcome')?.remove();
    const tempId='turn-'+Date.now();
    box.insertAdjacentHTML('beforeend',`<div class="bubble user sending" id="${tempId}"><div class="message-body">${richText(message)}</div><small><span class="bubble-sender">You</span> · <span class="bubble-status">Sending…</span></small></div><div class="bubble companion typing-indicator" id="chat-typing-indicator" role="status" aria-label="${esc(chatName())} is thinking"><div class="typing-dots"><span></span><span></span><span></span></div><small>${esc(chatName())} is thinking…</small></div>`);
    box.scrollTo({top:box.scrollHeight,behavior:'smooth'});
    $('chat-message').value='';
    $('chat-message').style.height='auto';
    try{
      const result=await action('/chat',{message,session:chatSession},async r=>{
        $('chat-typing-indicator')?.remove();
        const pendingBubble=$(tempId);
        const nowAt=new Date();
        const timeStr=nowAt.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
        if(pendingBubble){
          pendingBubble.classList.remove('sending');
          const statusEl=pendingBubble.querySelector('.bubble-status');
          if(statusEl)statusEl.textContent=timeStr;
        }
        chatSession=r.session||chatSession;
        sessionStorage.setItem(chatKey('session'),chatSession||'');
        sessionStorage.removeItem(chatKey('draft'));
        if(current!=='chat'){notice('Reply received from '+chatName()+'. Open Conversation to read it.');return;}
        if(r.session&&$('session-select')&&![...$('session-select').options].some(o=>o.value===r.session)){
          const label=(r.session.slice(0,14))+' · new';
          $('session-select').insertAdjacentHTML('beforeend',`<option value="${esc(r.session)}" selected>${esc(label)}</option>`);
          $('session-select').value=r.session;
        }
        const replyObj=(r.messages||[]).filter(m=>m.role==='assistant').at(-1);
        const rawReplyText=replyObj?.content||r.response||'';
        const replyAttachments=[...(replyObj?.attachments||[])];
        const {text:replyText,extractedMedia}=extractMediaFromContent(rawReplyText);
        replyAttachments.push(...extractedMedia);
        if(replyText||replyAttachments.length){
          box.insertAdjacentHTML('beforeend',`<div class="bubble animate-in"><div class="message-body">${richText(replyText)}</div>${replyAttachments.map(inlineMedia).join('')}<small>${esc(chatName())} · ${esc(timeStr)}</small></div>`);
        }
        box.scrollTo({top:box.scrollHeight,behavior:'smooth'});
        $('send-message').disabled=false;$('session-select').disabled=false;$('new-chat').disabled=false;$('chat-message').readOnly=false;
        if($('chat-status'))$('chat-status').textContent='Enter to send · Shift+Enter for a new line';
        $('chat-message').focus();
        await speakBrowserReply(r);
      });
      if(result.status!=='complete')throw Error(result.error||'Message could not be completed. Your draft is saved.');
    }catch(error){
      $('chat-typing-indicator')?.remove();
      voiceReplyRequested=false;
      const pendingBubble=$(tempId);
      if(pendingBubble){
        pendingBubble.classList.remove('sending');
        pendingBubble.classList.add('send-error');
        const statusEl=pendingBubble.querySelector('.bubble-status');
        if(statusEl)statusEl.innerHTML='<span class="bad">Failed to send</span>';
      }
      $('chat-message').value=message;
      $('chat-message').style.height='auto';
      $('chat-message').style.height=Math.min($('chat-message').scrollHeight,220)+'px';
      if($('chat-status'))$('chat-status').textContent='Could not finish. Your draft is saved; you can retry.';
      $('send-message').disabled=false;$('session-select').disabled=false;$('new-chat').disabled=false;$('chat-message').readOnly=false;
      throw error;
    }
  };
};
let chatLoadGeneration=0;
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
  let lastDay='';
  return messages.map(m=>{const at=new Date(m.timestamp*1000),day=at.toLocaleDateString();const divider=day!==lastDay?`<div class="chat-day">${esc(day)}</div>`:'';lastDay=day;const {text,extractedMedia}=extractMediaFromContent(m.content);const allAttachments=[...(m.attachments||[]),...extractedMedia];return divider+`<div class="bubble ${m.role==='user'?'user':''}"><div class="message-body">${richText(text)}</div>${allAttachments.map(inlineMedia).join('')}<small>${m.role==='user'?'You':esc(chatName())} · ${esc(at.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}</small></div>`;}).join('');
}
async function loadChat(){
  const generation=++chatLoadGeneration,requestedSession=chatSession;
  const d=chatSession?await api('/sessions/'+encodeURIComponent(chatSession)):{messages:[]};
  if(current!=='chat'||!$('chat-log')||generation!==chatLoadGeneration||requestedSession!==chatSession)return;
  $('chat-log').innerHTML=chatMessagesHtml(d.messages)||`
    <div class="chat-welcome">
      <div class="avatar">${esc(chatName().slice(0,1))}</div>
      <h2>A little time with ${esc(chatName())}</h2>
      <p>Say hello, pick up a thought, or ask what’s on their mind.</p>
      <div class="welcome-prompts" style="display:flex;gap:8px;justify-content:center;margin-top:14px;flex-wrap:wrap">
        <button class="quiet small welcome-prompt" type="button">Hey, how are you feeling right now?</button>
        <button class="quiet small welcome-prompt" type="button">What are you thinking about today?</button>
        <button class="quiet small welcome-prompt" type="button">Good morning! Ready for the day?</button>
      </div>
    </div>`;
  for(const b of $('chat-log').querySelectorAll('.welcome-prompt')){
    b.onclick=()=>{
      $('chat-message').value=b.textContent;
      $('chat-message').focus();
      $('chat-message').dispatchEvent(new Event('input'));
    };
  }
  mountOlderMessages(d.next_cursor,generation,requestedSession);
  $('chat-log').scrollTop=$('chat-log').scrollHeight;
}
function mountOlderMessages(cursor,generation,session){
  const controls=$('chat-archive-controls');if(!controls)return;
  controls.hidden=!cursor;
  const button=$('older-messages');
  const log=$('chat-log');
  if(log){
    log.onscroll=()=>{
      if(log.scrollTop<60 && !button.disabled && !button.hidden){
        button.click();
      }
    };
  }
  button.onclick=async()=>{
    button.disabled=true;button.textContent='Loading earlier messages…';
    try{
      const page=await api('/sessions/'+encodeURIComponent(session)+'?before='+encodeURIComponent(cursor));
      if(current!=='chat'||generation!==chatLoadGeneration||session!==chatSession)return;
      const height=log.scrollHeight,top=log.scrollTop;
      log.insertAdjacentHTML('afterbegin',chatMessagesHtml(page.messages));
      log.scrollTop=top+log.scrollHeight-height;
      cursor=page.next_cursor;button.hidden=!cursor;
      $('history-status').textContent=page.messages.length+' earlier messages loaded'+(cursor?'':' · beginning of conversation');
    }finally{button.disabled=false;button.textContent='Load older messages';}
  };
}

function inlineMedia(item){const url=mediaUrl(item.url);const p=item.path?` data-photo-path="${esc(item.path)}"`:'';const u=` data-photo-url="${esc(item.url)}"`;if(item.kind==='image'&&item.blur)return `<details class="media-reveal"><summary><img class="chat-media concealed-media" src="${url}" alt="Concealed image"><span>Reveal sensitive or unreviewed image</span></summary><div class="chat-media-card" onclick="openChatPhoto(this.querySelector('img'))"${p}${u}><img class="chat-media" src="${url}" alt="${esc(item.title)}" loading="lazy"></div></details>`;return item.kind==='image'?`<div class="chat-media-card" onclick="openChatPhoto(this.querySelector('img'))"${p}${u}><img class="chat-media" src="${url}" alt="${esc(item.title)}" loading="lazy"><div class="chat-media-bar"><span class="chat-media-caption">${esc(item.title||'Photo')}</span><button type="button" class="chat-media-zoom">Zoom 🔍</button></div></div>`:item.kind==='audio'?`<div class="chat-audio-card"><audio class="chat-media" controls preload="metadata" src="${url}"></audio><div class="chat-audio-caption">🎵 ${esc(item.title||'Voice note')}</div></div>`:item.kind==='video'?`<video class="chat-media" controls preload="none" src="${url}"></video>`:'';}
function openChatPhoto(imgEl){if(!imgEl)return;const card=imgEl.closest('.chat-media-card');const path=card?.dataset.photoPath||'';const url=card?.dataset.photoUrl||imgEl.src;const title=imgEl.alt||'Photo';if(typeof openPhotoViewer==='function'){openPhotoViewer({url,path,title,at:new Date().toISOString()});}else{window.open(url,'_blank');}}
function renderIntimacyCard(intimacy, companionName){
  if(!intimacy)return '';
  const score=intimacy.score||0;
  const stage=intimacy.stage||0;
  const stageName=esc(intimacy.stage_name||'Just Met');
  const paceLabel={slow:'Gradual rhythm',natural:'Natural rhythm',quick:'Quick familiarity'}[intimacy.pace]||intimacy.pace;
  const adultStatus=intimacy.permanent_friend?'<span class="pill bad">Friendship</span>':intimacy.nsfw_revoked?'<span class="pill">Friendship</span>':intimacy.explicit_opted_in?'<span class="pill good">Romantic connection open</span>':'<span class="pill">Friendly connection</span>';
  const stages=['Just Met','Flirting','Chemistry','Intimacy','Bonded'];
  return `<div class="card intimacy-escalation-card" style="margin-bottom:20px;border-top:3px solid var(--accent)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
      <div>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:20px">💖</span>
          <h2 style="margin:0">Relationship & Connection Dynamic</h2>
          <span class="pill ${stage>=3?'good':''}">${stageName}</span>
        </div>
        <p class="dim small" style="margin:4px 0 0;max-width:560px">${esc(intimacy.description)}</p>
      </div>
      <div style="text-align:right">
        <div style="font-size:20px;font-weight:700;color:var(--accent)">${stageName}</div>
        <div class="dim small">${paceLabel}</div>
      </div>
    </div>
    <div style="margin:16px 0 10px">
      <div style="height:10px;background:color-mix(in srgb,var(--ink) 8%,transparent);border-radius:6px;overflow:hidden;position:relative">
        <div style="height:100%;width:${score}%;background:linear-gradient(90deg,var(--accent),var(--accent),var(--accent));border-radius:6px;transition:width 0.3s ease"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:11px;color:color-mix(in srgb,var(--ink) 50%,transparent);margin-top:6px">
        ${stages.map((stg,idx)=>`<span style="${stage>=idx?'color:#fff;font-weight:600':''}">${stg}</span>`).join('')}
      </div>
    </div>
    ${intimacy.permanent_friend?`
    <div class="card" style="margin-top:14px;background:color-mix(in srgb,var(--bad) 8%,transparent);border-left:4px solid var(--bad);padding:14px">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:18px">🤝</span>
        <strong style="color:var(--bad);font-size:14px">Friendship Established</strong>
      </div>
      <p class="dim small" style="margin:6px 0 0;line-height:1.45">Following repeated boundary violations, trust was fractured. ${esc(companionName)} has stepped back to friendship. Private and romantic closeness is closed.</p>
    </div>`:intimacy.nsfw_revoked?`
    <div class="card" style="margin-top:14px;background:color-mix(in srgb,var(--ink) 3%,transparent);border-left:4px solid var(--dim);padding:14px">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:18px">🕊️</span>
        <strong style="color:var(--ink-2);font-size:14px">Relationship Stepped Back</strong>
      </div>
      <p class="dim small" style="margin:6px 0 0;line-height:1.45">Your relationship is rooted in friendship and affectionate companionship.</p>
    </div>`:''}
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:14px">
      <div style="background:color-mix(in srgb,var(--ink) 3%,transparent);padding:14px;border-radius:10px;border:1px solid color-mix(in srgb,var(--ink) 6%,transparent)">
        <strong style="font-size:13px;display:block;margin-bottom:6px">💬 Connection & Chemistry</strong>
        <p class="dim small" style="margin:0;line-height:1.45">Companions naturally banter, tease, and reciprocate affection as mutual trust deepens. At Stage 4 (Bonded), warmth, closeness, and affection unfold organically in private moments without artificial pressure.</p>
      </div>
      <div style="background:color-mix(in srgb,var(--ink) 3%,transparent);padding:14px;border-radius:10px;border:1px solid color-mix(in srgb,var(--ink) 6%,transparent)">
        <strong style="font-size:13px;display:block;margin-bottom:6px">🔒 Agency & Mutual Respect</strong>
        <p class="dim small" style="margin:0;line-height:1.45">${esc(companionName)} holds genuine agency. Mutual respect is essential; repeated boundary violations will cause your companion to step back to friendship.</p>
      </div>
    </div>
    ${intimacy.violations_count?`<div style="margin-top:12px;padding:10px 14px;background:color-mix(in srgb,var(--bad) 12%,transparent);border-left:3px solid var(--bad);border-radius:6px"><strong style="color:var(--bad);font-size:12.5px">⚠️ Boundary Violations Recorded (${intimacy.violations_count} / 2)</strong><p class="dim small" style="margin:2px 0 0">${intimacy.violations_count>=2?'Two violations occurred. Relationship has stepped back to friendship.':'A boundary violation was recorded. Mutual respect and space are required for trust to rebuild.'}</p></div>`:''}
    <div style="display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap">
      ${adultStatus}
    </div>
  </div>`;
}
function connectionSignals(bars){
  if(!bars)return '';
  if(bars.feelings)return feelingsSummary(bars.feelings);
  const rows=[['Feeling the gap',bars.feeling_the_gap,'Based on time since your last message.','⏱️'],['Recent wellbeing',bars.wellbeing,'Based on the last recorded moods.','🌱']];
  return `<div class="card connection-signals"><h2>How things feel lately</h2><div class="row" style="gap:16px;margin-top:12px">${rows.map(([label,value,description,emoji])=>{
    const pct=value==null?null:Math.round(value*100);
    return `<div class="signal" style="background:var(--panel);border:1px solid var(--surface-3);border-radius:10px;padding:14px;flex:1">
      <div class="signal-heading" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-weight:600;font-size:13.5px">${emoji} ${esc(label)}</span>
        <strong style="color:${pct!=null?(pct>65?'var(--good)':pct>35?'var(--warn)':'var(--bad)'):'var(--dim)'}">${pct==null?'Not enough history':pct+'%'}</strong>
      </div>
      ${value==null?'':`<div style="background:var(--surface-2);height:6px;border-radius:3px;overflow:hidden;margin:8px 0 6px"><div style="background:linear-gradient(90deg,var(--accent),var(--good));height:100%;width:${Math.max(0,Math.min(100,pct))}%;border-radius:3px;transition:width .3s"></div></div>`}
      <p class="dim small" style="margin:0">${description}</p>
    </div>`;
  }).join('')}</div><p class="dim small" style="margin-top:10px">These indicators describe recent state, not relationship progress.</p></div>`;
}
workspaceHandlers.relationship=async()=>{
  const d=await api('/relationship');const s=d.settings;
  const companionName=chatName()||'Your companion';
  $('relationship').innerHTML=heading('Your story together','Small firsts, familiar rituals, and jokes that only make sense between you. A shared history grows through experience.')+
  connectionSignals(d.bars)+
  renderIntimacyCard(d.intimacy,companionName)+
  `<div class="story-hero-card">
    <div class="story-hero-text">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
        <span style="font-size:24px">✨</span>
        <h3 style="margin:0">Shared Journey with ${esc(companionName)}</h3>
      </div>
      <p class="dim" style="margin:0;max-width:560px">Milestones, memorable moments, and personal history that define your relationship over time.</p>
    </div>
    <div style="display:flex;gap:16px;align-items:center">
      <div style="text-align:right">
        <div style="font-size:20px;font-weight:700;color:#fff">${d.moments?d.moments.length:0}</div>
        <div class="dim small">Moments recorded</div>
      </div>
      ${d.milestones?`<div style="text-align:right">
        <div style="font-size:20px;font-weight:700;color:var(--warn)">${d.milestones.filter(m=>m.earned).length} / ${d.milestones.length}</div>
        <div class="dim small">Milestones earned</div>
      </div>`:''}
    </div>
  </div>`+
  (s.relationship_progression==='milestones'?`
  <div class="card" style="margin-bottom:20px">
    <h2>Relationship Milestones</h2>
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
  `<div class="card" style="margin-top:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div>
        <h2 style="margin:0">Shared History (${d.moments.length})</h2>
        <p class="dim small" style="margin:2px 0 0">Memorable moments and milestones preserved through your time together.</p>
      </div>
      <span class="dim small">Authentic ledger</span>
    </div>
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
workspaceHandlers.environment=async()=>{
  const d=await api('/environment');envState=d;
  const gateway=await api('/gateway');
  const known=roster.find(p=>p.id===PROFILE);
  $('environment').innerHTML=heading('Hermes settings','Manage the Hermes environment behind this companion. Providers, backups, and scheduled routines all live in Hermes’s own configuration.')+
  `<div class="card"><h2>Installation</h2><p><span class="pill">${d.runtime.managed?'Kit-managed':'Existing Hermes'}</span> <span class="dim small">${esc(d.runtime.root)}</span></p>
  <div class="actions">${!d.runtime.available?'<button class="act" id="env-install">Install Hermes</button>':'<button class="quiet" id="check-version">Check version</button><button class="quiet" id="update-hermes">Update Hermes</button>'}
  ${known&&!known.installed?'<button class="act" id="adopt-companion">Adopt as a companion</button>':''}</div><p class="dim small">The vault lives outside Hermes’s code checkout. Updates are handled by Hermes; run Health checks afterwards.</p></div>
  <div class="card"><h2>Local companion stack</h2><p>Install a local conversation model on the Hermes host, then choose image and voice engines for this companion.</p><div class="actions"><button class="act" id="open-local-models">Local models</button><button class="quiet" id="env-stack-images">Image studio</button><button class="quiet" id="env-stack-voice">Voice studio</button></div></div>
  ${d.runtime.available?`<div class="card" data-environment-group="1"><h2>Inference Presets & Free Cascades</h2><p class="dim small">One-click model cascades. Automatically sets your primary model and ordered fallbacks for zero downtime.</p><div id="inference-presets" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:10px"></div></div>
  <div class="card" data-environment-group="1"><h2>Models and fallbacks</h2><p class="dim small">Choose a model available to your account. A configured model is not yet a tested response.</p><datalist id="provider-ids"></datalist>
  <form id="models-form"><div class="form-grid"><label>Primary provider<input id="primary-provider" list="provider-ids" value="${esc(d.model.provider)}" placeholder="openrouter"></label><label>Primary model<input id="primary-model" value="${esc(d.model.default)}" placeholder="provider/model-name" required></label><label class="wide">Custom base URL (optional)<input id="primary-url" type="url" value="${esc(d.model.base_url)}" placeholder="http://localhost:11434/v1"></label></div>
  <details open><summary>Ordered fallback providers</summary><p class="dim small">Hermes tries this chain when the primary is unavailable. No provider chain can cover a complete network outage.</p><div id="fallbacks"></div><button class="quiet" id="add-fallback" type="button">Add a fallback</button></details>
  <details><summary>Models for background jobs</summary><div class="form-grid">${['loops','reflection'].map(t=>`<label>${t} provider<input id="tier-${t}-provider" list="provider-ids" value="${esc(d.tiers[t]?.provider||'')}"></label><label>${t} model<input id="tier-${t}-model" value="${esc(d.tiers[t]?.model||'')}" placeholder="Follow profile default"></label><label>${t} reasoning<select id="tier-${t}-effort">${options([['','Hermes default'],['none','None'],['low','Low'],['medium','Medium'],['high','High']],d.tiers[t]?.reasoning_effort||'')}</select></label>`).join('')}</div></details>
  <div class="actions"><button class="act">Save model configuration</button><button class="quiet" id="test-model" type="button">Test saved model chain</button><button class="quiet" id="apply-models" type="button">Apply job models</button></div></form><p class="dim small">${esc(d.restart_note)}</p></div>
  <div class="card" data-environment-group="1"><h2>Accounts and credentials</h2><p class="dim">For ChatGPT or Grok account sign-in, choose Account sign-in / OAuth and select the provider in Hermes’s menu. The available login methods come from your installed Hermes version. You can also use an API key below. Stored keys are never sent back to this page.</p>
  <form id="credentials-form"><div class="form-grid"><label>Credential<select id="credential-name"><option>Loading provider catalog…</option></select></label><label>Value (blank removes it)<input id="credential-value" type="password" autocomplete="new-password"></label></div><div class="actions"><button class="act">Save credential</button></div></form><div id="credential-status" class="dim small"></div>
  <div class="actions"><button class="quiet native-console" data-console="models">Account sign-in / OAuth</button><button class="quiet native-console" data-console="messaging">Telegram & messaging</button><button class="quiet native-console" data-console="tools">Tools, voice, images & MCP</button><button class="quiet native-console" data-console="setup">Full Hermes setup</button><button class="quiet" id="advanced-config">All Hermes settings</button></div><div id="native-console"></div></div>
  <div class="card" data-environment-group="2" id="gateway-controls"><h2>Gateway & background life</h2><p class="dim">Closing this app leaves an independently running Hermes gateway and its enabled jobs running. The host must stay awake; photos require an enabled schedule and working image provider.</p><div class="grid">${Object.entries(gateway.preflight.checks).map(([key,value])=>`<div><span class="pill ${value?'status-good':'status-warn'}">${value?'Verified':'Not verified'}</span><p class="small">${esc(key.replaceAll('_',' '))}</p></div>`).join('')}</div><p class="small dim">Gateway owner: ${esc(gateway.preflight.owner_home)}</p>${gateway.preflight.notes.map(n=>`<p class="small warn">${esc(n)}</p>`).join('')}<p class="dim">Review the hooks once, verify the provider, then start the gateway and activate the routine. Model-free maintenance remains active when the routine is paused.</p>
  <div class="actions"><button class="quiet" id="review-hooks">Review & approve hooks</button><button class="quiet" id="repair-companion">Install / repair jobs</button><button class="act" id="activate-routine">Activate routine</button><button class="quiet" id="pause-routine">Pause routine</button><button class="quiet" id="doctor-companion">Check installation</button></div><div id="hook-review"></div>
  <details open><summary>Gateway service controls</summary><div class="actions">${['status','install','start','stop','restart','uninstall','restart-root'].map(a=>`<button class="quiet gateway-action" data-action="${a}">${a[0].toUpperCase()+a.slice(1)}</button>`).join('')}</div>
  <label>Gateway ownership<select id="gateway-mode"><option value="">Keep current ownership</option><option value="shared">Use the shared root gateway</option><option value="dedicated">Use this profile’s own gateway</option></select></label><button class="quiet" id="save-gateway-mode">Apply ownership</button><p class="dim small">Changing ownership can require restarting the root gateway. A shared gateway restart affects all profiles it serves.</p></details></div>
  ${PROFILE&&PROFILE!=='default'?`<div class="card"><h2>Profile lifecycle</h2><p class="dim">Archive this profile to remove it from the roster. Its external vault stays intact, and you can restore the profile later.</p><button class="quiet" id="archive-profile">Archive ${esc(PROFILE)}</button></div>`:''}`:''}
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
  for(const b of $('environment').querySelectorAll('.gateway-action'))b.onclick=async()=>{const affects=['stop','restart','uninstall','restart-root'].includes(b.dataset.action);if(affects&&!confirm('This can affect every profile served by the owning gateway. Continue?'))return;await action('/gateway/'+b.dataset.action,{affects_all_profiles:affects,root_restarted:false});};
  $('save-gateway-mode').onclick=()=>{if($('gateway-mode').value)return action('/gateway/'+$('gateway-mode').value);};
  if($('archive-profile'))$('archive-profile').onclick=async()=>{const name=prompt('Type '+PROFILE+' to archive it. Stop its gateway first.');if(name===PROFILE)await action('/profile/archive',{confirm:name},()=>navigateProfile('default','roster'));};
  for(const b of $('environment').querySelectorAll('.native-console'))b.onclick=()=>openConsole(b.dataset.console);
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
  api('/providers').then(p=>{if(current!=='environment'||!$('provider-ids'))return;providerRows=p.providers;$('provider-ids').innerHTML=p.providers.map(x=>`<option value="${esc(x.slug)}">${esc(x.label)}</option>`).join('');
    const keys=new Map();for(const row of p.providers)for(const key of row.api_key_env_vars||[])keys.set(key,row.label+' · '+key);
    for(const key of ['TELEGRAM_BOT_TOKEN','TELEGRAM_ALLOWED_USERS','DISCORD_BOT_TOKEN','DISCORD_ALLOWED_USERS'])keys.set(key,key);
    $('credential-name').innerHTML=options([...keys],'');$('credential-status').textContent=p.providers.filter(p=>p.credential_configured).map(p=>p.label+' configured').join(' · ')||'No API key detected. OAuth accounts can be managed through Provider sign-in.';
  }).catch(e=>{if($('credential-status'))$('credential-status').textContent=e.message;});
  api('/inference/presets').then(res=>{
    const c=$('inference-presets');
    if(!c||current!=='environment'||!res.presets)return;
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
          workspaceHandlers.environment();
        }catch(err){
          b.disabled=false;b.textContent='Apply Preset';
          notice('Failed to apply preset: '+err.message);
        }
      };
    }
  }).catch(()=>{});
};
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
const originalHealth=renderHealth;
workspaceHandlers.health=async()=>{await originalHealth();const d=await api('/jobs');$('health').insertAdjacentHTML('afterbegin',heading('Keeping life running','Inspect individual jobs, queue a run, or change a schedule. Hermes remains the scheduler.')+`<div class="card"><h2>Job controls</h2><div class="actions"><button class="quiet" id="job-history">Recent run history</button></div>${d.jobs.map(j=>`<div class="actions"><span style="flex:1">${esc(j.name)} <span class="dim small">${esc(j.schedule?.expr||'')}</span></span><button class="quiet job-control" data-job="${esc(j.id)}" data-action="run">Run next tick</button>${!j.no_agent?`<button class="quiet job-control" data-job="${esc(j.id)}" data-action="${j.enabled?'pause':'resume'}">${j.enabled?'Pause':'Resume'}</button>`:''}<button class="quiet job-control" data-job="${esc(j.id)}" data-action="edit">Schedule</button></div>`).join('')||'<p class="dim">No jobs installed yet. Use Install / repair jobs in Hermes & providers.</p>'}</div>`);bindAction('job-history','/jobs/history');for(const b of $('health').querySelectorAll('.job-control'))b.onclick=()=>{const payload={};if(b.dataset.action==='edit'){const schedule=prompt('New cron expression or Hermes schedule:');if(!schedule)return;payload.schedule=schedule;}return action('/jobs/'+encodeURIComponent(b.dataset.job)+'/'+b.dataset.action,payload);};};
const imageTimeline=renderTimeline;
workspaceHandlers.timeline=async()=>{await imageTimeline();const d=await api('/life');$('timeline').insertAdjacentHTML('afterbegin',heading('A continuing life','Their recorded days, alongside the images you choose to keep.')+`<div class="card"><h2>Recent lived state</h2>${d.events.map(e=>`<div style="padding:12px 0;border-bottom:1px solid var(--edge)"><span class="dim small">${esc(new Date(e.recorded_at).toLocaleString())}</span> <span class="pill">${e.state.confirmed===false?'Carried forward · unconfirmed':'Recorded by companion'}</span><p>${esc(e.state.activity)} · ${esc(e.state.location)}</p><span class="dim">${esc(e.state.mood)}</span></div>`).join('')||'<p class="dim">No lived state yet. After setup, the background routine starts recording their day.</p>'}</div>`);};

