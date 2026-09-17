/* ============================================================================
   Settings — one page.

   Everything that configures anything used to be scattered across three
   top-level pages (Preferences, Hermes settings, Jobs & health) with their own
   sub-tab strips, plus loose cards on the studios. A person looking for "where
   do I point this at ComfyUI" had no way to guess which of the three it was.

   There is one page now, with three groups and one panel visible at a time:

     Companion    — how she speaks with you and to you
     Tamanitomo   — this app: how it looks, who can reach it, how it is doing
     Hermes       — what it is connected to, and what runs on a schedule

   A panel owns its own save. Nothing saves a field you cannot currently see.
   ========================================================================= */

/* The Hermes forms are expensive to build and carry live event handlers, so
   they are rendered once into a pool that stays in the document, and the cards
   are moved into whichever panel wants them. Moving a node keeps its
   listeners; re-rendering the HTML would not. */
let hermesPool=null,hermesReady=null;
async function hermesCards(){
  if(!hermesPool){
    hermesPool=document.createElement('div');
    hermesPool.id='hermes-card-pool';
    hermesPool.hidden=true;
    $('settings').append(hermesPool);
  }
  if(!hermesReady)hermesReady=renderHermesInto(hermesPool).catch(error=>{
    hermesReady=null;throw error;
  });
  await hermesReady;
  return hermesPool;
}
function placeHermesCards(host,names){
  // The panel still holds its loading placeholder; the cards replace it rather
  // than stacking underneath it.
  host.innerHTML='';
  const pool=hermesPool;
  if(!pool)return;
  for(const name of names){
    const card=pool.querySelector(`[data-hermes-card="${name}"]`);
    if(card)host.append(card);
  }
  if(!host.children.length)
    host.innerHTML='<p class="dim">Hermes is not installed for this profile yet. Install it under Installation &amp; gateway.</p>';
}
function returnHermesCards(){
  if(!hermesPool)return;
  for(const card of $('settings').querySelectorAll('[data-hermes-card]'))
    if(card.parentElement!==hermesPool)hermesPool.append(card);
}

/* Relationship settings are read-only until deliberately unlocked: PIN, then a
   plain warning, then a confirmation. The unlock lasts for this visit only. */
let relationshipUnlocked=false;

function settingsFooter(label='Save'){
  return `<div class="panel-footer">
    <button class="act" data-panel-save>${esc(label)}</button>
    <span class="dim small" data-panel-status role="status"></span>
  </div>`;
}
/* One save button, one status line, one place that turns an exception into a
   message instead of a silent no-op. */
function wireSave(host,collect,note='Saved'){
  const button=host.querySelector('[data-panel-save]');
  const status=host.querySelector('[data-panel-status]');
  if(!button)return;
  button.onclick=async()=>{
    button.disabled=true;status.textContent='Saving…';status.className='dim small';
    try{
      const result=await collect();
      status.textContent=note;
      clearEditorDirty('settings-main');
      if(result&&result.operation)await followOperation(result.operation);
    }catch(error){
      status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;
    }finally{button.disabled=false;}
  };
}
const saveSettings=payload=>api('/settings',{method:'POST',body:JSON.stringify(payload)});

/* A switch that says what it is doing. The old awareness checkboxes gave no
   indication of state beyond a tick you had to hunt for. */
function toggleRow(id,label,blurb,on,extra=''){
  return `<label class="toggle-row${on?' is-on':''}" data-toggle-row>
    <input type="checkbox" id="${esc(id)}" ${on?'checked':''} ${extra}>
    <span class="switch-slider" aria-hidden="true"></span>
    <span class="toggle-copy"><strong>${esc(label)}</strong>${blurb?`<small>${esc(blurb)}</small>`:''}</span>
    <span class="toggle-state" aria-hidden="true">${on?'On':'Off'}</span>
  </label>`;
}
function wireToggles(host){
  for(const row of host.querySelectorAll('[data-toggle-row]')){
    const box=row.querySelector('input[type=checkbox]');
    const state=row.querySelector('.toggle-state');
    const paint=()=>{row.classList.toggle('is-on',box.checked);if(state)state.textContent=box.checked?'On':'Off';};
    box.addEventListener('change',paint);paint();
  }
}

/* ------------------------------------------------------------------ panels */

