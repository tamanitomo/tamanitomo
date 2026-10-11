/* The same derived state is displayed here and carried into model context. */
/* The five meters, as markup any surface can drop in. The same derived state is
   displayed here and carried into model context, so one renderer keeps the page
   and the prompt telling the same story. */
const FEELING_METERS=[
  ['warmth','Warmth','🔥','Affection toward you right now.'],
  ['trust','Trust','🛡️','How safe it feels to be open with you.'],
  ['hurt','Hurt','🩹','Lingering pain from something that went wrong.'],
  ['irritation','Irritation','⚡','Friction that has not been talked through yet.'],
  ['longing','Missing you','⏳','How much your absence is being felt.'],
];
/* What is moving a meter, from the server's own explanation (companion_meters.
   explain): the first lines on Home, all of them on Us. Causes name what
   happened, never a number to chase. */
function meterWhy(info,limit=2){
  if(!info)return '';
  const sign=s=>s==='+'?'up':s==='−'?'down':'note';
  const rows=(info.causes||[]).slice(0,limit).map(x=>
    `<li class="why-${sign(x.sign)}"><span class="why-sign" aria-hidden="true">${esc(x.sign||'·')}</span> ${esc(x.text)}</li>`).join('');
  const held=info.held&&typeof info.heading==='number'
    ?`<li class="why-held">Heading for ${Math.round(info.heading*100)}%; today's change is capped</li>`:'';
  return rows||held?`<ul class="meter-why">${rows}${held}</ul>`:'';
}
/* Where closeness is heading, in one line: the next stage and about how many
   good days it takes, or why it is cooling. */
function closenessLine(info){
  if(!info?.line)return '';
  const hint=info.next?.good_days?`A good day: ${info.good_day}.`:'';
  return `<p class="closeness-line"${hint?` title="${esc(hint)}"`:''}>${esc(info.line)}</p>`;
}
/* What the next stage brings, from the stage ladder (companion_gates). */
function closenessNext(info){
  const next=info?.next;
  if(!next?.unlocks?.length)return '';
  return `<p class="closeness-next"><span class="closeness-next-name">At ${esc(next.name)}:</span> ${next.unlocks.map(esc).join(' · ')}</p>`;
}
/* What she needs right now, in words, never as a number or a bar: the page only
   shows that she has needs and which are calling. She lives them. */
const NEED_WORDS={energy:'rest',social:'company',fun:'fun',affection:'closeness'};
function needsRow(needs){
  if(!needs?.has?.length)return '';
  const wants=needs.wants||[];
  const say=needs.asleep?'Asleep, catching up on rest':wants.length?wants.join(', '):'Nothing pressing';
  const luck=(['lucky','unlucky'].includes(needs.luck?.kind)?` Today: ${needs.luck.what}.`:'')
    +(needs.going_on||[]).map(x=>` Still: ${x.what}.`).join('');
  const title=`She has needs (${needs.has.map(n=>NEED_WORDS[n]||n).join(', ')}). They move with her day and your time together.${luck}`;
  return `<div class="presence-chip-row" title="${esc(title)}"><span class="chip-label">🫶 Needs:</span> <span class="chip-val">${esc(say)}</span></div>`;
}
function feelingMeters(meters){
  return `<div class="meter-grid">${FEELING_METERS.map(([key,label,icon,why])=>{
    const value=meters?meters[key]:null;
    const pct=typeof value==='number'&&isFinite(value)?Math.round(Math.max(0,Math.min(1,value))*100):0;
    return `<div class="meter-card meter-${key}" title="${esc(why)}">
      <div class="meter-head"><span>${icon} ${label}</span><strong>${pct}%</strong></div>
      <div class="meter-track"><div class="meter-fill" style="width:${pct}%"></div></div>
      <small class="dim">${esc(why)}</small>
    </div>`;
  }).join('')}</div>`;
}
/* One experience per row, evidence folded away. Used by the emotional history
   on the Us page; the story feed there tells the same events in plainer words. */
function feelingHistoryRows(rows){
  return rows.map(x=>`<article class="moment-row"><div><span class="pill ${x.kind==='connection'?'good':x.kind==='rupture'?'bad':''}">${esc(x.kind)}</span><small>${esc(when(x.at))}</small></div><div><p style="margin:0;font-size:13.5px;line-height:1.4">${esc(x.text)}</p><details style="margin-top:4px"><summary class="dim small" style="cursor:pointer">Context & evidence</summary><p class="dim small" style="margin:4px 0">${esc(x.evidence)}</p></details></div></article>`).join('')||'<p class="dim small" style="padding:14px;text-align:center">No emotional experiences recorded yet. Meaningful connections or ruptures will be noted naturally during conversation.</p>';
}
/* The full, paged history, drawn into whatever host asks for it. A page that
   arrives after the host has gone (the dialog closed, another opened) is dropped. */
