/* Settings: five groups, related sections together, independent saves. */

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
  if(!pool||!host.isConnected)return;
  const labels={stack:'Optional local components',gateway:'Gateway & background service',lifecycle:'Profile maintenance',presets:'Ready-made model configurations'};
  for(const [index,name] of names.entries()){
    const card=pool.querySelector(`[data-hermes-card="${name}"]`);
    if(!card)continue;
    if(index===0){host.append(card);continue;}
    const disclosure=document.createElement('details');
    disclosure.className='settings-advanced';
    const summary=document.createElement('summary');
    summary.textContent=labels[name]||name;
    disclosure.append(summary,card);host.append(disclosure);
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
      if(result&&result.operation){const row=await followOperation(result.operation);if(row.status!=='complete')throw Error(row.error||'Saved, but job synchronization failed.');}
      status.textContent=note;
      clearEditorDirty(editorScope(host));
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

// Common schedules have controls; an advanced expression remains available.
function scheduleShape(expression){
  const parts=String(expression||'').trim().split(/\s+/);
  if(parts.length!==5)return {mode:'custom',expression};
  const [minute,hour,day,month,weekday]=parts;
  if(/^\d+$/.test(minute)&&/^\d+$/.test(hour)&&day==='*'&&month==='*'&&(weekday==='*'||/^[0-6]$/.test(weekday)))
    return {mode:weekday==='*'?'daily':'weekly',time:hour.padStart(2,'0')+':'+minute.padStart(2,'0'),day:weekday,expression};
  if(parts.slice(1).every(p=>p==='*')){
    const step=minute.match(/^(?:\*|\d+-59)\/(\d+)$/);
    if(step&&[5,10,15,20,30].includes(Number(step[1])))return {mode:step[1],expression};
    if(/^\d+$/.test(minute))return {mode:'60',expression};
    const times=minute.split(',').map(Number);
    const spacing=times.length>1?times[1]-times[0]:0;
    if([5,10,15,20,30].includes(spacing)&&times.length===60/spacing&&times.every((t,i)=>t===times[0]+i*spacing))return {mode:String(spacing),expression};
  }
  return {mode:'custom',expression};
}
function scheduleLabel(expression){
  const shape=scheduleShape(expression);
  if(shape.mode==='daily')return 'Daily at '+shape.time;
  if(shape.mode==='weekly')return ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][Number(shape.day)]+' at '+shape.time;
  if(shape.mode!=='custom')return shape.mode==='60'?'Every hour':'Every '+shape.mode+' minutes';
  return expression||'No schedule';
}
function scheduleEditorHTML(id,expression){
  const s=scheduleShape(expression);
  return `<div class="schedule-editor wide" data-schedule-editor data-original="${esc(expression)}" data-mode="${esc(s.mode)}">
    <div class="time-pair"><label>Frequency<select data-schedule-mode>${options([['5','Every 5 minutes'],['10','Every 10 minutes'],['15','Every 15 minutes'],['20','Every 20 minutes'],['30','Every 30 minutes'],['60','Every hour'],['daily','Daily'],['weekly','Weekly'],['custom','Advanced schedule']],s.mode)}</select></label>
    <label data-schedule-clock ${['daily','weekly'].includes(s.mode)?'':'hidden'}>At<input type="time" data-schedule-time value="${esc(s.time||'09:00')}"></label></div>
    <label data-schedule-weekday ${s.mode==='weekly'?'':'hidden'}>Day<select data-schedule-day>${options(['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'].map((d,i)=>[String(i),d]),s.day||'0')}</select></label>
    <label data-schedule-advanced ${s.mode==='custom'?'':'hidden'}>Schedule expression<input data-field="schedule" data-job="${esc(id)}" value="${esc(expression)}" placeholder="Minute hour day month weekday"></label>
  </div>`;
}
function wireScheduleEditors(host){
  for(const editor of host.querySelectorAll('[data-schedule-editor]')){
    editor.querySelector('[data-schedule-mode]').onchange=()=>{
      const mode=editor.querySelector('[data-schedule-mode]').value;
      editor.querySelector('[data-schedule-clock]').hidden=!['daily','weekly'].includes(mode);
      editor.querySelector('[data-schedule-weekday]').hidden=mode!=='weekly';
      editor.querySelector('[data-schedule-advanced]').hidden=mode!=='custom';
    };
  }
}
function readSchedule(editor){
  const mode=editor.querySelector('[data-schedule-mode]').value;
  if(mode==='custom')return editor.querySelector('[data-field=schedule]').value;
  if(mode==='daily'||mode==='weekly'){
    const time=editor.querySelector('[data-schedule-time]');if(!time.value)throw Error('Choose a scheduled time.');
    const [hour,minute]=time.value.split(':').map(Number);
    return `${minute} ${hour} * * ${mode==='weekly'?editor.querySelector('[data-schedule-day]').value:'*'}`;
  }
  // Preserve a staggered phase when the frequency has not changed.
  if(mode===editor.dataset.mode)return editor.dataset.original;
  return mode==='60'?'0 * * * *':`*/${mode} * * * *`;
}

