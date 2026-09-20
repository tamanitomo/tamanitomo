function mediaPrivacy(item){return item.blur?'class="concealed-media" title="Sensitive or unreviewed image · open details to reveal"':'';}
const paths={now:'M3 11 12 3l9 8v10h-6v-7H9v7H3Z',chat:'M4 4h16v12H9l-5 4Z',timeline:'M6 3v18M10 5h10M10 12h7M10 19h10',photos:'M3 4h18v16H3ZM3 16l5-5 5 5 3-3 5 5M16 8h.01',journals:'M5 3h14v18H5ZM8 7h8M8 11h8M8 15h5',creations:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',relationship:'M12 20S2 14 2 8a5 5 0 0 1 10-1 5 5 0 0 1 10 1c0 6-10 12-10 12Z',loops:'M4 5h16v16H4ZM8 2v6M16 2v6M4 11h16',knows:'M12 3v18M12 6C7 1 2 5 3 10c-3 5 2 10 9 8M12 6c5-5 10-1 9 4 3 5-2 10-9 8',vault:'M3 6h7l2 3h9v12H3Z',identity:'M8 7a4 4 0 1 0 8 0 4 4 0 1 0-8 0M4 21v-3c0-6 16-6 16 0v3',settings:'M4 7h16M4 17h16M8 4v6M16 14v6','local-models':'M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Zm5 3h6v6H9V9Zm-5 2h2m-2 4h2m14-4h2m-2 4h2m-9-11v2m4-2v2m-4 14v2m4-2v2',environment:'M12 2v4M12 18v4M2 12h4M18 12h4M5 5l3 3M16 16l3 3M19 5l-3 3M8 16l-3 3M7 12a5 5 0 1 0 10 0 5 5 0 1 0-10 0',health:'M2 12h5l3-8 4 16 3-8h5',roster:'M8 8a3 3 0 1 0 6 0 3 3 0 1 0-6 0M3 21v-3c0-5 14-5 14 0v3M17 5c5 0 5 6 0 6M20 15c2 1 2 3 2 6',search:'M10 3a7 7 0 1 0 0 14 7 7 0 1 0 0-14M16 16l5 5',download:'M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',album:'M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16l-8-4-8 4V5Z',shield_alert:'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm0-14v4m0 4h.01',shield_check:'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-2-10 2 2 4-4',info:'M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z',trash:'M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2',close:'M18 6 6 18M6 6l12 12',chevron_left:'M15 18l-6-6 6-6',chevron_right:'M9 18l6-6-6-6',arrow_left:'M19 12H5m7 7-7-7 7-7',arrow_right:'M5 12h14m-7-7 7 7-7 7',voice:'M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm5 9a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z','image-studio':'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',more:'M5 12h.01M12 12h.01M19 12h.01',pin:'M12 17v5M9 3h6l-1 7 3 3v2H7v-2l3-3-1-7Z',select:'M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',profile:'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M16 3l2 2 4-4'};
const icon=name=>`<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[name]||paths.creations}"/></svg>`;
const tabLabel=id=>({chat:'Chat',photos:'Photos',journals:'Journal',now:'Home'}[id])||(TABS.find(t=>t[0]===id)?.[1])||({'image-studio':'Image studio','voice':'Voice studio','local-models':'Local models','companion-edit':'Edit companion'}[id])||id;
/* ---------------------------------------------------------------- navigation
   One destination map drives three surfaces: the desktop rail, the mobile
   bottom bar (whichever destinations the person pinned), and the More
   directory. Anything added here appears in all three. */
const primaryDestinations=['now','chat','photos','journals'];
const navGroups=[
  ['Life & memories', ['identity','timeline','relationship','knows','loops','creations','vault']],
  ['Studios',         ['image-studio','voice','local-models']],
  ['Setup & system',  ['settings','roster']]
];
/* One line each, so the More page explains itself without being read twice. */
const navBlurb={
  now:'Today at a glance',chat:'Talk with your companion',timeline:'Their day, hour by hour',
  photos:'Every picture and album',journals:'The reflections they write',
  creations:'Files and things they have made',relationship:'Feelings, milestones and repair',
  loops:'Tasks, plans and open threads',knows:'What they remember about you',
  vault:'Shared notes and documents',identity:'Who they are — persona and soul',
  settings:'Companion, app and Hermes — all in one place',roster:'All of your companions',
  'image-studio':'Compose and generate images',voice:'Voice, speech and cloning',
  'local-models':'Run models on your own hardware'
};
/* The bottom bar has room for one word. */
const navShort={now:'Home',chat:'Chat',timeline:'Timeline',photos:'Photos',journals:'Journal',
  creations:'Files',relationship:'Together',loops:'Tasks',knows:'Memory',vault:'Vault',
  identity:'Identity',settings:'Settings',roster:'Companions',
  'image-studio':'Images',voice:'Voice','local-models':'Models',more:'More'};
const shortLabel=id=>navShort[id]||tabLabel(id);
const navDestinations=[...primaryDestinations,...navGroups.flatMap(([,ids])=>ids)];
const navigationButtons=ids=>ids.map(id=>`<button data-tab="${id}">${icon(id)}<span>${esc(tabLabel(id))}</span></button>`).join('');

/* Desktop rail: Core primary section is always visible and prominent; secondary groups are collapsible. */
$('tabs').innerHTML=`<div class="nav-primary-section">${navigationButtons(primaryDestinations)}</div>`+
  navGroups.map(([label,ids],i)=>`<details class="nav-group-collapsible" ${i<1?'open':''}><summary>${esc(label)}</summary><div class="nav-group-items">${navigationButtons(ids)}</div></details>`).join('');
for(const button of $('tabs').querySelectorAll('button'))button.onclick=()=>showTab(button.dataset.tab);

/* The review count and the update notice. Both belong to the workspace rather
   than to any one page, so they are drawn wherever the layout has room and are
   refreshed as you move around rather than only when Home happens to render. */
let reviewState={problems:0,update:null,setupPending:[],agentName:''},reviewCheckedAt=0,reviewChecking=false;
function setReviewBanner(problems,updateInfo,setupPending=[],agentName=''){
  reviewState={
    problems:problems|0,
    update:updateInfo||reviewState.update,
    setupPending:setupPending||reviewState.setupPending||[],
    agentName:agentName||reviewState.agentName||''
  };
  reviewCheckedAt=Date.now();
  paintReviewBanner();
}
function paintReviewBanner(){
  const {problems,update,setupPending,agentName}=reviewState;
  const isDismissed=localStorage.getItem('dismiss_setup_'+(agentName||'default'))==='true';
  const html=problems
    ? `<button class="link-button small" id="header-health" style="color:var(--bad)"><span aria-hidden="true">⚠️</span> ${problems} item${problems===1?'':'s'} to review</button>`
    : (update?.has_update
      ? `<button class="link-button small" id="header-update" style="color:var(--warn)">✨ Update v${esc(update.latest_version)} available</button>`
      : (!isDismissed && setupPending && setupPending.length>0
        ? `<button class="link-button small" id="header-finish-setup" style="color:var(--accent);font-weight:600"><span aria-hidden="true">✨</span> Finish setting up ${esc(agentName||'your companion')} (${setupPending.length} remaining) →</button>`:''));
  for(const host of document.querySelectorAll('#banner,#home-banner')){
    host.innerHTML=html;
    const health=host.querySelector('#header-health'),upd=host.querySelector('#header-update'),fin=host.querySelector('#header-finish-setup');
    if(health)health.onclick=()=>openSettings(null,'diagnostics');
    if(upd)upd.onclick=()=>openSettings(null,'updates');
    if(fin)fin.onclick=()=>openFinishCustomizingDialog();
  }
}
async function refreshReviewBanner(){
  if(reviewChecking||Date.now()-reviewCheckedAt<30000)return paintReviewBanner();
  reviewChecking=true;
  try{
    const d=await api('/overview');
    reviewState.problems=(d.problems||[]).length;
    reviewState.setupPending=d.setup_pending||[];
    reviewState.agentName=d.agent||'';
    reviewCheckedAt=Date.now();
    paintReviewBanner();
  }catch(error){/* leave the last known count in place */}
  finally{reviewChecking=false;}
}

async function openFinishCustomizingDialog(){
  if(!await confirmEditorLeave('dialog'))return;
  const agentName=reviewState.agentName||$('who')?.textContent||'your companion';
  dialog('Finish Setting Up '+agentName, '<p class="dim" style="text-align:center;padding:24px 0">Loading preferences…</p>');
  try{
    const [s,v]=await Promise.all([
      api('/settings').catch(()=>({})),
      api('/voice').catch(()=>({}))
    ]);
    const tts=v.tts||{};
    const currentProvider=tts.provider||'edge';
    const currentVoice=tts[currentProvider]?.voice||tts[currentProvider]?.voice_id||'';
    const currentStyle=s.image_style||'none';
    const hasTimeline=Boolean(s.image_timeline);
    const loc=s.location||'';
    const activeSensors=s.sensors||[];
    const availSensors=s.available_sensors||{
      battery_level:'Battery level & charging status',
      ambient_light:'Daylight & ambient lux',
      step_motion:'Steps & device motion',
      device_time:'Local circadian time'
    };

    const html=`
      <div class="finish-customizing-container" style="display:flex;flex-direction:column;gap:18px;padding:4px 0">
        <p class="dim" style="margin:0">Give <strong>${esc(agentName)}</strong> a voice, visual style, and ambient senses. You can configure them now or adjust anytime in Settings.</p>

        <!-- 1. Voice -->
        <div class="card" style="padding:16px;border-radius:12px;background:var(--panel);border:1px solid var(--surface-3)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h3 style="margin:0;display:flex;align-items:center;gap:8px;font-size:15px"><span>🎙️</span> Spoken Voice</h3>
            <button type="button" class="link-button small" id="fin-deep-voice">Open Voice Studio →</button>
          </div>
          <p class="small dim" style="margin:0 0 10px">Choose the speech engine for voice replies and spoken previews.</p>
          <div class="form-grid">
            <label>Speech Engine
              <select id="fin-voice-engine">
                ${options([
                  ['edge','Edge (Online · Free, instant)'],
                  ['openai','OpenAI Audio'],
                  ['xai','xAI / Grok Voice'],
                  ['elevenlabs','ElevenLabs'],
                  ['piper','Piper (Local offline)'],
                  ['kittentts','KittenTTS (Local offline)']
                ], currentProvider)}
              </select>
            </label>
            <label>Voice / Pitch
              <input id="fin-voice-name" value="${esc(currentVoice)}" placeholder="Default voice (or custom voice ID)">
            </label>
          </div>
          <div style="margin-top:10px;display:flex;align-items:center;gap:10px">
            <button type="button" class="quiet small" id="fin-voice-test">🔊 Test Voice Preview</button>
            <span class="dim small" id="fin-voice-status"></span>
          </div>
        </div>

        <!-- 2. Images & Camera -->
        <div class="card" style="padding:16px;border-radius:12px;background:var(--panel);border:1px solid var(--surface-3)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h3 style="margin:0;display:flex;align-items:center;gap:8px;font-size:15px"><span>📸</span> Visual Style & Camera</h3>
            <button type="button" class="link-button small" id="fin-deep-photos">Photo Settings →</button>
          </div>
          <p class="small dim" style="margin:0 0 10px">Aesthetic portrait style for photo sessions and visual messages.</p>
          <div class="form-grid">
            <label>Portrait Art Style
              <select id="fin-image-style">
                ${options(Object.entries(s.image_styles||{
                  none:'None (Text only)',
                  realistic:'Photorealistic portrait',
                  anime:'Anime & Manga style',
                  cinematic:'Cinematic 3D render',
                  painting:'Digital illustration / Painting'
                }), currentStyle)}
              </select>
            </label>
            <label style="display:flex;align-items:center;gap:8px;margin-top:24px;cursor:pointer">
              <input type="checkbox" id="fin-image-timeline" ${hasTimeline?'checked':''}>
              <span>Enable 15-minute background photo timeline</span>
            </label>
          </div>
        </div>

        <!-- 3. Sensors & Awareness -->
        <div class="card" style="padding:16px;border-radius:12px;background:var(--panel);border:1px solid var(--surface-3)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
            <h3 style="margin:0;display:flex;align-items:center;gap:8px;font-size:15px"><span>🌐</span> Location & Passive Senses</h3>
            <button type="button" class="link-button small" id="fin-deep-awareness">Awareness Settings →</button>
          </div>
          <p class="small dim" style="margin:0 0 10px">Grounds ${esc(agentName)} in your real-world timezone, weather, and activity.</p>
          <div class="form-grid">
            <label style="grid-column:1/-1">Your City / Location
              <input id="fin-location" value="${esc(loc)}" placeholder="e.g. Raleigh, NC or Tokyo, Japan">
              <small class="dim">Used for local weather, sunlight times, and seasonal shifts.</small>
            </label>
          </div>
          <div style="margin-top:10px">
            <strong class="small" style="display:block;margin-bottom:6px">Active Hardware Sensors:</strong>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px">
              ${Object.entries(availSensors).map(([k,label])=>`
                <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer">
                  <input type="checkbox" data-fin-sensor="${esc(k)}" ${activeSensors.includes(k)?'checked':''}>
                  <span>${esc(k.replaceAll('_',' '))}</span>
                </label>
              `).join('')}
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding-top:14px;border-top:1px solid var(--edge)">
          <button type="button" class="link-button small dim" id="fin-dismiss-never">Don’t show this again</button>
          <div style="display:flex;gap:10px">
            <button type="button" class="quiet" id="fin-dismiss-later">Later</button>
            <button type="button" class="act" id="fin-save" style="padding:10px 24px">Save & Apply</button>
          </div>
        </div>
      </div>
    `;

    dialog('Finish Setting Up '+agentName, html);

    // Deep links
    $('fin-deep-voice').onclick=()=>{ $('product-dialog').close(); openSettings(null, 'connect-voice'); };
    $('fin-deep-photos').onclick=()=>{ $('product-dialog').close(); openSettings(null, 'photos'); };
    $('fin-deep-awareness').onclick=()=>{ $('product-dialog').close(); openSettings(null, 'awareness'); };

    // Voice test preview
    $('fin-voice-test').onclick=async()=>{
      const status=$('fin-voice-status');
      status.textContent='Generating sample…';
      try{
        const r=await api('/voice/preview',{
          method:'POST',
          headers:{'content-type':'application/json'},
          body:JSON.stringify({text:`Hello! I am happy to be chatting with you.`})
        });
        status.textContent='Playing…';
        const audio=new Audio((r.audio||'/api/voice/preview-audio')+'?t='+Date.now());
        audio.play().catch(()=>{});
        audio.onended=()=>{ status.textContent='Done.'; };
      }catch(e){
        status.textContent='Preview unavailable: '+(e.message||'error');
      }
    };

    // Save and dismiss handlers
    $('fin-dismiss-later').onclick=()=>{ $('product-dialog').close(); };
    $('fin-dismiss-never').onclick=()=>{
      localStorage.setItem('dismiss_setup_'+(agentName||'default'), 'true');
      $('product-dialog').close();
      paintReviewBanner();
      notice('Banner dismissed.');
    };

    $('fin-save').onclick=async()=>{
      const btn=$('fin-save');
      btn.disabled=true;
      btn.textContent='Saving…';
      try{
        const selectedSensors=[...document.querySelectorAll('[data-fin-sensor]:checked')].map(el=>el.dataset.finSensor);
        await saveSettings({
          location:$('fin-location').value.trim(),
          sensors:selectedSensors,
          image_style:$('fin-image-style').value,
          image_timeline:$('fin-image-timeline').checked
        });

        const provider=$('fin-voice-engine').value;
        const voiceName=$('fin-voice-name').value.trim();
        await api('/voice',{
          method:'POST',
          headers:{'content-type':'application/json'},
          body:JSON.stringify({provider,voice:voiceName})
        }).catch(()=>{});

        localStorage.setItem('dismiss_setup_'+(agentName||'default'), 'true');
        reviewState.setupPending=[];
        paintReviewBanner();
        $('product-dialog').close();
        notice(`Customizations applied! ${agentName} is fully tuned.`);
      }catch(err){
        alert('Could not save customizations: '+(err.message||err));
        btn.disabled=false;
        btn.textContent='Save & Apply';
      }
    };

  }catch(err){
    dialog('Finish Setting Up '+agentName, `<p class="bad">Error loading settings: ${esc(err.message)}</p>`);
  }
}
window.openFinishCustomizingDialog=openFinishCustomizingDialog;

/* Mobile bottom bar. Home holds the left corner and More the right; between
   them are up to four slots the person chooses, so nothing they rely on is ever
   more than one tap away and the two fixed ends never move. */
const NAV_FREE_SLOTS=4;
const navPins=()=>{
  const saved=(window.Appearance&&window.Appearance.state.nav_pins)||[];
  const chosen=saved.filter(id=>id!=='now'&&id!=='more'&&navDestinations.includes(id));
  // An older setting counted Home as one of the four. Dropping it here just
  // frees the slot it used to occupy.
  return chosen.slice(0,NAV_FREE_SLOTS);
};
function renderTabbar(){
  const bar=$('tabbar');if(!bar)return;
  const slots=[['now',true],...navPins().map(id=>[id,false]),['more',true]];
  bar.innerHTML=slots.map(([id,fixed])=>`<button data-tab="${id}"${fixed?' class="is-fixed"':''} aria-current="${String(current===id)}">${icon(id)}<span>${esc(shortLabel(id))}</span></button>`).join('');
  for(const b of bar.querySelectorAll('button'))b.onclick=()=>showTab(b.dataset.tab);
}
window.addEventListener('appearance-change',renderTabbar);

window.productNavigate=name=>{
  document.body.dataset.page=name;
  for(const el of document.querySelectorAll('[data-creating]'))delete el.dataset.creating;
  const tabs=$('tabs');
  if(tabs){const parent=tabs.querySelector(`details:has([data-tab="${name}"])`);if(parent)parent.open=true;}
  if($('crumb-page'))$('crumb-page').textContent=tabLabel(name);
  refreshReviewBanner();
  if($('crumb-agent'))$('crumb-agent').textContent=$('who')?.textContent||'Companion';
  document.body.classList.remove('menu-open');
  for(const b of $('tabs').querySelectorAll('button[data-tab]'))b.setAttribute('aria-current',String(b.dataset.tab===name));
  renderTabbar();syncNavigation();window.scrollTo({top:0});
};
const compactLayout=matchMedia('(max-width:900px)');
function syncNavigation(){
  const open=document.body.classList.contains('menu-open');
  document.querySelector('header').inert=compactLayout.matches&&!open;
  if($('mobile-menu'))$('mobile-menu').setAttribute('aria-expanded',String(open));
  if($('navigation-backdrop'))$('navigation-backdrop').hidden=!compactLayout.matches||!open;
}
if($('mobile-menu'))$('mobile-menu').onclick=()=>{document.body.classList.toggle('menu-open');syncNavigation();};
if($('navigation-backdrop'))$('navigation-backdrop').onclick=()=>{document.body.classList.remove('menu-open');syncNavigation();};
compactLayout.addEventListener('change',()=>{syncNavigation();renderTabbar();});
syncNavigation();renderTabbar();

/* The More directory: every destination, with pin controls for the bar. */
workspaceHandlers.more=async()=>{
  const pins=navPins();
  const row=id=>{
    if(id==='now')return '';
    const pinned=pins.includes(id),full=pins.length>=NAV_FREE_SLOTS;
    return `<div class="more-row${pinned?' is-pinned':''}">
      <button class="more-go" data-tab="${id}">${icon(id)}<span><strong>${esc(tabLabel(id))}</strong><small>${esc(navBlurb[id]||'')}</small></span></button>
      <button class="pin-toggle" data-pin="${id}" aria-pressed="${String(pinned)}" ${!pinned&&full?'disabled':''}
        title="${pinned?'Remove from the bottom bar':(full?'Unstar something first \u2014 the bar holds four':'Add to the bottom bar')}"
        aria-label="${pinned?'Unpin '+tabLabel(id):'Pin '+tabLabel(id)+' to the bottom bar'}">${pinned?'★':'☆'}</button>
    </div>`;
  };
  const allNavGroups=[
    ['Core pages', primaryDestinations],
    ...navGroups
  ];
  const HINT_KEY='bottom-bar-hint-dismissed';
  let hintSeen=false;
  try{hintSeen=localStorage.getItem(HINT_KEY)==='1';}catch(error){hintSeen=false;}
  const hint=hintSeen?'':`<div class="more-hint" id="more-hint">
      <div>
        <strong>The bottom bar is yours</strong>
        <p class="dim small">Star anything below and it appears on the bar; unstar it and it goes.
        Home and More keep the two ends, leaving four slots in between.</p>
      </div>
      <button class="icon-button" id="more-hint-close" aria-label="Got it, hide this">\u2715</button>
    </div>`;
  $('more').innerHTML=heading('More','Every part of the workspace.')+hint+
    allNavGroups.map(([label,ids])=>{
      const rows=ids.map(row).join('');
      return rows.trim()?`<section class="more-group"><h2>${esc(label)}</h2><div class="more-list">${rows}</div></section>`:'';
    }).join('');
  if($('more-hint-close'))$('more-hint-close').onclick=()=>{
    try{localStorage.setItem(HINT_KEY,'1');}catch(error){}
    $('more-hint').remove();
  };
  for(const b of $('more').querySelectorAll('[data-tab]'))b.onclick=()=>showTab(b.dataset.tab);
  for(const b of $('more').querySelectorAll('[data-pin]'))b.onclick=async()=>{
    const id=b.dataset.pin,next=pins.includes(id)?pins.filter(x=>x!==id):[...pins,id];
    if(next.length>NAV_FREE_SLOTS){notice('The bar holds four. Unstar one first.');return;}
    await window.Appearance.set({nav_pins:next});
    render('more');
  };
};
if($('refresh-page'))$('refresh-page').onclick=async()=>{if(await confirmEditorLeave(current))render(current);};
function openCompanionSwitchDialog(){
  const list=roster||[];
  dialog('Switch Companion',`
    <div class="companion-switch-modal-list" style="display:flex;flex-direction:column;gap:10px;padding:4px 0">
      ${list.map(p=>{
        const isCurrent=p.id===PROFILE;
        const initial=(p.name||p.id||'C').charAt(0).toUpperCase();
        return `
          <div class="companion-switch-item card" data-profile-id="${esc(p.id)}" style="margin:0;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;gap:14px;cursor:pointer;border-color:${isCurrent?'var(--accent)':'var(--edge)'};background:${isCurrent?'var(--accent-soft)' : 'var(--surface-2)'};transition:all .15s">
            <div style="display:flex;align-items:center;gap:12px">
              <div class="profile-avatar-pill" style="width:38px;height:38px;font-size:16px;border-radius:10px">${initial}</div>
              <div>
                <strong style="font-size:15px;color:var(--ink);display:block">${esc(p.name||p.id)}</strong>
                <span class="dim small">${isCurrent?'Current companion':(p.installed?'Ready to spend time with':'Profile available')}</span>
              </div>
            </div>
            <div>
              ${isCurrent?'<span class="pill status-good" style="font-weight:600">Active</span>':'<button type="button" class="act small">Select</button>'}
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `);
  for(const item of $('dialog-body').querySelectorAll('[data-profile-id]')){
    item.onclick=async()=>{
      const pid=item.dataset.profileId;
      $('product-dialog').close();
      if(pid!==PROFILE){
        navigateProfile(pid,'now');
      }
    };
  }
}
if($('companion-switch-trigger'))$('companion-switch-trigger').onclick=openCompanionSwitchDialog;
$('close-dialog').onclick=async()=>{if(await confirmEditorLeave('dialog'))$('product-dialog').close();};
$('product-dialog').addEventListener('cancel',async e=>{e.preventDefault();if(await confirmEditorLeave('dialog'))$('product-dialog').close();});
function dialog(title,html){$('dialog-title').textContent=title;$('dialog-body').innerHTML=html;if(!$('product-dialog').open)$('product-dialog').showModal();}
$('open-search').onclick=async()=>{if(!await confirmEditorLeave('dialog'))return;dialog('Go to page',`<input id="command-search" aria-label="Find a page" placeholder="Photos, providers, memories…"><div id="command-results" class="search-results"></div>`);const update=()=>{$('command-results').innerHTML=TABS.filter(t=>t[0]!=='more').filter(t=>(t[1]+' '+t[0]+' '+({knows:'facts memories',vault:'files notes',settings:'preferences contact quiet hours relationship awareness sensors network pin appearance updates diagnostics hermes providers models gateway credentials cron jobs schedules comfyui voice','image-studio':'images workflows','voice':'audio cloning speech','local-models':'local models llama gguf hardware vulkan server'}[t[0]]||'')).toLowerCase().includes($('command-search').value.toLowerCase())).map(([id,label])=>`<button class="quiet" data-go="${id}">${icon(id)}${label}</button>`).join('');for(const b of $('command-results').querySelectorAll('button'))b.onclick=()=>{$('product-dialog').close();showTab(b.dataset.go);};};$('command-search').oninput=update;update();$('command-search').focus();};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();$('open-search').click();}});
let profileTimezone;
const stamp=(value,opts={})=>{if(!value)return 'Not recorded';const d=new Date(value);return Number.isNaN(d.getTime())?value:new Intl.DateTimeFormat(undefined,{timeZone:profileTimezone,month:'short',day:'numeric',...opts}).format(d);};
const dayKey=value=>{if(!value)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;try{return new Intl.DateTimeFormat('en-CA',{timeZone:profileTimezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));}catch{return '';}};
const when=value=>stamp(value,{hour:'numeric',minute:'2-digit'});
const plain=value=>String(value||'').replace(/<!--[^]*?-->/g,'').replace(/[#*_`>\[\]]/g,'').trim();
const excerpt=(value,n=180)=>{const text=plain(value);return text.length>n?text.slice(0,n).replace(/\s+\S*$/,'')+'…':text;};
const empty=(symbol,title,body,button='')=>`<div class="empty-state">${icon(symbol)}<h3>${esc(title)}</h3><p>${esc(body)}</p>${button}</div>`;
/* A link to another page. `panel` names a panel of the Settings page, which
   is one page with many panels rather than a page of its own. */
const jump=(id,label,primary=false,panel='')=>`<button class="${primary?'act':'link-button'}" data-route="${id}"${panel?` data-settings-panel="${panel}"`:''}>${esc(label)} ${icon(id)}</button>`;
function wireRoutes(root){
  for(const b of root.querySelectorAll('[data-route]'))
    b.onclick=()=>{if(b.dataset.settingsPanel)return openSettings(null,b.dataset.settingsPanel);showTab(b.dataset.route);};
  for(const b of root.querySelectorAll('[data-settings-panel]:not([data-route])'))
    b.onclick=()=>openSettings(null,b.dataset.settingsPanel);
}
function richText(raw){
  // Escape raw HTML first. Never execute HTML or fetch remote images in authored notes.
  let source=String(raw||'').replace(/<!--[^]*?-->/g,'');
  const inline=s=>esc(s).replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>').replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return source.split(/\n{2,}/).map(block=>{if(block.startsWith('```'))return `<pre><code>${esc(block.replace(/^```[^\n]*\n/,'').replace(/\n```\s*$/,''))}</code></pre>`;if(/^#{1,6}\s/.test(block)){const lines=block.split('\n'),h=lines.shift().replace(/^#+\s/,'');return `<h3>${inline(h)}</h3>${lines.length?`<p>${inline(lines.join('\n'))}</p>`:''}`;}if(/^> /.test(block))return `<blockquote>${inline(block.replace(/^> /gm,''))}</blockquote>`;if(/^(?:[-*] |\d+\. )/.test(block))return '<ul>'+block.split('\n').map(l=>'<li>'+inline(l.replace(/^(?:[-*] |\d+\. )/,''))+'</li>').join('')+'</ul>';return '<p>'+inline(block).replace(/\n/g,'<br>')+'</p>';}).join('');
}

function isBlacklistedUndergarment(item){
  if(!item)return false;
  const str=typeof item==='string'?item:((item.description||'')+' '+(item.id||''));
  return /\b(panties|panty|thong|thongs|lingerie|underpants|undies|boxers|boxer|briefs|brief)\b/i.test(str);
}

function isIntimateGarment(item){
  if(!item)return false;
  const str=typeof item==='string'?item:((item.description||'')+' '+(item.id||''));
  if(/\bsports[\s_-]?bra\b/i.test(str))return false;
  return /\b(panties|panty|bra|bras|bralette|underwear|undergarment|undergarments|boxers|boxer|briefs|brief|thong|thongs|lingerie|underpants|undies)\b/i.test(str);
}

/* What part of an outfit a garment is, for display only. These emoji never
   reach an image prompt: prompts are built server-side from item.description,
   which this does not touch.

   Matching order is not display order. "low-top canvas sneakers" contains
   "top", so footwear has to be recognised before tops are; the list people
   read is ordered head down. */
const WARDROBE_SLOTS=[
  ['hat','\u{1F9E2}','Hat'],
  ['jewelry','\u{1F48D}','Jewelry'],
  ['top','\u{1F455}','Top'],
  ['undies','\u{1FA72}','Undies'],
  ['bottom','\u{1F456}','Bottom'],
  ['sock','\u{1F9E6}','Sock'],
  ['shoes','\u{1F45F}','Shoes'],
  ['additional','\u{1F9E5}','Additional']];
const SLOT_WORDS=[
  ['jewelry',/necklace|earring|\bring\b|bracelet|anklet|pendant|chain|brooch|\bwatch\b/i],
  ['shoes',/sneaker|shoe|boot|sandal|heel|loafer|trainer|slipper|flip.?flop|\bflats\b/i],
  ['sock',/\bsocks?\b|stocking|tights|hosiery|legwarmer/i],
  // A sports bra is worn as an athletic top, and the stage filter already
  // treats it as one; classifying it as underwear would contradict that.
  ['top',/sports bra|athletic bra/i],
  ['undies',/panti|knicker|thong|briefs|boxer|underwear|\bbra\b|bralette|lingerie|boyshort/i],
  ['bottom',/legging|jeans|trouser|\bpants\b|shorts|skirt|jogger|sweatpant|chino|capri|slacks/i],
  // "cap sleeves" is a tee and "hooded" is usually a jacket, so neither word
  // is trusted on its own.
  ['hat',/\bhat\b|\bcap\b(?!\s*sleeve)|beanie|headband|visor|bandana|\bberet\b/i],
  ['top',/\btop\b|shirt|\btee\b|blouse|sweater|hoodie|tank|cami|jumper|jersey|sweatshirt|bodysuit|dress|pullover/i],
  ['additional',/jacket|coat|cardigan|scarf|belt|\bbag\b|glasses|glove|shawl|vest|blazer/i]];

function wardrobeSlot(item){
  const text=typeof item==='string'?item:`${item?.category||''} ${item?.id||''} ${item?.description||''}`;
  for(const [slot,pattern] of SLOT_WORDS)if(pattern.test(text))return slot;
  return 'additional';
}
const slotIcon=slot=>(WARDROBE_SLOTS.find(s=>s[0]===slot)||WARDROBE_SLOTS[7])[1];
const slotLabel=slot=>(WARDROBE_SLOTS.find(s=>s[0]===slot)||WARDROBE_SLOTS[7])[2];
const bySlot=items=>{
  const rank=Object.fromEntries(WARDROBE_SLOTS.map(([slot],i)=>[slot,i]));
  return [...(items||[])].sort((a,b)=>rank[wardrobeSlot(a)]-rank[wardrobeSlot(b)]);
};
/* One chip: what state it is in, what part of the outfit it is, then the
   garment itself. */
const wardrobeChip=(item,cls,state,prefix='')=>{
  const text=typeof item==='string'?item:(item.description||item.id||'');
  const slot=wardrobeSlot(item);
  return `<span class="wardrobe-chip ${cls}" title="${esc(prefix)}${esc(slotLabel(slot))} \u00b7 ${esc(text)}">`+
    `${state} <span class="wardrobe-slot" aria-hidden="true">${slotIcon(slot)}</span> ${esc(text)}</span>`;
};

function filterWardrobeItems(items,stage=0){
  if(stage>=4)return items||[];
  if(stage>=2)return (items||[]).filter(it=>!isBlacklistedUndergarment(it));
  return (items||[]).filter(it=>!isIntimateGarment(it));
}

function renderWardrobeCard(closet,s,stage=0){
  const filterG=list=>filterWardrobeItems(list,stage);
  const wearing=filterG(closet?.wearing||s?.outfit||[]);
  const laidOut=closet?.laid_out;
  const laidOutItems=filterG(laidOut?.items);
  const hamper=filterG(closet?.hamper);
  const washing=filterG(closet?.washing);
  const clean=filterG(closet?.clean);
  const laundry=closet?.laundry_in_progress;
  let html=`<div class="card wardrobe-card"><div class="section-subheading" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px"><span class="eyebrow">Wardrobe & Care</span>${laundry?'<span class="pill is-washing" style="font-size:11px">🧺 Laundry running</span>':''}</div>`;
  html+=`<div class="wardrobe-block"><div class="wardrobe-block-title"><span>Currently Wearing</span><span class="dim small">${wearing.length} piece${wearing.length===1?'':'s'}</span></div><div class="wardrobe-chip-list">${bySlot(wearing).map(w=>wardrobeChip(w,'is-wearing','\u{1F464}')).join('')||'<span class="dim small">Casual wear</span>'}</div></div>`;
  if(laidOut&&(laidOutItems.length||laidOut.plan?.intent)){
    const plan=laidOut.plan||{};
    html+=`<div class="wardrobe-block" style="border-left:3px solid var(--warn);margin-top:12px"><div class="wardrobe-block-title"><span style="color:var(--warn)">✨ Laid Out For Tomorrow</span><span class="dim small">${laidOutItems.length} pieces</span></div>${laidOutItems.length?`<div class="wardrobe-chip-list">${bySlot(laidOutItems).map(w=>wardrobeChip(w,'is-laid-out','\u{1F6CF}\uFE0F','Laid out \u00b7 ')).join('')}</div>`:''}${plan.intent?`<div class="laid-out-intent-quote">“${esc(plan.intent)}”</div>`:''}</div>`;
  }
  if(hamper.length||washing.length){
    html+=`<details class="wardrobe-block" style="cursor:pointer;margin-top:12px"><summary class="wardrobe-block-title"><span>Hamper & Wash (Dirty Clothes)</span><span class="dim small">${hamper.length} dirty${washing.length?` · ${washing.length} in wash`:''}</span></summary><div class="wardrobe-chip-list" style="margin-top:8px">${bySlot(washing).map(w=>wardrobeChip(w,'is-washing','\u{1FAE7}','In the wash \u00b7 ')).join('')}${bySlot(hamper).map(w=>wardrobeChip(w,'is-hamper','\u{1F9FA}','In the hamper \u00b7 ')).join('')}</div></details>`;
  } else {
    html+=`<details class="wardrobe-block" style="cursor:pointer;margin-top:12px"><summary class="wardrobe-block-title"><span>Hamper & Wash (Dirty Clothes)</span><span class="dim small">0 dirty</span></summary><div class="dim small" style="margin-top:8px">🧺 Hamper is empty · All clothes are clean.</div></details>`;
  }
  if(clean.length){
    html+=`<details class="wardrobe-block" style="cursor:pointer;margin-top:12px"><summary class="wardrobe-block-title"><span>Clean in Closet</span><span class="dim small">${clean.length} piece${clean.length===1?'':'s'}</span></summary><div class="wardrobe-chip-list" style="margin-top:8px">${bySlot(clean).map(w=>wardrobeChip(w,'is-clean','\u2728','Clean \u00b7 ')).join('')}</div></details>`;
  }
  html+=`</div>`;
  return html;
}

let calYear=new Date().getFullYear(),calMonth=new Date().getMonth(),selectedCalDate=null;

function buildCalendarHtml(agentName,missions,prefix='cal'){
  const monthNames=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const monthTitle=`${monthNames[calMonth]} ${calYear}`;

  const firstDayIndex=new Date(calYear,calMonth,1).getDay();
  const daysInMonth=new Date(calYear,calMonth+1,0).getDate();
  const todayStr=new Date().toISOString().slice(0,10);
  selectedCalDate=selectedCalDate||todayStr;

  let calendarCellsHtml='';
  for(let i=0;i<firstDayIndex;i++){
    calendarCellsHtml+=`<div class="calendar-cell is-other-month"></div>`;
  }
  for(let day=1;day<=daysInMonth;day++){
    const dayStr=`${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    const isToday=dayStr===todayStr;
    const isSelected=dayStr===selectedCalDate;
    const dayMissions=missions.filter(x=>x.wanted_by===dayStr);

    calendarCellsHtml+=`
      <div class="calendar-cell ${isToday?'is-today':''} ${isSelected?'is-selected':''}" data-${prefix}-date="${esc(dayStr)}">
        <span class="calendar-cell-date">${day}</span>
        <div class="calendar-indicators">
          ${dayMissions.length?`<span class="cal-badge-pill" title="${esc(dayMissions.map(x=>x.title).join(', '))}">${dayMissions.length} event${dayMissions.length===1?'':'s'}</span>`:''}
        </div>
      </div>`;
  }

  const selectedDayMissions=missions.filter(x=>x.wanted_by===selectedCalDate);

  return `
  <div class="card calendar-card" id="${prefix}-card">
    <div class="calendar-top-bar">
      <div class="calendar-nav-group">
        <button class="icon-button" id="${prefix}-prev" aria-label="Previous month">←</button>
        <h2 class="calendar-month-title">${esc(monthTitle)}</h2>
        <button class="icon-button" id="${prefix}-next" aria-label="Next month">→</button>
        <button class="quiet small" id="${prefix}-today">Today</button>
      </div>
      <div class="actions" style="margin:0">
        <a class="quiet small" href="/api/calendar.ics" download="${esc(agentName)}-calendar.ics" style="text-decoration:none">📅 Export iCal (.ics)</a>
      </div>
    </div>

    <div class="calendar-grid">
      <div class="calendar-day-head">Sun</div>
      <div class="calendar-day-head">Mon</div>
      <div class="calendar-day-head">Tue</div>
      <div class="calendar-day-head">Wed</div>
      <div class="calendar-day-head">Thu</div>
      <div class="calendar-day-head">Fri</div>
      <div class="calendar-day-head">Sat</div>
      ${calendarCellsHtml}
    </div>

    <div class="calendar-selected-day-pane">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
        <strong>Events & commitments for ${esc(selectedCalDate)}</strong>
        <span class="pill">${selectedDayMissions.length} scheduled</span>
      </div>
      ${selectedDayMissions.length?`
      <div class="cal-events-list" style="margin-top:10px;display:flex;flex-direction:column;gap:8px">
        ${selectedDayMissions.map(x=>`
          <div class="cal-event-row" style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:var(--surface);border:1px solid var(--edge);border-radius:8px">
            <div>
              <strong style="color:var(--ink)">${esc(x.title)}</strong>
              ${x.detail?`<p style="margin:2px 0 0;color:var(--dim);font-size:13px">${esc(x.detail)}</p>`:''}
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="pill ${x.status==='open'?'status-good':x.status==='dropped'?'status-bad':''}">${esc(x.status)}</span>
              ${x.status==='open'?`<button class="quiet small-btn" data-${prefix}-drop="${esc(x.id)}">Drop</button>`:''}
            </div>
          </div>`).join('')}
      </div>`:
      '<p class="dim small" style="margin:8px 0 0">No events or commitments on this date.</p>'
      }
      <div class="cal-add-event-box" style="margin-top:14px;padding-top:12px;border-top:1px solid var(--edge)">
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input id="${prefix}-new-title" placeholder="Add event for this day…" style="flex:1;min-width:180px;padding:8px 12px;font-size:13px">
          <button class="act small" id="${prefix}-add-btn">Add Event</button>
        </div>
      </div>
    </div>
  </div>`;
}

function wireCalendarComponent(root,missions,agentName,refreshFn,prefix='cal'){
  const prevBtn=$(prefix+'-prev'),nextBtn=$(prefix+'-next'),todayBtn=$(prefix+'-today');
  if(prevBtn)prevBtn.onclick=async()=>{
    calMonth--;
    if(calMonth<0){calMonth=11;calYear--;}
    await refreshFn();
  };
  if(nextBtn)nextBtn.onclick=async()=>{
    calMonth++;
    if(calMonth>11){calMonth=0;calYear++;}
    await refreshFn();
  };
  if(todayBtn)todayBtn.onclick=async()=>{
    calYear=new Date().getFullYear();
    calMonth=new Date().getMonth();
    selectedCalDate=new Date().toISOString().slice(0,10);
    await refreshFn();
  };
  for(const cell of root.querySelectorAll(`[data-${prefix}-date]`)){
    cell.onclick=async()=>{
      selectedCalDate=cell.getAttribute(`data-${prefix}-date`);
      await refreshFn();
    };
  }
  for(const b of root.querySelectorAll(`[data-${prefix}-drop]`)){
    b.onclick=async()=>{
      b.disabled=true;
      try{
        await action('/missions/'+b.getAttribute(`data-${prefix}-drop`)+'/drop');
        notice('Event dropped.');
        await refreshFn();
      }catch(err){notice('Failed to drop: '+err.message);b.disabled=false;}
    };
  }
  const addBtn=$(prefix+'-add-btn');
  if(addBtn){
    addBtn.onclick=async()=>{
      const titleInput=$(prefix+'-new-title');
      const title=(titleInput?.value||'').trim();
      if(!title){notice('Please enter an event title.');return;}
      addBtn.disabled=true;
      try{
        await post('/missions',{
          title,
          detail:'Scheduled from calendar',
          wanted_by:selectedCalDate||new Date().toISOString().slice(0,10),
          status:'open'
        });
        notice('Event saved to shared calendar.');
        await refreshFn();
      }catch(err){notice('Failed to add event: '+err.message);addBtn.disabled=false;}
    };
  }
}

function renderHeroMetersContent(emotions,bars){
  const meters=emotions?.state?.meters||bars?.feelings?.meters||{};
  // Home is a glance and Together is the page, so they keep different
  // treatments — but they must not describe the same meter in different words.
  // The labels and the explanations come from one place; the colour, the glow
  // and the resting value are the hero's own.
  const look={
    warmth:{color:'linear-gradient(90deg,#f43f5e,#fb923c)',glow:'rgba(244,63,94,0.4)',defaultVal:0.8},
    trust:{color:'linear-gradient(90deg,#0ea5e9,#10b981)',glow:'rgba(14,165,233,0.4)',defaultVal:0.75},
    hurt:{color:'linear-gradient(90deg,#ef4444,#f87171)',glow:'rgba(239,68,68,0.4)',defaultVal:0.0},
    irritation:{color:'linear-gradient(90deg,#eab308,#f59e0b)',glow:'rgba(234,179,8,0.4)',defaultVal:0.0},
    longing:{color:'linear-gradient(90deg,#8b5cf6,#d946ef)',glow:'rgba(139,92,246,0.4)',defaultVal:0.0},
  };
  const config=FEELING_METERS.map(([key,label,icon,desc])=>({key,label,icon,desc,...(look[key]||{defaultVal:0})}));
  return config.map(m=>{
    const raw=meters[m.key]!=null?meters[m.key]:m.defaultVal;
    const pct=Math.round(Math.max(0,Math.min(1,raw))*100);
    return `
      <div class="hero-meter-item" title="${esc(m.label)}: ${pct}% · ${esc(m.desc)}" tabindex="0" aria-label="${esc(m.label)} meter: ${pct}%">
        <div class="hero-meter-label-row">
          <span class="hero-meter-label"><span class="meter-icon">${m.icon}</span> <span class="meter-name">${m.label}</span></span>
          <span class="hero-meter-pct">${pct}%</span>
        </div>
        <div class="hero-meter-bar-track">
          <div class="hero-meter-bar-fill" style="width:${pct}%;background:${m.color};box-shadow:0 0 8px ${m.glow}"></div>
        </div>
        <div class="hero-meter-tooltip" role="tooltip">
          <div class="hero-meter-tooltip-title"><span>${m.icon} ${esc(m.label)}</span> <span class="hero-meter-tooltip-val">${pct}%</span></div>
          <div class="hero-meter-tooltip-desc">${esc(m.desc)}</div>
        </div>
      </div>`;
  }).join('');
}

workspaceHandlers.now=async()=>{
  const [d,content,journal,timeline,closet,updateInfo,emotions]=await Promise.all([
    api('/overview'),
    api('/content'),
    api('/journals'),
    api('/timeline'),
    api('/closet').catch(()=>null),
    api('/updates').catch(()=>null),
    api('/feelings').catch(()=>null)
  ]);
  if(current!=='now')return;
  profileTimezone=d.timezone;$('who').textContent=d.agent;if($('crumb-agent'))$('crumb-agent').textContent=d.agent;
  if($('companion-avatar-pill'))$('companion-avatar-pill').outerHTML=
    faceHtml(d.agent,'profile-avatar-pill').replace('class="avatar has-face','id="companion-avatar-pill" class="avatar has-face');
  setReviewBanner(d.problems.length,updateInfo);

  const s=d.state?.state;
  const photo=content.items.find(x=>x.kind==='image');
  const entry=journal.entries[0];
  const stage=Number(emotions?.intimacy?.stage??d.intimacy?.stage??0);
  const wearingPieces=filterWardrobeItems(closet?.wearing||[],stage);
  const rawOutfit=Array.isArray(s?.outfit)?filterWardrobeItems(s.outfit,stage):[];
  const currentOutfit=wearingPieces.map(x=>x.description||x.id).join(', ')||rawOutfit.map(x=>x.description||x.id).join(', ')||(typeof s?.outfit==='string'&&filterWardrobeItems([s.outfit],stage).length?s.outfit:'');
  const chemistry=emotions?.intimacy||d.intimacy||null;
  const feelingBadge=chemistry?.romantic_progression===false?`<span class="chem-stage">${esc(chemistry.connection_label||'Familiarity')}</span>`:chemistry?`<span class="chem-icon" aria-hidden="true">✨</span><span class="chem-stage">${esc(chemistry.stage_badge)}</span><span class="chem-score">${chemistry.score}%</span>`:'';

  let latestThought='';
  let thoughtSource='';
  if(entry?.text){
    const clean=entry.text.replace(/^[#*_`>\s-]+/gm,'').trim();
    const match=clean.match(/.*?[.!?](?:\s|$)/);
    latestThought=match?match[0].trim():clean.slice(0,180);
    thoughtSource=`From ${esc(d.agent)}'s journal · ${esc(entry.day)}`;
  }else if(s?.private_stance){
    latestThought=s.private_stance;
    thoughtSource='Current inner stance';
  }

  $('now').innerHTML=`
  ${updateInfo?.has_update?`<div class="notice-strip" style="border-left-color:var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent)">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;width:100%">
      <div>
        <p style="margin:0"><strong>Tamanitomo v${esc(updateInfo.latest_version)}</strong> is available. (Installed: v${esc(updateInfo.version)})</p>
        <p class="dim small" style="margin:2px 0 0 0">Your companions’ memories, journals, and vault remain completely untouched.</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="act small" data-settings-panel="updates">See what’s new &amp; update</button>
      </div>
    </div>
  </div>`:''}

  <div class="presence-sanctuary">
    <div class="presence-hero-card">
      <div class="presence-grid-container">
        <div class="presence-avatar-column">
          <div class="presence-avatar-frame-tall">
            ${photo?`<img class="presence-avatar-img-tall" ${mediaPrivacy(photo)} src="${mediaUrl(photo.url)}" alt="${esc(d.agent)}">`:`<div class="presence-avatar-placeholder-tall">${esc(d.agent.slice(0,1))}</div>`}
            <span class="presence-pulse-dot" title="Active presence"></span>
          </div>
        </div>

        <div class="presence-identity-column">
          <div class="presence-name-header">
            <h1 class="presence-name">${esc(d.agent)}</h1>
            ${(roster||[]).length>1?`<button type="button" class="quiet small presence-switch" id="presence-switch">\u21c4 Switch</button>`:''}
            <span id="home-banner" class="home-banner"></span>
          </div>

          <div class="presence-status-stack">
            <div class="presence-chip-row"><span class="chip-label">✨ Status:</span> <span class="chip-val">${esc(s?.activity||'Resting quietly')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">📍 Location:</span> <span class="chip-val">${esc(s?.location||'Home')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">💭 Mood:</span> <span class="chip-val">${esc(s?.mood||'Peaceful')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">👗 Attire:</span> <span class="chip-val">${esc(currentOutfit||'Casual wear')}</span></div>
          </div>

          ${latestThought?`
          <div class="presence-thought-quote" style="margin-top:auto;margin-bottom:0">
            <div class="quote-mark">“</div>
            <p class="thought-text">${esc(latestThought)}</p>
            <div class="thought-footer">
              <span class="dim small">${thoughtSource}</span>
            </div>
          </div>`:''}
        </div>

        <div class="presence-atmosphere-column">
          <div class="hero-meters-card">
            ${feelingBadge?`
            <div class="hero-chemistry-row">
              <span class="pill status-good hero-chemistry-pill" style="--chem-score:${Number(chemistry.score)||0}%"
                title="${esc(chemistry.romantic_progression===false?chemistry.connection_label:chemistry.stage_badge)}">
                ${feelingBadge}
              </span>
            </div>`:''}
            <div class="hero-meters-stack">
              ${renderHeroMetersContent(emotions,d.bars)}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="home-columns" style="margin-top:28px">
    <div>
      <section class="home-block" data-block="journal">
      <div class="section-heading" style="margin-top:0"><h2>From the journal</h2>${jump('journals','All reflections')}</div>
      ${entry?`
      <article class="card journal-preview" style="border-radius:var(--r-lg);padding:26px">
        <span class="eyebrow" style="color:var(--dim)">Nightly reflection · ${esc(entry.day)}</span>
        <h3 style="margin:10px 0 14px">${new Intl.DateTimeFormat(undefined,{weekday:'long',month:'short',day:'numeric'}).format(new Date(entry.day+'T12:00:00'))}</h3>
        <p style="margin:0 0 16px;line-height:1.7">${esc(excerpt(entry.text,420))}</p>
        <div style="display:flex;justify-content:flex-end">
          <button class="link-button" id="read-latest" style="font-weight:600">Read ${esc(d.agent)}'s journal (${Math.max(1,Math.ceil(entry.words/220))} min) →</button>
        </div>
      </article>`:empty('journals','No journal entries yet','Daily reflections are recorded automatically by the scheduled nightly routine at 4:00 AM.',jump('settings','View routine status',false,'jobs'))}

      </section>

      <section class="home-block" data-block="photos">
      <div class="section-heading"><h2>Recent moments & captures</h2>${jump('photos','Open photo library')}</div>
      <div class="grid">
        ${(content.items.filter(x=>x.kind==='image').slice(0,6).length?content.items.filter(x=>x.kind==='image').slice(0,6):content.items.slice(0,6)).map(x=>{
          const originalIndex=content.items.indexOf(x);
          return `
          <button class="card photo-card" data-home-file="${originalIndex}">
            ${x.kind==='image'?`<div class="photo-wrap"><img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}"></div>`:`<div class="file-art">${icon(x.kind==='writing'?'journals':'creations')}</div>`}
            <div class="photo-meta"><p>${esc(x.title)}</p><small>${esc(x.kind)} · ${when(x.at)}</small></div>
          </button>`;
        }).join('')||'<p class="dim">Photos and captures appear here as your companion records their day.</p>'}
      </div>
      </section>
    </div>

    <div>
      <section class="home-block" data-block="calendar">
      <div class="section-heading" style="margin-top:0"><h2>Calendar</h2>${jump('loops','Planner')}</div>
      ${buildCalendarHtml(d.agent,d.missions,'home-cal')}

      </section>

      <section class="home-block" data-block="wardrobe">
      <div class="section-heading"><h2>Current presence &amp; closet</h2></div>
      ${renderWardrobeCard(closet,s,stage)}
      </section>
    </div>
  </div>`;

  wireRoutes($('now'));
  if($('presence-switch'))$('presence-switch').onclick=openCompanionSwitchDialog;
  wireCalendarComponent($('now'), d.missions, d.agent, () => render('now'), 'home-cal');
  if($('read-latest'))$('read-latest').onclick=()=>{if(entry?.id)selectedJournal=entry.id;showTab('journals');};
  for(const b of $('now').querySelectorAll('[data-home-file]'))b.onclick=()=>openContent(content.items[Number(b.dataset.homeFile)]);
};
let selectedJournal=null;
let journalPageGeneration=0;
// Held so that revisiting the page replaces this listener instead of stacking
// another one on the document for every visit.
let journalOutsideClick=null;
/* The journal is a reader, not a list beside a reader. Every way of reaching a
   different entry — the calendar and the search — lives in one panel behind the
   date in the middle of the reader's top bar, so the page itself stays a page
   of writing at every width. */
