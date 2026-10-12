/* Shared time is local state. Starting it does not turn on a camera or microphone. */
function sharedTimeHtml(data){
  const live=data.sessions||[];
  const recent=(data.recent_sessions||[]).filter(s=>!live.some(x=>x.id===s.id)).slice(-2).reverse();
  const sessionCard=s=>`<article class="shared-session" data-session="${esc(s.id)}">
    <div class="shared-session-title"><strong>${esc(s.title)}</strong><span class="dim">${esc(s.state)}</span></div>
    <p class="dim small">${s.mode==='manual'?'Progress comes from what you share.':'Playback comes from your media server.'} ${s.comments==='quiet'?'Quiet company.':'Occasional comments welcome.'}</p>
    ${['active','paused'].includes(s.state)?`<div class="actions"><button class="quiet" type="button" data-shared-action="${s.state==='paused'?'resume':'pause'}">${s.state==='paused'?'Resume together':'Pause together'}</button><button class="quiet" type="button" data-shared-action="stop">Finish together</button></div>
      <form class="shared-checkpoint" data-shared-form="report"><label>Where are you up to?<input name="text" maxlength="400" required placeholder="We just met the detective…"></label><button class="quiet" type="submit">Share progress</button></form>`:''}
    ${s.report?`<p class="small">You shared: ${esc(s.report.text)}</p>`:''}
    <form class="shared-checkpoint" data-shared-form="moment"><label>A moment to remember<input name="text" maxlength="350" required placeholder="Something that made this time ours…"></label><button class="quiet" type="submit">Keep this moment</button></form>
  </article>`;
  return `<p class="dim">Pick something to watch and spend a little time together. You can also start by asking in chat.</p>
    ${live.map(sessionCard).join('')}
    <details ${live.length?'':'open'}><summary>Start watching together</summary>
      <form id="shared-start" class="shared-start">
        <label>Film or series<input name="title" required maxlength="120" placeholder="What are we watching?"></label>
        <div class="form-grid"><label>Company<select name="comments"><option value="occasional">Occasional comments</option><option value="quiet">Quiet company</option></select></label>
        <label>Progress<select name="mode"><option value="auto">Use my media server if connected</option><option value="manual">I'll share where we're up to</option></select></label>
        <label>For up to<select name="hours"><option value="1">1 hour</option><option value="2">2 hours</option><option value="3" selected>3 hours</option><option value="4">4 hours</option><option value="8">8 hours</option></select></label></div>
        <button class="act" type="submit">Start together</button>
      </form>
    </details>
    ${recent.length?`<details class="shared-recent"><summary>Recent shared time</summary>${recent.map(sessionCard).join('')}</details>`:''}
    ${(data.moments||[]).length?`<div class="shared-moments">${data.moments.slice(-3).reverse().map(m=>`<p>“${esc(m.text)}”</p>`).join('')}</div>`:''}
    <button type="button" class="quiet" data-shared-refresh>Refresh shared time</button>
    <p class="small dim" id="shared-status" role="status"></p>`;
}

function musicSuggestionsHtml(rows,enabled=true){
  const off=enabled?'':'<p class="dim">Music is switched off, so your companion does not read Spotify or pick albums. Turn on Music under Settings → Sensors to allow it.</p>';
  if(!rows.length)return off||'<p class="dim">Albums chosen for you will appear here, with the reason they brought you to mind. Ask in chat for an album from an artist you love; a Spotify connection lets your companion look through your listening and the catalog.</p>';
  return off+rows.slice(0,6).map(row=>{
    const album=row.album||{},safe=/^https:\/\/open\.spotify\.com\/album\/[A-Za-z0-9]{22}$/.test(album.url||'');
    const title=esc(album.name||'Album');
    return `<article class="shared-album"><strong>${safe?`<a href="${esc(album.url)}" target="_blank" rel="noopener noreferrer">${title} ↗</a>`:title}</strong><p class="dim small">${esc((album.artists||[]).map(a=>a.name).join(', '))}</p><p>${esc(row.note||'')}</p></article>`;
  }).join('');
}

async function mountSharedTime(host,musicHost){
  const captured=INSTALLATION+':'+PROFILE;
  const current=()=>host.isConnected&&captured===INSTALLATION+':'+PROFILE;
  let busy=false,revision='',request=0;
  const perform=async(path,payload)=>{
    if(busy||!current())return;
    busy=true;request++;
    for(const button of host.querySelectorAll('button'))button.disabled=true;
    const status=host.querySelector('[role=status]');
    if(status)status.textContent='Saving…';
    try{
      const data=await post(path,payload);
      if(current()){revision=JSON.stringify(data);host.innerHTML=sharedTimeHtml(data);host.querySelector('[role=status]').textContent='Saved.';}
    }catch(error){if(current()&&status)status.textContent=error.message||'Could not save. Try again.';}
    finally{busy=false;if(current())for(const button of host.querySelectorAll('button'))button.disabled=false;}
  };
  host.onclick=event=>{
    if(event.target.closest('[data-shared-refresh]')){refresh();return;}
    const button=event.target.closest('[data-shared-action]');
    if(!button)return;
    const id=button.closest('[data-session]').dataset.session;
    perform('/viewing/sessions/'+encodeURIComponent(id)+'/'+button.dataset.sharedAction,{});
  };
  host.onsubmit=event=>{
    event.preventDefault();
    const form=event.target,data=new FormData(form);
    if(form.id==='shared-start')perform('/viewing/sessions',{title:data.get('title'),comments:data.get('comments'),mode:data.get('mode'),hours:Number(data.get('hours'))});
    else if(form.dataset.sharedForm){
      const id=form.closest('[data-session]').dataset.session;
      perform('/viewing/sessions/'+encodeURIComponent(id)+'/'+form.dataset.sharedForm,{text:data.get('text')});
    }
  };
  const refresh=async()=>{
    if(busy||!current()||document.hidden)return;
    const ticket=++request;
    const results=await Promise.allSettled([api('/viewing/sessions'),api('/music/suggestions')]);
    if(!current()||ticket!==request||busy)return;
    if(results[0].status==='fulfilled'){
      const next=JSON.stringify(results[0].value);
      if(next!==revision){
        const hasDraft=Array.from(host.querySelectorAll('input')).some(input=>input.value.trim());
        if(hasDraft){const status=host.querySelector('[role=status]');if(status)status.textContent='Shared time changed. Keep or clear your note before refreshing.';}
        else{revision=next;host.innerHTML=sharedTimeHtml(results[0].value);}
      }
    }else if(!revision)host.innerHTML='<p class="dim">Shared time could not be loaded. Reopen this page to try again.</p>';
    if(musicHost?.isConnected)musicHost.innerHTML=results[1].status==='fulfilled'?musicSuggestionsHtml(results[1].value.suggestions||[],results[1].value.enabled!==false):'<p class="dim">Saved albums could not be loaded.</p>';
  };
  await refresh();
  const onFocus=()=>{if(current())refresh();};
  window.addEventListener('focus',onFocus);
  const timer=setInterval(()=>{
    if(!current()){clearInterval(timer);window.removeEventListener('focus',onFocus);}
    else refresh();
  },60000);
}