/* ------------------------------------------------------------------ panels */

const settingsPanels=[
{group:'Companion',id:'contact',title:'Contact & outreach',
 blurb:'When they may write first, and how often',
 keywords:'quiet hours outreach messages photos voice notes boundaries initiative',
 async render(host){
  const s=await api('/settings');
  const perm=k=>options([['yes','Always welcome'],['ask','Ask me first'],['no','Never']],s.content_permissions[k]);
  host.innerHTML=`
  <h2>Contact & outreach</h2>
  <p class="dim">Limits for messages they start. Replies are always allowed.</p>

  <h3 class="section-subheading">Quiet hours</h3>
  <div class="time-pair">
    <label>From<input type="time" id="qs" value="${esc(s.quiet_start)}" placeholder="22:00"></label>
    <label>To<input type="time" id="qe" value="${esc(s.quiet_end)}" placeholder="08:00"></label>
  </div>
  ${toggleRow('adapt','Adapt quiet hours',
    'Adjust to your sleep pattern.',s.adaptive_quiet)}

  <h3 class="section-subheading">Outreach</h3>
  <div class="time-pair">
    <label>They may write first
      <select id="out">${options([['free','Social & updates'],['updates_only','Updates only'],['never','Replies only']],s.outreach)}</select>
    </label>
    <label>Daily limit
      <input id="cap" type="number" min="0" max="100" value="${s.outreach_per_day??3}">
    </label>
  </div>
  <p class="dim small">Daily limit: 0 means unlimited.</p>

  <h3 class="section-subheading">Unprompted media</h3>
  <div class="time-pair">
    <label>Photos<select id="pimage">${perm('image')}</select></label>
    <label>Voice notes<select id="pvoice">${perm('voice')}</select></label>
  </div>
  ${settingsFooter('Save')}`;
  wireToggles(host);
  const cap=host.querySelector('#cap');
  wireSave(host,()=>{
    if(!cap.reportValidity())throw Error('Check the daily limit.');
    return saveSettings({
      quiet_start:host.querySelector('#qs').value,quiet_end:host.querySelector('#qe').value,
      adaptive_quiet:host.querySelector('#adapt').checked,outreach:host.querySelector('#out').value,
      outreach_per_day:Number(cap.value),
      content_permissions:{image:host.querySelector('#pimage').value,voice:host.querySelector('#pvoice').value}});
  });
 }},

{group:'Schedule & usage',id:'rhythm',title:'Daily rhythm',
 blurb:'Their own hours, and what carries between companions',
 keywords:'autonomy windows routine reflection continuity shared memory',
 async render(host){
  const s=await api('/settings');
  host.innerHTML=`
  <h2>Daily rhythm</h2>
  <p class="dim">Times for independent reading and projects.</p>
  <div id="autonomy-times" class="time-chips"></div>
  <button type="button" class="quiet small" id="add-autonomy-time">Add time</button>

  <h3 class="section-subheading">Shared memory</h3>
  ${toggleRow('share','Share memories about you',
    'Let your other companions use these memories.',s.share_people)}
  ${settingsFooter('Save rhythm')}`;
  wireToggles(host);
  const times=host.querySelector('#autonomy-times');
  const addTime=value=>{
    const row=document.createElement('div');row.className='time-chip';
    row.innerHTML=`<input type="time" aria-label="Independent activity time" value="${esc(value)}" required><button type="button" class="quiet" aria-label="Remove time">×</button>`;
    row.querySelector('button').onclick=()=>{row.remove();host.querySelector('#add-autonomy-time').disabled=false;dirtyEditors.add(editorScope(host));updateEditorStatus();};
    times.append(row);host.querySelector('#add-autonomy-time').disabled=times.children.length>=6;
  };
  s.autonomy_windows.forEach(addTime);
  host.querySelector('#add-autonomy-time').onclick=()=>{addTime('12:00');dirtyEditors.add(editorScope(host));updateEditorStatus();};
  wireSave(host,()=>saveSettings({
    autonomy_windows:[...new Set([...times.querySelectorAll('input')].map(x=>x.value))],
    share_people:host.querySelector('#share').checked}));
 }},

{group:'Companion',id:'awareness',title:'Awareness',
 blurb:'Where you live, and what they can passively sense',
 keywords:'sensors location weather realism ambient context senses awareness',
 async render(host){
  const s=await api('/settings');
  const on=Object.keys(s.available_sensors).filter(k=>s.sensors.includes(k)).length;
  const total=Object.keys(s.available_sensors).length;
  host.innerHTML=`
  <h2>Awareness</h2>
  <p class="dim">Choose what they can notice.</p>
  <label>Where you live<input id="loc" value="${esc(s.location)}" placeholder="Raleigh, NC"></label>

  <div class="section-heading" style="margin-top:26px">
    <h3 class="section-subheading" style="margin:0">Sensors</h3>
    <span class="pill ${on?'status-good':'status-warn'}" id="sensor-count">${on} of ${total} on</span>
  </div>
  <div class="toggle-stack">
    ${Object.entries(s.available_sensors).map(([k,blurb])=>
      toggleRow('sensor-'+k,({dates:'Important dates',care:'Follow-ups',durations:'Milestones',thread:'Conversation rhythm',daylight:'Daylight',weather:'Weather',music:'Music'})[k]||k,({weather:'Local conditions, updated hourly.',daylight:'Seasons, moon and daylight.',dates:'Upcoming birthdays and anniversaries.',care:'Things worth checking in about.',durations:'Time since important dates.',thread:'Time since your last conversation.',music:'Spotify playback or room mood.'})[k]||blurb,s.sensors.includes(k),`data-sensor="${esc(k)}"`)).join('')}
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

{group:'Images & voice',id:'photos',title:'Photo sessions',
 blurb:'Visual glimpses of their day, and what is blurred',
 keywords:'photos timeline images style budget nsfw blur scanner nudenet review',
 async render(host){
  const [s,prefs,scanner]=await Promise.all([api('/settings'),api('/media/preferences'),api('/media/scanner')]);
  host.innerHTML=`
  <h2>Photo sessions</h2>
  <p class="dim">Capture scenes from their day with your connected image provider.</p>
  ${toggleRow('tl','Automatic photos','',s.image_timeline)}
  <label>Time between photos<select id="image-interval">${options([5,10,15,20,30,60,120,240,360,720,1440].map(n=>[String(n),n<60?n+' minutes':n===60?'1 hour':n===1440?'24 hours':(n/60)+' hours']),String(s.image_interval_minutes||15))}</select></label>
  <div class="form-grid" style="margin-top:16px">
    <label>Image style
      <select id="image-style">${options(Object.entries(s.image_styles),s.image_style)}</select>
    </label>
    <label>Storage budget
      <input id="gb" type="number" step="0.5" min="0" value="${s.timeline_budget_gb}">
      <small class="dim">Gigabytes kept before the oldest are pruned.</small>
    </label>
  </div>

  <details class="settings-advanced"><summary>Review &amp; blurring</summary>
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
  </details>

  ${settingsFooter('Save')}`;
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
      image_interval_minutes:Number(host.querySelector('#image-interval').value),
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
    <p class="dim">Unlock to change relationship preferences.</p>
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
      : 'No platform PIN is set, so unlocking asks you to type their name instead. A PIN can be set under App &amp; access → Network &amp; access.'}</p>`;
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

{group:'App & access',id:'appearance',title:'Appearance',
 blurb:'Theme, accent and the Hermes runtime this workspace uses',
 keywords:'theme dark light accent colour color appearance runtime installation',
 async render(host){
  host.innerHTML=appearancePanelHTML();
  wireAppearancePanel(host);
 }},

{group:'App & access',id:'network',title:'Network & access',
 blurb:'Where this workspace is reachable, and the PIN that guards it',
 keywords:'network lan wifi address port pin security remote access localhost',
 async render(host){
  const [s,net]=await Promise.all([api('/settings'),api('/network')]);
  host.innerHTML=`
  <h2>Network &amp; access</h2>
  <p class="dim">Connection addresses and access controls.</p>

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
  <p class="dim">Required on other devices and to unlock relationship settings.</p>
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

{group:'App & access',id:'updates',title:'Updates',
 blurb:'What version you are on, and how to move',
 keywords:'update version release upgrade changelog github',
 async render(host){
  const d=await api('/updates').catch(error=>({version:'unknown',has_update:false,error:error.message}));
  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <h2 style="margin:0">Updates</h2>
    <span class="pill ${d.has_update?'status-warn':'status-good'}">${d.has_update?`v${esc(d.latest_version)} available`:d.error?'Check unavailable':'Up to date'}</span>
  </div>
  <dl class="fact-list">
    <div><dt>Installed</dt><dd>v${esc(d.version)}</dd></div>
    <div><dt>Latest released</dt><dd>${d.latest_version?'v'+esc(d.latest_version):'Not checked'}</dd></div>
  </dl>
  ${d.has_update?`<div class="notice-strip" style="border-left-color:var(--accent);margin-top:16px">
    <p><strong>Tamanitomo v${esc(d.latest_version)} is available.</strong></p>
    <p class="dim small" style="margin-top:4px">This will update the Tamanitomo application. Your companion’s memories, emotions, journals, and vault will remain completely untouched.</p>
    <section class="update-release-notes" aria-labelledby="update-release-notes-title">
      <h3 id="update-release-notes-title">What’s new in v${esc(d.latest_version)}</h3>
      <div class="update-release-notes-body">${esc(d.release_notes||'No patch notes were provided for this release.')}</div>
    </section>
    <div class="update-actions">
      <button class="act" id="btn-inapp-update">⚡ Update to v${esc(d.latest_version)} Now</button>
      ${d.release_url?`<a class="link-button" href="${esc(d.release_url)}" target="_blank" rel="noopener">Open release page →</a>`:''}
    </div>
  </div>`:`<div class="notice-strip" style="margin-top:16px">
    <p class="dim" style="margin:0">${d.error?esc(d.error):d.latest_version?'You have the latest stable release.':'No update check is available yet.'} Installed: v${esc(d.version)}.</p>
    <div style="margin-top:10px">
      <button class="quiet" id="btn-check-updates">🔄 Check for updates</button>
    </div>
  </div>`}
  <h3 class="section-subheading">Update scope</h3>
  <p class="dim small">This updates Tamanitomo’s interface, autonomous companion routines, and application code. The upstream Hermes Agent engine and external model providers are kept isolated and stable.</p>
  <p class="dim small">Updates come from the latest stable <a href="https://github.com/tamanitomo/tamanitomo/releases/latest" target="_blank" rel="noopener">official GitHub release</a>.</p>`;

  const updateBtn = host.querySelector('#btn-inapp-update');
  if (updateBtn) {
    updateBtn.onclick = async () => {
      if (!confirm(`Install Tamanitomo v${d.latest_version} now?\n\nYour companions’ memories and vault files will remain untouched.\nThe workspace will restart automatically.`)) return;
      updateBtn.disabled = true;
      updateBtn.textContent = 'Updating...';
      try {
        const result = await action('/updates/apply', {});
        if (result.result?.restarting && window.waitForRestart) window.waitForRestart(result.result.version, d.instance_id);
        else openSettings(null, 'updates');
      } catch (err) {
        updateBtn.disabled = false;
        updateBtn.textContent = `⚡ Update to v${d.latest_version} Now`;
        alert('Update failed: ' + err.message);
      }
    };
  }

  const checkBtn = host.querySelector('#btn-check-updates');
  if (checkBtn) {
    checkBtn.onclick = async () => {
      checkBtn.disabled = true;
      checkBtn.textContent = 'Checking GitHub...';
      try {
        const fresh = await api('/updates/check', { method: 'POST' });
        if (fresh.error) {
          notice(fresh.error, true);
        } else if (fresh.has_update) {
          notice(`New version v${fresh.latest_version} available!`);
        } else {
          notice('Tamanitomo is up to date.');
        }
        openSettings(null, 'updates');
      } catch (err) {
        notice('Check failed: ' + err.message, true);
        checkBtn.disabled = false;
        checkBtn.textContent = '🔄 Check for updates';
      }
    };
  }
 }},

{group:'App & access',id:'diagnostics',title:'Diagnostics',
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

{group:'App & access',id:'hermes-core',bare:true,title:'Installation & gateway',
 blurb:'The runtime behind your companion, and the process that keeps it running',
 keywords:'hermes install update gateway routine service hooks doctor repair profile archive',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['installation','stack','gateway','lifecycle']);
 }},

{group:'Models & providers',id:'hermes-models',bare:true,title:'Models & fallbacks',
 blurb:'Which model answers, and what answers when it cannot',
 keywords:'model provider fallback openrouter ollama base url presets cascade reasoning',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['models','presets']);
 }},