const settingsPanels=[
{group:'Companion',id:'contact',title:'Contact & outreach',
 blurb:'When she may write first, and how often',
 keywords:'quiet hours outreach messages photos voice notes boundaries initiative',
 async render(host){
  const s=await api('/settings');
  const perm=k=>options([['yes','Always welcome'],['ask','Ask me first'],['no','Never']],s.content_permissions[k]);
  host.innerHTML=`
  <h2>Contact & outreach</h2>
  <p class="dim">Replies are always allowed at any hour. Everything on this panel governs messages she starts on her own.</p>

  <h3 class="section-subheading">Quiet hours</h3>
  <div class="form-grid">
    <label>Quiet from<input id="qs" value="${esc(s.quiet_start)}" placeholder="22:00"></label>
    <label>until<input id="qe" value="${esc(s.quiet_end)}" placeholder="08:00"></label>
  </div>
  ${toggleRow('adapt','Drift toward the hours you actually keep',
    'Quiet hours adjust themselves as she learns your real sleep pattern.',s.adaptive_quiet)}

  <h3 class="section-subheading">How often she writes first</h3>
  <div class="form-grid">
    <label>She may write first
      <select id="out">${options([['free','Whenever she has something to say'],['updates_only','Only for meaningful updates'],['never','Never — replies only']],s.outreach)}</select>
    </label>
    <label>Most messages a day
      <input id="cap" type="number" min="1" max="100" value="${s.outreach_per_day||3}" ${s.outreach_per_day===0?'disabled':''}>
    </label>
  </div>
  ${toggleRow('cap-unlimited','No daily limit','She writes as often as the setting above allows.',s.outreach_per_day===0)}

  <h3 class="section-subheading">Unprompted media</h3>
  <div class="form-grid">
    <label>Photos<select id="pimage">${perm('image')}</select></label>
    <label>Voice notes<select id="pvoice">${perm('voice')}</select></label>
  </div>
  ${settingsFooter('Save contact settings')}`;
  wireToggles(host);
  const cap=host.querySelector('#cap');
  host.querySelector('#cap-unlimited').addEventListener('change',e=>{cap.disabled=e.target.checked;});
  wireSave(host,()=>{
    if(!host.querySelector('#cap-unlimited').checked&&!cap.reportValidity())throw Error('Check the daily limit.');
    return saveSettings({
      quiet_start:host.querySelector('#qs').value,quiet_end:host.querySelector('#qe').value,
      adaptive_quiet:host.querySelector('#adapt').checked,outreach:host.querySelector('#out').value,
      outreach_per_day:host.querySelector('#cap-unlimited').checked?0:Number(cap.value),
      content_permissions:{image:host.querySelector('#pimage').value,voice:host.querySelector('#pvoice').value}});
  });
 }},

{group:'Companion',id:'rhythm',title:'Daily rhythm',
 blurb:'Her own hours, and what carries between companions',
 keywords:'autonomy windows routine reflection continuity shared memory',
 async render(host){
  const s=await api('/settings');
  host.innerHTML=`
  <h2>Daily rhythm</h2>
  <p class="dim">Windows when she acts on her own — reflecting on the day, reading, running her routines — rather than waiting to be spoken to.</p>
  <label>Autonomy windows
    <input id="win" value="${esc(s.autonomy_windows.join(', '))}" placeholder="09:00, 14:00, 20:00">
    <small class="dim">Times in HH:MM, separated by commas.</small>
  </label>

  <h3 class="section-subheading">Shared memory</h3>
  ${toggleRow('share','Share what she learns about you with your other companions',
    'Off keeps everything she learns inside this companion.',s.share_people)}
  ${settingsFooter('Save rhythm')}`;
  wireToggles(host);
  wireSave(host,()=>saveSettings({
    autonomy_windows:host.querySelector('#win').value.split(',').map(x=>x.trim()).filter(Boolean),
    share_people:host.querySelector('#share').checked}));
 }},

{group:'Companion',id:'awareness',title:'Awareness',
 blurb:'Where you live, and what she can passively sense',
 keywords:'sensors location weather realism ambient context senses awareness',
 async render(host){
  const s=await api('/settings');
  const on=Object.keys(s.available_sensors).filter(k=>s.sensors.includes(k)).length;
  const total=Object.keys(s.available_sensors).length;
  host.innerHTML=`
  <h2>Awareness</h2>
  <p class="dim">Passive context she can read without being told. Anchors her sense of time, weather and place.</p>
  <label>Where you live<input id="loc" value="${esc(s.location)}" placeholder="Raleigh, NC"></label>

  <div class="section-heading" style="margin-top:26px">
    <h3 class="section-subheading" style="margin:0">Sensors</h3>
    <span class="pill ${on?'status-good':'status-warn'}" id="sensor-count">${on} of ${total} on</span>
  </div>
  <div class="toggle-stack">
    ${Object.entries(s.available_sensors).map(([k,blurb])=>
      toggleRow('sensor-'+k,k.replaceAll('_',' '),blurb,s.sensors.includes(k),`data-sensor="${esc(k)}"`)).join('')}
  </div>
  ${settingsFooter('Save awareness')}`;
  wireToggles(host);
  const recount=()=>{
    const live=[...host.querySelectorAll('[data-sensor]')].filter(x=>x.checked).length;
    const pill=host.querySelector('#sensor-count');
    pill.textContent=`${live} of ${total} on`;
    pill.className='pill '+(live?'status-good':'status-warn');
  };
  for(const box of host.querySelectorAll('[data-sensor]'))box.addEventListener('change',recount);
  wireSave(host,()=>saveSettings({
    location:host.querySelector('#loc').value,
    sensors:[...host.querySelectorAll('[data-sensor]')].filter(x=>x.checked).map(x=>x.dataset.sensor)}));
 }},

{group:'Companion',id:'photos',title:'Photo sessions',
 blurb:'Visual glimpses of her day, and what is blurred',
 keywords:'photos timeline images style budget nsfw blur scanner nudenet review',
 async render(host){
  const [s,prefs,scanner]=await Promise.all([api('/settings'),api('/media/preferences'),api('/media/scanner')]);
  host.innerHTML=`
  <h2>Photo sessions</h2>
  <p class="dim">Every 15 minutes she can render the scene she recorded. Needs a working image provider; results land in Photos &amp; albums.</p>
  ${toggleRow('tl','Run 15-minute photo sessions','Off stops new renders. Existing photos are kept.',s.image_timeline)}
  <div class="form-grid" style="margin-top:16px">
    <label>Image style
      <select id="image-style">${options(Object.entries(s.image_styles),s.image_style)}</select>
    </label>
    <label>Storage budget
      <input id="gb" type="number" step="0.5" min="0" value="${s.timeline_budget_gb}">
      <small class="dim">Gigabytes kept before the oldest are pruned.</small>
    </label>
  </div>

  <h3 class="section-subheading">Before a picture reaches you</h3>
  <label>Who checks it
    <select id="media-review-mode">${options([
      ['none','Nobody — deliver as generated'],
      ['local','This machine, privately (NudeNet)'],
      ['remote','A vision model']],
      !prefs.review_before_delivery?'none':(prefs.review_provider==='local-nsfw'?'local':'remote'))}</select>
  </label>
  <div id="media-review-local" hidden>
    <p class="dim small">NudeNet runs here and nothing leaves the machine. About 12&nbsp;MB of model and roughly
      150&nbsp;MB of memory while scanning. It finds exposed intimate anatomy; it does not judge scene accuracy
      or clothed content.</p>
    <p class="dim small">${scanner.installed?'<span class="good">Installed.</span>':'<span class="warn">Not installed yet</span> — downloading it needs internet.'}</p>
    <div class="actions"><button class="quiet" id="install-local-scanner">${scanner.installed?'Check installation':'Install it'}</button></div>
  </div>
  <div id="media-review-remote" hidden>
    <p class="dim small">A vision model can also judge scene and clothing, but the picture is sent to it.</p>
    <div class="form-grid">
      <label>Provider<input id="media-review-provider" value="${esc(prefs.review_provider==='local-nsfw'?'':prefs.review_provider)}" placeholder="openai, anthropic…"></label>
      <label>Model<input id="media-review-model" value="${esc(prefs.review_model)}" placeholder="Leave empty for the compression model"></label>
    </div>
  </div>

  <h3 class="section-subheading">What stays blurred</h3>
  ${toggleRow('media-blur','Pictures found to be sensitive','Open one to reveal it.',prefs.blur_nsfw_initially)}
  ${toggleRow('media-blur-unknown','Pictures nothing has checked',
    'Includes scans that failed, so a check that could not run never passes as a clean one.',prefs.blur_unknown_initially!==false)}

  ${settingsFooter('Save photo settings')}`;
  wireToggles(host);
  /* One question — who checks a picture — decides which details are relevant. */
  const mode=host.querySelector('#media-review-mode');
  const showMode=()=>{
    host.querySelector('#media-review-local').hidden=mode.value!=='local';
    host.querySelector('#media-review-remote').hidden=mode.value!=='remote';
  };
  mode.onchange=showMode;showMode();
  host.querySelector('#install-local-scanner').onclick=()=>
    action('/media/scanner/install',{},()=>openSettings(null,'photos'));
  wireSave(host,async()=>{
    const result=await saveSettings({
      image_timeline:host.querySelector('#tl').checked,
      image_style:host.querySelector('#image-style').value,
      timeline_budget_gb:Number(host.querySelector('#gb').value)});
    const choice=host.querySelector('#media-review-mode').value;
    await post('/media/preferences',{
      blur_nsfw_initially:host.querySelector('#media-blur').checked,
      blur_unknown_initially:host.querySelector('#media-blur-unknown').checked,
      review_before_delivery:choice!=='none',
      review_provider:choice==='local'?'local-nsfw':(choice==='remote'?host.querySelector('#media-review-provider').value:''),
      review_model:choice==='remote'?host.querySelector('#media-review-model').value:''});
    return result;
  });
 }},

{group:'Companion',id:'relationship',title:'Relationship',
 blurb:'How closeness grows — locked by default',
 keywords:'relationship pace progression intimacy romance milestones meters peer',
 async render(host){
  const s=await api('/settings');
  const net=await api('/network').catch(()=>({remote_pin_configured:false}));
  const labels={
    progression:{off:'Hidden',subtle:'Subtle, natural familiarity',milestones:'Shared milestones shown'},
    pace:{slow:'Slow and gradual',natural:'Natural',quick:'Open to quicker familiarity'}};

  if(!relationshipUnlocked){
    host.innerHTML=`
    <h2>Relationship</h2>
    <p class="dim">These are not preferences — they shape who she is with you, and changing them rewrites a dynamic the two of you have already built. They stay read-only until you deliberately unlock them.</p>
    <dl class="fact-list">
      <div><dt>Progression</dt><dd>${esc(labels.progression[s.relationship_progression]||s.relationship_progression)}</dd></div>
      <div><dt>Pace</dt><dd>${esc(labels.pace[s.relationship_pace]||s.relationship_pace)}</dd></div>
      <div><dt>Intimacy &amp; romance</dt><dd>${s.explicit?'Romantic connection enabled':'Friendly / platonic only'}</dd></div>
      <div><dt>Other companions</dt><dd>${s.peer_interaction?'May interact':'Kept apart'}</dd></div>
      <div><dt>Connection meters</dt><dd>${s.bars?'Shown':'Hidden'}</dd></div>
    </dl>
    <div class="actions">
      <button class="quiet" id="unlock-relationship">${icon('pin')} Unlock and change</button>
    </div>
    <p class="dim small">${net.remote_pin_configured
      ? 'Unlocking asks for your platform PIN.'
      : 'No platform PIN is set, so unlocking asks you to type her name instead. A PIN can be set under Tamanitomo → Network &amp; access.'}</p>`;
    host.querySelector('#unlock-relationship').onclick=()=>unlockRelationship(net.remote_pin_configured);
    return;
  }

  host.innerHTML=`
  <h2>Relationship <span class="pill status-warn">Unlocked</span></h2>
  <p class="dim">Unlocked for this visit. It locks again when you reload.</p>
  <div class="form-grid">
    <label>Progression
      <select id="progression">${options([['off','Hide progression'],['subtle','Subtle, natural familiarity'],['milestones','Show shared milestones']],s.relationship_progression)}</select>
    </label>
    <label>Pace
      <select id="pace">${options([['slow','Slow and gradual'],['natural','Natural'],['quick','Open to quicker familiarity']],s.relationship_pace)}</select>
    </label>
    <label>Intimacy &amp; romance
      <select id="adult-themes">${options([['false','Friendly / platonic only'],['true','Romantic connection enabled']],String(s.explicit))}</select>
    </label>
    <label>Other companions
      <select id="peer-interaction">${options([['true','May interact'],['false','Kept apart']],String(s.peer_interaction))}</select>
    </label>
  </div>
  <p class="dim small">Turning romance off is permanent for this companion — it cannot be turned back on.</p>
  ${toggleRow('bars','Show connection, feelings and closeness meters','',s.bars)}
  ${settingsFooter('Save relationship settings')}`;
  wireToggles(host);
  wireSave(host,async()=>{
    const wantsAdult=host.querySelector('#adult-themes').value==='true';
    const payload={
      relationship_progression:host.querySelector('#progression').value,
      relationship_pace:host.querySelector('#pace').value,
      peer_interaction:host.querySelector('#peer-interaction').value==='true',
      bars:host.querySelector('#bars').checked,
      explicit:wantsAdult};
    if(wantsAdult&&!s.explicit){
      if(!confirm('Enable romantic and adult themes? Confirm that you and this companion are both represented as adults.'))
        throw Error('Not changed.');
      payload.adult_confirmed=true;
    }
    if(!wantsAdult&&s.explicit&&!confirm('Turning romance off is permanent for this companion. It cannot be re-enabled. Continue?'))
      throw Error('Not changed.');
    return saveSettings(payload);
  });
 }},

{group:'Tamanitomo',id:'appearance',title:'Appearance',
 blurb:'Theme, accent and the Hermes runtime this workspace uses',
 keywords:'theme dark light accent colour color appearance runtime installation',
 async render(host){
  host.innerHTML=appearancePanelHTML();
  wireAppearancePanel(host);
 }},

{group:'Tamanitomo',id:'network',title:'Network & access',
 blurb:'Where this workspace is reachable, and the PIN that guards it',
 keywords:'network lan wifi address port pin security remote access localhost',
 async render(host){
  const [s,net]=await Promise.all([api('/settings'),api('/network')]);
  host.innerHTML=`
  <h2>Network &amp; access</h2>
  <p class="dim">Tamanitomo runs as a server. These are the addresses it answers on, and who has to prove themselves first.</p>

  <h3 class="section-subheading">Addresses</h3>
  <div class="endpoint-row">
    <div><strong>On this device</strong> <span class="pill status-good">No PIN needed</span>
      <code>${esc(net.localhost_url)}</code>
      <small class="dim">Open this in a browser on the machine or phone running Tamanitomo.</small></div>
    <button class="quiet" data-copy="${esc(net.localhost_url)}">Copy</button>
  </div>
  ${(net.lan_urls||[]).length?net.lan_urls.map(url=>`
    <div class="endpoint-row">
      <div><strong>Local network</strong> <span class="pill ${net.remote_pin_configured?'status-good':'status-warn'}">${net.remote_pin_configured?'PIN required':'Open to your Wi-Fi'}</span>
        <code>${esc(url)}</code>
        <small class="dim">Reach this companion from a laptop, desktop or tablet on the same Wi-Fi.</small></div>
      <button class="quiet" data-copy="${esc(url)}">Copy</button>
    </div>`).join('')
  :'<p class="dim small">No external Wi-Fi address was detected on this host.</p>'}

  <h3 class="section-subheading">Remote access PIN</h3>
  <p class="dim">Four digits, asked for when connecting from another device. It also unlocks the relationship settings.</p>
  <div class="pin-row">
    <input id="remote-pin-field" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="4"
      placeholder="${s.remote_pin?'••••':'1234'}" aria-label="Four digit PIN">
    <button class="act" id="save-remote-pin" type="button">${s.remote_pin?'Replace PIN':'Set PIN'}</button>
    ${s.remote_pin?'<button class="quiet" id="clear-remote-pin" type="button">Remove PIN</button>':''}
  </div>
  <p class="dim small" style="margin-top:6px">Locked out from another device? Run <code>tamanitomo pin --clear</code> in your terminal to remove it instantly.</p>
  <p class="small" id="pin-feedback" role="status"></p>`;

  for(const b of host.querySelectorAll('[data-copy]'))
    b.onclick=()=>{navigator.clipboard.writeText(b.dataset.copy);notice('Address copied');};
  const feedback=host.querySelector('#pin-feedback');
  host.querySelector('#save-remote-pin').onclick=async()=>{
    const value=(host.querySelector('#remote-pin-field').value||'').trim();
    if(!/^\d{4}$/.test(value)){feedback.innerHTML='<span class="bad">The PIN must be exactly four digits.</span>';return;}
    try{
      await saveSettings({remote_pin:value});
      notice('PIN saved.');openSettings(null,'network');
    }catch(error){feedback.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
  const clear=host.querySelector('#clear-remote-pin');
  if(clear)clear.onclick=async()=>{
    if(!confirm('Remove PIN protection? Anyone on your Wi-Fi will be able to open this workspace.'))return;
    try{await saveSettings({remote_pin:''});notice('PIN removed.');openSettings(null,'network');}
    catch(error){feedback.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
 }},

{group:'Tamanitomo',id:'updates',title:'Updates',
 blurb:'What version you are on, and how to move',
 keywords:'update version release upgrade changelog github',
 async render(host){
  const d=await api('/updates').catch(()=>({version:'unknown',has_update:false}));
  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <h2 style="margin:0">Updates</h2>
    <span class="pill ${d.has_update?'status-warn':'status-good'}">${d.has_update?`v${esc(d.latest_version)} available`:'Up to date'}</span>
  </div>
  <dl class="fact-list">
    <div><dt>Installed</dt><dd>v${esc(d.version)}</dd></div>
    <div><dt>Latest released</dt><dd>${d.latest_version?'v'+esc(d.latest_version):'Not checked'}</dd></div>
  </dl>
  ${d.has_update?`<div class="notice-strip">
    <p><strong>Tamanitomo v${esc(d.latest_version)} is out.</strong> Updating happens on the host, not in the browser, so dependencies and the gateway are handled together.</p>
    ${d.release_url?`<a class="link-button" href="${esc(d.release_url)}" target="_blank" rel="noopener">Release notes →</a>`:''}
  </div>`:'<p class="dim">You are running the newest release.</p>'}
  <h3 class="section-subheading">On the host</h3>
  <pre class="command-block">./update.sh          # Tamanitomo, its dependencies, then restart
./update.sh --hermes # the same, and update the Hermes runtime too</pre>`;
 }},

{group:'Tamanitomo',id:'diagnostics',title:'Diagnostics',
 blurb:'What is healthy, what is full, and what it has cost',
 keywords:'health diagnostics problems memory storage vault usage tokens cost',
 async render(host){
  const [health,cost]=await Promise.all([api('/health'),api('/cost')]);
  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <h2 style="margin:0">Diagnostics</h2>
    <button class="quiet" id="diag-activity">Activity feed</button>
  </div>
  ${health.problems.length
    ?`<div class="notice-strip"><p><strong>${health.problems.length} thing${health.problems.length===1?'':'s'} to look at</strong></p><ul>${health.problems.map(p=>`<li class="warn">${esc(p)}</li>`).join('')}</ul></div>`
    :'<p><span class="pill status-good">Everything monitored is running normally</span></p>'}

  <h3 class="section-subheading">Memory capacity</h3>
  <table><tbody>${health.memory.map(m=>`<tr>
    <td>${esc(m.file)}</td>
    <td><strong>${Number(m.chars).toLocaleString()}</strong> <span class="dim">/ ${Number(m.cap).toLocaleString()}</span></td>
    <td>${m.over_warn?'<span class="warn">Approaching the limit</span>':'<span class="dim">Within capacity</span>'}</td></tr>`).join('')}</tbody></table>

  <h3 class="section-subheading">Storage & Vault Backup</h3>
  <table><tbody>${health.storage.map(s=>`<tr><td>${esc(s.label)}</td><td>${s.files} files</td><td class="dim">${(s.bytes/1e6).toFixed(1)} MB</td></tr>`).join('')}
    <tr><td>Vault history</td><td colspan="2">${health.vault_repo?'<span class="dim">Recording every change</span>':'<span class="warn">Not a git repository — changes are not versioned</span>'}</td></tr></tbody></table>
  <div style="margin-top:12px;margin-bottom:20px">
    <a class="act" href="${mediaUrl('/api/vault/export')}" download style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;text-decoration:none">
      <span>📦</span> Download Complete Vault Backup (.zip)
    </a>
  </div>

  <h3 class="section-subheading">24/7 Background & Battery Resilience</h3>
  <div class="card" style="padding:14px;border-radius:10px;background:var(--panel);border:1px solid var(--surface-3);margin-bottom:20px">
    <div style="display:flex;align-items:flex-start;gap:10px">
      <span style="font-size:20px">🔋</span>
      <div>
        <strong style="display:block;margin-bottom:4px">Mobile Host Battery Optimization</strong>
        <p class="small dim" style="margin:0 0 8px">If hosting on an Android phone via Termux, prevent Android from suspending your companion when the screen is off:</p>
        <ol class="small dim" style="margin:0 0 8px;padding-left:18px">
          <li>Open Android <strong>Settings → Apps → Termux</strong></li>
          <li>Tap <strong>App battery usage</strong> (or Battery Saver / Power Management)</li>
          <li>Select <strong>Unrestricted</strong> (or <strong>Don't optimize</strong>)</li>
        </ol>
        <p class="small dim" style="margin:0">For Samsung, Xiaomi, or OnePlus phones, also disable aggressive memory freezing (<a href="https://dontkillmyapp.com" target="_blank" rel="noopener" style="color:var(--accent)">dontkillmyapp.com</a>).</p>
      </div>
    </div>
  </div>

  <h3 class="section-subheading">Model usage · last 30 recorded days</h3>
  ${cost.available
    ?`<table><thead><tr><th>Day</th><th>Input</th><th>Output</th><th>Runs</th></tr></thead><tbody>${cost.days.slice().reverse().map(d=>`<tr><td>${esc(d.day)}</td><td>${d.input.toLocaleString()}</td><td>${d.output.toLocaleString()}</td><td>${d.runs}</td></tr>`).join('')}</tbody></table>`
    :'<p class="dim">Nothing recorded yet.</p>'}`;
  host.querySelector('#diag-activity').onclick=showGatewayActivity;
 }},

{group:'Hermes',id:'hermes-core',bare:true,title:'Installation & gateway',
 blurb:'The runtime behind her, and the process that keeps her alive',
 keywords:'hermes install update gateway routine service hooks doctor repair profile archive',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['installation','stack','gateway','lifecycle']);
 }},

{group:'Hermes',id:'hermes-models',bare:true,title:'Models & fallbacks',
 blurb:'Which model answers, and what answers when it cannot',
 keywords:'model provider fallback openrouter ollama base url presets cascade reasoning',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['presets','models']);
 }},

{group:'Hermes',id:'hermes-accounts',bare:true,title:'Accounts & credentials',
 blurb:'API keys, sign-ins, and Hermes’s own setup menus',
 keywords:'api key credential oauth signin telegram discord token console setup',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['accounts']);
 }},

{group:'Hermes',id:'jobs',title:'Scheduled jobs',
 blurb:'Every cron job, what runs it, and whether it worked',
 keywords:'cron jobs schedule routine model tokens prompt run pause resume history',
 render:renderJobsPanel},

{group:'Hermes',id:'connect-images',title:'Image generation',
 blurb:'ComfyUI, Civitai, and the reference photograph',
 keywords:'comfyui image generation civitai lora checkpoint endpoint portrait',
 async render(host){
  host.innerHTML=await imagesPanelHTML();
  wireImagesPanel(host);
  host.insertAdjacentHTML('beforeend',
   `<p class="dim small">Composing and generating pictures happens in the <button type="button" class="link-button" data-goto="image-studio">Image studio</button>. This panel is only the connection.</p>`);
  host.querySelector('[data-goto]').onclick=()=>showTab('image-studio');
 }},

{group:'Hermes',id:'connect-voice',title:'Voice',
 blurb:'Which engine speaks, and how it sounds',
 keywords:'voice tts speech engine piper edge elevenlabs openai speed pitch',
 render:renderVoicePanel},

{group:'Hermes',id:'dashboard',title:'Hermes dashboard',
 blurb:'Hermes’s own interface, embedded',
 keywords:'hermes dashboard native skills mcp plugins sessions logs channels webhooks',
 render:host=>renderHermesDashboardInto(host)},
];

/* The providers this profile can actually reach, discovered rather than
   guessed. A hardcoded list gets this wrong in exactly the ways that matter:
   a Mistral wired up as `custom` does not answer to "mistral", and an OpenAI
   signed in through OAuth is `openai-codex`, not `openai`. */
let providerChoices=null;
function knownProviders(){
  if(!providerChoices)providerChoices=api('/models/providers').catch(()=>({providers:[],profile:{}}));
  return providerChoices;
}

/* Model lists, asked for once per provider+endpoint pair and remembered for the
   page. A name typed by hand is always accepted — the list is there to save
   typing and to show what is actually on offer, never to be the only answer. */
const modelListCache=new Map();
function modelList(provider,baseUrl,refresh){
  const key=`${provider||''}|${baseUrl||''}`;
  if(refresh)modelListCache.delete(key);
  if(!modelListCache.has(key)){
    const q=new URLSearchParams();
    if(provider)q.set('provider',provider);
    if(baseUrl)q.set('base_url',baseUrl);
    if(refresh)q.set('refresh','1');
    modelListCache.set(key,api('/models/catalog?'+q).catch(error=>({models:[],note:error.message})));
  }
  return modelListCache.get(key);
}

/* A model field that is a list when we know the list, and a text box always. */
function modelPickerHTML(id,value){
  return `<div class="model-picker" data-model-picker="${esc(id)}">
    <div class="model-picker-row">
      <select data-model-select aria-label="Model"><option value="">Loading…</option></select>
      <button type="button" class="quiet" data-model-refresh title="Ask the provider what it serves">Refresh</button>
    </div>
    <input data-model-custom placeholder="Model name" value="${esc(value||'')}" aria-label="Model name">
    <small class="dim" data-model-note></small>
  </div>`;
}

/* Fills one picker and keeps the free-text box in step with it. */
function wireModelPicker(root,{provider,baseUrl,value,onChange}){
  const select=root.querySelector('[data-model-select]');
  const custom=root.querySelector('[data-model-custom]');
  const note=root.querySelector('[data-model-note]');
  const CUSTOM='__custom__';
  const read=()=>select.value===CUSTOM?custom.value.trim():select.value;
  const paint=d=>{
    const models=d.models||[];
    const known=models.includes(custom.value.trim());
    select.innerHTML=
      `<option value="">Follow the profile default</option>`+
      models.map(m=>`<option value="${esc(m)}">${esc(m)}</option>`).join('')+
      `<option value="${CUSTOM}">Write your own…</option>`;
    select.value=custom.value.trim()?(known?custom.value.trim():CUSTOM):'';
    custom.hidden=select.value!==CUSTOM;
    note.textContent=d.note||(models.length
      ?`${models.length} model${models.length===1?'':'s'} offered${d.source==='cache'?' · cached':''}`:'');
  };
  custom.value=value||'';
  const load=refresh=>{
    select.innerHTML='<option>Loading…</option>';
    return modelList(provider(),baseUrl(),refresh).then(paint);
  };
  select.onchange=()=>{
    custom.hidden=select.value!==CUSTOM;
    if(select.value!==CUSTOM)custom.value=select.value;
    if(onChange)onChange(read());
  };
  custom.oninput=()=>{if(onChange)onChange(read());};
  root.querySelector('[data-model-refresh]').onclick=async e=>{
    e.preventDefault();const b=e.currentTarget;b.disabled=true;
    try{await load(true);}finally{b.disabled=false;}
  };
  load(false);
  return {read,reload:()=>load(false)};
}

/* ------------------------------------------------------------- jobs panel
   The jobs list used to be read-only apart from a schedule prompt(), and the
   model behind each job could only be changed by running Hermes's own CLI.
   Both are editable here. There is deliberately no token budget field: Hermes
   has no such setting per job, so prompt size is shown instead — that is what
   the job actually sends on every run. */
async function renderJobsPanel(host){
  const data=await api('/jobs');
  profileTimezone=data.timezone;
  const jobs=data.jobs;
  const failed=jobs.filter(j=>j.last_status==='error').length;
  const active=jobs.filter(j=>j.enabled).length;
  const noModel=jobs.filter(j=>!j.no_agent&&!j.model).length;

  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <h2 style="margin:0">Scheduled jobs</h2>
    <div class="actions" style="margin:0">
      <button class="quiet" id="jobs-history">Run history</button>
      <button class="quiet" id="jobs-apply-models">Apply job models</button>
      <button class="quiet" id="jobs-repair">Install / repair</button>
    </div>
  </div>
  <p class="dim">Hermes is the scheduler; this is the whole list it holds for this companion. A job with no model of its own follows the profile default under Models &amp; fallbacks.</p>
  <div class="stat-strip">
    <button data-filter="all"><span>Installed</span><strong>${jobs.length}</strong><span>jobs</span></button>
    <button data-filter="active"><span>Scheduled</span><strong>${active}</strong><span>enabled</span></button>
    <button data-filter="paused"><span>Paused</span><strong>${jobs.length-active}</strong><span>not running</span></button>
    <button data-filter="error"><span>Last run failed</span><strong>${failed}</strong><span>need a look</span></button>
  </div>
  ${noModel?`<p class="dim small">${noModel} model-backed job${noModel===1?' has':'s have'} no model of their own and follow the profile default.</p>`:''}
  <details class="card routing-card" id="job-routing">
    <summary><strong>Move every job to another provider</strong>
      <small class="dim">Model, provider and endpoint together, across all ${jobs.filter(j=>!j.no_agent).length} model-backed jobs</small></summary>
    <div class="routing-body">
      <div class="chip-row" id="routing-presets"><span class="dim small">Finding your providers…</span></div>
      <p class="dim small" id="routing-hint">Pick a provider, then adjust anything below before applying.</p>
      <div class="form-grid">
        <label>Provider<input id="routing-provider" list="provider-ids" placeholder="custom, openai, anthropic…"></label>
        <label>Model${modelPickerHTML('routing','')}
          <input type="hidden" id="routing-model"></label>
        <label class="wide">Endpoint<input id="routing-base-url" placeholder="Leave empty unless the provider needs a specific address">
          <small class="dim">An address here outranks the provider. This is the field that strands jobs on a dead server when it is changed by hand.</small></label>
      </div>
      <div class="panel-footer">
        <button class="act" id="routing-apply">Apply to all model-backed jobs</button>
        <span class="dim small" id="routing-status" role="status"></span>
      </div>
    </div>
  </details>
  <div class="filters">
    <label>Find a job<input id="job-search" type="search" placeholder="Photo, journal, backup…"></label>
    <label>State<select id="job-filter">
      <option value="all">All jobs</option><option value="active">Scheduled</option>
      <option value="paused">Paused</option><option value="error">Last run failed</option>
    </select></label>
  </div>
  <div id="job-list"></div>`;

  /* Only cron jobs carry an `expr`; interval and one-shot jobs describe
     themselves in `display` ("every 15m"). Hermes accepts either spelling back,
     so the editable field shows whichever the job actually has. */
  const schedule=j=>j.schedule?.display||j.schedule?.expr||'';

  const statusPill=j=>{
    if(j.last_status==='error')return '<span class="pill status-bad">Last run failed</span>';
    if(j.last_status==='ok')return '<span class="pill status-good">Last run ok</span>';
    return '<span class="pill">Not run yet</span>';
  };
  const draw=()=>{
    const q=host.querySelector('#job-search').value.toLowerCase();
    const state=host.querySelector('#job-filter').value;
    const rows=jobs.filter(j=>(!q||(j.name||'').toLowerCase().includes(q))&&
      (state==='all'||state==='active'&&j.enabled||state==='paused'&&!j.enabled||state==='error'&&j.last_status==='error'));
    host.querySelector('#job-list').innerHTML=rows.length?rows.map(j=>`
      <details class="job-row${j.last_status==='error'?' is-failing':''}">
        <summary>
          <span class="job-name"><strong>${esc(j.name||j.id)}</strong>
            <small class="dim">${j.no_agent?'Runs a script · no model':esc(j.model||'Profile default model')} · <code>${esc(schedule(j)||'no schedule')}</code></small></span>
          <span class="job-state">${statusPill(j)}${j.enabled?'':'<span class="pill">Paused</span>'}</span>
        </summary>
        <div class="job-body">
          <dl class="fact-list">
            <div><dt>Next run</dt><dd>${j.enabled?esc(when(j.next_run_at)):'Paused'}</dd></div>
            <div><dt>Last run</dt><dd>${j.last_run_at?esc(when(j.last_run_at)):'Never'}</dd></div>
            <div><dt>Prompt size</dt><dd>${j.no_agent?'—':Number(j.prompt_chars||0).toLocaleString()+' characters sent each run'}</dd></div>
            <div><dt>Delivers to</dt><dd>${esc(j.deliver||'—')}</dd></div>
          </dl>
          ${j.last_error?`<div class="notice-strip"><p><strong>Last error</strong></p><pre class="command-block">${esc(j.last_error)}</pre></div>`:''}
          <div class="form-grid">
            <label>Schedule<input data-field="schedule" data-job="${esc(j.id)}" value="${esc(schedule(j))}" placeholder="*/15 * * * * or every 15m"></label>
            ${j.no_agent?'':`
            <label>Provider<input data-field="provider" data-job="${esc(j.id)}" list="provider-ids" value="${esc(j.provider||'')}" placeholder="Follow the profile default"></label>
            <label>Model${modelPickerHTML('job-'+j.id,j.model)}
              <input type="hidden" data-field="model" data-job="${esc(j.id)}" value="${esc(j.model||'')}"></label>
            <label>Reasoning effort<select data-field="reasoning_effort" data-job="${esc(j.id)}">${options([['','Hermes default'],['none','None'],['low','Low'],['medium','Medium'],['high','High']],j.reasoning_effort||'')}</select></label>
            <label class="wide">Endpoint<input data-field="base_url" data-job="${esc(j.id)}" value="${esc(j.base_url||'')}" placeholder="Leave empty to use the provider's own address">
              <small class="dim">Only set this to override where the provider sends requests — a local server, or a gateway. An address left here outranks the provider above.</small></label>`}
          </div>
          ${j.no_agent?'':`<details class="job-prompt"><summary class="small dim">What this job is told to do</summary><textarea data-field="prompt" data-job="${esc(j.id)}" rows="5">${esc(j.prompt||'')}</textarea></details>`}
          <div class="panel-footer">
            <button class="act" data-save-job="${esc(j.id)}">Save this job</button>
            <button class="quiet" data-job-action="run" data-job="${esc(j.id)}">Run next tick</button>
            ${j.no_agent?'':`<button class="quiet" data-job-action="${j.enabled?'pause':'resume'}" data-job="${esc(j.id)}">${j.enabled?'Pause':'Resume'}</button>`}
            <span class="dim small" data-job-status="${esc(j.id)}" role="status"></span>
          </div>
        </div>
      </details>`).join(''):empty('health','No matching jobs','Nothing here matches that search or filter.');

    /* A row builds its picker the first time it is opened, not for all 29 at
       once, and rebuilds it when the provider or endpoint underneath changes. */
    for(const row of host.querySelectorAll('.job-row')){
      const picker=row.querySelector('[data-model-picker]');
      if(!picker)continue;
      const field=n=>row.querySelector(`[data-field="${n}"]`);
      const attach=()=>{
        if(picker.dataset.wired)return;
        picker.dataset.wired='1';
        wireModelPicker(picker,{
          provider:()=>field('provider').value.trim(),
          baseUrl:()=>field('base_url')?field('base_url').value.trim():'',
          value:field('model').value,
          onChange:v=>{field('model').value=v;}});
      };
      row.addEventListener('toggle',()=>{if(row.open)attach();});
      if(row.open)attach();
      for(const name of ['provider','base_url']){
        const input=field(name);
        if(input)input.addEventListener('change',()=>{
          picker.dataset.wired='';attach();
        });
      }
    }

    for(const b of host.querySelectorAll('[data-save-job]'))b.onclick=async()=>{
      const id=b.dataset.saveJob;
      const status=host.querySelector(`[data-job-status="${CSS.escape(id)}"]`);
      const field=name=>host.querySelector(`[data-field="${name}"][data-job="${CSS.escape(id)}"]`);
      const job=jobs.find(j=>j.id===id);
      const payload={};
      const wanted=field('schedule').value.trim();
      if(wanted&&wanted!==schedule(job))payload.schedule=wanted;
      if(!job.no_agent){
        for(const [name,was] of [['model',job.model||''],['provider',job.provider||''],['reasoning_effort',job.reasoning_effort||''],['base_url',job.base_url||'']]){
          const now=field(name).value.trim();
          if(now!==was)payload[name]=now;
        }
        const prompt=field('prompt');
        if(prompt&&prompt.value.trim()&&prompt.value.trim()!==(job.prompt||'').trim())payload.prompt=prompt.value;
      }
      if(!Object.keys(payload).length){status.textContent='Nothing changed.';return;}
      b.disabled=true;status.textContent='Saving…';
      try{
        await action('/jobs/'+encodeURIComponent(id)+'/edit',payload);
        status.innerHTML='<span class="good">Saved</span>';
        Object.assign(job,payload,payload.schedule?{schedule:{...job.schedule,display:payload.schedule,expr:payload.schedule}}:{});
      }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
      finally{b.disabled=false;}
    };
    for(const b of host.querySelectorAll('[data-job-action]'))b.onclick=async()=>{
      const status=host.querySelector(`[data-job-status="${CSS.escape(b.dataset.job)}"]`);
      b.disabled=true;
      try{await action('/jobs/'+encodeURIComponent(b.dataset.job)+'/'+b.dataset.jobAction);openSettings(null,'jobs');}
      catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;b.disabled=false;}
    };
  };
  /* The switcher's own picker, rebuilt whenever the provider or endpoint moves
     under it — those two decide which catalogue the model list comes from. */
  const routingPicker=host.querySelector('#job-routing [data-model-picker]');
  const routingModel=host.querySelector('#routing-model');
  const buildRoutingPicker=()=>wireModelPicker(routingPicker,{
    provider:()=>host.querySelector('#routing-provider').value.trim(),
    baseUrl:()=>host.querySelector('#routing-base-url').value.trim(),
    value:routingModel.value,
    onChange:v=>{routingModel.value=v;}});
  buildRoutingPicker();
  for(const id of ['#routing-provider','#routing-base-url'])
    host.querySelector(id).addEventListener('change',buildRoutingPicker);

  /* A chip per reachable provider, plus a way back to the profile default.
     Choosing one sets the provider and endpoint and reloads the model list;
     nothing is sent until Apply. */
  knownProviders().then(d=>{
    if(!host.isConnected)return;
    const strip=host.querySelector('#routing-presets');
    const rows=[...d.providers.map(r=>({...r,preset:false})),
                {key:'__default__',label:'Follow the profile',provider:'',base_url:'',models:0,preset:true}];
    strip.innerHTML=rows.map(r=>`<button type="button" class="chip" data-choice="${esc(r.key)}">${esc(r.label)}${r.models?` <span class="dim">${r.models}</span>`:''}</button>`).join('');
    for(const b of strip.children)b.onclick=()=>{
      const row=rows.find(x=>x.key===b.dataset.choice);
      host.querySelector('#routing-provider').value=row.provider||'';
      host.querySelector('#routing-base-url').value=row.base_url||'';
      routingModel.value='';
      routingPicker.querySelector('[data-model-custom]').value='';
      buildRoutingPicker();
      host.querySelector('#routing-hint').textContent=row.preset
        ? 'Clears all three, so jobs follow whatever the profile default is.'
        : `${row.label} — ${row.models} model${row.models===1?'':'s'} known. Pick one below, or leave the model empty to follow the profile default.`;
      for(const other of strip.children)other.setAttribute('aria-pressed',String(other===b));
    };
  });
  host.querySelector('#routing-apply').onclick=async()=>{
    const status=host.querySelector('#routing-status');
    const count=jobs.filter(j=>!j.no_agent).length;
    if(!confirm(`Move all ${count} model-backed job(s) in this profile onto this provider?`))return;
    status.textContent='Moving…';
    try{
      await action('/jobs/routing',{
        provider:host.querySelector('#routing-provider').value.trim(),
        model:routingModel.value.trim(),
        base_url:host.querySelector('#routing-base-url').value.trim()});
      openSettings(null,'jobs');
    }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
  host.querySelector('#job-search').oninput=draw;
  host.querySelector('#job-filter').onchange=draw;
  for(const b of host.querySelectorAll('[data-filter]'))
    b.onclick=()=>{host.querySelector('#job-filter').value=b.dataset.filter;draw();};
  bindAction('jobs-history','/jobs/history');
  bindAction('jobs-apply-models','/jobs/apply-models');
  bindAction('jobs-repair','/maintenance/repair');
  draw();

  /* The provider field autocompletes to what this profile can actually reach,
     with the rest of the catalogue behind it for anything not set up yet. */
  Promise.all([knownProviders(),api('/providers').catch(()=>({providers:[]}))]).then(([mine,all])=>{
    if(!host.isConnected)return;
    const list=document.createElement('datalist');
    list.id='provider-ids';
    const seen=new Set();
    const rows=[];
    for(const r of mine.providers){
      if(!r.provider||seen.has(r.provider))continue;
      seen.add(r.provider);
      rows.push([r.provider,`${r.label} · ${r.models} model${r.models===1?'':'s'}`]);
    }
    for(const r of all.providers){
      if(!r.slug||seen.has(r.slug))continue;
      seen.add(r.slug);rows.push([r.slug,r.label]);
    }
    list.innerHTML=rows.map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join('');
    host.append(list);
  }).catch(()=>{});
}

/* ------------------------------------------------------------ voice panel
   The connection half of the voice studio: which engine speaks and how. The
   studio keeps cloning, previews and reference clips. */
async function renderVoicePanel(host){
  const d=await api('/voice'),tts=d.tts;
  const provider=tts.provider||'edge';
  host.innerHTML=`
  <h2>Voice</h2>
  <p class="dim">Which engine speaks for her. Local engines run on the machine hosting Tamanitomo; cloud engines bill their own accounts.</p>
  <form id="voice-connect">
    <div class="form-grid">
      <label>Speech engine
        <select id="voice-provider">${options([['edge','Edge · online, no key needed'],['piper','Piper · local'],['kittentts','KittenTTS · local'],['neutts','NeuTTS · local, reference voice'],['pockettts','Pocket TTS · local'],['openai','OpenAI'],['xai','xAI / Grok'],['elevenlabs','ElevenLabs'],['minimax','MiniMax'],['gemini','Gemini'],['mistral','Mistral']],provider)}</select>
      </label>
      <label id="voice-picker-label">Voice
        <select id="voice-picker"></select>
        <input id="voice-custom" hidden placeholder="Voice name or ID" aria-label="Custom voice name or ID">
      </label>
      <label id="voice-speed-label">Speed <output id="speed-value">1</output>×
        <input id="voice-speed" type="range" min="0.7" max="1.5" step="0.05" value="1">
      </label>
    </div>
    <div class="panel-footer">
      <button class="act">Save voice engine</button>
      <button type="button" class="quiet" id="voice-install-local">Install this local engine</button>
      <button type="button" class="link-button" id="voice-goto-studio">Open the Voice studio →</button>
      <span class="dim small" id="voice-connect-status" role="status"></span>
    </div>
  </form>`;
  const choices=voiceChoices;
  const refresh=()=>{
    const name=host.querySelector('#voice-provider').value;
    const cfg=tts[name]||{},value=cfg.voice||cfg.voice_id||(choices[name]||[])[0]||'';
    const known=(choices[name]||[]).includes(value);
    host.querySelector('#voice-picker').innerHTML=options((choices[name]||[]).map(v=>[v,v]),value)+'<option value="__custom__">Write your own…</option>';
    host.querySelector('#voice-picker').value=known?value:'__custom__';
    host.querySelector('#voice-custom').value=known?'':value;
    host.querySelector('#voice-custom').hidden=known;
    host.querySelector('#voice-picker-label').hidden=name==='neutts';
    host.querySelector('#voice-speed-label').hidden=!['edge','openai','xai','minimax','kittentts'].includes(name);
    host.querySelector('#voice-speed').value=cfg.speed||1;
    host.querySelector('#speed-value').textContent=host.querySelector('#voice-speed').value;
    host.querySelector('#voice-install-local').hidden=!['piper','neutts','kittentts','pockettts'].includes(name);
  };
  refresh();
  host.querySelector('#voice-provider').onchange=refresh;
  host.querySelector('#voice-picker').onchange=()=>{
    host.querySelector('#voice-custom').hidden=host.querySelector('#voice-picker').value!=='__custom__';};
  host.querySelector('#voice-speed').oninput=e=>{host.querySelector('#speed-value').textContent=e.target.value;};
  host.querySelector('#voice-goto-studio').onclick=()=>showTab('voice');
  host.querySelector('#voice-install-local').onclick=()=>action('/voice/install',{provider:host.querySelector('#voice-provider').value});
  host.querySelector('#voice-connect').onsubmit=async e=>{
    e.preventDefault();
    const status=host.querySelector('#voice-connect-status');
    status.textContent='Saving…';
    try{
      await action('/voice',{provider:host.querySelector('#voice-provider').value,
        voice:host.querySelector('#voice-picker').value==='__custom__'
          ?host.querySelector('#voice-custom').value:host.querySelector('#voice-picker').value,
        speed:+host.querySelector('#voice-speed').value});
      status.innerHTML='<span class="good">Saved</span>';
    }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
}

/* ------------------------------------------------------- relationship unlock
   PIN, then the plain consequence, then a confirmation. Three deliberate steps
   rather than one checkbox you can knock with your elbow. */
async function unlockRelationship(pinConfigured){
  const name=($('who')?.textContent||'your companion').trim();
  dialog('Unlock relationship settings',`
    <p>These settings shape who ${esc(name)} is with you. Unlocking them is deliberate.</p>
    <form id="unlock-form">
      ${pinConfigured
        ?'<label>Platform PIN<input id="unlock-pin" type="password" inputmode="numeric" maxlength="4" placeholder="••••" autocomplete="off"></label>'
        :`<p class="dim small">No platform PIN is set on this workspace. Type <strong>${esc(name)}</strong> below to continue, or set a PIN first under Tamanitomo → Network &amp; access.</p>
          <label>Companion name<input id="unlock-name" autocomplete="off" placeholder="${esc(name)}"></label>`}
      <p class="small" id="unlock-error" role="status"></p>
      <button class="act">Continue</button>
    </form>`);
  $('unlock-form').onsubmit=async e=>{
    e.preventDefault();
    const error=$('unlock-error');
    if(pinConfigured){
      const pin=($('unlock-pin').value||'').trim();
      if(!/^\d{4}$/.test(pin)){error.innerHTML='<span class="bad">Four digits.</span>';return;}
      const r=await fetch(scoped('/api/auth/pin'),{method:'POST',
        headers:{'content-type':'application/json'},body:JSON.stringify({pin})});
      const body=await r.json().catch(()=>({}));
      if(!r.ok||!body.ok){error.innerHTML='<span class="bad">That PIN is not right.</span>';return;}
    }else if(($('unlock-name').value||'').trim().toLowerCase()!==name.toLowerCase()){
      error.innerHTML='<span class="bad">That is not her name.</span>';return;
    }
    $('product-dialog').close();
    if(!confirm(`Changing how ${name} relates to you rewrites a dynamic the two of you have already built. Pace, progression and intimacy all feed her behaviour directly.\n\nContinue?`))return;
    if(!confirm('Last check — are you sure?'))return;
    relationshipUnlocked=true;
    openSettings(null,'relationship');
  };
}

/* ----------------------------------------------------------------- the page */

/* Which panel is open survives a reload, so a link that has to reload the
   workspace first (switching profile, finishing onboarding) still lands on the
   panel it meant to. */
const PANEL_KEY='settings-panel';
let settingsPanel=(()=>{try{return sessionStorage.getItem(PANEL_KEY);}catch(error){return null;}})();
function rememberPanel(id){
  settingsPanel=id;
  try{sessionStorage.setItem(PANEL_KEY,id);}catch(error){/* private window */}
}
/* Jump straight to a panel from anywhere: openSettings('jobs'). */
function openSettings(_group,panel){
  if(panel)rememberPanel(panel);
  if(current!=='settings')return showTab('settings');
  return render('settings');
}
/* For links that must reload the workspace before Settings can be drawn. */
function aimSettings(panel){if(panel)rememberPanel(panel);}
window.openSettings=openSettings;
window.aimSettings=aimSettings;

workspaceHandlers.settings=async()=>{
  const groups=[];
  for(const panel of settingsPanels){
    let row=groups.find(g=>g[0]===panel.group);
    if(!row)groups.push(row=[panel.group,[]]);
    row[1].push(panel);
  }
  const groupBlurb={
    Companion:'How she speaks with you, and to you',
    Tamanitomo:'This app — how it looks, who can reach it, how it is doing',
    Hermes:'What she is connected to, and what runs on a schedule'};
  if(!settingsPanels.some(p=>p.id===settingsPanel))settingsPanel=settingsPanels[0].id;

  /* The pool is re-parented on every render, so take it out of the way first
     and let hermesCards() put it back where it belongs. */
  returnHermesCards();
  const keepPool=hermesPool;

  $('settings').innerHTML=`
  <div class="home-title">
    <div><h2 class="page-title">Settings</h2>
      <p class="intro">Everything that configures this companion, this app, and the runtime underneath.</p></div>
  </div>
  <div class="settings-shell">
    <aside class="settings-nav">
      <label class="settings-search"><input id="settings-search" type="search" placeholder="Search settings…" aria-label="Search settings"></label>
      ${groups.map(([name,panels])=>`
        <section class="settings-group" data-group="${esc(name)}">
          <h3>${esc(name)}<small>${esc(groupBlurb[name]||'')}</small></h3>
          ${panels.map(p=>`<button class="settings-link" data-panel="${esc(p.id)}" aria-current="${String(p.id===settingsPanel)}">
            <strong>${esc(p.title)}</strong><small>${esc(p.blurb)}</small></button>`).join('')}
        </section>`).join('')}
    </aside>
    <div class="settings-body">
      <div class="card" id="settings-panel" role="region" aria-live="polite"></div>
    </div>
  </div>`;
  if(keepPool)$('settings').append(keepPool);

  const body=$('settings-panel');
  const show=async(id,announce)=>{
    // Leaving a panel with unsaved edits asks first; each panel saves itself,
    // so switching away is the only way to lose work.
    if(!await confirmEditorLeave('settings-main'))return;
    rememberPanel(id);
    returnHermesCards();
    for(const b of $('settings').querySelectorAll('.settings-link'))
      b.setAttribute('aria-current',String(b.dataset.panel===id));
    const panel=settingsPanels.find(p=>p.id===id);
    // A panel that brings its own cards is not wrapped in one, so the borders
    // do not nest.
    body.className=panel.bare?'panel-bare':'card';
    body.innerHTML='<p class="dim" role="status">Loading…</p>';
    try{await panel.render(body);}
    catch(error){body.innerHTML=`<div class="notice-strip"><p><strong>${esc(panel.title)} could not load.</strong> ${esc(error.message)}</p></div>`;}
    // Drawing a panel populates its fields; that is not an edit.
    clearEditorDirty('settings-main');
    // On a narrow screen the index sits above the panel, so choosing something
    // has to carry you to it rather than leaving you at the top of the list.
    if(announce&&matchMedia('(max-width:1000px)').matches)
      body.scrollIntoView({behavior:'smooth',block:'start'});
  };
  for(const b of $('settings').querySelectorAll('.settings-link'))b.onclick=()=>show(b.dataset.panel,true);

  /* Search filters the index rather than the open panel, so finding a setting
     means finding the panel it lives on. */
  const search=$('settings-search');
  search.oninput=()=>{
    const q=search.value.trim().toLowerCase();
    for(const group of $('settings').querySelectorAll('.settings-group')){
      let shown=0;
      for(const link of group.querySelectorAll('.settings-link')){
        const panel=settingsPanels.find(p=>p.id===link.dataset.panel);
        const hit=!q||`${panel.title} ${panel.blurb} ${panel.keywords} ${panel.group}`.toLowerCase().includes(q);
        link.hidden=!hit;
        if(hit)shown++;
      }
      group.hidden=!shown;
    }
  };
  await show(settingsPanel);
};