async function mountFeelingHistory(host){
  if(!host)return;
  const first=await api('/feelings/experiences');
  if(!host.isConnected)return;
  const history=[...first.experiences];let cursor=first.next_cursor,total=first.total;
  host.innerHTML=`<p class="dim">Warmth, trust, ruptures and repairs, as they happened in conversation — this is what the feelings are made of.</p>
    <div class="feelings-history"></div>
    <div class="actions"><span class="dim small" role="status"></span><button type="button" class="quiet" hidden>Load older experiences</button></div>`;
  const list=host.querySelector('.feelings-history'),count=host.querySelector('[role=status]'),older=host.querySelector('button');
  const draw=()=>{list.innerHTML=feelingHistoryRows(history);count.textContent=`${history.length} of ${total} experiences`;older.hidden=!cursor;};
  older.onclick=async()=>{
    older.disabled=true;
    try{
      const page=await api('/feelings/experiences?'+new URLSearchParams({before:cursor}));
      if(!host.isConnected)return;
      history.push(...page.experiences.filter(row=>!history.some(x=>x.id===row.id)));cursor=page.next_cursor;total=page.total;
      draw();
    }catch(error){if(host.isConnected)count.textContent=error.message;}
    finally{older.disabled=false;}
  };
  draw();
}

/* Dated plans carry the human's explanation. Browser timezone never decides the
   interval: wall times are resolved in the companion's zone by the server. */
