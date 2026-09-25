/* Journal: an archive of days, read two ways.

   Day shows what was recorded on a date -- her scenes, the photos whose capture
   names that scene, a plan if one was written for it, and a shared moment only
   when one was recorded with that exact date. Reflection is the nightly entry
   for the same date, drawn the way the reader always drew it.

   The selected date and view live in the address (#journals/<date>/<view>), so
   refresh, back/forward and a shared link all land on the same page. Opening,
   switching or refreshing reads records and nothing else: no model, no job, no
   write. A day with nothing on record says so instead of being filled in. */

const JOURNAL_VIEWS=['day','reflection'];
/* Real calendar dates only; 2026-02-30 is not a day to navigate to. */
function journalValidDay(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const d=new Date(value+'T00:00:00Z');
  return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===value;
}
function journalRouteParse(hash){
  const parts=String(hash||'').replace(/^#/,'').split('/');
  if(parts[0]!=='journals')return null;
  return {day:journalValidDay(parts[1])?parts[1]:null,view:JOURNAL_VIEWS.includes(parts[2])?parts[2]:null};
}
function journalRouteHash(day,view){return '#journals/'+day+'/'+view;}
/* Calendar arithmetic on the date itself, never on a local midnight, so a
   daylight-saving change cannot skip or repeat a day. */
function journalAddDays(day,n){const d=new Date(day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
function journalNeighbours(days,day){
  const sorted=[...new Set(days)].sort();
  return {older:[...sorted].reverse().find(d=>d<day)||null,newer:sorted.find(d=>d>day)||null};
}
const JOURNAL_STATUS={planned:'Planned, not recorded as happening',skipped:'Skipped',
  carried_forward:'Carried forward · unconfirmed'};

/* Remembered across tab switches; the address wins whenever it names a day. */
const journalState={day:null,view:null,entry:null};
let journalPageGeneration=0,journalRequest=0,journalApply=null;
// Held so that revisiting the page replaces this listener instead of stacking
// another one on the document for every visit.
let journalOutsideClick=null;

workspaceHandlers.journals=async()=>{
  const pageGeneration=++journalPageGeneration;
  const scope=INSTALLATION+'|'+PROFILE;
  const alive=()=>current==='journals'&&pageGeneration===journalPageGeneration&&scope===INSTALLATION+'|'+PROFILE;
  $('journals').innerHTML=`
    <div class="reader-shell">
      <div class="segmented journal-views" role="tablist" aria-label="Journal view">
        <button role="tab" id="journal-view-day" data-view="day" aria-controls="journal-page" aria-selected="false">Day</button>
        <button role="tab" id="journal-view-reflection" data-view="reflection" aria-controls="journal-page" aria-selected="false">Reflection</button>
      </div>
      <div class="journal-nav-bar">
        <button class="journal-nav-btn" id="journal-older-btn" disabled>${icon('arrow_left')}<span class="nav-word">Older</span></button>
        <button class="reader-browse-btn" id="journal-browse" aria-expanded="false" aria-controls="journal-picker">
          <span aria-hidden="true">\u{1F4C5}</span><span id="journal-browse-label">Loading…</span><span class="reader-browse-caret" aria-hidden="true">▾</span>
        </button>
        <button class="journal-nav-btn" id="journal-newer-btn" disabled><span class="nav-word">Newer</span>${icon('arrow_right')}</button>
      </div>
      <div class="reader-picker" id="journal-picker" hidden>
        <label class="journal-date-jump"><span class="dim small">Go to a date</span>
          <input id="journal-date" type="date" aria-label="Go to a date"></label>
        <input id="journal-search" type="search" maxlength="200" autocomplete="off"
          placeholder="Search every reflection…" aria-label="Search journal entries">
        <div id="journal-picker-body"></div>
        <div class="reader-picker-foot">
          <span id="journal-count" class="dim small"></span>
          <span class="journal-picker-actions">
            <button class="quiet small" id="journal-today">Today</button>
            <button class="quiet small" id="journal-latest">Latest reflection</button>
          </span>
        </div>
      </div>
    </div>
    <div id="journal-warnings"></div>
    <article id="journal-page" role="tabpanel" aria-live="polite"><p class="dim" role="status">Opening the journal…</p></article>`;

  let entries=[],warnings=[],index={days:{}},today=companionToday(),results=null,searchTimer=null,pickerMonth='';
  const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dayFormat=day=>new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T12:00:00Z'));
  const shortDay=day=>new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(new Date(day+'T12:00:00Z'));
  const clock=t=>stamp(t,{hour:'numeric',minute:'2-digit',month:undefined,day:undefined});
  const reflectionDays=()=>entries.map(x=>x.day);
  const recordDays=()=>Object.keys(index.days||{});

  /* ------------------------------------------------------------ routing */
  const setHash=(push)=>{
    if(current!=='journals')return;
    const hash=journalRouteHash(journalState.day,journalState.view);
    if(location.hash===hash)return;
    history[push?'pushState':'replaceState'](null,'',location.pathname+location.search+hash);
  };
  const go=async(day,view,{push=true,entry=null}={})=>{
    if(!journalValidDay(day))day=today;
    if(!JOURNAL_VIEWS.includes(view))view='day';
    journalState.day=day;journalState.view=view;
    if(entry)journalState.entry=entry;
    else if(view==='reflection'&&!entries.some(x=>x.id===journalState.entry&&x.day===day))journalState.entry=entries.find(x=>x.day===day)?.id||null;
    // Another page asks for an entry by setting selectedJournal; once shown, the request is spent.
    selectedJournal=null;
    setHash(push);
    openPicker(false);
    for(const b of $('journals').querySelectorAll('[data-view]')){
      const on=b.dataset.view===view;
      b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;
    }
    $('journal-browse-label').textContent=shortDay(day)+(day===today?' · Today':'');
    pickerMonth=day.slice(0,7);
    const near=journalNeighbours(view==='reflection'?reflectionDays():[...recordDays(),...reflectionDays()],day);
    const olderBtn=$('journal-older-btn'),newerBtn=$('journal-newer-btn');
    olderBtn.disabled=!near.older;newerBtn.disabled=!near.newer;
    const noun=view==='reflection'?'reflection':'day on record';
    olderBtn.title=near.older?'Older: '+shortDay(near.older):`No older ${noun}`;
    newerBtn.title=near.newer?'Newer: '+shortDay(near.newer):`No newer ${noun}`;
    olderBtn.onclick=near.older?()=>go(near.older,view):null;
    newerBtn.onclick=near.newer?()=>go(near.newer,view):null;
    const token=++journalRequest;
    const fresh=()=>alive()&&token===journalRequest&&journalState.day===day&&journalState.view===view;
    $('journal-page').innerHTML='<p class="dim" role="status">Opening '+esc(shortDay(day))+'…</p>';
    if(view==='day')await drawDay(day,fresh);
    else await drawReflection(day,fresh);
  };
  journalApply=route=>go(route.day||journalState.day||today,route.view||journalState.view||'day',{push:false});

  /* ---------------------------------------------------------- day view */
  const drawDay=async(day,fresh)=>{
    let data;
    try{data=await api('/journal/archive/'+encodeURIComponent(day));}
    catch(error){if(fresh())$('journal-page').innerHTML=`<p class="bad">The day could not be opened: ${esc(error.message)}</p>`;return;}
    if(!fresh()||data.day!==day)return;
    profileTimezone=data.timezone||profileTimezone;
    const who=esc(data.agent||'Your companion');
    const scenes=data.scenes||[],unplaced=data.unplaced_photos||[];
    const allPhotos=[...scenes.flatMap(x=>x.photos),...unplaced.flatMap(x=>x.photos)];
    const shots=allPhotos.length;
    const counts=[scenes.length?scenes.length+(scenes.length===1?' scene':' scenes'):'',shots?shots+(shots===1?' photo':' photos'):''].filter(Boolean).join(' · ');
    const notes=[];
    if(data.sources.scenes==='unavailable')notes.push(`This day's scene record could not be read. It has not been changed; refresh to try again, or open it in the Vault.`);
    if(data.sources.photos==='unavailable')notes.push('Photo records could not be read, so no photos are shown for these scenes.');
    if(data.sources.photos==='partial')notes.push('The photo library is larger than one scan, so some photos from these scenes may not be shown.');
    if(data.plan.state==='unavailable')notes.push('A plan file for this day exists but could not be read.');
    if(data.together.state==='unavailable')notes.push('Shared moments could not be read.');
    if(data.reflection.state==='unavailable')notes.push('A journal file could not be read, so a reflection for this day may be missing here.');
    const photo=x=>{const i=allPhotos.indexOf(x);return `<button class="tl-shot${x.blur?' is-private':''}" data-archive-photo="${i}" aria-label="Open photo: ${esc(x.title||'')}">
        <img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title||'')}">
        ${x.blur?'<span class="tl-shot-lock">Hidden · tap to view</span>':''}
        <time>${esc(clock(x.at))}</time></button>`;};
    const scene=x=>{
      const mins=x.until?Math.round(((Date.parse(x.until)||0)-(Date.parse(x.at)||0))/60000):0;
      const sleep=/\b(sleep|sleeping|asleep|nap|napping)\b/i.test(x.activity||'');
      const status=JOURNAL_STATUS[x.status];
      return `<li class="tl-scene${sleep?' is-sleep':''}${x.status==='carried_forward'?' is-unconfirmed':''} is-${esc(x.status)}" data-scene="${esc(x.id)}">
        <time>${x.time_known?esc(clock(x.at)):'<span class="dim">Time not recorded</span>'}</time>
        <div class="tl-card">
          <div class="tl-top">
            <p class="tl-title">${sleep?'<span aria-hidden="true">☾ </span>':''}${esc(sentenceCase(x.activity)||'A scene')}</p>
            ${mins>=5?`<span class="tl-span">${spanLabel(mins)}</span>`:''}
          </div>
          ${x.mood?`<p class="tl-mood">${esc(sentenceCase(x.mood))}</p>`:''}
          ${x.location||status||x.snapshots>1?`<div class="tl-meta">${x.location?`<span class="tl-place">${esc(x.location)}</span>`:''}${status?`<span class="pill">${esc(status)}</span>`:''}${x.snapshots>1?`<span class="dim small" title="Adjacent identical snapshots, shown once; every one is still stored">${x.snapshots} unchanged snapshots</span>`:''}</div>`:''}
          ${x.photos.length?`<div class="tl-strip">${x.photos.map(photo).join('')}</div>`:''}
          ${x.missing_photos?`<p class="dim small">${x.missing_photos===1?'A photo':x.missing_photos+' photos'} taken in this scene ${x.missing_photos===1?'is':'are'} no longer in the library.</p>`:''}
        </div></li>`;
    };
    const entry=(data.reflection.entries||[])[0];
    const lead=entry?`<article class="day-lead journal-day-reflection">
        <span class="eyebrow">From the reflection</span>
        <p>${esc(excerpt(entry.excerpt,320))}</p>
        <button class="link-button" id="journal-to-reflection">Read the reflection →</button></article>`:'';
    const plan=data.plan.state==='available'?`<section class="journal-day-section">
        <h3>Planned for this day</h3>
        <p class="dim small">A plan is an intention written ahead of time, not a record that any of it happened.</p>
        <ul class="journal-plan">${data.plan.items.map(x=>`<li><span class="dim small">${esc(x.start)}${x.end?'–'+esc(x.end):''}</span> ${esc(x.what)}${x.where?` <span class="dim small">· ${esc(x.where)}</span>`:''} <span class="pill">${esc(x.status)}</span></li>`).join('')}</ul>
      </section>`:'';
    const together=(data.together.moments||[]).length?`<section class="journal-day-section journal-together">
        <h3>You two</h3>
        <ul>${data.together.moments.map(x=>`<li>${esc(x.text)}${x.status==='retired'?' <span class="pill">retired</span>':''}</li>`).join('')}</ul>
        ${jump('relationship','Open Us')}
      </section>`:'';
    const loose=unplaced.length?`<section class="journal-day-section">
        <h3>Photos whose scene is no longer on record</h3>
        <p class="dim small">Each capture names the scene it was taken in, and that scene is missing from this day's record. They are shown here rather than attached to a different scene.</p>
        ${unplaced.map(x=>`<p class="small">${esc(clock(x.at))} · ${esc(sentenceCase(x.activity)||'Unnamed scene')}</p><div class="tl-strip">${x.photos.map(photo).join('')}</div>`).join('')}
      </section>`:'';
    let body='';
    if(scenes.length){
      body=`<p class="dim small journal-provenance">${who}'s own account of the day, recorded by the companion. It is not a record of what you did.</p>
        <ol class="tl-rail">${scenes.map(scene).join('')}</ol>`;
    }else if(data.sources.scenes!=='unavailable'){
      const future=day>data.today;
      body=`<p class="dim journal-day-empty">${future?'This day has not happened yet, so nothing is recorded for it.':
        data.sources.scenes==='empty'?"This day's record file exists but holds no scenes.":'No scenes were recorded on this day.'}</p>`;
    }
    const nothing=!scenes.length&&!entry&&!plan&&!together&&!loose&&!notes.length;
    $('journal-page').innerHTML=`<section class="day-group journal-day" data-day="${esc(day)}">
      <div class="day-head">
        <div><h2>${esc(dayFormat(day))}</h2>${day===data.today?'<span class="tl-today">Today</span>':''}</div>
        <span class="dim small">${esc(counts||'Nothing recorded')}</span>
      </div>
      ${notes.map(x=>`<p class="warn">${esc(x)}</p>`).join('')}
      ${nothing?empty('journals','Nothing on record for this day','No scene, plan or reflection was recorded for this date. Opening it here never creates one.'):lead+body}
      ${loose}${plan}${together}
      <p class="dim small journal-sources">Sources: scenes in <code>companion-life/episodes</code>${entry?` · reflection in <code>${esc(entry.source)}</code>`:''}</p>
      <p class="journal-sources">${jump('timeline','Open Timeline')}</p>
    </section>`;
    for(const b of $('journal-page').querySelectorAll('[data-archive-photo]'))
      b.onclick=()=>{const i=+b.dataset.archivePhoto;openPhotoViewer(allPhotos[i],allPhotos,i);};
    if($('journal-to-reflection'))$('journal-to-reflection').onclick=()=>go(day,'reflection',{entry:entry.id});
    wireRoutes($('journal-page'));
  };

  /* --------------------------------------------------- reflection view */
  const drawReflection=async(day,fresh)=>{
    const found=entries.filter(x=>x.day===day);
    if(!found.length){
      const near=journalNeighbours(reflectionDays(),day);
      const nav=[near.older?`<button class="quiet" data-go-day="${esc(near.older)}">Older reflection · ${esc(shortDay(near.older))}</button>`:'',
        near.newer?`<button class="quiet" data-go-day="${esc(near.newer)}">Newer reflection · ${esc(shortDay(near.newer))}</button>`:'',
        `<button class="quiet" data-go-day="${esc(day)}" data-go-view="day">See the day</button>`].join('');
      $('journal-page').innerHTML=warnings.length
        ? `<div class="empty-state">${icon('journals')}<h3>The reflection could not be read</h3>
            <p>No reflection can be shown for ${esc(dayFormat(day))} because a journal file could not be read. Nothing has been written in its place.</p>${nav}</div>`
        : entries.length
          ? empty('journals','No reflection saved for this day',`Nothing was written for ${dayFormat(day)}. Reflections are written by the nightly routine; opening this page never writes one.`,nav)
          : empty('journals','No journal entries yet','Daily reflections are recorded automatically by the scheduled nightly routine at 4:00 AM.',
              jump('settings','View routine status',false,'jobs'));
      for(const b of $('journal-page').querySelectorAll('[data-go-day]'))b.onclick=()=>go(b.dataset.goDay,b.dataset.goView||'reflection');
      wireRoutes($('journal-page'));
      return;
    }
    const full=[];
    for(let entry of found){
      if(entry.truncated||entry.text===undefined){
        try{entry=(await api('/journals/'+encodeURIComponent(entry.id))).entry;}
        catch(error){if(fresh())$('journal-page').innerHTML=`<p class="bad">${esc(error.message)}</p>`;return;}
        if(!fresh())return;
      }
      full.push(entry);
    }
    const dayPhotos=await api('/content?'+new URLSearchParams({kind:'image',limit:'12',day}))
      .then(r=>r.items.filter(x=>x.kind==='image')).catch(()=>[]);
    if(!fresh())return;
    const strip=dayPhotos.length?`
      <div class="journal-day-photos">
        <span class="eyebrow">${dayPhotos.length} ${dayPhotos.length===1?'picture':'pictures'} from this day</span>
        <div class="journal-day-strip">${dayPhotos.map((x,i)=>`
          <button class="journal-day-shot" data-day-photo="${i}" aria-label="Open ${esc(x.title)}">
            <img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}">
          </button>`).join('')}</div>
      </div>`:'';
    $('journal-page').innerHTML=full.map((entry,i)=>`<div class="paper" data-entry="${esc(entry.id)}"${i?' style="margin-top:18px"':''}>
      <div class="paper-head">
        <span class="eyebrow" style="color:var(--faint)">Daily reflection · ${Math.max(1,Math.ceil(entry.words/220))} min read</span>
        <span class="pill" style="border-color:color-mix(in srgb,var(--surface-2) 30%,transparent);color:var(--faint)">Nightly Entry</span>
      </div>
      <h2>${esc(dayFormat(entry.day))}</h2>
      <div class="prose">${richText(entry.text)}</div>
      ${i===full.length-1?strip:''}
      <div class="paper-foot">
        <span style="font-family:Georgia,serif;font-style:italic;color:var(--faint);font-size:14px">Written during nightly introspection</span>
        <span class="dim small">${entry.words.toLocaleString()} words · ${esc(entry.source)}</span>
      </div>
    </div>`).join('')+`<p class="journal-reflection-foot"><button class="link-button" id="journal-to-day">See this day's scenes →</button></p>`;
    for(const b of $('journal-page').querySelectorAll('[data-day-photo]'))
      b.onclick=()=>openPhotoViewer(dayPhotos[+b.dataset.dayPhoto],dayPhotos,+b.dataset.dayPhoto);
    $('journal-to-day').onclick=()=>go(day,'day');
    const target=$('journal-page').querySelector(`[data-entry="${CSS.escape(journalState.entry||'')}"]`);
    (target||$('journal-page')).scrollIntoView({block:'start',behavior:'smooth'});
  };

  /* ------------------------------------------------------------- picker */
  const openPicker=open=>{
    $('journal-picker').hidden=!open;
    $('journal-browse').setAttribute('aria-expanded',String(open));
    if(open){$('journal-date').value=journalState.day||'';drawPicker();$('journal-date').focus();}
  };
  const drawPicker=()=>{
    const body=$('journal-picker-body');
    if(results){
      $('journal-count').textContent=`${results.length} matching ${results.length===1?'entry':'entries'}`;
      body.innerHTML=results.length
        ? `<div class="reader-picker-results">${results.map(x=>`
            <button data-pick="${esc(x.id)}" data-pick-day="${esc(x.day)}" ${x.id===journalState.entry?'aria-current="true"':''}>
              <strong>${esc(shortDay(x.day))}</strong><small>${esc(excerpt(x.excerpt||x.text,110))}</small>
            </button>`).join('')}</div>`
        : '<p class="dim small reader-picker-empty">Nothing matches that.</p>';
      return;
    }
    const byDay=new Map();
    for(const e of entries){if(!byDay.has(e.day))byDay.set(e.day,[]);byDay.get(e.day).push(e);}
    const [year,month]=pickerMonth.split('-').map(Number);
    const first=new Date(Date.UTC(year,month-1,1)).getUTCDay(),count=new Date(Date.UTC(year,month,0)).getUTCDate();
    let cells='';
    for(let i=0;i<first;i++)cells+='<div class="calendar-cell is-other-month"></div>';
    for(let day=1;day<=count;day++){
      const key=`${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
      const found=byDay.get(key)||[],records=(index.days||{})[key];
      const marked=found.length||records;
      const classes=['calendar-cell',found.length?'has-entry':'',records?.scenes?'has-scenes':'',marked?'':'is-quiet',
        key===today?'is-today':'',key===journalState.day?'is-selected':''].filter(Boolean).join(' ');
      const label=[dayFormat(key),found.length?'reflection':'',records?.scenes?'scenes':''].filter(Boolean).join(' · ');
      cells+=`<button class="${classes}" data-pick-day="${key}" title="${esc(label)}" aria-label="${esc(label)}"${key===journalState.day?' aria-current="date"':''}>
             <span class="calendar-cell-date">${day}</span>
             ${found.length>1?`<span class="cal-badge-pill">${found.length}</span>`:''}</button>`;
    }
    const total=new Set([...recordDays(),...reflectionDays()]).size;
    $('journal-count').textContent=`${entries.length} ${entries.length===1?'reflection':'reflections'} · ${total} ${total===1?'day':'days'} on record`;
    body.innerHTML=`
      <div class="reader-picker-bar">
        <button class="icon-button" id="journal-cal-prev" aria-label="Previous month">←</button>
        <strong>${MONTHS[month-1]} ${year}</strong>
        <button class="icon-button" id="journal-cal-next" aria-label="Next month">→</button>
      </div>
      <div class="calendar-grid reader-picker-grid">
        ${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=>`<div class="calendar-day-head">${d}</div>`).join('')}
        ${cells}
      </div>
      <p class="dim small journal-picker-key"><span class="journal-key has-entry"></span> reflection <span class="journal-key has-scenes"></span> scenes</p>`;
    const shift=step=>{
      const d=new Date(Date.UTC(year,month-1+step,1));
      pickerMonth=d.toISOString().slice(0,7);
      drawPicker();
    };
    $('journal-cal-prev').onclick=()=>shift(-1);
    $('journal-cal-next').onclick=()=>shift(1);
  };

  for(const b of $('journals').querySelectorAll('[data-view]')){
    b.onclick=()=>go(journalState.day||today,b.dataset.view);
    b.onkeydown=event=>{
      if(event.key!=='ArrowLeft'&&event.key!=='ArrowRight')return;
      const next=b.dataset.view==='day'?'reflection':'day';
      go(journalState.day||today,next);$('journal-view-'+next).focus();
    };
  }
  $('journal-browse').onclick=()=>openPicker($('journal-picker').hidden);
  $('journal-latest').onclick=()=>{if(entries[0])go(entries[0].day,'reflection',{entry:entries[0].id});};
  $('journal-today').onclick=()=>go(today,'day');
  $('journal-date').onchange=()=>{const v=$('journal-date').value;if(journalValidDay(v))go(v,journalState.view||'day');};
  $('journal-picker').addEventListener('click',event=>{
    const pick=event.target.closest('[data-pick-day]');
    if(!pick)return;
    if(pick.dataset.pick)go(pick.dataset.pickDay,'reflection',{entry:pick.dataset.pick});
    else go(pick.dataset.pickDay,journalState.view||'day');
  });
  $('journal-search').oninput=()=>{
    const query=$('journal-search').value.trim();
    clearTimeout(searchTimer);
    searchTimer=setTimeout(async()=>{
      if(!alive())return;
      if(!query){results=null;drawPicker();return;}
      try{
        const data=await api('/journals?limit=1000&q='+encodeURIComponent(query));
        if(!alive()||$('journal-search').value.trim()!==query)return;
        results=data.entries;drawPicker();
      }catch(error){if(alive())$('journal-count').textContent=error.message;}
    },220);
  };
  // Escape closes the panel; a click anywhere outside it does too.
  $('journals').addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!$('journal-picker').hidden){openPicker(false);$('journal-browse').focus();}
  });
  if(journalOutsideClick)document.removeEventListener('click',journalOutsideClick);
  journalOutsideClick=event=>{
    if(!alive()||$('journal-picker')?.hidden!==false)return;
    if(!event.target.closest('#journal-picker')&&!event.target.closest('#journal-browse'))openPicker(false);
  };
  document.addEventListener('click',journalOutsideClick);

  /* --------------------------------------------------------------- load */
  // Capture another page's entry request before awaiting, but resolve the
  // address afterwards so a newer date/view selection remains authoritative.
  const asked=selectedJournal;
  try{
    const [list,archive]=await Promise.all([api('/journals?limit=1000'),
      api('/journal/archive').catch(error=>({days:{},error:error.message}))]);
    if(!alive())return;
    const route=journalRouteParse(location.hash);
    profileTimezone=list.timezone;
    entries=list.entries;warnings=list.warnings||[];index=archive;
    today=archive.today||companionToday();
    const notes=[...warnings];
    if(archive.error)notes.push('The list of recorded days could not be read: '+archive.error);
    if(archive.scenes_unavailable)notes.push('Some days’ scene records could not be read and are not marked in the calendar.');
    $('journal-warnings').innerHTML=notes.map(x=>`<p class="warn">${esc(x)}</p>`).join('');
    const pick=asked&&entries.find(x=>x.id===asked);
    if(route&&route.day)return await go(route.day,route.view||journalState.view||'day',{push:false});
    if(pick)return await go(pick.day,'reflection',{push:false,entry:pick.id});
    if(journalState.day)return await go(journalState.day,route?.view||journalState.view,{push:false});
    if(entries[0])return await go(entries[0].day,route?.view||'reflection',{push:false,entry:entries[0].id});
    await go(today,route?.view||'day',{push:false});
  }catch(error){
    if(alive())$('journal-page').innerHTML=`<p class="bad">${esc(error.message)}</p>`;
  }
};

/* Back and forward. Tab switches replace the address and Journal pushes a new
   one for each date or view chosen, so this only ever lands on a Journal route
   or on a page that was replaced into the history. */
window.addEventListener('popstate',()=>{
  const route=journalRouteParse(location.hash);
  if(route&&current==='journals'&&journalApply){journalApply(route);return;}
  const tab=location.hash.slice(1).split('/')[0];
  const name=TAB_ALIASES[tab]||tab;
  if(name&&name!==current&&TABS.some(([id])=>id===name))showTab(name);
});