{group:'Models & providers',id:'hermes-accounts',bare:true,title:'Accounts & credentials',
 blurb:'API keys, sign-ins, and Hermes’s own setup menus',
 keywords:'api key credential oauth signin telegram discord token console setup',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['accounts']);
 }},

{group:'Schedule & usage',id:'jobs',title:'Scheduled jobs',
 blurb:'Every cron job, what runs it, and whether it worked',
 keywords:'cron jobs schedule routine model tokens prompt run pause resume history',
 render:renderJobsPanel},

{group:'Images & voice',id:'connect-images',title:'Image generation',
 blurb:'ComfyUI, Civitai, and the reference photograph',
 keywords:'comfyui image generation civitai lora checkpoint endpoint portrait',
 async render(host){
  host.innerHTML=await imagesPanelHTML();
  wireImagesPanel(host);

 }},

{group:'Images & voice',id:'connect-voice',title:'Voice',
 blurb:'Which engine speaks, and how it sounds',
 keywords:'voice tts speech engine piper edge elevenlabs openai speed pitch',
 render:renderVoicePanel},

{group:'App & access',id:'dashboard',title:'Hermes dashboard',
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
function wireModelPicker(root,{provider,baseUrl,value,onChange,defaultLabel="Follow the profile default"}){
  const select=root.querySelector('[data-model-select]');
  const custom=root.querySelector('[data-model-custom]');
  const note=root.querySelector('[data-model-note]');
  const CUSTOM='__custom__';
  const read=()=>select.value===CUSTOM?custom.value.trim():select.value;
  const paint=d=>{
    const models=d.models||[];
    const known=models.includes(custom.value.trim());
    select.innerHTML=
      `<option value="">${esc(defaultLabel)}</option>`+
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
    const request=Symbol();root.modelRequest=request;
    return modelList(provider(),baseUrl(),refresh).then(data=>{if(root.modelRequest===request)paint(data);});
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

// One provider-aware editor for the primary model and background tiers.
function providerNeedsURL(provider,existing=''){const name=String(provider).toLowerCase();return name!=='openai-codex'&&(Boolean(existing)||['custom','ollama','lmstudio','lm-studio','vllm','local'].includes(name));}
async function wireAvailableModel(providerField,modelField,urlField,{primary=false}={}){
  const data=await knownProviders();
  if(!providerField.isConnected)return;
  const currentProvider=providerField.value;
  const choices=new Map(data.providers.map(p=>[p.provider,p.provider==='openai-codex'?'ChatGPT':p.label]));
  if(currentProvider&&!choices.has(currentProvider))choices.set(currentProvider,currentProvider);
  choices.set('custom','Custom / local server');
  const select=document.createElement('select');
  for(const attribute of providerField.attributes)if(!['list','type','value','placeholder'].includes(attribute.name))select.setAttribute(attribute.name,attribute.value);
  select.innerHTML=options([['',primary?'Choose a provider':'Follow primary provider'],...choices],currentProvider);
  providerField.replaceWith(select);
  modelField.type='hidden';
  modelField.insertAdjacentHTML('afterend',modelPickerHTML(modelField.id||'available-model',modelField.value));
  const picker=modelField.nextElementSibling;
  const refresh=()=>{
    if(urlField){urlField.closest('label').hidden=!providerNeedsURL(select.value,urlField.value);if(!providerNeedsURL(select.value,urlField.value))urlField.value='';}
    return wireModelPicker(picker,{provider:()=>select.value||(primary?'':$('primary-provider')?.value||''),baseUrl:()=>urlField?.value||(!select.value&&!primary?$('primary-url')?.value||'':''),value:modelField.value,
      defaultLabel:primary||select.value?'Choose a model':'Follow primary model',onChange:value=>{modelField.value=value;}});
  };
  select.onchange=()=>{modelField.value='';if(urlField)urlField.value='';refresh();};
  if(urlField)urlField.onchange=()=>refresh();
  if(!primary)for(const id of ['primary-provider','primary-url'])$(id)?.addEventListener('change',()=>{if(!select.value){modelField.value='';refresh();}});
  refresh();
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
  const usage=data.usage||{};
  const tokens=n=>n==null?'Unknown':Number(n).toLocaleString();
  const failed=jobs.filter(j=>j.last_status==='error').length;
  const active=jobs.filter(j=>j.enabled).length;
  const noModel=jobs.filter(j=>!j.no_agent&&!j.model).length;

  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <h2 style="margin:0">Scheduled jobs</h2>
    <div class="actions" style="margin:0">
      <button class="quiet" id="jobs-pause">Pause model jobs</button><button class="quiet" id="jobs-activate">Enable model jobs</button><button class="quiet" id="jobs-history">Run history</button>
      <button class="quiet" id="jobs-apply-models">Apply job models</button>
      <button class="quiet" id="jobs-repair">Install / repair</button>
    </div>
  </div>
  <p class="dim">Times are in ${esc(data.timezone)}. Model-free maintenance stays active when model jobs are paused.</p>
  <p class="dim small">${esc(usage.note||'Token usage unavailable.')}${usage.partial?' Recent history is truncated.':''}</p>
  <details><summary>Which model should I use?</summary><p class="dim small">Use a small or fast model with reliable tool use for frequent checks. Try a stronger reasoning model for daily and weekly reflection. Script-only jobs need no model. Image tasks need an image provider; a conversation model alone is not enough.</p></details>
  <div class="stat-strip">
    <button data-filter="all"><span>Installed</span><strong>${jobs.length}</strong></button>
    <button data-filter="active"><span>Scheduled</span><strong>${active}</strong></button>
    <button data-filter="paused"><span>Paused</span><strong>${jobs.length-active}</strong></button>
    <button data-filter="error"><span>Last run failed</span><strong>${failed}</strong></button>
  </div>
  ${noModel?`<p class="dim small">${noModel} model-backed job${noModel===1?' has':'s have'} no model of their own and follow the profile default.</p>`:''}
  <details class="card routing-card" id="job-routing">
    <summary><strong>Move every job to another provider</strong>
      <small class="dim">Model, provider and endpoint together, across all ${jobs.filter(j=>!j.no_agent).length} model-backed jobs</small></summary>
    <div class="routing-body">
      <div class="chip-row" id="routing-presets"><span class="dim small">Finding your providers…</span></div>
      <p class="dim small" id="routing-hint">Pick a provider, then adjust anything below before applying.</p>
      <div class="form-grid">
        <label>Provider<select id="routing-provider"><option value="">Follow primary provider</option></select></label>
        <label>Model${modelPickerHTML('routing','')}
          <input type="hidden" id="routing-model"></label>
        <label class="wide">Endpoint<input id="routing-base-url" placeholder="Leave empty unless the provider needs a specific address">
          <small class="dim">Address of your local server or custom gateway.</small></label>
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
  const schedule=j=>j.schedule?.expr||j.schedule?.display||'';

  const statusPill=j=>{
    if(j.last_status==='error')return '<span class="pill status-bad">Last run failed</span>';
    if(j.last_status==='ok')return '<span class="pill status-good">Last run ok</span>';
    return '<span class="pill">Not run yet</span>';
  };
  const draw=async()=>{
    if(!await confirmEditorLeave('settings-main'))return;
    const q=host.querySelector('#job-search').value.toLowerCase();
    const state=host.querySelector('#job-filter').value;
    const rows=jobs.filter(j=>(!q||(j.name||'').toLowerCase().includes(q))&&
      (state==='all'||state==='active'&&j.enabled||state==='paused'&&!j.enabled||state==='error'&&j.last_status==='error'));
    host.querySelector('#job-list').innerHTML=rows.length?rows.map(j=>`
      <details class="job-row${j.last_status==='error'?' is-failing':''}" data-job-id="${esc(j.id)}">
        <summary>
          <span class="job-name"><strong>${esc(j.name||j.id)}</strong>
            <small class="dim">${j.no_agent?'Runs a script · no model':esc(j.model||'Profile default model')} · <code data-schedule-label>${esc(scheduleLabel(schedule(j)))}</code></small></span>
          <span class="job-state">${statusPill(j)}${j.enabled?'':'<span class="pill">Paused</span>'}</span>
        </summary>
        <div class="job-body">
          <dl class="fact-list">
            <div><dt>Next run</dt><dd>${j.enabled?esc(when(j.next_run_at)):'Paused'}</dd></div>
            <div><dt>Last run</dt><dd>${j.last_run_at?esc(when(j.last_run_at)):'Never'}</dd></div>
            <div><dt>Prompt size</dt><dd>${j.no_agent?'—':Number(j.prompt_chars||0).toLocaleString()+' characters sent each run'}</dd></div>
            ${j.no_agent?'<div><dt>Model tokens</dt><dd>None · script only</dd></div>':[['Last run','last_run'],['Last hour','hour'],['Last 24 hours','day'],['Last 7 days','week']].map(([label,key])=>`<div><dt>${label} tokens</dt><dd>${tokens(usage.jobs?.[j.id]?.[key])}</dd></div>`).join('')}
            <div><dt>Delivers to</dt><dd>${esc(j.deliver||'—')}</dd></div>
          </dl>
          ${j.last_error?`<div class="notice-strip"><p><strong>Last error</strong></p><pre class="command-block">${esc(j.last_error)}</pre></div>`:''}
          <div class="form-grid">
            ${scheduleEditorHTML(j.id,schedule(j))}
            ${j.no_agent?'':`
            <label>Provider<input data-field="provider" data-job="${esc(j.id)}" list="job-provider-ids" value="${esc(j.provider||'')}" placeholder="Follow the profile default"></label>
            <label>Model${modelPickerHTML('job-'+j.id,j.model)}
              <input type="hidden" data-field="model" data-job="${esc(j.id)}" value="${esc(j.model||'')}"></label>
            <label>Reasoning effort<select data-field="reasoning_effort" data-job="${esc(j.id)}">${options([['','Hermes default'],['none','None'],['low','Low'],['medium','Medium'],['high','High']],j.reasoning_effort||'')}</select></label>
            <label class="wide">Endpoint<input data-field="base_url" data-job="${esc(j.id)}" value="${esc(j.base_url||'')}" placeholder="Leave empty to use the provider's own address">
              <small class="dim">Address of your local server or custom gateway.</small></label>`}
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
    wireScheduleEditors(host);
    for(const row of host.querySelectorAll('.job-row')){
      const picker=row.querySelector('[data-model-picker]');
      if(!picker)continue;
      const field=n=>row.querySelector(`[data-field="${n}"]`);
      const available=await knownProviders();
      const providers=new Map(available.providers.map(p=>[p.provider,p.provider==='openai-codex'?'ChatGPT':p.label]));
      if(field('provider').value&&!providers.has(field('provider').value))providers.set(field('provider').value,field('provider').value);
      providers.set('custom','Custom / local server');
      const previous=field('provider');previous.outerHTML=`<select data-field="provider" data-job="${esc(row.dataset.jobId)}">${options([['','Follow primary provider'],...providers],previous.value)}</select>`;

      const paintEndpoint=()=>{const endpoint=field('base_url');if(endpoint){endpoint.closest('label').hidden=!providerNeedsURL(field('provider').value,endpoint.value);if(!providerNeedsURL(field('provider').value,endpoint.value))endpoint.value='';}};
      paintEndpoint();
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
          if(name==='provider'){field('model').value='';field('base_url').value='';}paintEndpoint();
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
      let wanted;try{wanted=readSchedule(field('schedule').closest('[data-schedule-editor]'));}catch(error){status.textContent=error.message;return;}
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
        clearEditorDirty('settings-main-job-'+id);
        Object.assign(job,payload,payload.schedule?{schedule:{...job.schedule,display:payload.schedule,expr:payload.schedule}}:{});
        const editor=field('schedule').closest('[data-schedule-editor]');editor.dataset.original=wanted;editor.dataset.mode=editor.querySelector('[data-schedule-mode]').value;field('schedule').value=wanted;
        b.closest('.job-row').querySelector('[data-schedule-label]').textContent=scheduleLabel(wanted);
        b.closest('.job-row').open=false;
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
  const buildRoutingPicker=()=>{const endpoint=host.querySelector('#routing-base-url');endpoint.closest('label').hidden=!providerNeedsURL(host.querySelector('#routing-provider').value,endpoint.value);if(endpoint.closest('label').hidden)endpoint.value='';return wireModelPicker(routingPicker,{
    provider:()=>host.querySelector('#routing-provider').value.trim(),
    baseUrl:()=>host.querySelector('#routing-base-url').value.trim(),
    value:routingModel.value,
    onChange:v=>{routingModel.value=v;}});};
  buildRoutingPicker();
  for(const id of ['#routing-provider','#routing-base-url'])
    host.querySelector(id).addEventListener('change',()=>{if(id==='#routing-provider'){routingModel.value='';host.querySelector('#routing-base-url').value='';}buildRoutingPicker();});

  /* A chip per reachable provider, plus a way back to the profile default.
     Choosing one sets the provider and endpoint and reloads the model list;
     nothing is sent until Apply. */
  knownProviders().then(d=>{
    if(!host.isConnected)return;
    const strip=host.querySelector('#routing-presets');
    const choices=new Map(d.providers.map(r=>[r.provider,r.provider==='openai-codex'?'ChatGPT':r.label]));choices.set('custom','Custom / local server');
    host.querySelector('#routing-provider').innerHTML=options([['','Follow primary provider'],...choices],'');
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
  bindAction('jobs-pause','/maintenance/pause',{},()=>openSettings(null,'jobs'));
  bindAction('jobs-activate','/maintenance/activate',{},()=>openSettings(null,'jobs'));
  bindAction('jobs-apply-models','/jobs/apply-models');
  bindAction('jobs-repair','/maintenance/repair');
  draw();

  /* The provider field autocompletes to what this profile can actually reach,
     with the rest of the catalogue behind it for anything not set up yet. */
  Promise.all([knownProviders(),api('/providers').catch(()=>({providers:[]}))]).then(([mine,all])=>{
    if(!host.isConnected)return;
    const list=document.createElement('datalist');
    list.id='job-provider-ids';
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
async function renderVoicePanel(host){return renderVoiceStudio(host,true);}

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
        :`<p class="dim small">No platform PIN is set on this workspace. Type <strong>${esc(name)}</strong> below to continue, or set a PIN first under App &amp; access → Network &amp; access.</p>
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
      error.innerHTML='<span class="bad">That is not their name.</span>';return;
    }
    $('product-dialog').close();
    if(!confirm(`Changing how ${name} relates to you rewrites a dynamic the two of you have already built. Pace, progression and intimacy all feed their behaviour directly.\n\nContinue?`))return;
    relationshipUnlocked=true;
    openSettings(null,'relationship');
  };
}

/* ----------------------------------------------------------------- the page */

/* Which panel is open survives a reload, so a link that has to reload the
   workspace first (switching profile, finishing onboarding) still lands on the
   panel it meant to. */
const PANEL_KEY='settings-panel';
let settingsDirectLink=false;
let settingsPanel=(()=>{try{return sessionStorage.getItem(PANEL_KEY);}catch(error){return null;}})();
function rememberPanel(id){
  settingsPanel=id;
  try{sessionStorage.setItem(PANEL_KEY,id);}catch(error){/* private window */}
}
/* Jump straight to a panel from anywhere: openSettings('jobs'). */
async function openSettings(_group,panel){
  if(current==='settings'&&!await confirmEditorLeave('settings-main'))return;
  if(panel){rememberPanel(panel);settingsDirectLink=true;}
  if(current!=='settings')return showTab('settings');
  return render('settings');
}
/* For links that must reload the workspace before Settings can be drawn. */
function aimSettings(panel){if(panel){rememberPanel(panel);settingsDirectLink=true;}}
window.openSettings=openSettings;
window.aimSettings=aimSettings;

workspaceHandlers.settings=async()=>{
  const order=['Companion','Models & providers','Images & voice','Schedule & usage','App & access'];
  const groups=order.map(name=>[name,settingsPanels.filter(p=>p.group===name)]);
  groups.find(([name])=>name==='Images & voice')[1].sort((a,b)=>['connect-images','photos','connect-voice'].indexOf(a.id)-['connect-images','photos','connect-voice'].indexOf(b.id));
  const descriptions=['Contact, awareness, relationship','Models, accounts, fallbacks','Providers, workflows, photos, voice','Daily rhythm, jobs, usage','Appearance, access, installation'];
  const requested=settingsPanels.find(p=>p.id===settingsPanel);
  returnHermesCards();
  const keepPool=hermesPool;
  $('settings').innerHTML=`
    <div class="home-title settings-title"><h2 class="page-title">Settings</h2></div>
    <div class="settings-shell">
      <nav class="settings-sidebar" aria-label="Settings groups">
        <label class="settings-search-label"><span class="sr-only">Find a setting</span><input id="settings-search" type="search" placeholder="Find a setting"></label>
        ${groups.map(([name],i)=>`<button class="settings-group-button" data-group="${i}"><span>${esc(name)}</span><small>${esc(descriptions[i])}</small><span class="settings-chevron" aria-hidden="true">›</span></button>`).join('')}
        <div id="settings-search-results" class="settings-search-results" hidden></div>
      </nav>
      <div class="settings-body" id="settings-panel">
        <div class="settings-group-heading"><button class="quiet settings-back" id="settings-back" aria-label="Back to settings">←</button><h2 id="settings-group-title" tabindex="-1"></h2></div>
        <div id="settings-group-content"></div>
      </div>
    </div>`;
  if(keepPool)$('settings').append(keepPool);
  let request=0;
  const show=async(index,focusPanel='',enter=true)=>{
    if(!await confirmEditorLeave('settings-main'))return false;
    const version=++request,[name,panels]=groups[index];
    rememberPanel(focusPanel||panels[0].id);
    returnHermesCards();
    $('settings-group-title').textContent=name;
    for(const button of $('settings').querySelectorAll('[data-group]'))button.setAttribute('aria-current',Number(button.dataset.group)===index?'page':'false');
    $('settings').classList.toggle('settings-detail',enter);
    const content=$('settings-group-content');content.replaceChildren();
    // Render sequentially: shared Hermes cards keep their handlers and unique IDs.
    for(const panel of panels){
      if(version!==request)return false;
      const host=document.createElement('section');
      host.dataset.settingsSection=panel.id;host.id='settings-section-'+panel.id;
      host.className='settings-section '+(panel.bare?'panel-bare':'card');
      host.setAttribute('aria-label',panel.title);content.append(host);
      host.innerHTML='<p class="dim" role="status">Loading…</p>';
      try{await panel.render(host);}catch(error){host.innerHTML=`<h3>${esc(panel.title)}</h3><p class="bad">${esc(error.message)}</p>`;}
    }
    if(version!==request)return false;
    if(enter){
      const destination=focusPanel?document.getElementById('settings-section-'+focusPanel):$('settings-group-title');
      destination?.scrollIntoView({block:'start'});
      $('settings-group-title').focus({preventScroll:true});
    }
    return true;
  };
  for(const button of $('settings').querySelectorAll('[data-group]'))button.onclick=()=>show(Number(button.dataset.group));
  $('settings-back').onclick=async()=>{
    if(!await confirmEditorLeave('settings-main'))return;
    $('settings').classList.remove('settings-detail');
    $('settings').querySelector('[aria-current="page"]')?.focus();
    $('settings').scrollIntoView({block:'start'});
  };
  const search=$('settings-search'),results=$('settings-search-results');
  search.oninput=()=>{
    const q=search.value.trim().toLowerCase();results.hidden=!q;
    const matches=settingsPanels.filter(p=>`${p.title} ${p.blurb} ${p.keywords} ${p.group}`.toLowerCase().includes(q));
    results.innerHTML=matches.map(p=>`<button class="quiet" data-panel="${esc(p.id)}">${esc(p.title)}</button>`).join('')||'<p class="dim">No matching settings.</p>';
    for(const button of results.querySelectorAll('button'))button.onclick=async()=>{
      const panel=settingsPanels.find(p=>p.id===button.dataset.panel);
      if(await show(order.indexOf(panel.group),panel.id)){search.value='';results.hidden=true;}
    };
  };
  await show(requested?order.indexOf(requested.group):0,requested?.id||'',Boolean(settingsDirectLink));
  settingsDirectLink=false;
};