function absenceLocalTime(value,timezone){
  if(!value)return '';
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
function expectedAbsencesSummary(rows=[]){
  const active=rows.filter(r=>['current','upcoming'].includes(r.status));
  return `${active.length?`<ul>${active.slice(0,3).map(r=>`<li><strong>${esc(r.label)}</strong> · ${esc(when(r.start))} – ${esc(when(r.end))}</li>`).join('')}</ul>`:'<p class="dim small">No dated plans recorded.</p>'}
    <button type="button" class="quiet" data-us-action="absences">Review or add time away</button>`;
}
async function openExpectedAbsences(){
  if(!await confirmEditorLeave('dialog'))return;
  dialog('Expected time apart','<div id="expected-absences"><p class="dim">Loading…</p></div>');
  const host=$('expected-absences');
  try{await mountExpectedAbsences(host);}catch(error){if(host.isConnected)host.innerHTML=`<p class="bad">${esc(error.message)}</p>`;}
}
async function mountExpectedAbsences(host){
  const scope=INSTALLATION+'\0'+PROFILE;
  const present=()=>host.isConnected&&scope===INSTALLATION+'\0'+PROFILE;
  let state=await api('/feelings/absences');
  if(!present())return;
  const paint=()=>{
    host.innerHTML=`<p class="dim">Trips, work and other time away you have explained. These plans are expectations, not observations. Explained time does not count as distance, and stays explained after the plan ends.</p>
      <p class="small dim">Dates use ${esc(state.timezone)}. Quiet hours still control messages separately.</p>
      <div class="actions"><button type="button" class="act" data-absence-new>Add time away</button><button type="button" class="quiet" data-absence-reload>Refresh</button></div>
      <div data-absence-list>${state.absences.slice().reverse().map(row=>`<article class="moment-row"><div><strong>${esc(row.label)}</strong><p class="dim small">${esc(row.status)}</p></div><div>
        <p>${esc(absenceLocalTime(row.start,state.timezone).replace('T',' '))} – ${esc(absenceLocalTime(row.end,state.timezone).replace('T',' '))}</p>
        <details><summary>Explanation &amp; history</summary>${state.history.filter(x=>x.id===row.id).map(x=>`<p class="small"><strong>${esc(x.action)}</strong> · ${esc(when(x.recorded_at))}<br>${esc(x.evidence)}<br><span class="dim">${esc(x.source)} · ${esc(x.start)} – ${esc(x.end)}</span></p>`).join('')}</details>
        ${row.status!=='cancelled'?`<div class="actions"><button type="button" class="quiet" data-absence-edit="${esc(row.id)}">Edit plan</button><button type="button" class="quiet" data-absence-cancel="${esc(row.id)}">Cancel plan</button></div>`:''}
        </div></article>`).join('')||'<p class="dim">No dated plans yet.</p>'}</div>
      <div data-absence-editor></div><p data-absence-status role="status"></p>`;
    host.querySelector('[data-absence-new]').onclick=()=>edit(null,'create');
    host.querySelector('[data-absence-reload]').onclick=async()=>{
      if(!await confirmEditorLeave('dialog')||!present())return;
      try{state=await api('/feelings/absences');if(present())paint();}
      catch(error){if(present())host.querySelector('[data-absence-status]').textContent=error.message;}
    };
    for(const button of host.querySelectorAll('[data-absence-edit], [data-absence-cancel]'))button.onclick=()=>{
      const id=button.dataset.absenceEdit||button.dataset.absenceCancel;
      return edit(state.absences.find(row=>row.id===id),button.dataset.absenceCancel?'cancel':'edit');
    };
  };
  const edit=async(row,action)=>{
    if(!await confirmEditorLeave('dialog')||!present())return;
    const box=host.querySelector('[data-absence-editor]');
    const revision=state.revision;
    box.innerHTML=`<form id="feelings-controls">
      <h3>${action==='cancel'?'Cancel':action==='edit'?'Edit':'Add'} ${row?esc(row.label):'time away'}</h3>
      ${action!=='create'?'<p class="dim small">Changes apply to the remaining plan. Time already explained stays explained.</p>':''}
      ${action!=='cancel'?`<label>Label<input name="label" required maxlength="80" value="${esc(row?.label||'')}"></label>
        <div class="form-grid"><label>Starts · ${esc(state.timezone)}<input type="datetime-local" name="start" required value="${esc(absenceLocalTime(row?.start,state.timezone))}"></label>
        <label>Ends · ${esc(state.timezone)}<input type="datetime-local" name="end" required value="${esc(absenceLocalTime(row?.end,state.timezone))}"></label></div>
        <label><input type="checkbox" name="explicit"> Use full ISO timestamps with UTC offsets (for a clock change)</label>`:''}
      <label>${action==='create'?'Your explanation':'What changed?'}<textarea name="evidence" required maxlength="1000" placeholder="Your own words about this time away"></textarea></label>
      <div class="actions"><button class="act" type="submit">${action==='cancel'?'Save cancellation':'Save plan'}</button><button type="button" class="quiet" data-absence-close>Back to plans</button></div>
      <p data-absence-error role="status"></p></form>`;
    const form=box.querySelector('form');
    if(action!=='cancel')form.elements.explicit.onchange=()=>{
      for(const key of ['start','end']){
        const input=form.elements[key];
        if(form.elements.explicit.checked){input.type='text';input.placeholder='2026-11-01T01:30:00-04:00';if(row&&input.value===absenceLocalTime(row[key],state.timezone))input.value=row[key];}
        else{const previous=input.value;input.type='datetime-local';input.value=/(?:Z|[+-]\d\d:\d\d)$/.test(previous)?absenceLocalTime(previous,state.timezone):previous;}
      }
    };
    box.querySelector('[data-absence-close]').onclick=async()=>{if(await confirmEditorLeave('dialog')&&present())box.innerHTML='';};
    form.onsubmit=async event=>{
      event.preventDefault();
      if(!form.reportValidity()||!present())return;
      const payload={action,revision,evidence:form.elements.evidence.value,source:'owner-app'};
      if(row)payload.id=row.id;
      if(action!=='cancel')for(const key of ['label','start','end'])payload[key]=form.elements[key].value;
      payload.timezone=state.timezone;
      const button=form.querySelector('[type=submit]');button.disabled=true;
      try{
        const saved=await api('/feelings/absences',{method:'POST',body:JSON.stringify(payload)});
        if(!present()||!form.isConnected)return;
        state=saved;clearEditorDirty('dialog');paint();
        host.querySelector('[data-absence-status]').textContent=action==='cancel'?'Plan cancelled. Elapsed time remains explained.':'Expected time away saved.';
        if(current==='relationship'&&$('us-absences'))$('us-absences').innerHTML=expectedAbsencesSummary(state.absences);
      }catch(error){if(present()&&form.isConnected)form.querySelector('[data-absence-error]').textContent=error.message+(error.status===409?' Keep your explanation, then refresh the plans before trying again.':'');}
      finally{button.disabled=false;}
    };
    form.elements.evidence.focus();
  };
  paint();
}