workspaceHandlers.journals=async()=>{
  const pageGeneration=++journalPageGeneration;
  const alive=()=>current==='journals'&&pageGeneration===journalPageGeneration;
  $('journals').innerHTML=`
    <div id="journal-warnings"></div>
    <div class="reader-shell">
      <div class="journal-nav-bar">
        <button class="journal-nav-btn" id="journal-older-btn" disabled>${icon('arrow_left')}<span class="nav-word">Older</span></button>
        <button class="reader-browse-btn" id="journal-browse" aria-expanded="false" aria-controls="journal-picker">
          <span aria-hidden="true">\u{1F4C5}</span><span id="journal-browse-label">Loading…</span><span class="reader-browse-caret" aria-hidden="true">▾</span>
        </button>
        <button class="journal-nav-btn" id="journal-newer-btn" disabled><span class="nav-word">Newer</span>${icon('arrow_right')}</button>
      </div>
      <div class="reader-picker" id="journal-picker" hidden>
        <input id="journal-search" type="search" maxlength="200" autocomplete="off"
          placeholder="Search every entry…" aria-label="Search journal entries">
        <div id="journal-picker-body"></div>
        <div class="reader-picker-foot">
          <span id="journal-count" class="dim small"></span>
          <button class="quiet small" id="journal-latest">Latest entry</button>
        </div>
      </div>
    </div>
    <article id="journal-page"><p class="dim" role="status">Opening the journal…</p></article>`;

  let entries=[],results=null,selection=0,searchTimer=null,pickerMonth='';
  const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dayFormat=day=>new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric',year:'numeric'}).format(new Date(day+'T12:00:00'));
  const shortDay=day=>new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',year:'numeric'}).format(new Date(day+'T12:00:00'));

  /* ------------------------------------------------------------- reader */
  const choose=async(id,{close=true}={})=>{
    const token=++selection;
    let entry=entries.find(x=>x.id===id)||(results||[]).find(x=>x.id===id);
    if(!entry)return;
    if(entry.truncated||entry.text===undefined){
      $('journal-page').innerHTML='<p class="dim" role="status">Opening the full entry…</p>';
      try{entry=(await api('/journals/'+encodeURIComponent(id))).entry;}
      catch(error){if(alive())$('journal-page').innerHTML=`<p class="bad">${esc(error.message)}</p>`;return;}
    }
    if(!alive()||selection!==token)return;
    selectedJournal=id;
    if(close)openPicker(false);
    // Neighbours come from the full list, so they are the true next and previous
    // entries even when the panel is showing a filtered search.
    const at=entries.findIndex(x=>x.id===id);
    const newer=at>0?entries[at-1]:null,older=at>=0&&at<entries.length-1?entries[at+1]:null;
    const olderBtn=$('journal-older-btn'),newerBtn=$('journal-newer-btn');
    olderBtn.disabled=!older;newerBtn.disabled=!newer;
    olderBtn.title=older?'Older: '+shortDay(older.day):'This is the oldest entry';
    newerBtn.title=newer?'Newer: '+shortDay(newer.day):'This is the newest entry';
    olderBtn.onclick=older?()=>choose(older.id):null;
    newerBtn.onclick=newer?()=>choose(newer.id):null;
    $('journal-browse-label').textContent=shortDay(entry.day);
    pickerMonth=entry.day.slice(0,7);
    const dayPhotos=await api('/content?'+new URLSearchParams({kind:'image',limit:'12',day:entry.day}))
      .then(r=>r.items.filter(x=>x.kind==='image')).catch(()=>[]);
    if(!alive()||selection!==token)return;
    const strip=dayPhotos.length?`
      <div class="journal-day-photos">
        <span class="eyebrow">${dayPhotos.length} ${dayPhotos.length===1?'picture':'pictures'} from this day</span>
        <div class="journal-day-strip">${dayPhotos.map((x,i)=>`
          <button class="journal-day-shot" data-day-photo="${i}" aria-label="Open ${esc(x.title)}">
            <img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}">
          </button>`).join('')}</div>
      </div>`:'';
    $('journal-page').innerHTML=`<div class="paper">
      <div class="paper-head">
        <span class="eyebrow" style="color:var(--faint)">Daily reflection · ${Math.max(1,Math.ceil(entry.words/220))} min read</span>
        <span class="pill" style="border-color:color-mix(in srgb,var(--surface-2) 30%,transparent);color:var(--faint)">Nightly Entry</span>
      </div>
      <h2>${esc(dayFormat(entry.day))}</h2>
      <div class="prose">${richText(entry.text)}</div>
      ${strip}
      <div class="paper-foot">
        <span style="font-family:Georgia,serif;font-style:italic;color:var(--faint);font-size:14px">Written during nightly introspection</span>
        <span class="dim small">${entry.words.toLocaleString()} words · ${esc(entry.source)}</span>
      </div>
    </div>`;
    for(const b of $('journal-page').querySelectorAll('[data-day-photo]'))
      b.onclick=()=>openPhotoViewer(dayPhotos[+b.dataset.dayPhoto],dayPhotos,+b.dataset.dayPhoto);
    $('journal-page').scrollIntoView({block:'start',behavior:'smooth'});
  };

  /* ------------------------------------------------------------- picker */
  const openPicker=open=>{
    $('journal-picker').hidden=!open;
    $('journal-browse').setAttribute('aria-expanded',String(open));
    if(open){drawPicker();$('journal-search').focus();}
  };

  const drawPicker=()=>{
    const body=$('journal-picker-body');
    if(results){
      $('journal-count').textContent=`${results.length} matching ${results.length===1?'entry':'entries'}`;
      body.innerHTML=results.length
        ? `<div class="reader-picker-results">${results.map(x=>`
            <button data-pick="${esc(x.id)}" ${x.id===selectedJournal?'aria-current="true"':''}>
              <strong>${esc(shortDay(x.day))}</strong><small>${esc(excerpt(x.excerpt||x.text,110))}</small>
            </button>`).join('')}</div>`
        : '<p class="dim small reader-picker-empty">Nothing matches that.</p>';
      return;
    }
    const byDay=new Map();
    for(const e of entries){if(!byDay.has(e.day))byDay.set(e.day,[]);byDay.get(e.day).push(e);}
    const [year,month]=pickerMonth.split('-').map(Number);
    const first=new Date(year,month-1,1).getDay(),count=new Date(year,month,0).getDate();
    const today=new Date().toISOString().slice(0,10);
    let cells='';
    for(let i=0;i<first;i++)cells+='<div class="calendar-cell is-other-month"></div>';
    for(let day=1;day<=count;day++){
      const key=`${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
      const found=byDay.get(key)||[];
      const classes=['calendar-cell',found.length?'has-entry':'is-empty',
        key===today?'is-today':'',found.some(x=>x.id===selectedJournal)?'is-selected':''].filter(Boolean).join(' ');
      cells+=found.length
        ? `<button class="${classes}" data-pick="${esc(found[0].id)}" title="${esc(dayFormat(key))}">
             <span class="calendar-cell-date">${day}</span>
             ${found.length>1?`<span class="cal-badge-pill">${found.length}</span>`:''}</button>`
        : `<div class="${classes}"><span class="calendar-cell-date">${day}</span></div>`;
    }
    const inMonth=entries.filter(x=>x.day.startsWith(pickerMonth)).length;
    $('journal-count').textContent=`${entries.length} ${entries.length===1?'entry':'entries'} in all`;
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
      ${inMonth?'':'<p class="dim small reader-picker-empty">No entries this month.</p>'}`;
    const shift=step=>{
      const d=new Date(year,month-1+step,1);
      pickerMonth=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
      drawPicker();
    };
    $('journal-cal-prev').onclick=()=>shift(-1);
    $('journal-cal-next').onclick=()=>shift(1);
  };

  $('journal-browse').onclick=()=>openPicker($('journal-picker').hidden);
  $('journal-latest').onclick=()=>{if(entries[0])choose(entries[0].id);};
  $('journal-picker').addEventListener('click',event=>{
    const pick=event.target.closest('[data-pick]');
    if(pick)choose(pick.dataset.pick);
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
  try{
    const data=await api('/journals?limit=1000');
    if(!alive())return;
    profileTimezone=data.timezone;
    entries=data.entries;
    $('journal-warnings').innerHTML=data.warnings.map(x=>`<p class="warn">${esc(x)}</p>`).join('');
    if(!entries.length){
      $('journal-browse-label').textContent='No entries';
      $('journal-page').innerHTML=empty('journals','No journal entries yet',
        'Daily reflections are recorded automatically by the scheduled nightly routine at 4:00 AM.',
        jump('settings','View routine status',false,'jobs'));
      return;
    }
    pickerMonth=entries[0].day.slice(0,7);
    await choose(entries.some(x=>x.id===selectedJournal)?selectedJournal:entries[0].id,{close:false});
  }catch(error){
    if(alive())$('journal-page').innerHTML=`<p class="bad">${esc(error.message)}</p>`;
  }
};
let viewerItems=[],viewerIndex=0,viewerAlbums=null,viewerInitialized=false;
function initPhotoViewer(){
  if(viewerInitialized)return;
  viewerInitialized=true;
  $('viewer-close').onclick=()=>closePhotoViewer();
  $('viewer-prev').onclick=()=>navigateViewer(-1);
  $('viewer-next').onclick=()=>navigateViewer(1);
  $('viewer-reveal-btn').onclick=()=>{
    $('viewer-conceal').hidden=true;
    $('viewer-img').classList.remove('concealed-media');
  };
  $('viewer-info-close').onclick=()=>{$('viewer-info-pane').hidden=true;};
  $('viewer-album-close').onclick=()=>{$('viewer-album-popover').hidden=true;};
  $('viewer-save-album').onclick=async()=>{
    const input=$('viewer-new-album'),name=(input.value||'').trim();
    if(!name)return;
    const item=viewerItems[viewerIndex];if(!item)return;
    try{
      await post('/content/album',{path:item.path,album:name});
      $('viewer-album-popover').hidden=true;
      input.value='';
      if(viewerAlbums&&!viewerAlbums.some(a=>a.name===name))viewerAlbums.push({name,count:1});
      notice('Saved copy to album: '+name);
      if(current==='photos')render('photos');
    }catch(err){notice('Failed to save album: '+err.message);}
  };
  $('photo-viewer').addEventListener('cancel',e=>{e.preventDefault();closePhotoViewer();});
  $('photo-viewer').addEventListener('close',()=>{document.body.style.overflow='';});
  const canvas=$('viewer-canvas'),img=$('viewer-img');
  let startX=0,startY=0,currentX=0,isSwiping=false,startTime=0;
  canvas.addEventListener('pointerdown',e=>{
    if(e.button!==0&&e.pointerType==='mouse')return;
    if(e.target.closest('button, a, input, select, textarea'))return;
    startX=e.clientX;startY=e.clientY;currentX=startX;isSwiping=true;startTime=Date.now();
    img.style.transition='none';
  });
  canvas.addEventListener('pointermove',e=>{
    if(!isSwiping)return;
    currentX=e.clientX;
    const dx=currentX-startX,dy=e.clientY-startY;
    if(Math.abs(dx)>Math.abs(dy)&&Math.abs(dx)>10){
      img.style.transform=`translateX(${dx*0.75}px)`;
    }
  });
  const endSwipe=()=>{
    if(!isSwiping)return;
    isSwiping=false;
    img.style.transition='transform .2s cubic-bezier(0.2,0.8,0.2,1)';
    const dx=currentX-startX,dt=Date.now()-startTime,speed=Math.abs(dx)/(dt||1);
    img.style.transform='';
    if(dx<-50||(dx<-25&&speed>0.4))navigateViewer(1);
    else if(dx>50||(dx>25&&speed>0.4))navigateViewer(-1);
  };
  canvas.addEventListener('pointerup',endSwipe);
  canvas.addEventListener('pointercancel',endSwipe);
  document.addEventListener('keydown',e=>{
    if(!$('photo-viewer').open)return;
    if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;
    if(e.key==='ArrowRight'){e.preventDefault();navigateViewer(1);}
    else if(e.key==='ArrowLeft'){e.preventDefault();navigateViewer(-1);}
    else if(e.key==='Escape'){
      e.preventDefault();
      if(!$('viewer-info-pane').hidden)$('viewer-info-pane').hidden=true;
      else if(!$('viewer-album-popover').hidden)$('viewer-album-popover').hidden=true;
      else closePhotoViewer();
    }
    else if(e.key==='i'||e.key==='I'){
      e.preventDefault();
      toggleViewerInfo();
    }
  });
}
function openPhotoViewer(item,items,index){
  initPhotoViewer();
  viewerItems=items&&items.length?items:[item];
  viewerIndex=typeof index==='number'&&index>=0&&index<viewerItems.length?index:viewerItems.indexOf(item);
  if(viewerIndex<0)viewerIndex=0;
  $('viewer-album-popover').hidden=true;
  $('viewer-info-pane').hidden=true;
  document.body.style.overflow='hidden';
  if(!$('photo-viewer').open)$('photo-viewer').showModal();
  renderViewerPhoto();
}
function closePhotoViewer(){
  if($('photo-viewer').open)$('photo-viewer').close();
  document.body.style.overflow='';
  $('viewer-album-popover').hidden=true;
  $('viewer-info-pane').hidden=true;
  $('viewer-img').src='';
}
function navigateViewer(dir){
  const next=viewerIndex+dir;
  if(next>=0&&next<viewerItems.length){
    viewerIndex=next;
    renderViewerPhoto();
  }
}
function toggleViewerInfo(){
  const pane=$('viewer-info-pane');
  if(!pane.hidden)pane.hidden=true;
  else{pane.hidden=false;populateViewerInfo(viewerItems[viewerIndex]);}
}
function populateViewerInfo(item){
  if(!item)return;
  const copies=(item.copies||[]).map(c=>esc(c.source+(c.path?' ('+c.path+')':''))).join('<br>')||'Original file';
  $('viewer-info-body').innerHTML=`<div><div class="info-field-label">Title</div><div class="info-field-value">${esc(item.title||'Untitled')}</div></div><div><div class="info-field-label">Date & Time</div><div class="info-field-value">${item.at?stamp(item.at,{weekday:'long',year:'numeric',month:'long',day:'numeric'})+' · '+when(item.at):'Not recorded'}</div></div><div><div class="info-field-label">Source / Origin</div><div class="info-field-value"><span class="pill">${esc(item.generation||item.source||item.kind||'image')}</span></div></div><div><div class="info-field-label">Safety & Review</div><div class="info-field-value"><span class="pill ${item.blur||item.rating==='nsfw'?'status-warn':'status-good'}">${esc(item.rating||'unrated')}${item.blur?' · blurred':''}</span> ${esc(item.review?.status||'unreviewed')}</div></div>${item.location?`<div><div class="info-field-label">Scene Location</div><div class="info-field-value">${esc(item.location)}</div></div>`:''}${item.mood?`<div><div class="info-field-label">Mood</div><div class="info-field-value">${esc(item.mood)}</div></div>`:''}${item.outfit?`<div><div class="info-field-label">Attire</div><div class="info-field-value">${esc(item.outfit)}</div></div>`:''}<div><div class="info-field-label">File Path</div><div class="info-field-value"><code style="font-size:12px;word-break:break-all">${esc(item.path||'')}</code></div></div><div><div class="info-field-label">Collections & Copies</div><div class="info-field-value small dim">${copies}</div></div>`;
}
async function populateAlbumChips(item){
  const chips=$('viewer-album-chips');
  chips.innerHTML='<span class="dim small">Loading albums…</span>';
  try{
    if(!viewerAlbums){const tl=await api('/timeline');viewerAlbums=tl.albums||[];}
    const standard=['Favorites'],names=[...new Set([...standard,...viewerAlbums.map(a=>a.name)])];
    const isInAlbum=(name)=>{
      const copies=[item,...(item.copies||[])];
      return copies.some(c=>c.path&&(c.path.startsWith('albums/'+name+'/')||c.path.startsWith('albums/'+name)));
    };
    chips.innerHTML=names.map(name=>{
      const active=isInAlbum(name);
      return `<button class="album-chip ${active?'is-active':''}" data-album="${esc(name)}">${active?'✓ ':'+ '}${esc(name)}</button>`;
    }).join('');
    for(const chip of chips.querySelectorAll('[data-album]')){
      chip.onclick=async()=>{
        const name=chip.dataset.album;
        if(isInAlbum(name)){
          notice('Photo is already in album: '+name);
          return;
        }
        try{
          await post('/content/album',{path:item.path,album:name});
          notice('Saved copy to album: '+name);
          if(!item.copies)item.copies=[];
          item.copies.push({path:'albums/'+name+'/'+(item.path.split('/').pop()||'photo.jpg'),source:'album'});
          if(viewerAlbums&&!viewerAlbums.some(a=>a.name===name))viewerAlbums.push({name,count:1});
          await populateAlbumChips(item);
          if(current==='photos')render('photos');
        }catch(err){notice('Failed to add to album: '+err.message);}
      };
    }
  }catch(err){chips.innerHTML='<span class="warn small">Could not load albums</span>';}
}
function renderViewerPhoto(){
  const item=viewerItems[viewerIndex];if(!item)return;
  $('viewer-counter').textContent=`${viewerIndex+1} / ${viewerItems.length}`;
  $('viewer-date').textContent=item.at?`${stamp(item.at)} · ${when(item.at)}`:(item.title||'Photo');
  $('viewer-prev').disabled=viewerIndex<=0;
  $('viewer-next').disabled=viewerIndex>=viewerItems.length-1;
  const img=$('viewer-img');
  img.src=mediaUrl(item.url);img.alt=item.title||'';
  const conceal=$('viewer-conceal');
  if(item.blur){conceal.hidden=false;img.classList.add('concealed-media');}
  else{conceal.hidden=true;img.classList.remove('concealed-media');}
  const isNsfw=item.blur||item.rating==='nsfw';
  const downloadUrl=mediaUrl(item.url+'&download=true');
  $('viewer-actions').innerHTML=`
    <button class="viewer-icon-btn ${isNsfw?'is-safe':'is-warn'}" id="viewer-btn-rate" title="${isNsfw?'Mark safe':'Mark NSFW'}" aria-label="${isNsfw?'Mark safe':'Mark NSFW'}">${icon(isNsfw?'shield_check':'shield_alert')}</button>
    <button class="viewer-icon-btn" id="viewer-btn-album" title="Add copy to album" aria-label="Add copy to album">${icon('album')}</button>
    <a class="viewer-icon-btn" href="${downloadUrl}" download title="Download image" aria-label="Download image">${icon('download')}</a>
    <button class="viewer-icon-btn" id="viewer-btn-profile" title="Set as profile photo" aria-label="Set as profile photo">${icon('profile')}</button>
    <button class="viewer-icon-btn" id="viewer-btn-info" title="Details (i)" aria-label="Details">${icon('info')}</button>
    ${item.deletable?`<button class="viewer-icon-btn viewer-btn-danger" id="viewer-btn-delete" title="Delete photo" aria-label="Delete photo">${icon('trash')}</button>`:''}
  `;
  $('viewer-btn-rate').onclick=async()=>{
    const newRating=isNsfw?'safe':'nsfw';
    try{
      await post('/content/rating',{path:item.path,rating:newRating});
      item.rating=newRating;item.blur=(newRating==='nsfw');
      renderViewerPhoto();
      notice(newRating==='nsfw'?'Marked as sensitive / NSFW':'Marked as safe');
      if(current==='photos')render('photos');
    }catch(err){notice('Rating update failed: '+err.message);}
  };
  $('viewer-btn-album').onclick=async()=>{
    const pop=$('viewer-album-popover');
    if(!pop.hidden){pop.hidden=true;return;}
    pop.hidden=false;await populateAlbumChips(item);
  };
  $('viewer-btn-info').onclick=()=>toggleViewerInfo();
  if($('viewer-btn-profile'))$('viewer-btn-profile').onclick=async()=>{
    const item=viewerItems[viewerIndex];if(!item)return;
    if(!confirm('Set this image as the companion\'s profile photo?'))return;
    try{await post('/portrait/from-content',{path:item.path});portraitVersion=Date.now();portraitStored=true;notice('Profile photo updated');if(current==='photos')render('photos');}catch(err){notice('Failed: '+err.message);}
  };
  if($('viewer-btn-delete')){
    $('viewer-btn-delete').onclick=async()=>{
      if(!confirm('Permanently delete this photo from the vault? Separate album copies are unaffected.'))return;
      try{
        await post('/content/delete',{path:item.path,etag:item.etag});
        notice('Photo deleted');
        viewerItems.splice(viewerIndex,1);
        if(viewerItems.length===0)closePhotoViewer();
        else{if(viewerIndex>=viewerItems.length)viewerIndex=viewerItems.length-1;renderViewerPhoto();}
        if(current==='photos')render('photos');
      }catch(err){notice('Delete failed: '+err.message);}
    };
  }
  if(!$('viewer-info-pane').hidden)populateViewerInfo(item);
}
async function openContent(item,items=null,index=0){
  if(!item)return;
  if(item.kind==='image'){openPhotoViewer(item,items,index);return;}
  let html;
  const download=mediaUrl(item.url+'&download=true');
  if(item.kind==='writing'){
    dialog(item.title,'<p class="dim">Opening document…</p>');
    try{const d=await api('/content/text?path='+encodeURIComponent(item.path));if(!$('product-dialog').open)return;html=`<div class="reader-tools"><span class="dim small">${esc(item.path)}</span><a class="quiet" href="${download}" download>Download</a></div><div class="paper"><div class="prose">${richText(d.text)}</div></div>`;}catch(e){html=empty('creations','Preview unavailable',e.message,`<a class="quiet" href="${download}" download>Download file</a>`);}
  }else html=`<div class="lightbox-layout"><div>${item.kind==='audio'?`<div class="file-art">${icon('creations')}</div><audio controls src="${mediaUrl(item.url)}"></audio>`:item.kind==='video'?`<video controls src="${mediaUrl(item.url)}"></video>`:'<p class="dim">Download this document to open it.</p>'}</div><div><span class="eyebrow">${esc(item.generation||item.source||item.kind)}</span><p class="dim">${when(item.at)}</p><div class="actions"><a class="quiet" href="${download}" download>Download</a>${item.deletable?'<button class="quiet" id="delete-content">Delete file</button>':''}</div><details><summary>File details</summary><code>${esc(item.path||'')}</code></details></div></div>`;
  dialog(item.title,html);
  if(item.deletable&&!$('delete-content'))$('dialog-body').insertAdjacentHTML('beforeend','<button class="quiet" id="delete-content">Delete file</button>');
  if($('delete-content'))$('delete-content').onclick=()=>{const b=$('delete-content');b.insertAdjacentHTML('afterend','<div id="delete-confirm"><p>Delete this file permanently? Separate album copies, provider output files and already-sent messages are unaffected.</p><button class="act" id="delete-confirm-yes">Permanently delete this file</button></div>');b.disabled=true;$('delete-confirm-yes').onclick=async()=>{await post('/content/delete',{path:item.path,etag:item.etag});$('product-dialog').close();await render(current);notice('File deleted.');};};
}
function photoInCollection(x,collection){return collection==='all'||(collection.startsWith('album:')?(x.copies||[x]).some(p=>p.path.startsWith('albums/'+collection.slice(6)+'/')):(x.copies||[x]).some(p=>p.source===collection));}
function photoForCollection(x,collection){const copy=(x.copies||[]).find(p=>collection.startsWith('album:')?p.path.startsWith('albums/'+collection.slice(6)+'/'):p.source===collection);return copy?{...x,...copy}:x;}
function mergePhotos(content,timeline){const captures=new Map(timeline.captures.map(x=>[x.image.split('/').pop(),x]));return content.items.filter(x=>x.kind==='image').map(x=>{const copy=(x.copies||[x]).find(p=>p.source==='photo session'),capture=copy?captures.get(copy.path.split('/').pop()):null;return capture?{...x,at:capture.at||x.at,title:capture.activity||x.title,mood:capture.mood,outfit:capture.outfit,capture:capture.id}:x;}).sort((a,b)=>(Date.parse(b.at)||0)-(Date.parse(a.at)||0));}
function photoDays(items){const groups=new Map();items.forEach((item,index)=>{const day=dayKey(item.at)||'unknown';if(!groups.has(day))groups.set(day,{day,items:[]});groups.get(day).items.push({item,index});});return [...groups.values()];}
const photoBrowse={query:'',day:'',collection:'all'};
const photoSelection=new Set();
let selectMode=false;
function toggleSelectMode(){
  selectMode=!selectMode;
  photoSelection.clear();
  const grid=document.querySelector('#photo-grid');
  if(grid)grid.classList.toggle('is-select-mode',selectMode);
  updateSelectionBar();
  const btn=$('photo-select-toggle');
  if(btn){btn.textContent=selectMode?'Cancel':'Select';btn.setAttribute('aria-pressed',String(selectMode));}
}
function updateSelectionBar(){
  const bar=$('photo-selection-bar');
  if(!bar)return;
  if(!selectMode||photoSelection.size===0){bar.hidden=true;return;}
  bar.hidden=false;
  bar.querySelector('.selection-count').textContent=`${photoSelection.size} selected`;
}
function togglePhotoSelected(contentId,cardEl){
  if(photoSelection.has(contentId)){photoSelection.delete(contentId);cardEl.classList.remove('is-selected');cardEl.querySelector('.photo-select-check')?.classList.remove('checked');}
  else{photoSelection.add(contentId);cardEl.classList.add('is-selected');cardEl.querySelector('.photo-select-check')?.classList.add('checked');}
  updateSelectionBar();
}
let photoPageGeneration=0;
/* The photos panel in Preferences owns every photo setting, including the blur
   toggles and the local scanner. The gear goes there rather than opening a
   smaller, separate copy of it. */
/* The gear beside the collections. It opens the panel that owns these
   settings; `preferencePanel` was the old page's variable and stopped meaning
   anything when Settings became one page, so the gear was landing on whatever
   panel happened to be open last. */
function openPhotoSettings(){openSettings(null,'photos');}

workspaceHandlers.photos=async()=>{
  const generation=++photoPageGeneration;
  let [content,tl]=await Promise.all([api('/content?'+new URLSearchParams({kind:'image',limit:'1500',q:photoBrowse.query,day:photoBrowse.day,collection:photoBrowse.collection})),api('/timeline')]);if(current!=='photos'||generation!==photoPageGeneration)return;
  profileTimezone=content.timezone;let items=mergePhotos(content,tl);
  // One search field and a row of collection chips, the way a photo library
  // does it; the day picker is gone, its job taken by the date rail.
  const collections=[['all','All photos'],['photo session','Timeline'],['creation','Creations'],
    ...tl.albums.map(a=>['album:'+a.name,a.name])];
  $('photos').innerHTML=`
    <div class="photo-toolbar">
      <div class="photo-search-pill">
        ${icon('search')}
        <input type="search" id="photo-search" maxlength="200" placeholder="Search your photos" aria-label="Search photos">
        <button class="photo-search-clear" id="photo-clear" aria-label="Clear search" hidden>\u2715</button>
      </div>
      <div class="photo-chips" id="photo-chips" role="tablist" aria-label="Collections">
        ${collections.map(([value,label])=>`<button class="photo-chip" role="tab" data-collection="${esc(value)}"
          aria-selected="${value===photoBrowse.collection}">${esc(label)}</button>`).join('')}
        <button class="photo-chip" id="photo-select-toggle" aria-pressed="false">Select</button>
        <button class="photo-chip photo-chip-icon" id="photo-manage-settings-btn" title="Manage photo settings" aria-label="Manage photo settings">\u2699</button>
      </div>
    </div>
    <div id="photo-grid" class="photo-library"></div>
    <div class="photo-scrubber" id="photo-scrubber" aria-hidden="true"></div>
    <p class="dim small" id="photo-count" role="status"></p>
    <div class="photo-selection-bar" id="photo-selection-bar" hidden>
      <span class="selection-count">0 selected</span>
      <button class="act" id="sel-add-album">Add to album</button>
      <button class="act" id="sel-new-album">Create album</button>
      <button class="quiet viewer-btn-danger" id="sel-delete">Delete</button>
    </div>`;
  if($('photo-manage-settings-btn'))$('photo-manage-settings-btn').onclick=openPhotoSettings;
  if($('photo-select-toggle'))$('photo-select-toggle').onclick=toggleSelectMode;
  if(selectMode&&$('photo-grid'))$('photo-grid').classList.add('is-select-mode');
  const draw=()=>{
    const shown=items.map(x=>photoForCollection(x,photoBrowse.collection));
    // One continuous grid. The pictures never break into per-day blocks; the
    // date rides the first tile of each day as a marker instead.
    let runningDay='';
    $('photo-grid').innerHTML=`<div class="photo-grid photo-flow">${shown.map((x,i)=>{
      const day=dayKey(x.at)||'unknown';
      const starts=day!==runningDay;
      if(starts)runningDay=day;
      return `
      <div class="photo-card${photoSelection.has(x.content_id||x.path)?' is-selected':''}" data-photo="${i}" data-content-id="${esc(x.content_id||x.path)}" ${starts?`data-day="${esc(day)}"`:''} tabindex="0" role="button" aria-label="Open ${esc(x.title)}">
        <div class="photo-wrap">
          <div class="photo-select-check${photoSelection.has(x.content_id||x.path)?' checked':''}" aria-hidden="true"></div>
          <img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}">
          ${starts?`<span class="photo-date-marker">${esc(day==='unknown'?'No date':stamp(x.at,{month:'short',day:'numeric'}))}</span>`:''}
        </div>
        <div class="photo-card-actions">
          <button class="card-action-btn ${x.blur||x.rating==='nsfw'?'is-safe':'is-warn'}" data-card-rate="${i}" title="${x.blur||x.rating==='nsfw'?'Mark safe':'Mark NSFW'}">
            ${icon(x.blur||x.rating==='nsfw'?'shield_check':'shield_alert')}
          </button>
          <button class="card-action-btn" data-card-album="${i}" title="Add copy to album">
            ${icon('album')}
          </button>
          <a class="card-action-btn" href="${mediaUrl(x.url+'&download=true')}" download title="Download" onclick="event.stopPropagation()">
            ${icon('download')}
          </a>
        </div>
      </div>`;}).join('')}</div>`;
    if(!shown.length)$('photo-grid').innerHTML=empty('photos',(photoBrowse.query||photoBrowse.day||photoBrowse.collection!=='all')?'No matching photos':'No photos in library',(photoBrowse.query||photoBrowse.day||photoBrowse.collection!=='all')?'Try another search, day or collection.':'Capture routines will populate images automatically.','<button class="act" id="photo-empty-manage-settings">⚙️ Manage settings</button>');
    if($('photo-empty-manage-settings'))$('photo-empty-manage-settings').onclick=openPhotoSettings;
    $('photo-count').textContent=`${shown.length} of ${content.total} images${content.scan_limited?' · scan limit reached; additional files remain in the Vault':''}`;
    for(const b of $('photo-grid').querySelectorAll('.photo-card')){
      b.onclick=e=>{
        if(e.target.closest('.photo-card-actions'))return;
        if(selectMode){const x=shown[+b.dataset.photo];togglePhotoSelected(x.content_id||x.path,b);draw();return;}
        openPhotoViewer(shown[+b.dataset.photo],shown,+b.dataset.photo);
      };
      b.onkeydown=e=>{
        if(e.key==='Enter'||e.key===' '){
          if(e.target.closest('.photo-card-actions'))return;
          e.preventDefault();
          if(selectMode){const x=shown[+b.dataset.photo];togglePhotoSelected(x.content_id||x.path,b);draw();return;}
          openPhotoViewer(shown[+b.dataset.photo],shown,+b.dataset.photo);
        }
      };
    }
    for(const b of $('photo-grid').querySelectorAll('[data-card-rate]')){
      b.onclick=async e=>{
        e.stopPropagation();
        const x=shown[+b.dataset.cardRate];
        const newRating=(x.blur||x.rating==='nsfw')?'safe':'nsfw';
        try{
          await post('/content/rating',{path:x.path,rating:newRating});
          x.rating=newRating;x.blur=(newRating==='nsfw');
          draw();
          notice(newRating==='nsfw'?'Marked as sensitive / NSFW':'Marked as safe');
        }catch(err){notice('Rating update failed: '+err.message);}
      };
    }
    for(const b of $('photo-grid').querySelectorAll('[data-card-album]')){
      b.onclick=async e=>{
        e.stopPropagation();
        const x=shown[+b.dataset.cardAlbum];
        openPhotoViewer(x,shown,+b.dataset.cardAlbum);
        $('viewer-btn-album')?.click();
      };
    }
    wireRoutes($('photos'));
    updateSelectionBar();
    if($('sel-add-album'))$('sel-add-album').onclick=async()=>{
      const items=shown.filter(x=>photoSelection.has(x.content_id||x.path));
      if(!items.length)return;
      const name=prompt('Album name:','Favorites');
      if(!name)return;
      try{await post('/content/batch-album',{paths:items.map(x=>x.path),album:name});notice(`Added ${items.length} photo(s) to ${name}`);selectMode=false;photoSelection.clear();await render('photos');}catch(err){notice('Failed: '+err.message);}
    };
    if($('sel-new-album'))$('sel-new-album').onclick=async()=>{
      const items=shown.filter(x=>photoSelection.has(x.content_id||x.path));
      if(!items.length)return;
      const name=prompt('New album name:');
      if(!name)return;
      try{await post('/content/batch-album',{paths:items.map(x=>x.path),album:name});notice(`Created album "${name}" with ${items.length} photo(s)`);selectMode=false;photoSelection.clear();await render('photos');}catch(err){notice('Failed: '+err.message);}
    };
    if($('sel-delete'))$('sel-delete').onclick=async()=>{
      const items=shown.filter(x=>photoSelection.has(x.content_id||x.path));
      if(!items.length)return;
      const d=document.createElement('dialog');d.className='editor-leave-dialog';
      d.setAttribute('aria-label','Confirm deletion');
      d.innerHTML=`<h2>Delete ${items.length} photo(s)?</h2><p>This permanently deletes the selected photos from the vault. Separate album copies are unaffected.</p><div class="actions"><button class="quiet" data-cancel autofocus>Cancel</button><button class="act viewer-btn-danger" data-confirm>Delete ${items.length} photo(s)</button></div>`;
      const finish=(confirmed)=>{d.close();d.remove();return confirmed;};
      d.querySelector('[data-cancel]').onclick=()=>finish(false);
      d.querySelector('[data-confirm]').onclick=async()=>{
        finish(true);
        try{await post('/content/batch-delete',{items:items.filter(x=>x.deletable).map(x=>({path:x.path,etag:x.etag}))});notice(`Deleted ${items.length} photo(s)`);selectMode=false;photoSelection.clear();await render('photos');}catch(err){notice('Delete failed: '+err.message);}
      };
      d.addEventListener('cancel',e=>{e.preventDefault();finish(false);});
      document.body.append(d);d.showModal();
    };
    buildScrubber();
  };

  /* A rail of months down the right edge, the way a photo library lets you
     throw yourself back through a year. Labels sit at each month's real share
     of the page, so dragging the thumb lands where the label says. */
  let scrubTimer=null;
  const buildScrubber=()=>{
    const rail=$('photo-scrubber'),groups=[...$('photo-grid').querySelectorAll('[data-day]')];
    if(!rail)return;
    const height=document.documentElement.scrollHeight-window.innerHeight;
    if(groups.length<2||height<400){rail.hidden=true;rail.innerHTML='';return;}
    rail.hidden=false;
    const marks=[];let lastMonth='';
    for(const group of groups){
      const day=group.dataset.day||'';
      const month=day.slice(0,7);
      if(!month||month===lastMonth)continue;
      lastMonth=month;
      const top=Math.min(1,Math.max(0,(group.offsetTop-90)/height));
      marks.push({month,top,label:new Intl.DateTimeFormat(undefined,{month:'short',year:'numeric'})
        .format(new Date(month+'-02T12:00:00'))});
    }
    rail.innerHTML=`<div class="photo-scrubber-thumb" id="photo-scrub-thumb"></div>`+
      marks.map(m=>`<button class="photo-scrubber-mark" style="top:${(m.top*100).toFixed(2)}%"
        data-scrub="${m.top}" title="Jump to ${esc(m.label)}"><span>${esc(m.label)}</span></button>`).join('');
    moveThumb();
  };
  const moveThumb=()=>{
    const thumb=$('photo-scrub-thumb');if(!thumb)return;
    const height=document.documentElement.scrollHeight-window.innerHeight;
    thumb.style.top=(height>0?Math.min(1,window.scrollY/height)*100:0).toFixed(2)+'%';
  };
  const scrubTo=fraction=>{
    const height=document.documentElement.scrollHeight-window.innerHeight;
    window.scrollTo({top:Math.max(0,Math.min(1,fraction))*height});
  };
  const railFraction=event=>{
    const rail=$('photo-scrubber'),box=rail.getBoundingClientRect();
    return (event.clientY-box.top)/box.height;
  };
  $('photo-scrubber').addEventListener('pointerdown',event=>{
    const mark=event.target.closest('[data-scrub]');
    $('photo-scrubber').classList.add('is-dragging');
    $('photo-scrubber').setPointerCapture(event.pointerId);
    scrubTo(mark?Number(mark.dataset.scrub):railFraction(event));
  });
  $('photo-scrubber').addEventListener('pointermove',event=>{
    if(!$('photo-scrubber').classList.contains('is-dragging'))return;
    event.preventDefault();scrubTo(railFraction(event));
  });
  for(const done of ['pointerup','pointercancel'])
    $('photo-scrubber').addEventListener(done,()=>$('photo-scrubber').classList.remove('is-dragging'));
  let request=0,timer,scrollLoading=false;
  const load=async more=>{
    const token=++request;
    const params=new URLSearchParams({kind:'image',limit:'1500',q:photoBrowse.query,day:photoBrowse.day,collection:photoBrowse.collection});
    if(more&&content.next_cursor)params.set('before',content.next_cursor);
    try{
      const page=await api('/content?'+params);
      if(current!=='photos'||generation!==photoPageGeneration||token!==request)return;
      const incoming=mergePhotos(page,tl);
      items=more?[...items,...incoming.filter(x=>!items.some(y=>(y.content_id||y.path)===(x.content_id||x.path)))]:incoming;
      content=page;draw();
    }catch(error){if(current==='photos'&&generation===photoPageGeneration&&token===request&&$('photo-count'))$('photo-count').textContent=error.message;}
  };
  const filter=()=>{request++;Object.assign(photoBrowse,{query:$('photo-search').value,collection:photoBrowse.collection});
    $('photo-clear').hidden=!$('photo-search').value;
    clearTimeout(timer);timer=setTimeout(()=>{if(current==='photos'&&generation===photoPageGeneration)load(false);},220);};
  $('photo-search').value=photoBrowse.query;
  $('photo-clear').hidden=!photoBrowse.query;
  $('photo-search').oninput=filter;
  $('photo-clear').onclick=()=>{$('photo-search').value='';filter();$('photo-search').focus();};
  for(const chip of $('photo-chips').querySelectorAll('[data-collection]'))chip.onclick=()=>{
    photoBrowse.collection=chip.dataset.collection;
    for(const other of $('photo-chips').querySelectorAll('[data-collection]'))
      other.setAttribute('aria-selected',String(other===chip));
    filter();
  };
  const onScroll=()=>{
    if(current!=='photos'||generation!==photoPageGeneration)return;
    moveThumb();
    $('photo-scrubber')?.classList.add('is-active');
    clearTimeout(scrubTimer);
    scrubTimer=setTimeout(()=>$('photo-scrubber')?.classList.remove('is-active'),2200);
    if(scrollLoading||!content?.next_cursor)return;
    if((window.innerHeight+window.scrollY)>=document.body.offsetHeight-600){
      scrollLoading=true;
      load(true).finally(()=>{scrollLoading=false;});
    }
  };
  window.addEventListener('scroll',onScroll,{passive:true});
  draw();
};
workspaceHandlers.creations=async()=>{
  const content=await api('/content');if(current!=='creations')return;profileTimezone=content.timezone;
  const items=content.items.filter(x=>x.source==='creation'&&x.kind!=='image');
  $('creations').innerHTML=heading('Creations','Writing, notes, audio, video, and documents stored in the companion vault.')+`<div class="filters"><label>Find a creation<input type="search" id="creation-search" placeholder="Search titles and folders…"></label><label>Type<select id="creation-type"><option value="all">Everything</option><option value="writing">Writing & notes</option><option value="audio">Audio</option><option value="video">Video</option><option value="document">Documents</option></select></label></div><div class="photo-grid" id="creation-grid"></div><p class="dim small">${content.limited?'Showing a bounded catalog. Browse the Vault for additional files.':'Files remain in their original folders. Changes appear when refreshed.'}</p>`;
  const filter=()=>{const q=$('creation-search').value.toLowerCase(),type=$('creation-type').value;const shown=items.filter(x=>(type==='all'||x.kind===type)&&(!q||(x.title+' '+x.path).toLowerCase().includes(q)));$('creation-grid').innerHTML=shown.map((x,i)=>`<button class="photo-card" data-file="${i}"><div class="file-art">${icon(x.kind==='writing'?'journals':'creations')}</div><div class="photo-meta"><small>${esc(x.kind)} · ${when(x.at)}</small><p>${esc(x.title)}</p><small>${esc(x.path.split('/').slice(0,-1).join(' / '))}</small></div></button>`).join('')||`<div style="grid-column:1/-1">${empty('creations','No creations found','Files saved in the companion vault appear here automatically. Try another filter or explore the Vault.',jump('vault','Open vault'))}</div>`;for(const b of $('creation-grid').querySelectorAll('[data-file]'))b.onclick=()=>openContent(shown[+b.dataset.file]);wireRoutes($('creations'));};$('creation-search').oninput=filter;$('creation-type').onchange=filter;filter();
};
workspaceHandlers.timeline=async()=>{
  const [life,content,tl,journal]=await Promise.all([api('/life'),api('/content'),api('/timeline'),api('/journals')]);if(current!=='timeline')return;
  profileTimezone=content.timezone;const photos=mergePhotos(content,tl);
  const events=[...life.events.map(x=>({kind:'moment',at:x.recorded_at,title:x.state.activity,text:x.state.mood,place:x.state.location,unconfirmed:x.state.confirmed===false})),...photos.map(x=>({kind:'photo',at:x.at,title:x.title,item:x})),...journal.entries.map(x=>({kind:'journal',at:x.day+'T23:59:00',day:x.day,title:'Daily reflection',text:excerpt(x.text,240),entry:x}))].sort((a,b)=>{const dayA=a.day||dayKey(a.at),dayB=b.day||dayKey(b.at);if(dayA!==dayB)return dayB.localeCompare(dayA);if(a.kind==='journal')return b.kind==='journal'?0:-1;if(b.kind==='journal')return 1;return (Date.parse(b.at)||0)-(Date.parse(a.at)||0);});
  $('timeline').innerHTML=heading('Timeline','High-density chronological stream of scene updates, captures, and journal reflections.')+`<div class="filters"><label>Show<select id="feed-kind"><option value="all">All records</option><option value="moment">Scene updates</option><option value="photo">Captures</option><option value="journal">Daily reflections</option></select></label><label>Day<input type="date" id="feed-day"></label><label>Search<input type="search" id="feed-search" placeholder="Search events…"></label><button class="quiet" id="feed-clear">Clear</button></div><div id="timeline-feed" class="timeline-compact-stream"></div><p class="dim small">Chronological feed of recorded scene changes, photo captures, and saved daily reflections.</p>`;
  const filter=()=>{
    const kind=$('feed-kind').value,day=$('feed-day').value,q=$('feed-search').value.toLowerCase();
    const shown=events.filter(x=>(kind==='all'||x.kind===kind)&&(!day||(x.day||dayKey(x.at))===day)&&(!q||(x.title+' '+(x.text||'')+' '+(x.place||'')).toLowerCase().includes(q)));
    let last='';
    $('timeline-feed').innerHTML=shown.slice(0,250).map((x,i)=>{
      const date=x.day||dayKey(x.at);
      const head=last!==date?`<div style="font-weight:700;font-size:13px;color:var(--ink-2);margin:14px 0 6px;padding-left:4px">📅 ${esc(date)}</div>`:'';
      last=date;
      const iconBox=x.kind==='photo'?'📸':x.kind==='journal'?'📖':'✨';
      const label=x.kind==='moment'?(x.unconfirmed?'Scene (unconfirmed)':'Scene update'):x.kind==='journal'?'Daily reflection':'Capture';
      return head+`
      <div class="timeline-row">
        <div class="timeline-icon-box">${iconBox}</div>
        <div class="timeline-row-info">
          <span class="pill ${x.kind==='photo'?'status-good':x.kind==='journal'?'':''}">${label}</span>
          <span class="timeline-row-title">${esc(x.title)}</span>
          ${x.text?`<span class="timeline-row-meta">${esc(excerpt(x.text,80))}</span>`:''}
          ${x.place?`<span class="dim small">📍 ${esc(x.place)}</span>`:''}
        </div>
        <div class="timeline-row-time">${x.kind==='journal'?'Daily':stamp(x.at,{hour:'numeric',minute:'2-digit',month:undefined,day:undefined})}</div>
        ${x.kind!=='moment'?`<button class="quiet small-btn" data-event="${i}">${x.kind==='photo'?'View photo':'Read'}</button>`:''}
      </div>`;
    }).join('')||empty('timeline','No events found','No matching events for this date or filter. New events appear as companion routines run.');
    for(const b of $('timeline-feed').querySelectorAll('[data-event]'))b.onclick=()=>{
      const x=shown[+b.dataset.event];
      if(x.kind==='photo')openContent(x.item);
      else{selectedJournal=x.entry.id;showTab('journals');}
    };
  };
  $('feed-kind').onchange=filter;$('feed-day').onchange=filter;$('feed-search').oninput=filter;
  $('feed-clear').onclick=()=>{$('feed-kind').value='all';$('feed-day').value='';$('feed-search').value='';filter();};
  filter();
};

workspaceHandlers.knows=async()=>{
  const d=await api('/ledgers');if(current!=='knows')return;
  const factsTotal=d.facts?d.facts.length:0;
  const standingTotal=d.standing?d.standing.length:0;
  const momentsTotal=d.relationship?d.relationship.length:0;
  const questionsTotal=d.questions?d.questions.length:0;
  const categories=['all',...new Set((d.facts||[]).map(f=>f.category).filter(Boolean))];

  $('knows').innerHTML=heading('Memory ledger','Verified personal knowledge, standing rules, and conversational context maintained by Hermes.')+
  `<div class="stat-strip memory-kpi-strip">
    <div class="stat-item"><span>Verified facts</span><strong>${factsTotal}</strong></div>
    <div class="stat-item"><span>Standing rules</span><strong>${standingTotal}</strong></div>
    <div class="stat-item"><span>Shared moments</span><strong>${momentsTotal}</strong></div>
    <div class="stat-item"><span>Open inquiries</span><strong>${questionsTotal}</strong></div>
  </div>
  <div class="filters">
    <label>Search memory<input type="search" id="memory-search" placeholder="Search statements, evidence, guidelines…"></label>
    <label>Category<select id="memory-category">${categories.map(c=>`<option value="${esc(c)}">${c==='all'?'All categories':esc(c[0].toUpperCase()+c.slice(1))}</option>`).join('')}</select></label>
    <button class="quiet" id="memory-clear">Clear</button>
  </div>
  <div class="card" style="margin-bottom:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h2 style="margin:0">Personal Facts & Knowledge</h2>
      <span class="dim small" id="memory-fact-count">${factsTotal} facts recorded</span>
    </div>
    <div class="memory-grid" id="memory-facts-grid"></div>
    <p class="dim small" style="margin-top:14px">Marking a fact incorrect records a superseding correction without deleting original evidence.</p>
  </div>
  <div class="row">
    <div class="card">
      <h2>Standing Guidelines (${standingTotal})</h2>
      <div id="memory-standing-list" class="memory-list" style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
        ${standingTotal?d.standing.map(r=>`<div class="memory-card"><div class="memory-card-header"><span class="pill">Guideline</span></div><p style="margin:6px 0;font-weight:500;color:var(--ink)">${esc(r.instruction)}</p><p class="dim small" style="margin:0">Evidence: ${esc(r.evidence)}</p></div>`).join(''):'<p class="dim small">No standing guidelines recorded.</p>'}
      </div>
    </div>
    <div class="card">
      <h2>Open Inquiries (${questionsTotal})</h2>
      <div id="memory-questions-list" class="memory-list" style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
        ${questionsTotal?d.questions.map(q=>`<div class="memory-card"><p style="margin:0;font-weight:500;color:var(--ink)">❓ ${esc(q.text)}</p></div>`).join(''):'<p class="dim small">No open inquiries right now.</p>'}
      </div>
    </div>
  </div>`;

  const filterFacts=()=>{
    const q=($('memory-search')?.value||'').toLowerCase();
    const cat=$('memory-category')?.value||'all';
    const matches=(d.facts||[]).filter(f=>{
      const matchCat=cat==='all'||f.category===cat;
      const matchQ=!q||(f.statement+' '+f.evidence+' '+(f.category||'')).toLowerCase().includes(q);
      return matchCat&&matchQ;
    });
    if($('memory-fact-count'))$('memory-fact-count').textContent=matches.length+' of '+factsTotal+' facts';
    const grid=$('memory-facts-grid');
    if(!grid)return;
    grid.innerHTML=matches.length?matches.map(f=>`
      <div class="memory-card">
        <div class="memory-card-header">
          <span class="pill">${esc(f.category||'fact')}</span>
          <button class="quiet small-btn" data-forget="${esc(f.id)}" title="Mark this fact as incorrect">Mark incorrect</button>
        </div>
        <div class="memory-statement">${esc(f.statement)}</div>
        ${f.evidence?`<div class="memory-evidence">“${esc(f.evidence)}”</div>`:''}
      </div>`).join(''):'<div class="dim small" style="grid-column:1/-1;padding:20px;text-align:center">No facts match this filter.</div>';
    for(const b of grid.querySelectorAll('[data-forget]')){
      b.onclick=async()=>{
        b.disabled=true;
        await api(`/facts/${b.dataset.forget}/forget`,{method:'POST'});
        notice('Fact marked incorrect.');
        await workspaceHandlers.knows();
      };
    }
  };
  $('memory-search').oninput=filterFacts;
  $('memory-category').onchange=filterFacts;
  $('memory-clear').onclick=()=>{
    $('memory-search').value='';
    $('memory-category').value='all';
    filterFacts();
  };
  filterFacts();
};

workspaceHandlers.loops=async()=>{
  const [d,m]=await Promise.all([api('/overview'),api('/missions')]);if(current!=='loops')return;
  const missions=m.missions||[];
  const loops=d.loops||[];
  const openCount=missions.filter(x=>x.status==='open').length;

  $('loops').innerHTML=heading('Plans & calendar','Shared schedule, commitments, autonomous investigations, and open threads.')+
  `<div class="stat-strip">
    <div class="stat-item"><span>Active tasks</span><strong>${openCount}</strong></div>
    <div class="stat-item"><span>Total scheduled</span><strong>${missions.length}</strong></div>
    <div class="stat-item"><span>Open threads</span><strong>${loops.length}</strong></div>
  </div>

  ${buildCalendarHtml(d.agent, missions, 'cal')}

  <div class="planner-layout">
    <div class="planner-column">
      <div class="card">
        <h2>Add Shared Event or Task</h2>
        <div class="form-grid">
          <label class="wide">What is happening or to be done?
            <input id="mtitle" placeholder="e.g. Dinner reservation at 7pm, or Research flight options" required>
          </label>
          <label class="wide">Details & constraints
            <input id="mdetail" placeholder="Time, location, specific requests or questions">
          </label>
          <label>Target or event date
            <input id="mwhen" placeholder="YYYY-MM-DD" type="date" value="${esc(selectedCalDate)}">
          </label>
        </div>
        <div class="actions" style="margin-top:14px">
          <button class="act" id="madd">Save to shared calendar</button>
        </div>
        <p class="dim small" style="margin-top:10px">Your companion references and remembers all calendar items during conversation and autonomous routines.</p>
      </div>

      <div class="card">
        <h2>Autonomous Open Threads (${loops.length})</h2>
        <div class="threads-container">
          ${loops.length?loops.map(l=>`
            <div class="thread-card">
              <div class="thread-title">💬 ${esc(l.title)}</div>
              ${l.detail?`<p class="thread-desc">${esc(l.detail)}</p>`:''}
              <div class="dim small" style="margin-top:6px">Context: ${esc(l.gentle_use)}</div>
            </div>`).join(''):'<p class="dim small">No active open threads tracked across sessions.</p>'}
        </div>
      </div>
    </div>

    <div class="planner-column">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h2 style="margin:0">All Scheduled Tasks (${missions.length})</h2>
          <span class="pill ${openCount>0?'status-good':''}">${openCount} active</span>
        </div>
        <div class="missions-container">
          ${missions.length?missions.map(x=>`
            <div class="mission-card ${x.status==='open'?'is-open':''}">
              <div class="mission-header" style="display:flex;justify-content:space-between;align-items:center">
                <strong style="font-size:14px;color:var(--ink)">${esc(x.title)}</strong>
                <span class="pill ${x.status==='open'?'status-good':x.status==='dropped'?'status-bad':''}">${esc(x.status)}</span>
              </div>
              ${x.detail?`<p class="mission-details" style="margin:8px 0;font-size:13px;color:var(--dim)">${esc(x.detail)}</p>`:''}
              ${x.detail_update?`<div class="mission-update-box" style="margin:8px 0"><strong>Update:</strong> ${esc(x.detail_update)}</div>`:''}
              <div class="mission-footer" style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding-top:8px;border-top:1px solid var(--surface-3)">
                <span class="dim small">${x.wanted_by?'Target: '+esc(x.wanted_by):'No target date'}</span>
                ${x.status==='open'?`<button class="quiet small-btn" data-drop="${esc(x.id)}">Drop task</button>`:''}
              </div>
            </div>`).join(''):'<p class="dim small" style="padding:20px;text-align:center">No active tasks in queue.</p>'}
        </div>
      </div>
    </div>
  </div>`;

  wireCalendarComponent($('loops'), missions, d.agent, () => workspaceHandlers.loops(), 'cal');
  if($('mwhen'))$('mwhen').value=selectedCalDate;

  $('madd').onclick=async()=>{
    const title=$('mtitle').value.trim();if(!title)return;
    await api('/missions',{method:'POST',body:JSON.stringify({title,detail:$('mdetail').value,wanted_by:$('mwhen').value})});
    notice('Event saved to shared calendar.');
    await workspaceHandlers.loops();
  };
  for(const b of $('loops').querySelectorAll('[data-drop]')){
    b.onclick=async()=>{
      await api(`/missions/${b.dataset.drop}/drop`,{method:'POST'});
      notice('Task dropped.');
      await workspaceHandlers.loops();
    };
  }
};

// Management retains the native adapters; panel tabs reduce the long setup form.
async function showGatewayActivity(){
  const data=await api('/activity');
  dialog('Gateway activity',`<p class="dim">Latest recorded job results and saved creations. Refresh to check again.</p><button class="quiet" id="refresh-activity">Refresh</button><div class="activity-feed">${data.events.map(e=>`<article class="moment-row"><div><span class="pill ${e.status==='error'?'status-bad':''}">${esc(e.status)}</span><p class="small dim">${e.at?when(e.at):'No run recorded'}</p></div><div><strong>${esc(e.title)}</strong>${e.detail?`<p class="small warn">${esc(e.detail)}</p>`:''}${e.kind==='job'?`<p class="dim small">${e.enabled?'Enabled':'Paused'} · Next: ${e.next?when(e.next):'Not scheduled'}</p>`:inlineMedia(e.media)}</div></article>`).join('')||'<p>No activity recorded yet.</p>'}</div>`);
  $('refresh-activity').onclick=showGatewayActivity;
}
const titled={identity:['Identity','Appearance specifications, persona definitions, and SOUL configuration.']};
for(const [id,[title,description]] of Object.entries(titled)){const original=workspaceHandlers[id]||({identity:renderIdentity})[id];if(!original)continue;workspaceHandlers[id]=async()=>{await original();if(current!==id)return;const page=$(id);if(!page.querySelector('.page-title'))page.insertAdjacentHTML('afterbegin',heading(title,description));};}
document.addEventListener('keydown',e=>{if(!$('product-dialog').open||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;if(e.key==='ArrowRight')$('next-photo')?.click();if(e.key==='ArrowLeft')$('previous-photo')?.click();});


/* ------------------------------------------------------------- appearance UI
   Theme, light/dark behaviour and accent colour. The swatches read their
   colours from the live stylesheet, so a preview can never disagree with the
   theme it is previewing. */
const ACCENTS=[['','Theme default'],['#6c9cff','Blue'],['#8b93ff','Indigo'],['#b388ff','Violet'],
  ['#f472b6','Pink'],['#fb7185','Rose'],['#f0b429','Amber'],['#4ade80','Green'],
  ['#2dd4bf','Teal'],['#60d5f0','Cyan']];

function themeSwatch(id,active){
  const c=window.Appearance.swatch(id);
  return `<button type="button" class="theme-card${active?' is-active':''}" data-theme-id="${id}"
    style="background:${c.bg};color:${c.ink};border-color:${active?'var(--accent)':c.edge}"
    aria-pressed="${String(active)}">
    <span class="theme-chips"><i style="background:${c.panel}"></i><i style="background:${c.accent}"></i><i style="background:${c.ink}"></i></span>
    <span class="theme-name">${esc(window.Appearance.name(id))}</span></button>`;
}
function appearancePanelHTML(){
  const s=window.Appearance.state;
  const mode=s.follow_system?'system':(window.Appearance.isDark(s.theme)?'dark':'light');
  const grid=ids=>`<div class="theme-cards-grid">${ids.map(id=>themeSwatch(id,!s.follow_system&&s.theme===id)).join('')}</div>`;
  return `
  <h2>Appearance</h2>
  <p class="dim">How this companion's workspace looks. Saved with the companion, so it follows them to your phone.</p>

  <h3 class="section-subheading">Appearance mode</h3>
  <div class="segmented" role="tablist" id="appearance-mode">
    ${[['dark','Dark'],['light','Light'],['system','Match system']].map(([v,l])=>
      `<button role="tab" type="button" data-mode="${v}" aria-selected="${String(mode===v)}">${l}</button>`).join('')}
  </div>

  <div id="appearance-themes">
    ${s.follow_system?`
      <h3 class="section-subheading">When your system is dark</h3>
      <div class="theme-cards-grid">${window.Appearance.DARK.map(id=>themeSwatch(id,s.dark_theme===id).replace('data-theme-id','data-dark-theme')).join('')}</div>
      <h3 class="section-subheading">When your system is light</h3>
      <div class="theme-cards-grid">${window.Appearance.LIGHT.map(id=>themeSwatch(id,s.light_theme===id).replace('data-theme-id','data-light-theme')).join('')}</div>`
    :grid(window.Appearance.isDark(s.theme)?window.Appearance.DARK:window.Appearance.LIGHT)}
  </div>

  <h3 class="section-subheading">Accent colour</h3>
  <p class="dim small">Used for links, highlights and the active tab. Overrides the theme's own accent.</p>
  <div class="accent-row">
    ${ACCENTS.map(([v,l])=>`<button type="button" class="accent-dot${s.accent===v?' is-active':''}" data-accent="${v}"
      title="${esc(l)}" aria-label="${esc(l)}" aria-pressed="${String(s.accent===v)}"
      style="${v?`background:${v}`:''}">${v?'':'<span class="accent-auto">A</span>'}</button>`).join('')}
    <label class="accent-custom" title="Pick any colour">
      <input type="color" id="accent-custom" value="${esc(s.accent||'#6c9cff')}" aria-label="Custom accent colour">
      <span>Custom</span>
    </label>
  </div>

  <h3 class="section-subheading">Hermes runtime</h3>
  <div style="max-width:400px">
    <label>Environment
      <select id="settings-installation-select">
        <option value="existing">Existing Hermes (system host)</option>
        <option value="managed">Kit-managed Hermes (isolated)</option>
      </select>
    </label>
    <p class="dim small">Private workspace · stored locally on this machine.</p>
  </div>`;
}
function wireAppearancePanel(panel){
  const redraw=()=>{panel.innerHTML=appearancePanelHTML();wireAppearancePanel(panel);};
  for(const b of panel.querySelectorAll('#appearance-mode button'))b.onclick=async()=>{
    const m=b.dataset.mode,s=window.Appearance.state;
    if(m==='system')await window.Appearance.set({follow_system:true});
    else await window.Appearance.set({follow_system:false,
      theme:m==='dark'?(window.Appearance.isDark(s.theme)?s.theme:s.dark_theme):(window.Appearance.isDark(s.theme)?s.light_theme:s.theme)});
    redraw();
  };
  for(const t of panel.querySelectorAll('[data-theme-id]'))t.onclick=async()=>{
    await window.Appearance.set({theme:t.dataset.themeId,
      [window.Appearance.isDark(t.dataset.themeId)?'dark_theme':'light_theme']:t.dataset.themeId});
    redraw();
  };
  for(const t of panel.querySelectorAll('[data-dark-theme]'))t.onclick=async()=>{await window.Appearance.set({dark_theme:t.dataset.darkTheme});redraw();};
  for(const t of panel.querySelectorAll('[data-light-theme]'))t.onclick=async()=>{await window.Appearance.set({light_theme:t.dataset.lightTheme});redraw();};
  for(const a of panel.querySelectorAll('[data-accent]'))a.onclick=async()=>{await window.Appearance.set({accent:a.dataset.accent});redraw();};
  const custom=panel.querySelector('#accent-custom');
  if(custom)custom.oninput=()=>window.Appearance.set({accent:custom.value});
  const setInst=panel.querySelector('#settings-installation-select');
  if(setInst&&$('installation-select')){
    setInst.value=$('installation-select').value;
    setInst.onchange=()=>{$('installation-select').value=setInst.value;$('installation-select').dispatchEvent(new Event('change'));};
  }
}


/* ------------------------------------------------- image generation settings

   Everything that configures picture-making rather than being part of doing it:
   where ComfyUI is, how to get one, the reference photograph, and the
   appearance sent to a provider. The studio had these bolted to its header;
   they belong with the rest of the configuration. */
async function imagesPanelHTML(){
  let config={},identity={},portrait={stored:false};
  try{config=(await api('/workflows')).settings||{};}catch(error){}
  try{identity=await api('/images');}catch(error){}
  try{portrait=await api('/portrait');}catch(error){}
  const settings=identity.settings||{};
  const following=settings.identity_override===null||settings.identity_override===undefined;
  const presets=settings.presets||[];
  const selected=presets.find(p=>p.id===settings.default_preset);
  const provider=selected?.provider==='comfyui'?'__comfy__':settings.default_preset||'';
  return `<script type="application/json" data-image-presets>${JSON.stringify({presets,comfy_routes:settings.comfy_routes||{},comfy_default:settings.comfy_default||''}).replaceAll("<","\\u003c")}</script>
  <h2>Image generation</h2>

  <div id="settings-image-providers" data-revision="${esc(identity.revision||'')}"></div>
  ${PROFILE!=='default'?`<label class="inline-label"><input id="set-image-inherit" type="checkbox" ${settings.inherit?'checked':''}>Use installation image defaults</label>`:''}
  <label>Provider<select id="set-image-provider">${options([['','Choose a provider'],...presets.filter(p=>p.provider!=='comfyui').map(p=>[p.id,p.name]),['__comfy__','ComfyUI']],provider)}</select></label>
  <div class="actions"><button class="quiet" id="set-image-accounts">Connect an account</button></div>
  <div id="set-image-lanes">
    <h3>Workflows by image type</h3>
    <p class="dim small">The companion chooses the image type. Its lane chooses the workflow.</p>
    <div class="lane-cards-grid">${(identity.categories||[]).map(category=>`<label class="lane-row"><span>${esc(formLabel(category))}</span><select data-image-route="${esc(category)}">${options([['','Use fallback'],...presets.map(p=>[p.id,p.name])],settings.routes?.[category]||'')}</select></label>`).join('')}</div>
    <label>Fallback workflow<select id="set-image-default">${options([['','Choose a workflow'],...presets.map(p=>[p.id,p.name])],settings.default_preset||'')}</select></label>
    <button class="quiet" id="set-image-routing">Manage workflows</button>
  </div>
  <details class="settings-advanced" id="set-comfy-section"><summary>ComfyUI connection</summary>
  <ol class="setup-checklist">
    <li class="setup-step" id="setup-step-comfy">
      <div class="setup-step-head">
        <span class="setup-step-name">Link ComfyUI</span>
        <span class="setup-state is-waiting" id="setup-comfy-state">Checking\u2026</span>
      </div>
      <input id="set-comfy-endpoint" type="url" value="${esc(config.endpoint||'')}" placeholder="http://127.0.0.1:8188">
      <small class="dim">The machine running ComfyUI. Workflows use this unless one overrides it.</small>
      <div class="studio-actions">
        <button class="quiet" id="set-comfy-check">Check again</button>
        <button class="quiet" id="set-comfy-install">Install ComfyUI here</button>
        <button class="quiet" id="set-comfy-start">Start ComfyUI</button>
      </div>
      <label class="inline-label switch-container" style="margin:6px 0 0">
        <input type="checkbox" id="set-comfy-cpu"><span class="switch-slider"></span>
        <span class="switch-label">Run on the processor instead of the graphics card</span>
      </label>
      <p class="dim small" id="set-comfy-status" role="status"></p>
    </li>
    <li class="setup-step">
      <div class="setup-step-head">
        <span class="setup-step-name">Civitai account <span class="dim">\u00b7 optional</span></span>
        <span class="setup-state ${config.api_key_configured?'is-done':'is-skipped'}" id="setup-key-state">${config.api_key_configured?'Saved':'Not set'}</span>
      </div>
      <input id="set-civitai-key" type="password" autocomplete="off"
        value="" placeholder="${config.api_key_configured?'\u2022\u2022\u2022\u2022 saved; blank keeps it':'Paste a key to download gated models'}">
      <small class="dim">Only needed for models Civitai gates behind an account.</small>
    </li>
    <li class="setup-step">
      <div class="setup-step-head">
        <span class="setup-step-name">Identify your models</span>
        <span class="setup-state ${config.hash_lookup?'is-done':'is-skipped'}" id="setup-hash-state">${config.hash_lookup?'On':'Off'}</span>
      </div>
      <label class="inline-label switch-container" style="margin:4px 0 0">
        <input type="checkbox" id="set-hash-lookup" ${config.hash_lookup?'checked':''}>
        <span class="switch-slider"></span>
        <span class="switch-label">Look up unrecognised models on Civitai by file hash</span>
      </label>
      <small class="dim">Match local model files to Civitai metadata. The first scan can take a while.</small>
    </li>
  </ol>
  </details>

  <h3 class="section-subheading">Reference photograph</h3>
  <div class="portrait-row">
    ${portrait.stored?`<img class="portrait-thumb" src="${mediaUrl('/media/portrait?t='+Date.now())}" alt="Reference portrait">`
      :'<div class="portrait-thumb portrait-empty">No photo</div>'}
    <div>
      <p class="dim">Used by providers that support a reference image.</p>
      <div class="actions">
        <label class="quiet" style="cursor:pointer">${portrait.stored?'Replace it':'Choose a photo'}<input id="set-pfile" type="file" accept="image/png,image/jpeg,image/webp" hidden></label>
        ${portrait.stored?'<button class="quiet" id="set-pdrop">Forget it</button>':''}
        <span class="dim small" id="set-pmsg"></span>
      </div>
    </div>
  </div>

  <h3 class="section-subheading">Appearance</h3>
  <p class="dim small" style="margin:0 0 12px">${following
    ? 'Uses their saved appearance.'
    : 'Uses their saved image description.'}
    Edit on the <button type="button" class="link-button" id="set-goto-identity">Identity page</button>.</p>
  <div class="studio-actions">
    <button class="act" id="set-images-save">Save image settings</button>
    <span class="dim small" id="set-images-saved" role="status"></span>
  </div>`;
}

function wireImagesPanel(panel){
  panel.querySelector('#set-image-accounts').onclick=()=>openSettings(null,'hermes-accounts');
  panel.querySelector('#set-image-routing').onclick=()=>showTab('image-studio');
  const provider=panel.querySelector('#set-image-provider'),fallback=panel.querySelector('#set-image-default');
  const savedRouting=JSON.parse(panel.querySelector('[data-image-presets]').textContent),presets=savedRouting.presets;
  let comfyRoutes={...savedRouting.comfy_routes},comfyDefault=savedRouting.comfy_default;
  const rememberComfy=()=>{if(presets.some(p=>p.id===fallback.value&&p.provider==='comfyui')){comfyDefault=fallback.value;comfyRoutes=Object.fromEntries([...panel.querySelectorAll('[data-image-route]')].filter(x=>x.value).map(x=>[x.dataset.imageRoute,x.value]));}};
  const paintProvider=()=>{
    const isComfy=provider.value==='__comfy__';
    panel.querySelector('#set-image-lanes').hidden=!isComfy;
    panel.querySelector('#set-comfy-section').hidden=!isComfy;
  };
  provider.onchange=()=>{
    if(provider.value==='__comfy__'){
      const available=presets.filter(p=>p.provider==='comfyui');
      if(!available.some(p=>p.id===fallback.value))fallback.value=available.find(p=>p.id===comfyDefault)?.id||available[0]?.id||'';
      for(const route of panel.querySelectorAll('[data-image-route]')){
        if(!available.some(p=>p.id===route.value))route.value=available.find(p=>p.id===comfyRoutes[route.dataset.imageRoute])?.id||available.find(p=>p.category===route.dataset.imageRoute)?.id||'';
      }
      panel.querySelector('#set-comfy-section').open=true;
    }else{
      rememberComfy();
      fallback.value=provider.value;
      for(const route of panel.querySelectorAll('[data-image-route]'))route.value='';
    }
    paintProvider();
  };
  paintProvider();
  const inherit=panel.querySelector('#set-image-inherit');
  if(inherit){const paint=()=>{for(const field of panel.querySelectorAll('#set-image-provider,#set-image-default,[data-image-route]'))field.disabled=inherit.checked;};inherit.onchange=paint;paint();}
  const status=panel.querySelector('#set-comfy-status');
  const goto=panel.querySelector('#set-goto-identity');
  if(goto)goto.onclick=()=>render('identity');

  /* Setting up should report itself rather than wait to be asked, so the first
     step says "Detected" on its own once ComfyUI answers. */
  const state=panel.querySelector('#setup-comfy-state');
  const setState=(node,text,kind)=>{
    if(!node)return;
    node.textContent=text;
    node.className='setup-state '+kind;
  };
  const checkComfy=async announce=>{
    setState(state,'Checking\u2026','is-waiting');
    if(announce)status.textContent='Checking\u2026';
    try{
      const result=await post('/images/check',{endpoint:panel.querySelector('#set-comfy-endpoint').value});
      const models=result.models||{};
      setState(state,'Detected','is-done');
      status.innerHTML=`<span class="good">${(models.ckpt_name||[]).length} models \u00b7 ${(models.lora_name||[]).length} LoRAs</span>`;
    }catch(error){
      setState(state,'Not found','is-missing');
      status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;
    }
  };
  const comfySection=panel.querySelector('#set-comfy-section');
  if(comfySection.open)checkComfy(false);else setState(state,'Optional','is-skipped');
  comfySection.ontoggle=()=>{if(comfySection.open&&state.textContent==='Optional')checkComfy(false);};
  panel.querySelector('#set-comfy-check').onclick=()=>checkComfy(true);

  const hash=panel.querySelector('#set-hash-lookup');
  if(hash)hash.onchange=()=>setState(panel.querySelector('#setup-hash-state'),
    hash.checked?'On':'Off',hash.checked?'is-done':'is-skipped');
  panel.querySelector('#set-comfy-install').onclick=async()=>
    action('/images/install',{cpu:panel.querySelector('#set-comfy-cpu').checked},()=>notice('ComfyUI installed.'));
  panel.querySelector('#set-comfy-start').onclick=async()=>
    action('/images/start',{cpu:panel.querySelector('#set-comfy-cpu').checked},()=>notice('ComfyUI starting.'));

  const pfile=panel.querySelector('#set-pfile');
  if(pfile)pfile.onchange=async()=>{
    const file=pfile.files[0];if(!file)return;
    const message=panel.querySelector('#set-pmsg');
    message.textContent='storing…';
    try{
      await uploadPortrait(file);
      portraitVersion=Date.now();await refreshPortraitState();
      await render('settings');
    }catch(error){message.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
  const pdrop=panel.querySelector('#set-pdrop');
  if(pdrop)pdrop.onclick=async()=>{
    if(!confirm('Remove the reference photograph?'))return;
    await api('/portrait',{method:'DELETE'});
    portraitVersion=Date.now();await refreshPortraitState();
    await render('settings');
  };

  panel.querySelector('#set-images-save').onclick=async()=>{
    const saved=panel.querySelector('#set-images-saved');
    saved.textContent='Saving…';
    try{
      const images=await api('/images');
      if(images.revision!==panel.querySelector('#settings-image-providers').dataset.revision)throw Error('Image settings changed elsewhere. Reload this page before saving.');
      if(provider.value==='__comfy__'&&!fallback.value&&!([...panel.querySelectorAll('[data-image-route]')].every(x=>x.value)))throw Error('Choose a fallback workflow or assign every image type.');
      const endpoint=panel.querySelector('#set-comfy-endpoint').value;
      const key=panel.querySelector('#set-civitai-key').value;
      const current=(await api('/workflows')).settings||{};
      await post('/workflows/settings',{...current,endpoint,
        hash_lookup:Boolean(hash&&hash.checked),
        ...(key?{api_key:key}:{})});
      if(key)setState(panel.querySelector('#setup-key-state'),'Saved','is-done');
      if(provider.value==='__comfy__')rememberComfy();
      images.settings.comfy_routes=comfyRoutes;images.settings.comfy_default=comfyDefault;
      images.settings.inherit=Boolean(inherit?.checked);
      images.settings.default_preset=panel.querySelector('#set-image-default').value;
      images.settings.routes=Object.fromEntries([...panel.querySelectorAll('[data-image-route]')].filter(x=>x.value).map(x=>[x.dataset.imageRoute,x.value]));
      const imageSave=await post('/images',{settings:images.settings,revision:images.revision});
      panel.querySelector('#settings-image-providers').dataset.revision=imageSave.revision;
      saved.textContent='Saved';clearEditorDirty(editorScope(panel));
    }catch(error){saved.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  };
}

const identityBase=workspaceHandlers.identity;
workspaceHandlers.identity=async()=>{
  await identityBase();if(current!=='identity')return;
  // Four buttons above the document turned the page into a control panel. The
  // document is the page; the tools that act on the whole file live in one menu
  // beside its heading, and the portrait moved to the image studio with the
  // rest of the image plumbing.
  const present=new Set([...$('identity').querySelectorAll('[data-passage]')].map(x=>x.dataset.passage));
  const missing=['core','appearance','relationship','voice'].filter(name=>!present.has(name));
  const tools=$('identity-tools');
  if(!tools)return;
  tools.innerHTML=`<details class="tool-menu" id="identity-tool-menu">
    <summary class="quiet">Document tools</summary>
    <div class="tool-menu-list">
      <button class="tool-menu-item" id="edit-full-soul"><strong>Edit the whole file</strong>
        <span>Raw markdown, including anything written outside these sections.</span></button>
      <button class="tool-menu-item" id="visual-builder"><strong>Build an appearance</strong>
        <span>Compose a description from the catalogue, then review it before it is saved.</span></button>
      <button class="tool-menu-item" id="repair-sections"><strong>Restore missing sections</strong>
        <span>${missing.length?`Missing now: ${missing.join(', ')}.`:'Re-wraps a hand-edited file. Existing writing is preserved.'}</span></button>
      <button class="tool-menu-item" id="tools-image-studio"><strong>Image studio</strong>
        <span>Reference portrait and the appearance sent to image providers.</span></button>
    </div></details>`;
  if(missing.length)$('soul-heading').insertAdjacentHTML('beforebegin',
    `<div class="notice-strip"><p><strong>${missing.length} section${missing.length===1?' is':'s are'} missing.</strong>
      ${esc(missing.join(', '))} — Hermes reads whatever is there, so this companion is running short of a definition.</p>
      <button class="quiet" id="repair-inline">Restore them</button></div>`);
  // Any tool that opens a dialog closes the menu behind it.
  for(const b of tools.querySelectorAll('.tool-menu-item'))
    b.addEventListener('click',()=>{$('identity-tool-menu').open=false;});
  $('tools-image-studio').onclick=()=>showTab('image-studio');

  const repair=async()=>{
    if(!await confirmEditorLeave('identity'))return;
    await post('/identity-repair');await render('identity');
    notice('Missing sections restored. Existing writing was preserved.');
  };
  $('repair-sections').onclick=repair;
  if($('repair-inline'))$('repair-inline').onclick=repair;

  $('edit-full-soul').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;const list=await api('/documents');let selected='SOUL.md',revision='';dialog('Edit companion documents',`<p>Every save keeps a backup. Edit the complete document, including writing created outside the kit. Other vault documents can be edited in Vault.</p><label>Document<select id="full-document">${options(list.documents.map(x=>[x,x]),selected)}</select></label><textarea id="full-soul" style="height:55vh"></textarea><button class="act" id="save-full-soul">Save document</button>`);const read=async()=>{if(!await confirmEditorLeave('dialog')){$('full-document').value=selected;return;}selected=$('full-document').value;const d=await api('/soul-document?document='+encodeURIComponent(selected));revision=d.revision;$('full-soul').value=d.text;};await read();$('full-document').onchange=read;$('save-full-soul').onclick=async()=>{await post('/soul-document',{document:selected,text:$('full-soul').value,revision});clearEditorDirty('dialog');$('product-dialog').close();await render('identity');notice('Document saved with a backup.');};};
  $('visual-builder').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;const d=await api('/catalog');const rows=Object.entries(d.catalog.categories).filter(([k,v])=>v.section==='appearance');dialog('Visual creator',`<p>Choose a look, then review the complete appearance before saving.</p><label>Catalog<select id="visual-gender"><option value="female">Feminine</option><option value="male">Masculine</option></select></label><div id="visual-fields" class="form-grid"></div><button class="quiet" id="compose-look">Build description</button><label>Appearance description<textarea id="visual-description"></textarea></label><button class="act" id="save-look">Save appearance</button>`);const populate=()=>{$('visual-fields').innerHTML=rows.filter(([k,v])=>v[$('visual-gender').value]).map(([k,v])=>`<label>${esc(v.label)}<select aria-label="${esc(v.label)}" data-visual="${esc(k)}"><option value="">Leave unspecified</option>${options(v[$('visual-gender').value].map(r=>[r.text,r.label]),'')}<option value="__custom__">Write your own…</option></select><input aria-label="Custom ${esc(v.label)}" hidden placeholder="Your description"></label>`).join('');for(const select of $('visual-fields').querySelectorAll('select'))select.onchange=()=>{select.nextElementSibling.hidden=select.value!=='__custom__';};};populate();$('visual-gender').onchange=populate;$('compose-look').onclick=()=>{$('visual-description').value=[...$('visual-fields').querySelectorAll('select')].map(s=>s.value==='__custom__'?s.nextElementSibling.value:s.value).filter(Boolean).join(' ').replaceAll('{A}',chatName()).replaceAll('{AS_LOWER}','they').replaceAll('{AS}','They').replaceAll('{AP}','their').replaceAll('{AO}','them');};$('save-look').onclick=async()=>{const body=$('visual-description').value.trim();if(!body)throw Error('Build or write an appearance first.');await post('/identity-repair',{appearance:body});await post('/identity/appearance',{body});$('product-dialog').close();await render('identity');notice('Appearance saved.');};};
};

/* The Voice studio's page and its known voices. The studio itself is drawn by
   studios.js; the Settings page reuses this same list for the engine picker. */
TABS.push(['voice','Voice studio']);const voiceSection=document.createElement('section');voiceSection.id='voice';voiceSection.hidden=true;document.querySelector('main').append(voiceSection);if(!$('tabs').querySelector('[data-tab="voice"]')){const voiceNav=document.createElement('button');voiceNav.dataset.tab='voice';voiceNav.innerHTML=icon('voice')+'<span>Voice studio</span>';voiceNav.onclick=()=>showTab('voice');($('tabs').querySelector('.nav-more')||$('tabs').lastElementChild||$('tabs')).append(voiceNav);}
const voiceChoices={edge:['en-US-AriaNeural','en-US-GuyNeural','en-GB-SoniaNeural'],piper:['en_US-lessac-medium'],kittentts:['Jasper','Bella','Luna','Bruno','Rosie','Hugo','Kiki','Leo'],openai:['alloy','echo','fable','onyx','nova','shimmer'],xai:['eve','ara','rex','sal','leo'],gemini:['Kore','Puck','Charon','Aoede'],neutts:[],elevenlabs:[],minimax:['English_expressive_narrator'],mistral:['c69964a6-ab8b-4f8a-9465-ec0925096ec8','1024d823-a11e-43ee-bf3d-d440dccc0577','98559b22-62b5-4a64-a7cd-fc78ca41faa8','5940190b-f58a-4c3e-8264-a40d63fd6883','01d985cd-5e0c-4457-bfd8-80ba31a5bc03']};
