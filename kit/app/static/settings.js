/* Settings: one section per page, listed in SETTINGS_NAV; each saves on its own. */

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
function placeHermesCards(host,names,{foldAll=false}={}){
  // The panel still holds its loading placeholder; the cards replace it rather
  // than stacking underneath it.
  host.innerHTML='';
  const pool=hermesPool;
  if(!pool||!host.isConnected)return;
  const labels={stack:'Optional local components',gateway:'Gateway & background service',lifecycle:'Profile maintenance',presets:'Ready-made model configurations',models:'Per-tier models (advanced)'};
  for(const [index,name] of names.entries()){
    const card=pool.querySelector(`[data-hermes-card="${name}"]`);
    if(!card)continue;
    if(index===0&&!foldAll){host.append(card);continue;}
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
      status.textContent=(result&&result.note)||note;
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
{id:'contact',title:'Contact & outreach',
 blurb:'When they may write first, and how often. Replies are always allowed.',
 keywords:'quiet hours outreach messages photos voice notes boundaries initiative',
 async render(host){
  const s=await api('/settings');
  const perm=k=>options([['yes','Always welcome'],['ask','Ask me first'],['no','Never']],s.content_permissions[k]);
  host.innerHTML=`

  <div class="contact-settings">
    <div class="contact-row">
      <label class="contact-label" for="qs">Quiet hours</label>
      <div class="contact-controls">
        <input type="time" id="qs" value="${esc(s.quiet_start)}" placeholder="22:00" aria-label="Quiet hours start">
        <span class="range-sep" aria-hidden="true">–</span>
        <input type="time" id="qe" value="${esc(s.quiet_end)}" placeholder="08:00" aria-label="Quiet hours end">
        <label class="switch-container compact-toggle" data-toggle-row title="Adjust to your sleep pattern">
          <input type="checkbox" id="adapt" ${s.adaptive_quiet?'checked':''}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label">Adapt quiet hours</span>
        </label>
      </div>
    </div>

    <div class="contact-row">
      <label class="contact-label" for="out">Outreach</label>
      <div class="contact-controls">
        <select id="out">${options([['free','Social & updates'],['updates_only','Updates only'],['never','Replies only']],s.outreach)}</select>
        <div class="daily-limit-field" title="Daily message limit (0 means unlimited)">
          <input id="cap" type="number" min="0" max="100" value="${s.outreach_per_day??3}" aria-label="Daily message limit (0 means unlimited)">
          <span class="dim small">/ day</span>
        </div>
      </div>
    </div>

    <h3 class="section-subheading">Messages they start with media</h3>
    <div class="contact-row">
      <label class="contact-label" for="pimage">Photos</label>
      <div class="contact-controls">
        <select id="pimage">${perm('image')}</select>
      </div>
    </div>

    <div class="contact-row">
      <label class="contact-label" for="pvoice">Voice notes</label>
      <div class="contact-controls">
        <select id="pvoice">${perm('voice')}</select>
      </div>
    </div>
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

{id:'rhythm',title:'Daily rhythm',
 blurb:'Their own hours, and what carries between companions',
 keywords:'autonomy windows routine reflection continuity shared memory',
 async render(host){
  const s=await api('/settings');
  host.innerHTML=`
  <h3 class="section-subheading">Independent time</h3>
  <p class="set-hint">When they read, write or work on their own projects.</p>
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:12px 0 16px">
    <div id="autonomy-times" class="time-chips" style="margin:0"></div>
    <button type="button" class="quiet small" id="add-autonomy-time" style="padding:6px 12px;height:34px">+ Add time</button>
  </div>

  <h3 class="section-subheading">Shared memory</h3>
  <div class="contact-settings" style="margin-top:10px">
    <div class="contact-row">
      <label class="contact-label">Shared memory</label>
      <div class="contact-controls">
        <label class="switch-container compact-toggle" data-toggle-row title="Let your other companions use these memories">
          <input type="checkbox" id="share" ${s.share_people?'checked':''}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label">Share memories about you with other companions</span>
        </label>
      </div>
    </div>
  </div>
  ${settingsFooter('Save')}`;
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

{id:'awareness',title:'Awareness',
 blurb:'Where you live, what they sense, and what carries between conversations',
 keywords:'sensors location weather realism ambient context senses awareness conversation handoff channels telegram reset web pages reader privacy',
 async render(host){
  const s=await api('/settings');
  const on=Object.keys(s.available_sensors).filter(k=>s.sensors.includes(k)).length;
  const total=Object.keys(s.available_sensors).length;
  host.innerHTML=`
  <div class="contact-settings" style="margin-bottom:18px">
    <div class="contact-row">
      <label class="contact-label" for="loc">Where you live</label>
      <div class="contact-controls">
        <input id="loc" value="${esc(s.location)}" placeholder="Raleigh, NC" style="max-width:300px">
      </div>
    </div>
  </div>

  <div class="section-heading" style="margin-top:20px">
    <h3 class="section-subheading">Conversations and reading</h3>
  </div>
  <div class="sensor-grid">
    ${toggleRow('conversation-handoff','Pick up where you left off','The last few messages from your other conversations (another channel, or before the morning fresh start) come along, so a new conversation keeps the thread.',s.conversation_handoff)}
    ${toggleRow('local-web-reader','Read web pages on this machine',s.local_web_reader||!s.web_reader_other
      ?'Pages are fetched from their own site and read here. No reading service sees what is read, and a failed read is never passed to one.'
      :`Pages are read by ${s.web_reader_other}, chosen in Hermes. Switch on to read them here instead.`,s.local_web_reader)}
  </div>

  <div class="section-heading" style="margin-top:20px">
    <h3 class="section-subheading">Sensors</h3>
    <span class="pill ${on?'status-good':'status-warn'}" id="sensor-count">${on} of ${total} on</span>
  </div>
  <div class="sensor-grid">
    ${Object.entries(s.available_sensors).map(([k,blurb])=>
      toggleRow('sensor-'+k,({dates:'Important dates',care:'Follow-ups',durations:'Milestones',thread:'Conversation rhythm',daylight:'Daylight',weather:'Weather',music:'Music'})[k]||k,({weather:'Local conditions, updated hourly.',daylight:'Seasons, moon and daylight.',dates:'Upcoming birthdays and anniversaries.',care:'Things worth checking in about.',durations:'Time since important dates.',thread:'Time since your last conversation.',music:'Spotify playback or room mood.'})[k]||blurb,s.sensors.includes(k),`data-sensor="${esc(k)}"`)).join('')}
  </div>
  ${settingsFooter('Save')}`;
  wireToggles(host);
  const recount=()=>{
    const live=[...host.querySelectorAll('[data-sensor]')].filter(x=>x.checked).length;
    const pill=host.querySelector('#sensor-count');
    pill.textContent=`${live} of ${total} on`;
    pill.className='pill '+(live?'status-good':'status-warn');
  };
  for(const box of host.querySelectorAll('[data-sensor]'))box.addEventListener('change',recount);
  wireSave(host,()=>{
    const payload={
      location:host.querySelector('#loc').value,
      conversation_handoff:host.querySelector('#conversation-handoff').checked,
      sensors:[...host.querySelectorAll('[data-sensor]')].filter(x=>x.checked).map(x=>x.dataset.sensor)};
    // Sent only when switched, so saving a location never overrides a reader chosen in Hermes.
    const reader=host.querySelector('#local-web-reader').checked;
    if(reader!==s.local_web_reader)payload.local_web_reader=reader;
    return saveSettings(payload);
  });
 }},

{id:'photos',title:'Photo sessions',
 blurb:'Pictures from their day, taken with your image provider, and what stays blurred',
 keywords:'photos timeline images style budget nsfw blur scanner nudenet review',
 async render(host){
  const [s,prefs,scanner]=await Promise.all([api('/settings'),api('/media/preferences'),api('/media/scanner')]);
  host.innerHTML=`

  <div class="contact-settings">
    <div class="contact-row">
      <label class="contact-label">Automatic photos</label>
      <div class="contact-controls">
        <label class="switch-container compact-toggle" data-toggle-row>
          <input type="checkbox" id="tl" ${s.image_timeline?'checked':''}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label">Enabled</span>
        </label>
        <span class="range-sep" aria-hidden="true">·</span>
        <label for="image-interval" style="margin:0;font-size:13.5px;color:var(--dim);display:inline-flex;align-items:center;gap:6px">Interval:
          <select id="image-interval" style="margin:0">${options([5,10,15,20,30,60,120,240,360,720,1440].map(n=>[String(n),n<60?n+' minutes':n===60?'1 hour':n===1440?'24 hours':(n/60)+' hours']),String(s.image_interval_minutes||15))}</select>
        </label>
      </div>
    </div>

    <div class="contact-row">
      <label class="contact-label" for="image-style">Image style</label>
      <div class="contact-controls">
        <select id="image-style">${options(Object.entries(s.image_styles),s.image_style)}</select>
        <span class="range-sep" aria-hidden="true">·</span>
        <div class="daily-limit-field" title="Gigabytes kept before the oldest are pruned">
          <label for="gb" style="margin:0;font-size:13.5px;color:var(--dim);display:inline-flex;align-items:center;gap:6px">Budget:
            <input id="gb" type="number" step="0.5" min="0" value="${s.timeline_budget_gb}" style="width:75px">
            <span class="dim small">GB</span>
          </label>
        </div>
      </div>
    </div>
  </div>

  <details class="settings-advanced"><summary>Review &amp; blurring</summary>
  <div class="contact-settings" style="margin-top:12px">
    <div class="contact-row">
      <label class="contact-label" for="media-review-mode">Who checks it</label>
      <div class="contact-controls">
        <select id="media-review-mode">${options([
          ['none','Nobody — deliver as generated'],
          ['local','This machine, privately (NudeNet)'],
          ['remote','A vision model']],
          !prefs.review_before_delivery?'none':(prefs.review_provider==='local-nsfw'?'local':'remote'))}</select>
      </div>
    </div>
  </div>
  <div id="media-review-local" hidden>
    <p class="dim small">NudeNet runs here and nothing leaves the machine. About 12&nbsp;MB of model and roughly
      150&nbsp;MB of memory while scanning. It finds exposed intimate anatomy; it does not judge scene accuracy
      or clothed content.</p>
    <p class="dim small">${scanner.installed?'<span class="good">Installed.</span>':'<span class="warn">Not installed yet</span> — downloading it needs internet.'}</p>
    <div class="actions"><button class="quiet" id="install-local-scanner">${scanner.installed?'Check installation':'Install it'}</button></div>
  </div>
  <div id="media-review-remote" hidden>
    <p class="dim small">A vision model can also judge scene and clothing, but the picture is sent to it.</p>
    <div class="contact-settings">
      <div class="contact-row">
        <label class="contact-label" for="media-review-provider">Provider</label>
        <div class="contact-controls">
          <input id="media-review-provider" value="${esc(prefs.review_provider==='local-nsfw'?'':prefs.review_provider)}" placeholder="openai, anthropic…">
        </div>
      </div>
      <div class="contact-row">
        <label class="contact-label" for="media-review-model">Model</label>
        <div class="contact-controls">
          <input id="media-review-model" value="${esc(prefs.review_model)}" placeholder="Leave empty for the compression model">
        </div>
      </div>
    </div>
  </div>

  <h3 class="section-subheading">What stays blurred</h3>
  <p class="dim small" style="margin-top:0">${s.adult_images
    ? 'Adult images are allowed for this companion, so the check <strong>sorts and labels</strong> rather than blocks: '
      + 'a picture meant to be explicit is delivered as it was made, not regenerated with clothes put back on. '
      + 'It still gets a rating, and the blur settings below still decide whether you see it covered first.'
    : 'Adult images are off for this companion, so anything the check rates sensitive is held rather than sent.'
      + (s.adult_images_available?' Allowing them is under Companion \u2192 Relationship.':'')}</p>
  <div class="contact-settings">
    <div class="contact-row">
      <label class="switch-container compact-toggle" data-toggle-row title="Open one to reveal it">
        <input type="checkbox" id="media-blur" ${prefs.blur_nsfw_initially?'checked':''}>
        <span class="switch-slider" aria-hidden="true"></span>
        <span class="switch-label">Blur pictures found to be sensitive</span>
      </label>
    </div>
    <div class="contact-row">
      <label class="switch-container compact-toggle" data-toggle-row title="Includes scans that failed, so a check that could not run never passes as a clean one">
        <input type="checkbox" id="media-blur-unknown" ${prefs.blur_unknown_initially!==false?'checked':''}>
        <span class="switch-slider" aria-hidden="true"></span>
        <span class="switch-label">Blur pictures nothing has checked</span>
      </label>
    </div>
  </div>
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

{id:'relationship',title:'Relationship',
 blurb:'How closeness grows — locked by default',
 keywords:'relationship pace progression intimacy romance milestones meters peer nsfw adult images nudity',
 async render(host){
  const s=await api('/settings');
  const net=await api('/network').catch(()=>({remote_pin_configured:false}));
  const labels={
    progression:{off:'Hidden',subtle:'Subtle, natural familiarity',milestones:'Shared milestones shown'},
    pace:{slow:'Slow and gradual',natural:'Natural',quick:'Open to quicker familiarity'}};

  if(!relationshipUnlocked){
    host.innerHTML=`
    <p class="dim">Locked. Unlock to change how your relationship develops.</p>
    <dl class="fact-list">
      <div><dt>Progression</dt><dd>${esc(labels.progression[s.relationship_progression]||s.relationship_progression)}</dd></div>
      <div><dt>Pace</dt><dd>${esc(labels.pace[s.relationship_pace]||s.relationship_pace)}</dd></div>
      <div><dt>Intimacy &amp; romance</dt><dd>${s.explicit?'Romantic connection enabled':'Friendly / platonic only'}</dd></div>
      ${s.adult_images_available?`<div><dt>Adult images</dt><dd>${s.adult_images?'Allowed':'Not allowed'}</dd></div>`:''}
      <div><dt>Other companions</dt><dd>${s.peer_interaction?'May interact':'Kept apart'}</dd></div>
      <div><dt>Connection meters</dt><dd>${s.bars?'Shown':'Hidden'}</dd></div>
    </dl>
    <div class="actions">
      <button class="quiet" id="unlock-relationship">${icon('pin')} Unlock and change</button>
    </div>
    <p class="dim small">${net.remote_pin_configured
      ? 'Unlocking asks for your platform PIN.'
      : 'No platform PIN is set, so unlocking asks you to type their name instead. A PIN can be set under Settings → App → Access &amp; PIN.'}</p>`;
    host.querySelector('#unlock-relationship').onclick=()=>unlockRelationship(net.remote_pin_configured);
    return;
  }

  host.innerHTML=`
  <p class="dim"><span class="pill status-warn">Unlocked</span> for this visit. It locks again when you reload.</p>
  <div class="contact-settings">
    <div class="contact-row">
      <label class="contact-label" for="progression">Progression</label>
      <div class="contact-controls">
        <select id="progression">${options([['off','Hide progression'],['subtle','Subtle, natural familiarity'],['milestones','Show shared milestones']],s.relationship_progression)}</select>
      </div>
    </div>
    <div class="contact-row">
      <label class="contact-label" for="pace">Pace</label>
      <div class="contact-controls">
        <select id="pace">${options([['slow','Slow and gradual'],['natural','Natural'],['quick','Open to quicker familiarity']],s.relationship_pace)}</select>
      </div>
    </div>
    <div class="contact-row">
      <label class="contact-label" for="adult-themes">Romance</label>
      <div class="contact-controls">
        <select id="adult-themes">${options([['false','Friendly / platonic only'],['true','Romantic connection enabled']],String(s.explicit))}</select>
        <span class="dim small" style="margin-left:4px">(Permanent if turned off)</span>
      </div>
    </div>
    ${s.adult_images_available?`<div class="contact-row">
      <label class="contact-label">Adult images</label>
      <div class="contact-controls">
        <label class="switch-container compact-toggle" data-toggle-row>
          <input type="checkbox" id="adult-images" ${s.adult_images?'checked':''} ${s.explicit?'':'disabled'}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label">Allow nudity in the pictures they send</span>
        </label>
        <span class="dim small" style="margin-left:4px">${s.explicit
          ? 'Separate from romance. A romantic companion sends nothing explicit unless this is on.'
          : 'Turn on Romance first.'}</span>
      </div>
    </div>`:''}
    <div class="contact-row">
      <label class="contact-label" for="peer-interaction">Companions</label>
      <div class="contact-controls">
        <select id="peer-interaction">${options([['true','May interact with each other'],['false','Kept apart']],String(s.peer_interaction))}</select>
      </div>
    </div>
    <div class="contact-row">
      <label class="contact-label">Meters</label>
      <div class="contact-controls">
        <label class="switch-container compact-toggle" data-toggle-row>
          <input type="checkbox" id="bars" ${s.bars?'checked':''}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label">Show connection, feelings and closeness meters</span>
        </label>
      </div>
    </div>
  </div>
  ${settingsFooter('Save')}`;
  wireToggles(host);
  const romance=host.querySelector('#adult-themes'),adultImages=host.querySelector('#adult-images');
  romance.onchange=()=>{
    if(!adultImages)return;
    const on=romance.value==='true';
    adultImages.disabled=!on;
    if(!on)adultImages.checked=false;
  };
  wireSave(host,async()=>{
    const wantsAdult=host.querySelector('#adult-themes').value==='true';
    const payload={
      relationship_progression:host.querySelector('#progression').value,
      relationship_pace:host.querySelector('#pace').value,
      peer_interaction:host.querySelector('#peer-interaction').value==='true',
      bars:host.querySelector('#bars').checked,
      explicit:wantsAdult};
    // Romance is the prerequisite, so this is never on without it. Offered only at
    // Bonded; while hidden it is left as it is, so a relationship that dips below
    // Bonded keeps the choice made there (the server still gates every picture).
    if(adultImages)payload.adult_images=wantsAdult&&adultImages.checked;
    if(wantsAdult&&!s.explicit){
      if(!confirm('Enable romantic and adult themes? Confirm that you and this companion are both represented as adults.'))
        throw Error('Not changed.');
      payload.adult_confirmed=true;
    }
    if(!wantsAdult&&s.explicit&&!confirm('Turning romance off is permanent for this companion. It cannot be re-enabled. Continue?'))
      throw Error('Not changed.');
    if(payload.adult_images&&!s.adult_images&&
       !confirm('Allow nudity in the pictures they send? The safety check will then label these pictures rather than hold them back.'))
      throw Error('Not changed.');
    return saveSettings(payload);
  });
 }},

{id:'appearance',title:'Appearance',
 blurb:'Theme and accent. Saved with the companion, so it follows them to your phone.',
 keywords:'theme dark light accent colour color appearance mode',
 async render(host){
  host.innerHTML=appearancePanelHTML();
  wireAppearancePanel(host);
 }},

{id:'network',title:'Access & PIN',
 blurb:'Addresses for your other devices, and the PIN that guards them',
 keywords:'network lan wifi address port pin security remote access localhost',
 async render(host){
  const [s,net]=await Promise.all([api('/settings'),api('/network')]);
  host.innerHTML=`

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
  <div class="contact-settings">
    <div class="contact-row">
      <label class="contact-label" for="remote-pin-field">4-digit PIN</label>
      <div class="contact-controls pin-row" style="margin:0">
        <input id="remote-pin-field" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="4"
          placeholder="${s.remote_pin?'••••':'1234'}" aria-label="Four digit PIN">
        <button class="act" id="save-remote-pin" type="button">${s.remote_pin?'Replace PIN':'Set PIN'}</button>
        ${s.remote_pin?'<button class="quiet" id="clear-remote-pin" type="button">Remove PIN</button>':''}
      </div>
    </div>
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

{id:'updates',title:'Updates',
 blurb:'What version you are on, and how to move',
 keywords:'update version release upgrade changelog github',
 async render(host){
  const d=await api('/updates').catch(error=>({version:'unknown',has_update:false,error:error.message}));
  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <span class="pill ${d.has_update?'status-warn':'status-good'}">${d.has_update?`v${esc(d.latest_version)} available`:d.error?'Check unavailable':'Up to date'}</span>
  </div>
  <dl class="fact-list">
    <div><dt>Installed</dt><dd>v${esc(d.version)}</dd></div>
    <div><dt>Latest released</dt><dd>${d.latest_version?'v'+esc(d.latest_version):'Not checked'}</dd></div>
  </dl>
  ${d.has_update?`<div class="notice-strip notice-stack" style="border-left-color:var(--accent);margin-top:16px">
    <p><strong>Tamanitomo v${esc(d.latest_version)} is available.</strong></p>
    <p class="dim small" style="margin-top:4px">This will update the Tamanitomo application. Your companion’s memories, emotions, journals, and vault will remain completely untouched.</p>
    <section class="update-release-notes" aria-labelledby="update-release-notes-title">
      <h3 id="update-release-notes-title">What’s new in v${esc(d.latest_version)}</h3>
      <div class="update-release-notes-body">${esc(d.release_notes||'No patch notes were provided for this release.')}</div>
    </section>
    <div class="update-actions">
      <button class="act update-primary-action" id="btn-inapp-update"><span aria-hidden="true">⚡</span><span>Update to v${esc(d.latest_version)} now</span></button>
      ${d.release_url?`<a class="link-button" href="${esc(d.release_url)}" target="_blank" rel="noopener">Open release page →</a>`:''}
    </div>
  </div>`:`<div class="notice-strip notice-stack" style="margin-top:16px">
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
        updateBtn.innerHTML = `<span aria-hidden="true">⚡</span><span>Update to v${esc(d.latest_version)} now</span>`;
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

{id:'diagnostics',title:'Diagnostics',
 blurb:'What is healthy, what is full, and what it has cost',
 keywords:'health diagnostics problems memory storage vault usage tokens cost',
 async render(host){
  const [health,cost]=await Promise.all([api('/health'),api('/cost')]);
  host.innerHTML=`
  <div class="section-heading" style="margin-top:0">
    <button class="quiet" id="diag-activity">Activity feed</button>
  </div>
  ${health.problems.length
    ?`<div class="notice-strip notice-stack"><p><strong>${health.problems.length} thing${health.problems.length===1?'':'s'} to look at</strong></p><ul>${health.problems.map(p=>`<li class="warn">${esc(p)}</li>`).join('')}</ul></div>`
    :'<p><span class="pill status-good">Everything monitored is running normally</span></p>'}

  <h3 class="section-subheading">Memory capacity</h3>
  <table><tbody>${health.memory.map(m=>`<tr>
    <td>${esc(m.file)}</td>
    <td><strong>${Number(m.chars).toLocaleString()}</strong> <span class="dim">/ ${Number(m.cap).toLocaleString()}</span></td>
    <td>${m.over_warn?'<span class="warn">Approaching the limit</span>':'<span class="dim">Within capacity</span>'}</td></tr>`).join('')}</tbody></table>

  <h3 class="section-subheading">Storage &amp; vault backup</h3>
  <table><tbody>${health.storage.map(s=>`<tr><td>${esc(s.label)}</td><td>${s.files} files</td><td class="dim">${(s.bytes/1e6).toFixed(1)} MB</td></tr>`).join('')}
    <tr><td>Vault history</td><td colspan="2">${health.vault_repo?'<span class="dim">Recording every change</span>':'<span class="warn">Not a git repository — changes are not versioned</span>'}</td></tr></tbody></table>
  <div class="actions">
    <a class="quiet" href="${mediaUrl('/api/vault/export')}" download>${icon('download')} Download vault backup (.zip)</a>
  </div>

  <h3 class="section-subheading">Model usage · last 30 recorded days</h3>
  ${cost.available
    ?`<table><thead><tr><th>Day</th><th>Input</th><th>Output</th><th>Runs</th></tr></thead><tbody>${cost.days.slice().reverse().map(d=>`<tr><td>${esc(d.day)}</td><td>${d.input==null?'Unknown':d.input.toLocaleString()}</td><td>${d.output==null?'Unknown':d.output.toLocaleString()}</td><td>${d.runs}</td></tr>`).join('')}</tbody></table>`
    :'<p class="dim">Nothing recorded yet.</p>'}`;
  host.querySelector('#diag-activity').onclick=showGatewayActivity;
 }},

{id:'hermes-core',bare:true,title:'Installation & gateway',
 blurb:'The runtime behind your companion, and the process that keeps it running',
 keywords:'hermes install update gateway routine service hooks doctor repair profile archive runtime environment existing managed android termux battery',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['installation','stack','gateway','lifecycle']);
  if(!host.isConnected)return;
  host.prepend(runtimeCard());
  host.append(androidHostingTips());
 }},

{id:'models',title:'Models',
 blurb:'Which models your companions run on, and what answers when one cannot',
 keywords:'model provider primary fallback openrouter free cascade grok chatgpt oauth ollama local reasoning tiers routines reflection conversation use everywhere apply all companions chain preset luna sol',
 render:renderModelPlan},

{id:'hermes-accounts',bare:true,title:'Sign-ins & API keys',
 blurb:'Connect subscription accounts and store API keys',
 keywords:'api key credential oauth signin telegram discord token console setup',
 async render(host){
  await hermesCards();
  placeHermesCards(host,['accounts']);
 }},

{id:'jobs',title:'Scheduled jobs',
 blurb:'The routines that keep their life going, and which model runs each',
 keywords:'continuity cron jobs schedule routine model provider reasoning tokens prompt run failures',
 render:renderJobsPanel},

{id:'connect-images',title:'Image generation',
 blurb:'ComfyUI, Civitai, and the reference photograph',
 keywords:'comfyui image generation civitai lora checkpoint endpoint portrait',
 async render(host){
  host.innerHTML=await imagesPanelHTML();
  wireImagesPanel(host);

 }},

{id:'connect-voice',title:'Voice',
 blurb:'Which engine speaks, and how it sounds',
 keywords:'voice tts speech engine piper edge elevenlabs openai speed pitch',
 render:renderVoicePanel},

{id:'dashboard',title:'Hermes dashboard',
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

// Whether a provider is reached at an address the person has to give.
function providerNeedsURL(provider,existing=''){const name=String(provider).toLowerCase();return name!=='openai-codex'&&name!=='mistral'&&(Boolean(existing)||['custom','ollama','lmstudio','lm-studio','vllm','local'].includes(name));}

/* ------------------------------------------------------------- model plan
   One plan for every companion: who answers a conversation, what the everyday
   routines and the reflections run on, and what answers when the first cannot.
   A model used to live in five places with a screen each -- Hermes's primary and
   fallbacks, the companion's tiers, every job's pin, Hermes's helper tasks and the
   cron default -- and each companion was changed on its own, so the pages
   disagreed with each other and "use it everywhere" meant doing it twice. This
   form writes all of them for the companions ticked, and moves anything still
   pointing at an account the plan no longer uses. Hermes reads the model on every
   message, so a change lands on the next one without restarting anything. */
const ACCOUNT_NAMES={'openai-codex':'ChatGPT (signed in)','xai-oauth':'Grok (signed in)',
  'openrouter':'OpenRouter','anthropic':'Anthropic','deepseek':'DeepSeek','mistral':'Mistral AI',
  'opencode-free':'OpenCode Free','ollama':'Ollama (local)','custom':'Custom / local server'};
function chainAccounts(data){
  const seen=new Map();
  for(const p of data.providers||[]){
    const key=`${p.provider}|${p.base_url||''}`;
    // The profile's own row repeats a signed-in account with its endpoint spelled out.
    if(p.kind==='profile'&&(data.providers||[]).some(o=>o!==p&&o.provider===p.provider&&!o.base_url))continue;
    if(!seen.has(key))seen.set(key,{provider:p.provider,base_url:p.base_url||'',
      label:ACCOUNT_NAMES[p.provider]&&!p.base_url?ACCOUNT_NAMES[p.provider]:(p.label||p.provider)});
  }
  return [...seen.values()];
}
const accountName=provider=>(ACCOUNT_NAMES[provider]||provider||'').replace(' (signed in)','');
const plural=(n,word)=>`${n} ${word}${n===1?'':'s'}`;
const PLAN_TIERS=[
  ['chat','Conversation','Telegram, this app and photos: the model your companion talks to you with.'],
  ['loops','Everyday routines','Life pulse, check-ins, mornings and wind-downs. They run every few minutes, so a quick model keeps life moving.'],
  ['reflection','Reflection','Daily journal, weekly and monthly reflection, autonomy windows. A few runs a week, worth your strongest model.'],
];
const PLAN_EFFORTS=[['','Hermes default'],['none','None'],['low','Low'],['medium','Medium'],['high','High']];
const routeText=r=>r&&r.model?`${accountName(r.provider)} · ${r.model}${r.reasoning_effort?` · ${r.reasoning_effort==='none'?'no':r.reasoning_effort} reasoning`:''}`:'';
const planKey=plan=>JSON.stringify([plan.chat,plan.loops||null,plan.reflection||null,plan.links||[]]);

function planStatusHTML(row){
  if(row.error)return `<li class="plan-companion"><strong>${esc(row.name)}</strong> <span class="bad small">${esc(row.error)}</span></li>`;
  const r=row.routines,plan=row.plan;
  const helpers=row.helpers.filter(h=>h.stranded);
  const own=row.own_jobs.filter(j=>j.stranded);
  const problems=r.off.length+helpers.length+own.length;
  return `<li class="plan-companion">
    <div class="plan-companion-head"><strong>${esc(row.name)}</strong>
      <span class="pill ${problems?'status-warn':'status-good'}">${problems?plural(problems,'thing')+' off the plan':'All on the plan'}</span></div>
    <small class="dim">${esc(routeText(plan.chat)||'No model set')}${plan.loops?` · routines ${esc(plan.loops.model)}`:''}${plan.reflection?` · reflection ${esc(plan.reflection.model)}`:''}</small>
    <small class="dim">${r.total?`${r.on_plan} of ${plural(r.total,'routine')} on this plan.`:'No routines installed.'}</small>
    ${problems?`<details class="plan-off"><summary class="small">What is off the plan</summary><ul class="small">
      ${r.off.map(j=>`<li>${esc(j.name)}: ${esc(routeText(j)||'no model of its own')}, expected ${esc(routeText({provider:j.expected_provider,model:j.expected_model})||'the profile default')}</li>`).join('')}
      ${helpers.map(h=>`<li>Hermes ${esc(h.label)}: ${esc(h.base_url||accountName(h.provider))}${h.model?' · '+esc(h.model):''} — an account this plan does not use</li>`).join('')}
      ${own.map(j=>`<li>Your job “${esc(j.name)}”: ${esc(routeText(j))} — an account this plan does not use</li>`).join('')}
    </ul><p class="dim small">Applying the plan moves all of these.</p></details>`:''}
  </li>`;
}

async function renderModelPlan(host){
  host.innerHTML='<p class="dim" role="status">Loading…</p>';
  let data,accounts;
  try{[data,accounts]=await Promise.all([api('/models/plan'),knownProviders().then(chainAccounts)]);}
  catch(error){host.innerHTML=`<p class="bad">${esc(error.message)}</p>`;return;}
  if(!host.isConnected)return;
  const companions=data.companions.filter(c=>c.plan);
  const bundles=Object.fromEntries(data.bundles.map(b=>[b.id,b]));
  const mine=companions.find(c=>c.selected)||companions[0];
  if(!mine){host.innerHTML='<p class="dim">No companion is installed yet.</p>';return;}
  // The form starts from this companion's plan; a tier equal to the conversation
  // model reads as "same as conversation".
  let form={chat:{...mine.plan.chat},loops:mine.plan.loops?{...mine.plan.loops}:null,
    reflection:mine.plan.reflection?{...mine.plan.reflection}:null,links:(mine.plan.links||[]).map(l=>({...l}))};
  const pickers=new Map();
  const accountOptions=(row,{follow=false}={})=>{
    const match=accounts.find(a=>a.provider===row?.provider&&a.base_url===(row?.base_url||''))
      ||accounts.find(a=>a.provider===row?.provider);
    const list=match||!row?.provider?accounts:[{provider:row.provider,base_url:row.base_url||'',label:accountName(row.provider)},...accounts];
    return (follow?'':`<option value="">Choose an account</option>`)+list.map(a=>
      `<option value="${esc(a.provider+'|'+a.base_url)}"${row?.provider&&(a===match||(!match&&a.provider===row.provider))?' selected':''}>${esc(a.label)}</option>`).join('')
      +(list.some(a=>a.provider==='custom')?'':`<option value="custom|">Custom / local server…</option>`);
  };
  const routeFields=(key,row)=>`
    <div class="plan-route" data-route="${key}">
      <label>Account<select data-account>${accountOptions(row)}</select></label>
      <div class="plan-model"><span class="chain-model-label">Model</span>${modelPickerHTML('plan-'+key,row?.model||'')}</div>
      <label>Reasoning<select data-effort>${options(PLAN_EFFORTS,row?.reasoning_effort||'')}</select></label>
      <label class="plan-url" ${row?.provider==='custom'||row?.base_url?'':'hidden'}>Endpoint<input data-url value="${esc(row?.base_url||'')}" placeholder="http://localhost:11434/v1"></label>
    </div>`;
  const tierHTML=([key,title,blurb])=>{
    const row=key==='chat'?form.chat:form[key];
    const follows=key!=='chat'&&!row;
    return `<section class="plan-tier" data-tier="${key}">
      <div class="plan-tier-head"><h3>${esc(title)}</h3>
        ${key==='chat'?'':`<label class="switch-container compact-toggle"><input type="checkbox" data-follow ${follows?'checked':''}><span class="switch-slider" aria-hidden="true"></span><span class="switch-label">Same as conversation</span></label>`}</div>
      <p class="dim small">${esc(blurb)}</p>
      ${follows?'':routeFields(key,row)}
    </section>`;
  };
  const linkHTML=(link,i)=>{
    const moves=`<div class="chain-moves">
      <button type="button" class="icon-button" data-move="-1" aria-label="Move up"${i===0?' disabled':''}>${icon('chevron_left')}</button>
      <button type="button" class="icon-button" data-move="1" aria-label="Move down"${i===form.links.length-1?' disabled':''}>${icon('chevron_right')}</button>
      <button type="button" class="icon-button" data-remove aria-label="Remove">${icon('close')}</button></div>`;
    if(link.bundle){
      const b=bundles[link.bundle]||{name:link.bundle,models:[]};
      return `<li class="chain-step is-bundle" data-link="${i}"><span class="chain-rank">${i+1}</span>
        <div class="chain-body"><strong>${esc(b.name)}</strong><small class="dim">${esc((b.models||[]).join(' → '))}</small></div>${moves}</li>`;
    }
    return `<li class="chain-step" data-link="${i}"><span class="chain-rank">${i+1}</span>
      <div class="chain-body">${routeFields('link-'+i,link)}</div>${moves}</li>`;
  };
  // Read a route block back from the page; the picker remembers what was typed.
  const readRoute=key=>{
    const box=host.querySelector(`[data-route="${CSS.escape(key)}"]`);
    if(!box)return null;
    const [provider,base]=(box.querySelector('[data-account]').value||'|').split('|');
    const url=box.querySelector('[data-url]')?.value.trim()||base||'';
    const model=(pickers.get(key)?.read()||'').trim();
    const effort=box.querySelector('[data-effort]')?.value||'';
    return {provider,model,...(url?{base_url:url}:{}),...(effort?{reasoning_effort:effort}:{})};
  };
  const collect=()=>{
    if(host.querySelector('[data-route="chat"]'))form.chat=readRoute('chat');
    for(const key of ['loops','reflection']){
      const follow=host.querySelector(`[data-tier="${key}"] [data-follow]`);
      if(follow)form[key]=follow.checked?null:(readRoute(key)||form[key]);
    }
    form.links=form.links.map((l,i)=>l.bundle?l:(readRoute('link-'+i)||l));
    return form;
  };
  const wireRoute=(key,row)=>{
    const box=host.querySelector(`[data-route="${CSS.escape(key)}"]`);
    if(!box)return;
    const account=box.querySelector('[data-account]'),urlRow=box.querySelector('.plan-url'),url=box.querySelector('[data-url]');
    const current=()=>(account.value||'|').split('|');
    const picker=wireModelPicker(box.querySelector('[data-model-picker]'),{
      provider:()=>current()[0],baseUrl:()=>url.value.trim()||current()[1]||'',value:row?.model||'',defaultLabel:'Choose a model'});
    pickers.set(key,picker);
    account.onchange=()=>{
      const [provider,base]=current();
      urlRow.hidden=provider!=='custom'&&!base;url.value=base||'';
      box.querySelector('[data-model-custom]').value='';picker.reload();
    };
    url.onchange=()=>picker.reload();
  };

  const paint=()=>{
    pickers.clear();
    const ticked=new Set([...host.querySelectorAll('[data-plan-profile]:checked')].map(b=>b.value));
    const chosen=ticked.size?ticked:new Set(companions.map(c=>c.profile));
    const differ=!data.same&&companions.length>1;
    host.innerHTML=`
      <p class="set-hint">One plan for your companions: who answers a conversation, what their everyday routines and reflections run on, and what to fall back to. It reaches everything that uses a model, and takes effect from the next message.</p>
      <ul class="plan-companions">${data.companions.map(planStatusHTML).join('')}</ul>
      ${differ?'<p class="small warn">Your companions are not on the same plan. Applying this one to both makes them match.</p>':''}
      <div class="card plan-card">
        ${(data.presets||[]).length||differ?`<div class="chip-row plan-presets"><span class="dim small">Start from</span>
          ${(data.presets||[]).map(p=>`<button type="button" class="chip-button" data-preset="${esc(p.id)}" title="${esc(p.description)}">${esc(p.label)}</button>`).join('')}
          ${differ?companions.map(c=>`<button type="button" class="chip-button" data-copy="${esc(c.profile)}">${esc(c.name)}’s current plan</button>`).join(''):''}</div>`:''}
        ${PLAN_TIERS.map(tierHTML).join('')}
        <section class="plan-tier">
          <div class="plan-tier-head"><h3>When it cannot answer</h3></div>
          <p class="dim small">Tried in order when the model above is busy, rate-limited or down. Every conversation and routine uses the same list.</p>
          ${form.links.length?`<ol class="chain-steps">${form.links.map(linkHTML).join('')}</ol>`:'<p class="dim small">No fallbacks: if the model above fails, that reply or routine waits for the next try.</p>'}
          <div class="actions"><button type="button" class="quiet" data-add-link>+ Add a fallback</button>
            ${form.links.some(l=>l.bundle==='openrouter-free')||!bundles['openrouter-free']?'':`<button type="button" class="quiet" data-add-free>+ Add ${esc(bundles['openrouter-free'].name)}</button>`}</div>
        </section>
        <div class="panel-footer plan-footer">
          ${companions.length>1?`<fieldset class="plan-who"><legend class="small">Apply to</legend>${companions.map(c=>`<label class="check"><input type="checkbox" data-plan-profile value="${esc(c.profile)}" ${chosen.has(c.profile)?'checked':''}> ${esc(c.name)}</label>`).join('')}</fieldset>`:''}
          <button type="button" class="act" data-apply>Apply</button>
          <span class="dim small" data-plan-status role="status"></span>
        </div>
        <div data-plan-after></div>
      </div>`;
    wireRoute('chat',form.chat);
    for(const key of ['loops','reflection'])if(form[key])wireRoute(key,form[key]);
    form.links.forEach((l,i)=>{if(!l.bundle)wireRoute('link-'+i,l);});
    const applyLabel=()=>{
      const names=companions.filter(c=>host.querySelector(`[data-plan-profile][value="${CSS.escape(c.profile)}"]`)?.checked??true).map(c=>c.name);
      host.querySelector('[data-apply]').textContent=names.length?`Apply to ${names.length>1?names.slice(0,-1).join(', ')+' and '+names.at(-1):names[0]}`:'Choose a companion';
      host.querySelector('[data-apply]').disabled=!names.length;
    };
    host.querySelectorAll('[data-plan-profile]').forEach(b=>b.onchange=applyLabel);applyLabel();
    host.querySelectorAll('[data-follow]').forEach(box=>box.onchange=()=>{
      collect();const key=box.closest('[data-tier]').dataset.tier;
      form[key]=box.checked?null:{...form.chat};paint();});
    host.querySelectorAll('[data-link] [data-move]').forEach(b=>b.onclick=()=>{
      collect();const i=Number(b.closest('[data-link]').dataset.link),j=i+Number(b.dataset.move);
      [form.links[i],form.links[j]]=[form.links[j],form.links[i]];paint();});
    host.querySelectorAll('[data-link] [data-remove]').forEach(b=>b.onclick=()=>{
      collect();form.links.splice(Number(b.closest('[data-link]').dataset.link),1);paint();});
    host.querySelector('[data-add-link]').onclick=()=>{collect();form.links.push({provider:'',model:''});paint();};
    host.querySelector('[data-add-free]')?.addEventListener('click',()=>{collect();form.links.push({bundle:'openrouter-free'});paint();});
    host.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{
      const p=data.presets.find(x=>x.id===b.dataset.preset).plan;
      form={chat:{...p.chat},loops:p.loops?{...p.loops}:null,reflection:p.reflection?{...p.reflection}:null,links:(p.links||[]).map(l=>({...l}))};
      paint();host.querySelector('[data-plan-status]').textContent=`${b.textContent} filled in. Nothing changes until you apply it.`;});
    host.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>{
      const p=companions.find(c=>c.profile===b.dataset.copy).plan;
      form={chat:{...p.chat},loops:p.loops?{...p.loops}:null,reflection:p.reflection?{...p.reflection}:null,links:(p.links||[]).map(l=>({...l}))};
      paint();});
    host.querySelector('[data-apply]').onclick=async e=>{
      const button=e.currentTarget,status=host.querySelector('[data-plan-status]');
      const plan=collect();
      const missing=[['Conversation',plan.chat],['Everyday routines',plan.loops],['Reflection',plan.reflection]]
        .find(([,r])=>r&&(!r.provider||!r.model));
      if(missing){status.innerHTML=`<span class="bad">${esc(missing[0])} needs an account and a model.</span>`;return;}
      const badLink=plan.links.findIndex(l=>!l.bundle&&(!l.provider||!l.model));
      if(badLink>=0){status.innerHTML=`<span class="bad">Fallback ${badLink+1} needs an account and a model.</span>`;return;}
      const profiles=companions.filter(c=>host.querySelector(`[data-plan-profile][value="${CSS.escape(c.profile)}"]`)?.checked??true).map(c=>c.profile);
      button.disabled=true;status.textContent='Applying…';
      try{
        // The callback stops the workspace redrawing the whole page on completion,
        // which would throw away the result shown below.
        const done=await action('/models/plan',{chat:plan.chat,loops:plan.loops,reflection:plan.reflection,
          fallbacks:plan.links.map(l=>l.bundle?{bundle:l.bundle}:{provider:l.provider,model:l.model,...(l.base_url?{base_url:l.base_url}:{})}),profiles},()=>{});
        clearEditorDirty(editorScope(host));
        const r=done.result||{};
        await renderModelPlan(host);
        const after=host.querySelector('[data-plan-after]');
        if(after){
          after.innerHTML=`<div class="chain-result"><p><strong>${esc(r.note||'Applied.')}</strong></p>
            ${(r.failed||[]).length?`<p class="warn small">${r.failed.map(esc).join('<br>')}</p>`:''}
            ${r.restart_gateway?`<p class="dim small">Restart the gateway once so it loads the kit's updated Hermes plugins (leaner conversation context, reading web pages on this machine).</p>
              <div class="actions"><button type="button" class="quiet" data-restart-gateway>Restart the gateway now</button></div>`:''}</div>`;
          after.querySelector('[data-restart-gateway]')?.addEventListener('click',async ev=>{
            ev.currentTarget.disabled=true;
            const restart=ev.currentTarget;
            try{await action('/gateway/restart-root',{affects_all_profiles:true,root_restarted:false},()=>{});restart.textContent='Gateway restarted';}
            catch(error){after.insertAdjacentHTML('beforeend',`<p class="bad small">${esc(error.message)}</p>`);}
          });
        }
      }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;button.disabled=false;}
    };
  };
  paint();
}

/* ------------------------------------------------------------- jobs panel
   The jobs list used to be read-only apart from a schedule prompt(), and the
   model behind each job could only be changed by running Hermes's own CLI.
   Both are editable here. There is deliberately no token budget field: Hermes
   has no such setting per job, so prompt size is shown instead — that is what
   the job actually sends on every run. */
// Three questions worth being able to answer about a background job: does it
// call a model at all, what does it put in the prompt, and where does that go.
// The list answered none of them, and showed a provider even on the seven jobs
// that never contact one -- which reads as though something is being sent.
// When things actually run, on one strip. A list of cron expressions is not an
// answer to "what happens at eight in the morning", and that was the only view
// there was.
function jobHours(job){
  const expr=job.schedule?.expr||'';
  const parts=expr.split(/\s+/);
  if(parts.length<5)return null;                       // interval or one-shot
  const [,hour]=parts;
  if(hour==='*')return 'every';
  const out=new Set();
  for(const piece of hour.split(',')){
    if(piece.includes('/')){
      const [range,step]=piece.split('/');
      const [lo,hi]=range==='*'?[0,23]:range.includes('-')?range.split('-').map(Number):[Number(range),23];
      for(let h=lo;h<=hi;h+=Number(step)||1)out.add(h);
    }else if(piece.includes('-')){
      const [lo,hi]=piece.split('-').map(Number);
      for(let h=lo;h<=hi;h++)out.add(h);
    }else if(/^\d+$/.test(piece))out.add(Number(piece));
  }
  return out.size?out:null;
}
function jobTimelineHtml(jobs,timezone){
  const rows=jobs.filter(j=>j.enabled);
  const hourly=rows.filter(j=>jobHours(j)==='every');
  const placed=rows.map(j=>({job:j,hours:jobHours(j)})).filter(x=>x.hours&&x.hours!=='every');
  const odd=rows.filter(j=>jobHours(j)===null);
  const byHour=Array.from({length:24},()=>[]);
  for(const {job,hours} of placed)for(const h of hours)byHour[h].push(job);
  const busiest=Math.max(1,...byHour.map(list=>list.length));
  return `<details class="card job-timeline" open>
    <summary><strong>What runs when</strong> <small class="dim">local time, ${esc(timezone||'')}</small></summary>
    <div class="timeline-strip" role="img" aria-label="Twenty-four hour view of scheduled jobs">
      ${byHour.map((list,h)=>`
        <div class="timeline-hour${list.length?' has-jobs':''}" style="--fill:${list.length/busiest}"
             title="${h.toString().padStart(2,'0')}:00 — ${list.length?list.map(j=>j.name).join(', '):'nothing scheduled'}">
          <span class="timeline-count">${list.length||''}</span>
          <span class="timeline-label">${h%6===0?h.toString().padStart(2,'0'):''}</span>
        </div>`).join('')}
    </div>
    <p class="dim small">${hourly.length} run every hour${hourly.length?': '+esc(hourly.map(j=>j.name).join(', ')):''}.
      ${odd.length?esc(odd.length+' run on an interval or once: '+odd.map(j=>j.name).join(', '))+'.':''}</p>
  </details>`;
}
function sensitiveSummary(jobs,data){
  const sensitive=jobs.filter(j=>j.sensitivity==='sensitive'&&j.enabled);
  if(!sensitive.length)return '';
  const where=new Map();
  for(const j of sensitive){
    const name=j.base_url?j.base_url:(j.provider||'the profile default provider');
    where.set(name,(where.get(name)||0)+1);
  }
  const local=name=>/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(name);
  const offMachine=[...where.keys()].filter(n=>!local(n));
  return `<div class="notice-strip sensitivity-summary">
    <p><strong>${sensitive.length} scheduled job${sensitive.length===1?'':'s'} send private material to a model.</strong></p>
    <p class="dim small">${[...where.entries()].map(([n,c])=>`${c}\u00d7 ${esc(n)}${local(n)?' (this machine)':''}`).join(' · ')}.
    ${offMachine.length?'Her SOUL file, recorded mood and private stance, and your own words, leave this machine to be answered.':'Nothing leaves this machine.'}</p>
  </div>`;
}
async function renderJobsPanel(host){
  const data=await api('/jobs');
  profileTimezone=data.timezone;
  const jobs=data.jobs;
  const usage=data.usage||{};
  const tokens=n=>n==null?'Unknown':Number(n).toLocaleString();
  const failed=jobs.filter(j=>j.last_status==='error').length;
  const active=jobs.filter(j=>j.enabled).length;
  const noModel=jobs.filter(j=>!j.no_agent&&!j.model).length;
  const legacy=jobs.filter(j=>j.legacy_worker).length;

  host.innerHTML=`
  <div class="settings-toolbar">
    <div class="actions">
      <button class="quiet" id="jobs-pause">Pause model jobs</button><button class="quiet" id="jobs-activate">Enable model jobs</button><button class="quiet" id="jobs-history">Run history</button>
      <button class="quiet" id="jobs-model-plan">Models for all jobs…</button>
      <button class="quiet" id="jobs-repair">Install / repair</button>
    </div>
  </div>
  <p class="dim">Choose the provider, model, and reasoning used by every model-backed part of the companion’s lived continuity. Times are in ${esc(data.timezone)}. Script-only maintenance has no model to configure and stays active when model jobs are paused.</p>
  ${legacy?`<div class="notice-strip"><p><strong>${legacy} legacy continuity worker${legacy===1?' is':'s are'} bypassing these model controls.</strong></p><p class="dim small">Install / repair migrates the old provider-pinned scripts to native Hermes routing, preserving job IDs and run history.</p></div>`:''}
  <p class="dim small">${esc(usage.note||'Token usage unavailable.')}${usage.partial?' Recent history is truncated.':''}</p>
  <details open><summary>Which model should I use?</summary><p class="dim small">Use a fast model with reliable tool use for frequent presence and check-in work. Use your strongest reasoning model for weekly and monthly reflection. Each Tamanitomo job below shows its own recommendation. Image timeline jobs plan the moment here, then call the separately configured image provider.</p></details>
  <div class="stat-strip">
    <button data-filter="all"><span>Installed</span><strong>${jobs.length}</strong></button>
    <button data-filter="active"><span>Scheduled</span><strong>${active}</strong></button>
    <button data-filter="paused"><span>Paused</span><strong>${jobs.length-active}</strong></button>
    <button data-filter="error"><span>Last run failed</span><strong>${failed}</strong></button>
  </div>
  ${noModel?`<p class="dim small">${noModel} model-backed job${noModel===1?' has':'s have'} no model of their own and follow the profile default.</p>`:''}
  ${sensitiveSummary(jobs,data)}
  ${jobTimelineHtml(jobs,data.timezone)}
  <div class="notice-strip"><p><strong>Which model each kind of routine runs on is set in one place.</strong></p>
    <p class="dim small">Models sets conversation, everyday routines and reflection for every companion together, and moves any job still pointing at an account you no longer use. Change a single job below only when it should differ. <button type="button" class="link-button small" id="jobs-open-plan">Open Models →</button></p></div>
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
    const groups=(data.sensitivity||[]).filter(g=>rows.some(j=>j.sensitivity===g.key));
    const origins=(data.origins||[]).filter(o=>rows.some(j=>j.origin===o.key));
    const card=j=>`
      <details class="job-row${j.last_status==='error'?' is-failing':''}" data-job-id="${esc(j.id)}">
        <summary>
          <span class="job-name"><strong>${esc(j.name||j.id)}</strong>
            <small class="dim">${j.no_agent?'Runs a script · never contacts a model':esc(j.model||'Profile default model')} · <code data-schedule-label>${esc(scheduleLabel(schedule(j)))}</code></small></span>
          <span class="job-state">${statusPill(j)}${j.enabled?'':'<span class="pill">Paused</span>'}</span>
        </summary>
        <div class="job-body">
          <dl class="fact-list">
            <div><dt>Next run</dt><dd>${j.enabled?esc(when(j.next_run_at)):'Paused'}</dd></div>
            <div><dt>Last run</dt><dd>${j.last_run_at?esc(when(j.last_run_at)):'Never'}</dd></div>
            <div><dt>Prompt size</dt><dd>${j.no_agent?'—':Number(j.prompt_chars||0).toLocaleString()+' characters sent each run'}</dd></div>
            ${j.no_agent?'<div><dt>Model tokens</dt><dd>None · script only</dd></div>':[['Last run','last_run'],['Last hour','hour'],['Last 24 hours','day'],['Last 7 days','week']].map(([label,key])=>`<div><dt>${label} tokens</dt><dd>${tokens(usage.jobs?.[j.id]?.[key])}<span class="dim small"> · input ${tokens(usage.jobs?.[j.id]?.breakdown?.[key]?.input)} / output ${tokens(usage.jobs?.[j.id]?.breakdown?.[key]?.output)}</span></dd></div>`).join('')}
            <div><dt>Delivers to</dt><dd>${esc(j.deliver||'—')}</dd></div>
            ${j.sends?`<div><dt>Sends</dt><dd>${esc(j.sends)}</dd></div>`:''}
            ${j.second_call?`<div><dt>Also calls</dt><dd>${esc(j.second_call.model)} via ${esc(j.second_call.provider)}${j.second_call.reasoning_effort?' · '+esc(j.second_call.reasoning_effort)+' reasoning':''}<br><small class="dim">${esc(j.second_call.why)} Set by <code>${esc(j.second_call.setting)}</code>, not by the model chosen below.${j.second_call.reasoning_reported===false?' This provider does not report how much it thought, so the effort is sent but cannot be confirmed.':''}</small></dd></div>`:''}
          </dl>
          ${j.last_error?`<div class="notice-strip"><p><strong>Last error</strong></p><pre class="command-block">${esc(j.last_error)}</pre></div>`:''}
          ${j.recommendation?`<div class="notice-strip"><p><strong>Recommended: ${esc(j.recommendation.model_role)} · ${esc(j.recommendation.reasoning_effort)} reasoning</strong></p><p class="dim small">${esc(j.recommendation.why)} <button type="button" class="link-button small" data-recommend-effort="${esc(j.recommendation.reasoning_effort)}">Use recommended effort</button></p></div>`:''}
          <div class="form-grid">
            ${scheduleEditorHTML(j.id,schedule(j))}
            ${j.no_agent?'':`
            <label>Provider<input data-field="provider" data-job="${esc(j.id)}" list="job-provider-ids" value="${esc(j.provider||'')}" placeholder="Follow the profile default"></label>
            <label>Model${modelPickerHTML('job-'+j.id,j.model)}
              <input type="hidden" data-field="model" data-job="${esc(j.id)}" value="${esc(j.model||'')}"></label>
            <label>Reasoning effort<select data-field="reasoning_effort" data-job="${esc(j.id)}">${options([['','Hermes default'],['none','None'],['minimal','Minimal'],['low','Low'],['medium','Medium'],['high','High'],['xhigh','Extra high'],['max','Maximum'],['ultra','Ultra']],j.reasoning_effort||'')}</select></label>
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
      </details>`;
    const bySensitivity=pool=>groups.map(g=>{
      const mine=pool.filter(j=>j.sensitivity===g.key);
      if(!mine.length)return '';
      return `<section class="job-group job-group-${esc(g.key)}">
        <div class="job-group-head">
          <h3>${esc(g.label)} <span class="pill">${mine.length}</span></h3>
          <p class="dim small">${esc(g.blurb)}</p>
          <p class="dim small job-group-advice"><strong>Safest:</strong> ${esc(g.advice)}</p>
        </div>
        ${mine.map(card).join('')}
      </section>`;}).join('');
    host.querySelector('#job-list').innerHTML=rows.length?origins.map(o=>{
      const mine=rows.filter(j=>j.origin===o.key);
      if(!mine.length)return '';
      return `<section class="job-origin job-origin-${esc(o.key)}">
        <div class="job-origin-head">
          <h2>${esc(o.label)} <span class="pill">${mine.length}</span></h2>
          <p class="dim small">${esc(o.blurb)}</p>
        </div>
        ${bySensitivity(mine)}
      </section>`;}).join(''):empty('health','No matching jobs','Nothing here matches that search or filter.');

    /* A row builds its picker the first time it is opened, not for all 29 at
       once, and rebuilds it when the provider or endpoint underneath changes. */
    wireScheduleEditors(host);
    for(const row of host.querySelectorAll('.job-row')){
      const picker=row.querySelector('[data-model-picker]');
      if(!picker)continue;
      const field=n=>row.querySelector(`[data-field="${n}"]`);
      const recommend=row.querySelector('[data-recommend-effort]');
      if(recommend)recommend.onclick=()=>{field('reasoning_effort').value=recommend.dataset.recommendEffort;field('reasoning_effort').dispatchEvent(new Event('change',{bubbles:true}));};
      const available=await knownProviders();
      const providers=new Map(available.providers.map(p=>[p.provider,p.provider==='openai-codex'?'ChatGPT':p.provider==='mistral'?'Mistral AI':p.label]));
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
  host.querySelector('#job-search').oninput=draw;
  host.querySelector('#job-filter').onchange=draw;
  for(const b of host.querySelectorAll('[data-filter]'))
    b.onclick=()=>{host.querySelector('#job-filter').value=b.dataset.filter;draw();};
  bindAction('jobs-history','/jobs/history');
  bindAction('jobs-pause','/maintenance/pause',{},()=>openSettings(null,'jobs'));
  bindAction('jobs-activate','/maintenance/activate',{},()=>openSettings(null,'jobs'));
  for(const id of ['#jobs-model-plan','#jobs-open-plan'])host.querySelector(id).onclick=()=>openSettings(null,'models');
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
        :`<p class="dim small">No platform PIN is set on this workspace. Type <strong>${esc(name)}</strong> below to continue, or set a PIN first under Settings → App → Access &amp; PIN.</p>
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

/* Which Hermes this workspace drives. It lives with the installation it picks,
   and mirrors the sidebar's picker so there is one source of truth. */
function runtimeCard(){
  const card=document.createElement('div');
  card.className='card';
  card.innerHTML=`
    <label for="settings-installation-select">Hermes runtime</label>
    <select id="settings-installation-select">
      <option value="existing">Existing Hermes (system host)</option>
      <option value="managed">Kit-managed Hermes (isolated)</option>
    </select>
    <p class="set-hint" style="margin-top:8px">Which Hermes installation this workspace talks to. Each keeps its own profiles and settings.</p>`;
  const select=card.querySelector('select'),source=$('installation-select');
  if(source){
    select.value=source.value;
    select.onchange=()=>{source.value=select.value;source.dispatchEvent(new Event('change'));};
  }else select.disabled=true;
  return card;
}
function androidHostingTips(){
  const box=document.createElement('details');
  box.className='settings-advanced';
  box.innerHTML=`<summary>Hosting on an Android phone</summary>
    <div class="card">
      <p>Android suspends apps when the screen is off. To keep your companion running under Termux:</p>
      <ol>
        <li>Open Android <strong>Settings → Apps → Termux</strong>.</li>
        <li>Tap <strong>App battery usage</strong> (or Battery saver / Power management).</li>
        <li>Choose <strong>Unrestricted</strong> (or <strong>Don’t optimise</strong>).</li>
      </ol>
      <p class="dim">Samsung, Xiaomi and OnePlus phones also freeze background apps; see <a href="https://dontkillmyapp.com" target="_blank" rel="noopener">dontkillmyapp.com</a>.</p>
    </div>`;
  return box;
}

/* ----------------------------------------------------------------- the page */

/* Every section, in the order people look for them. A string is a section in
   settingsPanels; an object is a page elsewhere in the workspace that belongs
   here too, so there is one list to scan instead of tiles plus groups. */
const SETTINGS_NAV=[
  ['Companion',[
    {route:'roster',title:'Companions',blurb:'Create, adopt, switch or archive a companion'},
    {route:'identity',title:'Identity',blurb:'Name, personality, appearance and story'},
    'contact','rhythm','awareness','relationship']],
  ['AI models',[
    'models','hermes-accounts','jobs',
    {route:'local-models',title:'Local models',blurb:'Run models on this machine with Ollama'}]],
  ['Images & voice',[
    'connect-images','photos','connect-voice',
    {route:'image-studio',title:'Image studio',blurb:'Workflows, presets and previews'},
    {route:'voice',title:'Voice studio',blurb:'Voices, cloning and previews'}]],
  ['App',['appearance','network','updates']],
  ['System',['hermes-core','diagnostics','dashboard']],
];
const settingsEntries=SETTINGS_NAV.flatMap(([group,items])=>items.map(item=>{
  const panel=typeof item==='string'?settingsPanels.find(p=>p.id===item):null;
  return panel?{...panel,group,id:panel.id}:{...item,group,id:'route:'+item.route};
}));

/* Which section is open survives a reload, so a link that has to reload the
   workspace first (switching profile, finishing onboarding) still lands on the
   section it meant to. */
const PANEL_KEY='settings-panel';
let settingsDirectLink=false;
let settingsPanel=(()=>{try{return sessionStorage.getItem(PANEL_KEY);}catch(error){return null;}})();
function rememberPanel(id){
  settingsPanel=id;
  try{sessionStorage.setItem(PANEL_KEY,id);}catch(error){/* private window */}
}
/* Jump straight to a section from anywhere: openSettings(null,'jobs'). */
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

const settingsNarrow=()=>matchMedia('(max-width:760px)').matches;

function settingsNavHTML(){
  return SETTINGS_NAV.map(([group,items])=>`
    <section class="settings-nav-group" data-nav-group>
      <h3>${esc(group)}</h3>
      <ul>${items.map(item=>{
        const entry=settingsEntries.find(e=>e.id===(typeof item==='string'?item:'route:'+item.route));
        if(!entry)return '';
        const attrs=entry.route?`data-route="${esc(entry.route)}"`:`data-panel="${esc(entry.id)}"`;
        return `<li><button type="button" class="settings-nav-item" ${attrs}>
          <span class="settings-nav-text"><span>${esc(entry.title)}</span><small>${esc(entry.blurb||'')}</small></span>
          ${entry.route?icon('arrow_right'):icon('chevron_right')}</button></li>`;
      }).join('')}</ul>
    </section>`).join('');
}

workspaceHandlers.settings=async()=>{
  const requested=settingsEntries.find(p=>p.id===settingsPanel&&!p.route);
  const narrow=settingsNarrow();
  // On a phone the list is the page; a section opens only when one was asked for.
  const opening=requested&&(!narrow||settingsDirectLink)?requested:(narrow?null:settingsEntries.find(p=>!p.route&&p.group==='Companion'));
  settingsDirectLink=false;
  returnHermesCards();
  const keepPool=hermesPool;
  $('settings').innerHTML=`
    <div class="settings-shell">
      <nav class="settings-nav" aria-label="Settings">
        <h2 class="page-title settings-nav-title">Settings</h2>
        <label class="settings-search"><span class="sr-only">Find a setting</span>
          ${icon('search')}<input id="settings-search" type="search" placeholder="Find a setting" autocomplete="off"></label>
        <div id="settings-nav-list">${settingsNavHTML()}</div>
        <p class="dim small settings-nav-empty" id="settings-nav-empty" hidden>No setting matches that.</p>
      </nav>
      <div class="settings-page" id="settings-panel" tabindex="-1" role="region" aria-label="Setting"></div>
    </div>`;
  wireRoutes($('settings'));
  if(keepPool)$('settings').append(keepPool);
  const page=$('settings-panel');
  let request=0;
  const mark=id=>{
    for(const b of $('settings').querySelectorAll('[data-panel]'))
      b.toggleAttribute('aria-current',b.dataset.panel===id);
  };
  const show=async(entry,{focus=true}={})=>{
    if(!await confirmEditorLeave('settings-main'))return false;
    const version=++request;
    rememberPanel(entry.id);mark(entry.id);
    returnHermesCards();
    $('settings').classList.add('settings-open');
    page.innerHTML=`
      <div class="settings-page-head">
        <button type="button" class="quiet settings-back" id="settings-back">${icon('chevron_left')}<span>Settings</span></button>
        <p class="settings-eyebrow">${esc(entry.group)}</p>
        <h2 id="settings-page-title">${esc(entry.title)}</h2>
        ${entry.blurb?`<p class="settings-lede">${esc(entry.blurb)}</p>`:''}
      </div>
      <section class="settings-section ${entry.bare?'panel-bare':'card'}" data-settings-section="${esc(entry.id)}" id="settings-section-${esc(entry.id)}" aria-labelledby="settings-page-title">
        <p class="dim" role="status">Loading…</p>
      </section>`;
    page.querySelector('#settings-back').onclick=async()=>{
      if(!await confirmEditorLeave('settings-main'))return;
      returnHermesCards();
      $('settings').classList.remove('settings-open');mark('');
      $('settings').querySelector(`[data-panel="${CSS.escape(entry.id)}"]`)?.focus();
      window.scrollTo({top:0});
    };
    const host=page.querySelector('.settings-section');
    try{await entry.render(host);}
    catch(error){if(version===request)host.innerHTML=`<p class="bad">${esc(error.message)}</p>`;}
    if(version!==request)return false;
    if(focus){
      if(settingsNarrow())window.scrollTo({top:0});
      else page.scrollIntoView({block:'nearest'});
      page.focus({preventScroll:true});
    }
    return true;
  };
  for(const b of $('settings').querySelectorAll('[data-panel]'))
    b.onclick=()=>show(settingsEntries.find(e=>e.id===b.dataset.panel));

  // Search narrows the list itself; Enter opens the first match.
  const search=$('settings-search');
  const matches=q=>settingsEntries.filter(e=>`${e.title} ${e.blurb||''} ${e.keywords||''} ${e.group}`.toLowerCase().includes(q));
  search.oninput=()=>{
    const q=search.value.trim().toLowerCase();
    const hits=new Set(matches(q).map(e=>e.id));
    for(const b of $('settings').querySelectorAll('.settings-nav-item')){
      const id=b.dataset.panel||'route:'+b.dataset.route;
      b.parentElement.hidden=Boolean(q)&&!hits.has(id);
    }
    for(const g of $('settings').querySelectorAll('[data-nav-group]'))
      g.hidden=![...g.querySelectorAll('li')].some(li=>!li.hidden);
    $('settings-nav-empty').hidden=!q||hits.size>0;
  };
  search.onkeydown=e=>{
    if(e.key!=='Enter')return;
    const first=$('settings').querySelector('[data-nav-group]:not([hidden]) li:not([hidden])>.settings-nav-item');
    if(first){e.preventDefault();first.click();}
  };

  if(opening)await show(opening,{focus:Boolean(requested)});
  else $('settings').classList.remove('settings-open');
};
