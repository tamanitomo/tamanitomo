function mediaPrivacy(item){return item.blur?'class="concealed-media" title="Sensitive or unreviewed image · open details to reveal"':'';}
const paths={now:'M3 11 12 3l9 8v10h-6v-7H9v7H3Z',chat:'M4 4h16v12H9l-5 4Z',timeline:'M6 3v18M10 5h10M10 12h7M10 19h10',photos:'M3 4h18v16H3ZM3 16l5-5 5 5 3-3 5 5M16 8h.01',journals:'M5 3h14v18H5ZM8 7h8M8 11h8M8 15h5',creations:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',relationship:'M12 20S2 14 2 8a5 5 0 0 1 10-1 5 5 0 0 1 10 1c0 6-10 12-10 12Z',loops:'M4 5h16v16H4ZM8 2v6M16 2v6M4 11h16',knows:'M12 3v18M12 6C7 1 2 5 3 10c-3 5 2 10 9 8M12 6c5-5 10-1 9 4 3 5-2 10-9 8',vault:'M3 6h7l2 3h9v12H3Z',identity:'M8 7a4 4 0 1 0 8 0 4 4 0 1 0-8 0M4 21v-3c0-6 16-6 16 0v3',settings:'M4 7h16M4 17h16M8 4v6M16 14v6','local-models':'M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Zm5 3h6v6H9V9Zm-5 2h2m-2 4h2m14-4h2m-2 4h2m-9-11v2m4-2v2m-4 14v2m4-2v2',environment:'M12 2v4M12 18v4M2 12h4M18 12h4M5 5l3 3M16 16l3 3M19 5l-3 3M8 16l-3 3M7 12a5 5 0 1 0 10 0 5 5 0 1 0-10 0',health:'M2 12h5l3-8 4 16 3-8h5',roster:'M8 8a3 3 0 1 0 6 0 3 3 0 1 0-6 0M3 21v-3c0-5 14-5 14 0v3M17 5c5 0 5 6 0 6M20 15c2 1 2 3 2 6',search:'M10 3a7 7 0 1 0 0 14 7 7 0 1 0 0-14M16 16l5 5',download:'M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',album:'M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16l-8-4-8 4V5Z',shield_alert:'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm0-14v4m0 4h.01',shield_check:'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-2-10 2 2 4-4',info:'M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z',trash:'M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2',close:'M18 6 6 18M6 6l12 12',chevron_left:'M15 18l-6-6 6-6',chevron_right:'M9 18l6-6-6-6',voice:'M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm5 9a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z','image-studio':'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',more:'M5 12h.01M12 12h.01M19 12h.01',pin:'M12 17v5M9 3h6l-1 7 3 3v2H7v-2l3-3-1-7Z'};
const icon=name=>`<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[name]||paths.creations}"/></svg>`;
const tabLabel=id=>({chat:'Chat',photos:'Photos',journals:'Journal',now:'Home'}[id])||(TABS.find(t=>t[0]===id)?.[1])||({'image-studio':'Image studio','voice':'Voice studio','local-models':'Local models','companion-edit':'Edit companion'}[id])||id;
/* ---------------------------------------------------------------- navigation
   One destination map drives three surfaces: the desktop rail, the mobile
   bottom bar (whichever destinations the person pinned), and the More
   directory. Anything added here appears in all three. */
const primaryDestinations=['now','chat','photos','journals'];
const navGroups=[
  ['Life & memories', ['timeline','relationship','knows','loops','identity','creations','vault']],
  ['Studios',         ['image-studio','voice','local-models']],
  ['Setup & system',  ['settings','environment','health','roster']]
];
/* One line each, so the More page explains itself without being read twice. */
const navBlurb={
  now:'Today at a glance',chat:'Talk with your companion',timeline:'Their day, hour by hour',
  photos:'Every picture and album',journals:'The reflections they write',
  creations:'Files and things they have made',relationship:'Feelings, milestones and repair',
  loops:'Tasks, plans and open threads',knows:'What they remember about you',
  vault:'Shared notes and documents',identity:'Who they are — persona and soul',
  settings:'Boundaries, quiet hours and appearance',environment:'Models, providers and the gateway',
  health:'Scheduled jobs and diagnostics',roster:'All of your companions',
  'image-studio':'Compose and generate images',voice:'Voice, speech and cloning',
  'local-models':'Run models on your own hardware'
};
/* The bottom bar has room for one word. */
const navShort={now:'Home',chat:'Chat',timeline:'Timeline',photos:'Photos',journals:'Journal',
  creations:'Files',relationship:'Together',loops:'Tasks',knows:'Memory',vault:'Vault',
  identity:'Identity',settings:'Settings',environment:'Hermes',health:'Jobs',roster:'Companions',
  'image-studio':'Images',voice:'Voice','local-models':'Models',more:'More'};
const shortLabel=id=>navShort[id]||tabLabel(id);
const navDestinations=[...primaryDestinations,...navGroups.flatMap(([,ids])=>ids)];
const navigationButtons=ids=>ids.map(id=>`<button data-tab="${id}">${icon(id)}<span>${esc(tabLabel(id))}</span></button>`).join('');

/* Desktop rail: Core primary section is always visible and prominent; secondary groups are collapsible. */
$('tabs').innerHTML=`<div class="nav-primary-section">${navigationButtons(primaryDestinations)}</div>`+
  navGroups.map(([label,ids],i)=>`<details class="nav-group-collapsible" ${i<1?'open':''}><summary>${esc(label)}</summary><div class="nav-group-items">${navigationButtons(ids)}</div></details>`).join('');
for(const button of $('tabs').querySelectorAll('button'))button.onclick=()=>showTab(button.dataset.tab);

/* Mobile bottom bar: the pinned destinations, then More, always last. */
const navPins=()=>{
  let saved=(window.Appearance&&window.Appearance.state.nav_pins)||[];
  if(!saved.length)return ['now','chat','photos','journals'];
  if(saved.includes('now')&&saved[0]!=='now'){
    saved=['now',...saved.filter(x=>x!=='now')];
  }
  const pins=saved.filter(id=>navDestinations.includes(id)).slice(0,4);
  return pins.length?pins:['now','chat','photos','journals'];
};
function renderTabbar(){
  const bar=$('tabbar');if(!bar)return;
  const slots=[...navPins().map(id=>[id,false]),['more',true]];
  bar.innerHTML=slots.map(([id,fixed])=>`<button data-tab="${id}"${fixed?' class="is-more"':''} aria-current="${String(current===id)}">${icon(id)}<span>${esc(shortLabel(id))}</span></button>`).join('');
  for(const b of bar.querySelectorAll('button'))b.onclick=()=>showTab(b.dataset.tab);
}
window.addEventListener('appearance-change',renderTabbar);

window.productNavigate=name=>{
  document.body.dataset.page=name;
  for(const el of document.querySelectorAll('[data-creating]'))delete el.dataset.creating;
  const tabs=$('tabs');
  if(tabs){const parent=tabs.querySelector(`details:has([data-tab="${name}"])`);if(parent)parent.open=true;}
  if($('crumb-page'))$('crumb-page').textContent=tabLabel(name);
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
    const pinned=pins.includes(id),full=pins.length>=4;
    return `<div class="more-row${pinned?' is-pinned':''}">
      <button class="more-go" data-tab="${id}">${icon(id)}<span><strong>${esc(tabLabel(id))}</strong><small>${esc(navBlurb[id]||'')}</small></span></button>
      <button class="pin-toggle" data-pin="${id}" aria-pressed="${String(pinned)}" ${!pinned&&full?'disabled':''}
        title="${pinned?'Remove from the bottom bar':(full?'Unpin something first — the bar holds four':'Pin to the bottom bar')}"
        aria-label="${pinned?'Unpin '+tabLabel(id):'Pin '+tabLabel(id)+' to the bottom bar'}">${pinned?'★':'☆'}</button>
    </div>`;
  };
  // On a phone the rail is hidden, so the switchers that live in it belong here.
  const switcher=`<div class="card more-switcher">
      <label>Your companion<select id="more-companion">${$('companion-select').innerHTML}</select></label>
      <label>Environment<select id="more-installation">${$('installation-select').innerHTML}</select></label>
    </div>`;
  const allNavGroups=[
    ['Core pages', primaryDestinations],
    ...navGroups
  ];
  $('more').innerHTML=heading('More','Every part of the workspace. Star up to four to keep them on the bottom bar.')+switcher+
    `<div class="pin-preview"><span class="eyebrow">Your bottom bar</span><div class="pin-preview-bar">${
      [...pins,'more'].map(id=>`<span${id==='more'?' class="is-more"':''}>${icon(id)}<small>${esc(shortLabel(id))}</small></span>`).join('')
    }</div><p class="dim small">More always keeps the last slot, so nothing is ever more than two taps away.</p></div>`+
    allNavGroups.map(([label,ids])=>`<section class="more-group"><h2>${esc(label)}</h2><div class="more-list">${ids.map(row).join('')}</div></section>`).join('');
  for(const b of $('more').querySelectorAll('[data-tab]'))b.onclick=()=>showTab(b.dataset.tab);
  // Mirror the rail's selects rather than moving them, so both layouts keep working.
  const mirror=(here,there)=>{const a=$(here),b=$(there);if(!a||!b)return;a.value=b.value;
    a.onchange=()=>{b.value=a.value;b.dispatchEvent(new Event('change'));};};
  mirror('more-companion','companion-select');mirror('more-installation','installation-select');
  for(const b of $('more').querySelectorAll('[data-pin]'))b.onclick=async()=>{
    const id=b.dataset.pin,next=pins.includes(id)?pins.filter(x=>x!==id):[...pins,id];
    if(!next.length){notice('Keep at least one destination on the bar.');return;}
    await window.Appearance.set({nav_pins:next});
    render('more');
  };
};
$('refresh-page').onclick=async()=>{if(await confirmEditorLeave(current))render(current);};
$('close-dialog').onclick=async()=>{if(await confirmEditorLeave('dialog'))$('product-dialog').close();};
$('product-dialog').addEventListener('cancel',async e=>{e.preventDefault();if(await confirmEditorLeave('dialog'))$('product-dialog').close();});
function dialog(title,html){$('dialog-title').textContent=title;$('dialog-body').innerHTML=html;if(!$('product-dialog').open)$('product-dialog').showModal();}
$('open-search').onclick=async()=>{if(!await confirmEditorLeave('dialog'))return;dialog('Go to page',`<input id="command-search" aria-label="Find a page" placeholder="Photos, providers, memories…"><div id="command-results" class="search-results"></div>`);const update=()=>{$('command-results').innerHTML=TABS.filter(t=>t[0]!=='more').filter(t=>(t[1]+' '+t[0]+' '+({environment:'providers models gateway administration hermes',health:'cron schedules diagnostics jobs',knows:'facts memories',vault:'files notes',settings:'contact preferences quiet hours','image-studio':'images workflows','voice':'audio cloning speech','local-models':'local models llama gguf hardware vulkan server'}[t[0]]||'')).toLowerCase().includes($('command-search').value.toLowerCase())).map(([id,label])=>`<button class="quiet" data-go="${id}">${icon(id)}${label}</button>`).join('');for(const b of $('command-results').querySelectorAll('button'))b.onclick=()=>{$('product-dialog').close();showTab(b.dataset.go);};};$('command-search').oninput=update;update();$('command-search').focus();};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='k'){e.preventDefault();$('open-search').click();}});
let profileTimezone;
const stamp=(value,opts={})=>{if(!value)return 'Not recorded';const d=new Date(value);return Number.isNaN(d.getTime())?value:new Intl.DateTimeFormat(undefined,{timeZone:profileTimezone,month:'short',day:'numeric',...opts}).format(d);};
const dayKey=value=>{if(!value)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;try{return new Intl.DateTimeFormat('en-CA',{timeZone:profileTimezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));}catch{return '';}};
const when=value=>stamp(value,{hour:'numeric',minute:'2-digit'});
const plain=value=>String(value||'').replace(/<!--[^]*?-->/g,'').replace(/[#*_`>\[\]]/g,'').trim();
const excerpt=(value,n=180)=>{const text=plain(value);return text.length>n?text.slice(0,n).replace(/\s+\S*$/,'')+'…':text;};
const empty=(symbol,title,body,button='')=>`<div class="empty-state">${icon(symbol)}<h3>${esc(title)}</h3><p>${esc(body)}</p>${button}</div>`;
const jump=(id,label,primary=false)=>`<button class="${primary?'act':'link-button'}" data-route="${id}">${esc(label)} ${icon(id)}</button>`;
let preferencePanel='contact';
function wireRoutes(root){for(const b of root.querySelectorAll('[data-route]'))b.onclick=()=>{if(b.dataset.preference)preferencePanel=b.dataset.preference;if(b.dataset.environmentPanel){environmentPanel=Number(b.dataset.environmentPanel);environmentFocus=true;}showTab(b.dataset.route);};}
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
  html+=`<div class="wardrobe-block"><div class="wardrobe-block-title"><span>Currently Wearing</span><span class="dim small">${wearing.length} piece${wearing.length===1?'':'s'}</span></div><div class="wardrobe-chip-list">${wearing.map(w=>`<span class="wardrobe-chip is-wearing" title="${esc(typeof w==='string'?w:(w.description||w.id))}">👕 ${esc(typeof w==='string'?w:(w.description||w.id))}</span>`).join('')||'<span class="dim small">Casual wear</span>'}</div></div>`;
  if(laidOut&&(laidOutItems.length||laidOut.plan?.intent)){
    const plan=laidOut.plan||{};
    html+=`<div class="wardrobe-block" style="border-left:3px solid var(--warn);margin-top:12px"><div class="wardrobe-block-title"><span style="color:var(--warn)">✨ Laid Out For Tomorrow</span><span class="dim small">${laidOutItems.length} pieces</span></div>${laidOutItems.length?`<div class="wardrobe-chip-list">${laidOutItems.map(w=>`<span class="wardrobe-chip is-laid-out" title="${esc(typeof w==='string'?w:(w.description||w.id))}">🛏️ ${esc(typeof w==='string'?w:(w.description||w.id))}</span>`).join('')}</div>`:''}${plan.intent?`<div class="laid-out-intent-quote">“${esc(plan.intent)}”</div>`:''}</div>`;
  }
  if(hamper.length||washing.length){
    html+=`<div class="wardrobe-block" style="margin-top:12px"><div class="wardrobe-block-title"><span>Hamper & Wash</span><span class="dim small">${hamper.length} dirty${washing.length?` · ${washing.length} in wash`:''}</span></div><div class="wardrobe-chip-list">${washing.map(w=>`<span class="wardrobe-chip is-washing" title="In the wash: ${esc(w.description||w.id)}">🫧 ${esc(w.description||w.id)}</span>`).join('')}${hamper.map(w=>`<span class="wardrobe-chip is-hamper" title="In the hamper: ${esc(w.description||w.id)}">🧺 ${esc(w.description||w.id)}</span>`).join('')}</div></div>`;
  }
  if(clean.length){
    html+=`<details class="wardrobe-block" style="cursor:pointer;margin-top:12px"><summary class="wardrobe-block-title"><span>Clean in Closet</span><span class="dim small">${clean.length} piece${clean.length===1?'':'s'}</span></summary><div class="wardrobe-chip-list" style="margin-top:8px">${clean.map(w=>`<span class="wardrobe-chip is-clean" title="${esc(w.description||w.id)}">✨ ${esc(w.description||w.id)}</span>`).join('')}</div></details>`;
  }
  html+=`</div>`;
  return html;
}

function renderHeroMetersContent(emotions,bars){
  const meters=emotions?.state?.meters||bars?.feelings?.meters||{};
  const config=[
    {key:'warmth',label:'Warmth',icon:'🔥',color:'linear-gradient(90deg,#f43f5e,#fb923c)',glow:'rgba(244,63,94,0.4)',defaultVal:0.8},
    {key:'trust',label:'Trust',icon:'🛡️',color:'linear-gradient(90deg,#0ea5e9,#10b981)',glow:'rgba(14,165,233,0.4)',defaultVal:0.75},
    {key:'irritation',label:'Irritation',icon:'⚡',color:'linear-gradient(90deg,#eab308,#f59e0b)',glow:'rgba(234,179,8,0.4)',defaultVal:0.05},
    {key:'longing',label:'Missing you',icon:'⏳',color:'linear-gradient(90deg,#8b5cf6,#d946ef)',glow:'rgba(139,92,246,0.4)',defaultVal:0.3}
  ];
  return config.map(m=>{
    const raw=meters[m.key]!=null?meters[m.key]:m.defaultVal;
    const pct=Math.round(Math.max(0,Math.min(1,raw))*100);
    return `<div class="hero-meter-item"><div class="hero-meter-label-row"><span class="hero-meter-label"><span class="meter-icon">${m.icon}</span> ${m.label}</span><span class="hero-meter-pct">${pct}%</span></div><div class="hero-meter-bar-track"><div class="hero-meter-bar-fill" style="width:${pct}%;background:${m.color};box-shadow:0 0 8px ${m.glow}"></div></div></div>`;
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
  let bannerHTML=d.problems.length?`<button class="link-button small" id="header-health">${d.problems.length} item${d.problems.length===1?'':'s'} to review</button>`:'';
  if(!bannerHTML&&updateInfo?.has_update){bannerHTML=`<button class="link-button small" id="header-update" style="color:var(--warn)">✨ Update v${esc(updateInfo.latest_version)} available</button>`;}
  $('banner').innerHTML=bannerHTML;
  if($('header-health'))$('header-health').onclick=()=>showTab('health');
  if($('header-update'))$('header-update').onclick=()=>showTab('environment');

  const s=d.state?.state;
  const photo=content.items.find(x=>x.kind==='image');
  const entry=journal.entries[0];
  const stage=Number(emotions?.intimacy?.stage??d.intimacy?.stage??0);
  const wearingPieces=filterWardrobeItems(closet?.wearing||[],stage);
  const rawOutfit=Array.isArray(s?.outfit)?filterWardrobeItems(s.outfit,stage):[];
  const currentOutfit=wearingPieces.map(x=>x.description||x.id).join(', ')||rawOutfit.map(x=>x.description||x.id).join(', ')||(typeof s?.outfit==='string'&&filterWardrobeItems([s.outfit],stage).length?s.outfit:'');
  const feelingBadge=emotions?.intimacy?`${emotions.intimacy.stage_badge} (${emotions.intimacy.score}%)`:(d.intimacy?`${d.intimacy.stage_badge} (${d.intimacy.score}%)`:'');

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
  ${d.problems.length?`<div class="notice-strip"><p>${esc(d.problems[0])}${d.problems.length>1?` · ${d.problems.length-1} more to review`:''}</p>${jump('health','Review')}</div>`:''}
  ${updateInfo?.has_update?`<div class="notice-strip" style="border-left-color:var(--warn);background:color-mix(in srgb,var(--warn) 8%,transparent)"><p><strong>Tamanitomo v${esc(updateInfo.latest_version)}</strong> is available. Run <code>./update.sh</code> in your host terminal to update.</p>${jump('environment','View')}</div>`:''}

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
            ${feelingBadge?`<div class="presence-stage-badge"><span class="pill status-good" style="font-size:11.5px;font-weight:600">${esc(feelingBadge)}</span></div>`:''}
          </div>

          <div class="presence-status-stack">
            <div class="presence-chip-row"><span class="chip-label">✨ Status:</span> <span class="chip-val">${esc(s?.activity||'Resting quietly')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">📍 Location:</span> <span class="chip-val">${esc(s?.location||'Home')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">💭 Mood:</span> <span class="chip-val">${esc(s?.mood||'Peaceful')}</span></div>
            <div class="presence-chip-row"><span class="chip-label">👗 Attire:</span> <span class="chip-val">${esc(currentOutfit||'Casual wear')}</span></div>
          </div>

          ${latestThought?`
          <div class="presence-thought-quote">
            <div class="quote-mark">“</div>
            <p class="thought-text">${esc(latestThought)}</p>
            <div class="thought-footer">
              <span class="dim small">${thoughtSource}</span>
              <button class="act small quote-read-btn" id="home-open-journal">
                📖 Read ${esc(d.agent)}'s Journal
              </button>
            </div>
          </div>`:''}

          <div class="presence-actions-bar">
            <button class="act small" data-route="chat">
              <svg class="icon" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              Talk with ${esc(d.agent)}
            </button>
            ${!latestThought?`
            <button class="act small" id="home-open-journal">
              📖 Read ${esc(d.agent)}'s Journal
            </button>`:''}
            <button class="quiet small" data-route="photos">
              <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
              Photos
            </button>
            <button class="quiet small" data-route="loops">
              <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              Plans
            </button>
          </div>
        </div>

        <div class="presence-atmosphere-column">
          <div class="hero-meters-card">
            <div class="hero-meters-header">
              <span class="eyebrow" style="margin:0;font-size:11px;letter-spacing:0.08em">Atmosphere</span>
              ${emotions?.state?.temperament||emotions?.state?.personality?`<span class="pill small" style="font-size:10px;padding:2px 7px">${esc(emotions.state.temperament||emotions.state.personality)}</span>`:''}
            </div>
            <div class="hero-meters-stack">
              ${renderHeroMetersContent(emotions,d.bars)}
            </div>
            <div class="hero-meters-footer">
              <span class="dim small" style="font-size:11px">Synchronized with companion state</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="stat-strip">
    <button data-route="photos"><span>Photos & captures</span><strong>${content.items.filter(x=>x.kind==='image').length}</strong><span>${timeline.enabled?'Scheduled captures active':'Scheduled captures paused'}</span></button>
    <button data-route="journals"><span>Journal entries</span><strong>${journal.total??journal.entries.length}</strong><span>${entry?'Latest · '+entry.day:'No entries yet'}</span></button>
    <button data-route="loops"><span>Plans & calendar</span><strong>${d.loops.length+d.missions.length}</strong><span>Shared calendar items</span></button>
    <button data-route="relationship"><span>Closeness & stage</span><strong>${emotions?.intimacy?emotions.intimacy.stage_badge.split('·')[0].trim():'Bond'}</strong><span>${emotions?.intimacy?emotions.intimacy.score+'% attunement':'Tamagotchi progression'}</span></button>
  </div>

  <div class="home-columns">
    <div>
      <div class="section-heading"><h2>From the journal</h2>${jump('journals','All reflections')}</div>
      ${entry?`
      <article class="card journal-preview" style="border-radius:var(--r-lg);padding:26px">
        <span class="eyebrow" style="color:var(--dim)">Nightly reflection · ${esc(entry.day)}</span>
        <h3 style="margin:10px 0 14px">${new Intl.DateTimeFormat(undefined,{weekday:'long',month:'short',day:'numeric'}).format(new Date(entry.day+'T12:00:00'))}</h3>
        <p style="margin:0 0 16px;line-height:1.7">${esc(excerpt(entry.text,420))}</p>
        <button class="link-button" id="read-latest" style="font-weight:600">Read entry (${Math.max(1,Math.ceil(entry.words/220))} min) →</button>
      </article>`:empty('journals','No journal entries yet','Daily reflections are recorded automatically by the scheduled nightly routine at 4:00 AM.',jump('health','View routine status'))}

      <div class="section-heading"><h2>Recent moments & captures</h2>${jump('photos','Open photo library')}</div>
      <div class="grid">
        ${content.items.slice(0,3).map((x,i)=>`
          <button class="card photo-card" data-home-file="${i}">
            ${x.kind==='image'?`<div class="photo-wrap"><img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}"></div>`:`<div class="file-art">${icon(x.kind==='writing'?'journals':'creations')}</div>`}
            <div class="photo-meta"><p>${esc(x.title)}</p><small>${esc(x.kind)} · ${when(x.at)}</small></div>
          </button>`).join('')||'<p class="dim">Photos and captures appear here as your companion records their day.</p>'}
      </div>
    </div>

    <div>
      <div class="section-heading"><h2>Current presence & closet</h2></div>
      ${renderWardrobeCard(closet,s,stage)}

      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <h2 style="margin:0">Active plans & calendar</h2>
          <span class="pill">${d.missions.length} item${d.missions.length===1?'':'s'}</span>
        </div>
        ${d.missions.length?`
        <div style="display:flex;flex-direction:column;gap:8px">
          ${d.missions.slice(0,3).map(m=>`
            <div style="padding:8px 10px;background:var(--surface);border:1px solid var(--edge);border-radius:6px;font-size:13px">
              <strong style="color:var(--ink)">${esc(m.title)}</strong>
              ${m.wanted_by?`<span class="dim small" style="display:block;margin-top:2px">📅 Target: ${esc(m.wanted_by)}</span>`:''}
            </div>`).join('')}
        </div>`:''
        }
        <div style="margin-top:14px">${jump('loops','Open shared calendar')}</div>
      </div>

      <div class="card">
        <span class="eyebrow">Conversation status</span>
        <p>${esc(d.thread?.available?d.thread.register:'No active conversation thread.')}</p>
        <p class="dim small">${d.thread?.last_from_human?'Last message '+ago(d.thread.last_from_human):'Thread synchronized across channels (Web, Telegram, Discord).'}</p>
        ${jump('chat','Open conversation')}
      </div>
    </div>
  </div>`;

  wireRoutes($('now'));
  if($('home-open-journal'))$('home-open-journal').onclick=()=>{if(entry?.id)selectedJournal=entry.id;showTab('journals');};
  if($('read-latest'))$('read-latest').onclick=()=>{if(entry?.id)selectedJournal=entry.id;showTab('journals');};
  for(const b of $('now').querySelectorAll('[data-home-file]'))b.onclick=()=>openContent(content.items[Number(b.dataset.homeFile)]);
};
let selectedJournal=null;
const journalBrowse={query:'',month:''};
let journalPageGeneration=0;
workspaceHandlers.journals=async()=>{
  const pageGeneration=++journalPageGeneration;
  $('journals').innerHTML=heading('Journal','Daily reflections written by your companion in their own voice during their nightly ritual.')+`<div class="filters"><label>Search entries<input id="journal-search" type="search" maxlength="200" placeholder="Search entries by topic or keyword…"></label><label>Month<input type="month" id="journal-month"></label><button class="quiet" id="journal-clear">Clear</button></div><p id="journal-status" class="dim small" role="status"></p><div id="journal-warnings"></div><div class="reader-layout"><details class="journal-browser" id="journal-browser" ${matchMedia('(max-width:900px)').matches?'':'open'}><summary id="journal-picker-label">Browse entries</summary><div class="reader-list" id="journal-list"></div><button class="quiet" id="journal-older" hidden>Load older entries</button></details><article id="journal-page"></article></div>`;
  $('journal-search').value=journalBrowse.query;$('journal-month').value=journalBrowse.month;
  let entries=[],cursor=null,request=0,selection=0,timer;
  const alive=()=>current==='journals'&&pageGeneration===journalPageGeneration;
  const choose=async (id,fromPicker=false)=>{
    const token=++selection;let entry=entries.find(x=>x.id===id);if(!entry)return;
    selectedJournal=id;for(const b of $('journal-list').querySelectorAll('button'))b.setAttribute('aria-current',String(b.dataset.entry===id));
    if(entry.truncated){$('journal-page').innerHTML='<p class="dim" role="status">Opening the full entry…</p>';try{entry=(await api('/journals/'+encodeURIComponent(id))).entry;}catch(error){if(alive()&&selection===token)$('journal-page').innerHTML=empty('journals','Entry unavailable',error.message);return;}}
    if(!alive()||selection!==token)return;
    $('journal-picker-label').textContent='Browse entries · '+entry.day;
    const currIdx=entries.findIndex(x=>x.id===id);
    const prevEntry=currIdx>0?entries[currIdx-1]:null;
    const nextEntry=currIdx<entries.length-1?entries[currIdx+1]:null;
    $('journal-page').innerHTML=`<div class="journal-nav-bar">
      <button class="journal-nav-btn" id="journal-prev-btn" ${prevEntry?'':'disabled'} style="${prevEntry?'':'opacity:0.4;cursor:default'}">← Newer (${prevEntry?esc(prevEntry.day):'none'})</button>
      <span style="font-weight:600;font-size:13px;color:var(--ink-2)">📅 ${esc(entry.day)}</span>
      <button class="journal-nav-btn" id="journal-next-btn" ${nextEntry?'':'disabled'} style="${nextEntry?'':'opacity:0.4;cursor:default'}">Older (${nextEntry?esc(nextEntry.day):'none'}) →</button>
    </div>
    <div class="paper">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;border-bottom:1px solid color-mix(in srgb,var(--surface-2) 20%,transparent);padding-bottom:10px">
        <span class="eyebrow" style="color:var(--faint)">Daily reflection · ${Math.max(1,Math.ceil(entry.words/220))} min read</span>
        <span class="pill" style="border-color:color-mix(in srgb,var(--surface-2) 30%,transparent);color:var(--faint)">Nightly Entry</span>
      </div>
      <h2>${new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric',year:'numeric'}).format(new Date(entry.day+'T12:00:00'))}</h2>
      <div class="prose">${richText(entry.text)}</div>
      <div style="margin-top:34px;padding-top:16px;border-top:1px solid color-mix(in srgb,var(--surface-2) 20%,transparent);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <span style="font-family:Georgia,serif;font-style:italic;color:var(--faint);font-size:14px">Written during nightly introspection</span>
        <span class="dim small">${entry.words.toLocaleString()} words · ${esc(entry.source)}</span>
      </div>
    </div>`;
    if($('journal-prev-btn')&&prevEntry)$('journal-prev-btn').onclick=()=>choose(prevEntry.id);
    if($('journal-next-btn')&&nextEntry)$('journal-next-btn').onclick=()=>choose(nextEntry.id);
    if(fromPicker&&matchMedia('(max-width:900px)').matches){$('journal-browser').open=false;$('journal-page').scrollIntoView({block:'start'});}
  };
  const draw=()=>{
    $('journal-list').innerHTML=entries.map(x=>`<button data-entry="${esc(x.id)}" aria-current="${x.id===selectedJournal}"><strong>${esc(x.day)}</strong><small>${esc(excerpt(x.excerpt||x.text,110))}</small><small>${Math.max(1,Math.ceil(x.words/220))} min read</small></button>`).join('');
    for(const b of $('journal-list').querySelectorAll('button'))b.onclick=()=>choose(b.dataset.entry,true);
    $('journal-older').hidden=!cursor;
  };
  const load=async more=>{
    const token=++request;if(!more)selection++;
    const query=journalBrowse.query,month=journalBrowse.month;
    const params=new URLSearchParams({limit:'100',q:query,month});if(more&&cursor)params.set('before',cursor);
    $('journal-status').textContent='Loading entries…';$('journal-older').disabled=true;
    try{
      const data=await api('/journals?'+params);
      if(!alive()||token!==request)return;
      profileTimezone=data.timezone;
      entries=more?[...entries,...data.entries.filter(x=>!entries.some(y=>y.id===x.id))]:data.entries;
      cursor=data.next_cursor;
      // Preserve an older selected entry when returning from another page.
      if(!more&&selectedJournal&&!entries.some(x=>x.id===selectedJournal)){
        const selected=await api('/journals/'+encodeURIComponent(selectedJournal)).catch(()=>null);
        if(!alive()||token!==request)return;
        if(selected&&(!month||selected.entry.day.startsWith(month))&&(!query||(selected.entry.day+' '+selected.entry.text).toLowerCase().includes(query.toLowerCase())))entries.unshift(selected.entry);
      }
      draw();$('journal-status').textContent=entries.length+' of '+data.total+' '+(query||month?'matching entries':'entries');
      $('journal-warnings').innerHTML=data.warnings.map(x=>`<p class="warn">${esc(x)}</p>`).join('');
      if(!more){if(entries.length)await choose(entries.some(x=>x.id===selectedJournal)?selectedJournal:entries[0].id);else{$('journal-picker-label').textContent='Browse entries';$('journal-page').innerHTML=empty('journals',query||month?'No matching entries':'No journal entries yet',query||month?'Try another search or month.':'Daily reflections appear here as the journal job runs.',query||month?'':jump('health','View journal schedule'));wireRoutes($('journal-page'));}}
    }catch(error){if(alive()&&token===request)$('journal-status').textContent=error.message;}
    finally{if(alive()&&token===request)$('journal-older').disabled=false;}
  };
  const filter=()=>{request++;selection++;$('journal-older').disabled=true;journalBrowse.query=$('journal-search').value;journalBrowse.month=$('journal-month').value;clearTimeout(timer);timer=setTimeout(()=>{if(alive())load(false);},180);};
  $('journal-search').oninput=filter;$('journal-month').onchange=filter;
  $('journal-clear').onclick=()=>{$('journal-search').value='';$('journal-month').value='';filter();};
  $('journal-older').onclick=()=>load(true);
  await load(false);
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
  if(!$('photo-viewer').open)$('photo-viewer').showModal();
  renderViewerPhoto();
}
function closePhotoViewer(){
  if($('photo-viewer').open)$('photo-viewer').close();
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
    chips.innerHTML=names.map(name=>`<button class="album-chip" data-album="${esc(name)}">${esc(name)}</button>`).join('');
    for(const chip of chips.querySelectorAll('[data-album]')){
      chip.onclick=async()=>{
        const name=chip.dataset.album;
        try{
          await post('/content/album',{path:item.path,album:name});
          $('viewer-album-popover').hidden=true;
          notice('Added copy to album: '+name);
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
  $('viewer-actions').innerHTML=`<button class="viewer-btn ${isNsfw?'is-safe':'is-warn'}" id="viewer-btn-rate" title="${isNsfw?'Mark safe':'Mark NSFW'}">${icon(isNsfw?'shield_check':'shield_alert')}<span>${isNsfw?'Mark Safe':'Mark NSFW'}</span></button><button class="viewer-btn" id="viewer-btn-album" title="Add copy to album">${icon('album')}<span>Album</span></button><a class="viewer-btn" href="${downloadUrl}" download title="Download full image">${icon('download')}<span>Download</span></a><button class="viewer-icon-btn" id="viewer-btn-info" title="Details (i)">${icon('info')}</button>${item.deletable?`<button class="viewer-icon-btn viewer-btn-danger" id="viewer-btn-delete" title="Delete file">${icon('trash')}</button>`:''}`;
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
let photoPageGeneration=0;
workspaceHandlers.photos=async()=>{
  const generation=++photoPageGeneration;
  let [content,tl,jobs]=await Promise.all([api('/content?'+new URLSearchParams({kind:'image',limit:'120',q:photoBrowse.query,day:photoBrowse.day,collection:photoBrowse.collection})),api('/timeline'),api('/jobs')]);if(current!=='photos'||generation!==photoPageGeneration)return;
  profileTimezone=content.timezone;let items=mergePhotos(content,tl);const job=jobs.jobs.find(j=>j.name?.endsWith(' image timeline'));
  const status=!tl.enabled?'Scheduled captures: disabled':!job?'Capture job: not installed':!job.enabled?'Scheduled captures: paused':job.last_status==='error'?'Scheduled captures: error on last run':'Scheduled captures: active';
  $('photos').innerHTML=`<div class="section-heading" style="margin:0 0 16px;align-items:center"><h2 class="page-title" style="margin:0">Photos</h2><div style="display:flex;gap:10px;align-items:center"><button class="quiet small" data-route="settings" data-preference="photos">⚙️ Manage settings</button></div></div>`+`<details class="photo-settings"><summary>${status} · settings & recent attempts</summary><div class="card"><div class="reader-tools"><div><span class="pill ${tl.enabled&&job?.enabled?'status-good':'status-warn'}">${status}</span><p class="dim small">${!tl.enabled?'Enable photo sessions in Preferences. Existing images remain available.':!job?'Enablement and job installation are separate. Use Install / repair jobs in Hermes settings.':`Schedule: ${esc(job.schedule?.expr||'Not set')} · Next: ${when(job.next_run_at)}`}</p></div>${tl.enabled?jump('health','Manage schedule'):'<button class="link-button" data-route="settings" data-preference="photos">Photo settings →</button>'}</div><span class="dim small">${tl.budget_gb} GB rolling timeline budget · Favorites are kept separately</span>${tl.attempts.length?`<details><summary>Recent capture attempts (${tl.attempts.length})</summary>${tl.attempts.slice(0,5).map(a=>`<p class="small"><span class="pill">${esc(a.status)}</span> ${when(a.at)} ${esc(a.error)}</p>`).join('')}</details>`:''}</div></details>
  <div class="filters"><label>Search photos<input type="search" id="photo-search" maxlength="200" placeholder="Search photos by title, prompt, or tag…"></label><label>Day<input type="date" id="photo-day"></label><label>Collection<select id="photo-collection"><option value="all">All photos</option><option value="photo session">Timeline captures</option><option value="creation">Creations</option>${tl.albums.map(a=>`<option value="album:${esc(a.name)}">${esc(a.name)}</option>`).join('')}</select></label><button class="quiet" id="photo-clear">Clear</button></div><div id="photo-grid" class="photo-library"></div><p class="dim small" id="photo-count" role="status"></p><button class="quiet" id="photo-older" hidden>Load older photos</button>`;
  const draw=()=>{
    const shown=items.map(x=>photoForCollection(x,photoBrowse.collection));
    $('photo-grid').innerHTML=photoDays(shown).map(group=>`<section class="photo-day-group"><h3>${esc(group.day==='unknown'?'Date not recorded':stamp(group.items[0].item.at,{weekday:'long',year:'numeric'}))}<span>${group.items.length}</span></h3><div class="photo-grid">${group.items.map(({item:x,index:i})=>`
      <div class="photo-card" data-photo="${i}" tabindex="0" role="button" aria-label="Open ${esc(x.title)}">
        <div class="photo-wrap">
          <img ${mediaPrivacy(x)} src="${mediaUrl(x.url)}" loading="lazy" alt="${esc(x.title)}">
          ${x.blur?'<span class="pill pill-blur">Sensitive</span>':''}
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
      </div>`).join('')}</div></section>`).join('')||empty('photos',(photoBrowse.query||photoBrowse.day||photoBrowse.collection!=='all')?'No matching photos':'No photos in library',(photoBrowse.query||photoBrowse.day||photoBrowse.collection!=='all')?'Try another search, day or collection.':'Capture routines will populate images automatically.',jump('settings','Manage settings'));
    $('photo-count').textContent=`${shown.length} of ${content.total} images${content.scan_limited?' · scan limit reached; additional files remain in the Vault':''}`;
    for(const b of $('photo-grid').querySelectorAll('.photo-card')){
      b.onclick=e=>{
        if(e.target.closest('.photo-card-actions'))return;
        openPhotoViewer(shown[+b.dataset.photo],shown,+b.dataset.photo);
      };
      b.onkeydown=e=>{
        if(e.key==='Enter'||e.key===' '){
          if(e.target.closest('.photo-card-actions'))return;
          e.preventDefault();
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
    $('photo-older').hidden=!content.next_cursor;
    wireRoutes($('photos'));
  };
  let request=0,timer;
  const load=async more=>{
    const token=++request;
    const params=new URLSearchParams({kind:'image',limit:'120',q:photoBrowse.query,day:photoBrowse.day,collection:photoBrowse.collection});
    if(more&&content.next_cursor)params.set('before',content.next_cursor);
    $('photo-older').disabled=true;$('photo-count').textContent='Loading photos…';
    try{
      const page=await api('/content?'+params);
      if(current!=='photos'||generation!==photoPageGeneration||token!==request)return;
      const incoming=mergePhotos(page,tl);
      items=more?[...items,...incoming.filter(x=>!items.some(y=>(y.content_id||y.path)===(x.content_id||x.path)))]:incoming;
      content=page;draw();
    }catch(error){if(current==='photos'&&generation===photoPageGeneration&&token===request)$('photo-count').textContent=error.message;}
    finally{if(current==='photos'&&generation===photoPageGeneration&&token===request)$('photo-older').disabled=false;}
  };
  const filter=()=>{request++;$('photo-older').disabled=true;Object.assign(photoBrowse,{query:$('photo-search').value,day:$('photo-day').value,collection:$('photo-collection').value});clearTimeout(timer);timer=setTimeout(()=>{if(current==='photos'&&generation===photoPageGeneration)load(false);},180);};
  $('photo-search').value=photoBrowse.query;$('photo-day').value=photoBrowse.day;$('photo-collection').value=photoBrowse.collection;
  $('photo-search').oninput=filter;$('photo-day').onchange=filter;$('photo-collection').onchange=filter;
  $('photo-clear').onclick=()=>{$('photo-search').value='';$('photo-day').value='';$('photo-collection').value='all';filter();};
  $('photo-older').onclick=()=>load(true);draw();
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
    <div class="stat-item"><span>Verified facts</span><strong>${factsTotal}</strong><span class="dim small">Personal ledger</span></div>
    <div class="stat-item"><span>Standing rules</span><strong>${standingTotal}</strong><span class="dim small">Behavioral guidelines</span></div>
    <div class="stat-item"><span>Shared moments</span><strong>${momentsTotal}</strong><span class="dim small">Milestone memories</span></div>
    <div class="stat-item"><span>Open inquiries</span><strong>${questionsTotal}</strong><span class="dim small">Active context</span></div>
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

let calYear=new Date().getFullYear(),calMonth=new Date().getMonth(),selectedCalDate=null;
workspaceHandlers.loops=async()=>{
  const [d,m]=await Promise.all([api('/overview'),api('/missions')]);if(current!=='loops')return;
  const missions=m.missions||[];
  const loops=d.loops||[];
  const openCount=missions.filter(x=>x.status==='open').length;

  const monthNames=['January','February','March','April','May','June','July','August','September','October','November','December'];
  const monthTitle=`${monthNames[calMonth]} ${calYear}`;

  // Build month cells
  const firstDayIndex=new Date(calYear,calMonth,1).getDay();
  const daysInMonth=new Date(calYear,calMonth+1,0).getDate();
  const todayStr=new Date().toISOString().slice(0,10);
  selectedCalDate=selectedCalDate||todayStr;

  let calendarCellsHtml='';
  // Empty leading days
  for(let i=0;i<firstDayIndex;i++){
    calendarCellsHtml+=`<div class="calendar-cell is-other-month"></div>`;
  }
  for(let day=1;day<=daysInMonth;day++){
    const dayStr=`${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    const isToday=dayStr===todayStr;
    const isSelected=dayStr===selectedCalDate;
    const dayMissions=missions.filter(x=>x.wanted_by===dayStr);

    calendarCellsHtml+=`
      <div class="calendar-cell ${isToday?'is-today':''} ${isSelected?'is-selected':''}" data-cal-date="${esc(dayStr)}">
        <span class="calendar-cell-date">${day}</span>
        <div class="calendar-indicators">
          ${dayMissions.length?`<span class="cal-badge-pill" title="${esc(dayMissions.map(x=>x.title).join(', '))}">${dayMissions.length} event${dayMissions.length===1?'':'s'}</span>`:''}
        </div>
      </div>`;
  }

  const selectedDayMissions=missions.filter(x=>x.wanted_by===selectedCalDate);

  $('loops').innerHTML=heading('Plans & calendar','Shared schedule, commitments, autonomous investigations, and open threads.')+
  `<div class="stat-strip">
    <div class="stat-item"><span>Active tasks</span><strong>${openCount}</strong><span class="dim small">Autonomy & calendar queue</span></div>
    <div class="stat-item"><span>Total scheduled</span><strong>${missions.length}</strong><span class="dim small">Missions & reminders</span></div>
    <div class="stat-item"><span>Open threads</span><strong>${loops.length}</strong><span class="dim small">Conversational continuity</span></div>
  </div>

  <div class="card calendar-card">
    <div class="calendar-top-bar">
      <div class="calendar-nav-group">
        <button class="icon-button" id="cal-prev" aria-label="Previous month">←</button>
        <h2 class="calendar-month-title">${esc(monthTitle)}</h2>
        <button class="icon-button" id="cal-next" aria-label="Next month">→</button>
        <button class="quiet small" id="cal-today">Today</button>
      </div>
      <div class="actions" style="margin:0">
        <a class="quiet small" href="/api/calendar.ics" download="${esc(d.agent)}-calendar.ics" style="text-decoration:none">📅 Export iCal (.ics)</a>
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
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>Events & commitments for ${esc(selectedCalDate)}</strong>
        <span class="pill">${selectedDayMissions.length} scheduled</span>
      </div>
      ${selectedDayMissions.length?`
      <div class="cal-events-list">
        ${selectedDayMissions.map(x=>`
          <div class="cal-event-row">
            <div>
              <strong>${esc(x.title)}</strong>
              ${x.detail?`<p style="margin:2px 0 0;color:var(--dim)">${esc(x.detail)}</p>`:''}
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="pill ${x.status==='open'?'status-good':x.status==='dropped'?'status-bad':''}">${esc(x.status)}</span>
              ${x.status==='open'?`<button class="quiet small-btn" data-drop="${esc(x.id)}">Drop</button>`:''}
            </div>
          </div>`).join('')}
      </div>`:
      '<p class="dim small" style="margin:8px 0 0">No events or commitments on this date.</p>'
      }
    </div>
  </div>

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

  $('cal-prev').onclick=async()=>{
    calMonth--;
    if(calMonth<0){calMonth=11;calYear--;}
    await workspaceHandlers.loops();
  };
  $('cal-next').onclick=async()=>{
    calMonth++;
    if(calMonth>11){calMonth=0;calYear++;}
    await workspaceHandlers.loops();
  };
  $('cal-today').onclick=async()=>{
    calYear=new Date().getFullYear();
    calMonth=new Date().getMonth();
    selectedCalDate=todayStr;
    await workspaceHandlers.loops();
  };
  for(const cell of $('loops').querySelectorAll('[data-cal-date]')){
    cell.onclick=async()=>{
      selectedCalDate=cell.dataset.calDate;
      if($('mwhen'))$('mwhen').value=selectedCalDate;
      await workspaceHandlers.loops();
    };
  }

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
let environmentPanel=0,environmentFocus=false;
const environmentPage=workspaceHandlers.environment;
workspaceHandlers.environment=async()=>{await environmentPage();if(current!=='environment')return;const section=$('environment');const cards=[...section.children].filter(x=>x.classList.contains('card'));const tabs=document.createElement('div');tabs.className='segmented manage-tabs';tabs.setAttribute('role','tablist');const groups=['Overview','Models & accounts','Gateway & routine'].map((name,i)=>[name,cards.filter(card=>Number(card.dataset.environmentGroup||0)===i)]);if(groups[1][1].length){tabs.innerHTML=groups.map(([name],i)=>`<button role="tab" data-panel="${i}" aria-selected="${i===0}">${name}</button>`).join('');section.insertBefore(tabs,cards[0]);const pick=i=>{environmentPanel=i;for(const card of cards)card.hidden=!groups[i][1].includes(card);for(const b of tabs.children)b.setAttribute('aria-selected',String(+b.dataset.panel===i));};for(const b of tabs.children)b.onclick=()=>pick(+b.dataset.panel);pick(environmentPanel);}};
const existingHealth=workspaceHandlers.health;
workspaceHandlers.health=async()=>{await existingHealth();if(current==='health'){const box=document.createElement('div');box.className='actions';box.innerHTML=jump('environment','Gateway & routine settings')+jump('photos','Photo session status');$('health').prepend(box);wireRoutes(box);}};
async function showGatewayActivity(){
  const data=await api('/activity');
  dialog('Gateway activity',`<p class="dim">Latest recorded job results and saved creations. Refresh to check again.</p><button class="quiet" id="refresh-activity">Refresh</button><div class="activity-feed">${data.events.map(e=>`<article class="moment-row"><div><span class="pill ${e.status==='error'?'status-bad':''}">${esc(e.status)}</span><p class="small dim">${e.at?when(e.at):'No run recorded'}</p></div><div><strong>${esc(e.title)}</strong>${e.detail?`<p class="small warn">${esc(e.detail)}</p>`:''}${e.kind==='job'?`<p class="dim small">${e.enabled?'Enabled':'Paused'} · Next: ${e.next?when(e.next):'Not scheduled'}</p>`:inlineMedia(e.media)}</div></article>`).join('')||'<p>No activity recorded yet.</p>'}</div>`);
  $('refresh-activity').onclick=showGatewayActivity;
}
const titled={identity:['Identity','Appearance specifications, persona definitions, and SOUL configuration.']};
for(const [id,[title,description]] of Object.entries(titled)){const original=workspaceHandlers[id]||({identity:renderIdentity})[id];if(!original)continue;workspaceHandlers[id]=async()=>{await original();if(current!==id)return;const page=$(id);if(!page.querySelector('.page-title'))page.insertAdjacentHTML('afterbegin',heading(title,description));};}
document.addEventListener('keydown',e=>{if(!$('product-dialog').open||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;if(e.key==='ArrowRight')$('next-photo')?.click();if(e.key==='ArrowLeft')$('previous-photo')?.click();});

workspaceHandlers.health=async()=>{
  const [health,jobs,cost]=await Promise.all([api('/health'),api('/jobs'),api('/cost')]);if(current!=='health')return;
  profileTimezone=jobs.timezone;const failed=jobs.jobs.filter(j=>j.last_status==='error').length,active=jobs.jobs.filter(j=>j.enabled).length;
  $('health').innerHTML=`<div class="home-title"><div><h2 class="page-title">Jobs & Health</h2><p class="intro">System status, scheduled cron routines, and resource metrics.</p></div><button class="quiet" id="health-repair">Install / repair jobs</button></div><div class="stat-strip"><button data-filter="all"><span>Installed jobs</span><strong>${jobs.jobs.length}</strong><span>Model tasks & routines</span></button><button data-filter="active"><span>Scheduled</span><strong>${active}</strong><span>Enabled in Hermes</span></button><button data-filter="paused"><span>Paused</span><strong>${jobs.jobs.length-active}</strong><span>Inactive routines</span></button><button data-filter="error"><span>Last run failed</span><strong>${failed}</strong><span>Inspect error history</span></button></div>
  ${health.problems.length?`<div class="card"><h2>Needs attention</h2><ul>${health.problems.map(p=>`<li class="warn">${esc(p)}</li>`).join('')}</ul>${jump('environment','Open Hermes settings')}</div>`:'<p><span class="pill status-good">All monitored services operating normally</span></p>'}
  <div class="filters"><label>Find a job<input id="job-search" type="search" placeholder="Photo, journal, morning…"></label><label>State<select id="job-filter"><option value="all">All jobs</option><option value="active">Scheduled</option><option value="paused">Paused</option><option value="error">Last run failed</option></select></label><button class="quiet" id="all-job-history">Run history</button><button class="quiet" id="gateway-activity">Activity feed</button><button class="quiet" data-route="environment" data-environment-panel="2">Gateway settings</button></div><div class="card" id="job-table"></div>
  <div class="row"><div class="card"><h2>Memory capacity</h2>${health.memory.map(m=>`<div class="moment-row"><span class="small">${esc(m.file)}</span><div><strong>${Number(m.chars).toLocaleString()} / ${Number(m.cap).toLocaleString()}</strong><p class="small ${m.over_warn?'warn':'dim'}">${m.over_warn?'Approaching the limit':'Within capacity'}</p></div></div>`).join('')}</div><div class="card"><h2>Storage & history</h2>${health.storage.map(s=>`<p class="small">${esc(s.label)} <strong>${(s.bytes/1e6).toFixed(1)} MB</strong> · ${s.files} files</p>`).join('')}<p class="dim small">Vault version history ${health.vault_repo?'is recording':'is not initialized'}.</p></div></div><details><summary>Model usage · last 30 recorded days</summary>${cost.available?`<table><thead><tr><th>Day</th><th>Input tokens</th><th>Output tokens</th><th>Runs</th></tr></thead><tbody>${cost.days.slice().reverse().map(d=>`<tr><td>${esc(d.day)}</td><td>${d.input.toLocaleString()}</td><td>${d.output.toLocaleString()}</td><td>${d.runs}</td></tr>`).join('')}</tbody></table>`:'<p class="dim">No usage records are available yet.</p>'}</details>`;
  const filter=()=>{const q=$('job-search').value.toLowerCase(),state=$('job-filter').value;const rows=jobs.jobs.filter(j=>(!q||j.name.toLowerCase().includes(q))&&(state==='all'||state==='active'&&j.enabled||state==='paused'&&!j.enabled||state==='error'&&j.last_status==='error'));$('job-table').innerHTML=rows.length?`<table><thead><tr><th>Routine</th><th>Next run</th><th>Last result</th><th>Controls</th></tr></thead><tbody>${rows.map(j=>`<tr><td><strong>${esc(j.name)}</strong><br><span class="small dim">${j.no_agent?'Local maintenance':'Model task'} · ${j.enabled?'Scheduled':'Paused'}</span><details><summary>Schedule</summary><code>${esc(j.schedule?.expr||'Not set')}</code></details></td><td>${when(j.next_run_at)}</td><td><span class="pill ${j.last_status==='error'?'status-bad':j.last_status==='ok'?'status-good':''}">${esc(j.last_status||'Not run yet')}</span></td><td><div class="actions"><button class="quiet" data-job="${esc(j.id)}" data-action="run">Run next tick</button>${!j.no_agent?`<button class="quiet" data-job="${esc(j.id)}" data-action="${j.enabled?'pause':'resume'}">${j.enabled?'Pause':'Resume'}</button>`:''}<button class="quiet" data-job="${esc(j.id)}" data-action="edit">Edit schedule</button></div></td></tr>`).join('')}</tbody></table>`:empty('health','No matching jobs','Try another search or install the companion routine.');for(const b of $('job-table').querySelectorAll('[data-job]'))b.onclick=async()=>{if(b.dataset.action==='edit'){dialog('Edit job schedule',`<form id="schedule-form"><label>Frequency<select id="schedule-preset"><option value="">Keep current / custom</option><option value="15">Every 15 minutes</option><option value="30">Every 30 minutes</option><option value="60">Every hour</option><option value="daily">Every day</option></select></label><label id="schedule-time-label" hidden>Time<input type="time" id="schedule-time" value="09:00"></label><label>Cron expression or Hermes schedule<input id="schedule-input" value="${esc(jobs.jobs.find(j=>j.id===b.dataset.job)?.schedule?.expr||'')}" required></label><p class="dim small">For example, */15 * * * * means every 15 minutes. Times follow the Hermes configuration.</p><button class="act">Save schedule</button></form>`);const preset=()=>{const mode=$('schedule-preset').value;$('schedule-time-label').hidden=mode!=='daily';if(mode==='daily'){const [hour,minute]=$('schedule-time').value.split(':').map(Number);$('schedule-input').value=minute+' '+hour+' * * *';}else if(mode)$('schedule-input').value=mode==='60'?'0 * * * *':'*/'+mode+' * * * *';};$('schedule-preset').onchange=preset;$('schedule-time').onchange=preset;$('schedule-form').onsubmit=async e=>{e.preventDefault();const value=$('schedule-input').value;await action('/jobs/'+encodeURIComponent(b.dataset.job)+'/edit',{schedule:value});$('product-dialog').close();};}else await action('/jobs/'+encodeURIComponent(b.dataset.job)+'/'+b.dataset.action);};};
  $('job-search').oninput=filter;$('job-filter').onchange=filter;for(const b of $('health').querySelectorAll('[data-filter]'))b.onclick=()=>{$('job-filter').value=b.dataset.filter;filter();};bindAction('health-repair','/maintenance/repair');bindAction('all-job-history','/jobs/history');$('gateway-activity').onclick=showGatewayActivity;filter();wireRoutes($('health'));
};

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

const settingsPage=workspaceHandlers.settings||(typeof renderSettings==='function'?renderSettings:null);
workspaceHandlers.settings=async()=>{
  if(settingsPage)await settingsPage();if(current!=='settings')return;
  const page=$('settings');
  if(!page.querySelector('.page-title'))page.insertAdjacentHTML('afterbegin',heading('Preferences','Boundaries, quiet hours, appearance, and how this workspace runs.'));
  let workspacePanel=page.querySelector('[data-preference-panel="workspace"]');
  if(!workspacePanel){
    workspacePanel=document.createElement('div');
    workspacePanel.className='card';
    workspacePanel.dataset.preferencePanel='workspace';
    page.append(workspacePanel);
  }
  workspacePanel.innerHTML=appearancePanelHTML();
  wireAppearancePanel(workspacePanel);

  const allCards=[...page.querySelectorAll('[data-preference-panel]')];
  const oldTabs=page.querySelector('.segmented[aria-label="Preference categories"]');
  if(oldTabs)oldTabs.remove();
  const tabs=document.createElement('div');
  tabs.className='segmented';
  tabs.setAttribute('role','tablist');
  tabs.setAttribute('aria-label','Preference categories');
  tabs.innerHTML=[['contact','Contact'],['photos','Photo sessions'],['routine','Daily rhythm'],['relationship','Relationship'],['senses','Awareness'],['network','Network & PIN'],['workspace','Appearance']].map(([id,label])=>`<button role="tab" data-preference="${id}">${label}</button>`).join('');
  page.insertBefore(tabs,allCards[0]);
  const pick=name=>{
    preferencePanel=name;
    for(const card of allCards)card.hidden=card.dataset.preferencePanel!==name;
    for(const b of tabs.children)b.setAttribute('aria-selected',String(b.dataset.preference===name));
  };
  for(const b of tabs.children)b.onclick=()=>pick(b.dataset.preference);
  pick(preferencePanel||'contact');
};

const identityBase=workspaceHandlers.identity;
workspaceHandlers.identity=async()=>{
  await identityBase();if(current!=='identity')return;
  // Tools belong under the profile header, not above the companion's name.
  const bar=`
    <div class="identity-actions-bar">
      <div class="identity-actions-copy">
        <strong>Edit their documents</strong>
        <p class="dim small">Plain text, exactly as Hermes reads it. Every save keeps an automatic backup.</p>
      </div>
      <div class="actions">
        <button class="act" id="edit-full-soul">Edit full documents</button>
        <button class="quiet" id="repair-sections">Restore missing sections</button>
        <button class="quiet" id="album-reference">Album reference</button>
        <button class="quiet" id="visual-builder">Visual creator</button>
      </div>
    </div>`;
  const hero=$('identity').querySelector('.identity-hero');
  if(hero)hero.insertAdjacentHTML('afterend',bar);
  else $('identity').insertAdjacentHTML('afterbegin',bar);
  $('edit-full-soul').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;const list=await api('/documents');let selected='SOUL.md',revision='';dialog('Edit companion documents',`<p>Every save keeps a backup. Edit the complete document, including writing created outside the kit. Other vault documents can be edited in Vault.</p><label>Document<select id="full-document">${options(list.documents.map(x=>[x,x]),selected)}</select></label><textarea id="full-soul" style="height:55vh"></textarea><button class="act" id="save-full-soul">Save document</button>`);const read=async()=>{if(!await confirmEditorLeave('dialog')){$('full-document').value=selected;return;}selected=$('full-document').value;const d=await api('/soul-document?document='+encodeURIComponent(selected));revision=d.revision;$('full-soul').value=d.text;};await read();$('full-document').onchange=read;$('save-full-soul').onclick=async()=>{await post('/soul-document',{document:selected,text:$('full-soul').value,revision});clearEditorDirty('dialog');$('product-dialog').close();await render('identity');notice('Document saved with a backup.');};};
  $('repair-sections').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;await post('/identity-repair');await render('identity');notice('Missing sections restored. Add an appearance below, or use the visual creator. Existing writing was preserved.');};
  $('album-reference').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;const d=await api('/content');const images=d.items.filter(x=>x.kind==='image');dialog('Choose a reference photo',`<div class="photo-grid">${images.map((x,i)=>`<button class="card" data-reference="${i}"><img ${mediaPrivacy(x)} style="width:100%;height:150px;object-fit:cover" src="${mediaUrl(x.url)}" alt="${esc(x.title)}"><span>${esc(x.title)} · ${esc(x.generation||x.source)}${x.blur?" · NSFW":""}</span></button>`).join('')||'<p>No saved photos yet. Upload a photo in Identity to get started.</p>'}</div>`);for(const b of $('dialog-body').querySelectorAll('[data-reference]'))b.onclick=async()=>{const r=await fetch(rawMediaUrl(images[+b.dataset.reference].url));if(!r.ok)throw Error('Photo could not be loaded');await uploadPortrait(await r.blob());$('product-dialog').close();await render('identity');};};
  $('visual-builder').onclick=async()=>{if(!await confirmEditorLeave('identity'))return;const d=await api('/catalog');const rows=Object.entries(d.catalog.categories).filter(([k,v])=>v.section==='appearance');dialog('Visual creator',`<p>Choose a look, then review the complete appearance before saving.</p><label>Catalog<select id="visual-gender"><option value="female">Feminine</option><option value="male">Masculine</option></select></label><div id="visual-fields" class="form-grid"></div><button class="quiet" id="compose-look">Build description</button><label>Appearance description<textarea id="visual-description"></textarea></label><button class="act" id="save-look">Save appearance</button>`);const populate=()=>{$('visual-fields').innerHTML=rows.filter(([k,v])=>v[$('visual-gender').value]).map(([k,v])=>`<label>${esc(v.label)}<select aria-label="${esc(v.label)}" data-visual="${esc(k)}"><option value="">Leave unspecified</option>${options(v[$('visual-gender').value].map(r=>[r.text,r.label]),'')}<option value="__custom__">Write your own…</option></select><input aria-label="Custom ${esc(v.label)}" hidden placeholder="Your description"></label>`).join('');for(const select of $('visual-fields').querySelectorAll('select'))select.onchange=()=>{select.nextElementSibling.hidden=select.value!=='__custom__';};};populate();$('visual-gender').onchange=populate;$('compose-look').onclick=()=>{$('visual-description').value=[...$('visual-fields').querySelectorAll('select')].map(s=>s.value==='__custom__'?s.nextElementSibling.value:s.value).filter(Boolean).join(' ').replaceAll('{A}',chatName()).replaceAll('{AS_LOWER}','they').replaceAll('{AS}','They').replaceAll('{AP}','their').replaceAll('{AO}','them');};$('save-look').onclick=async()=>{const body=$('visual-description').value.trim();if(!body)throw Error('Build or write an appearance first.');await post('/identity-repair',{appearance:body});await post('/identity/appearance',{body});$('product-dialog').close();await render('identity');notice('Appearance saved.');};};
};
TABS.push(['voice','Voice studio']);const voiceSection=document.createElement('section');voiceSection.id='voice';voiceSection.hidden=true;document.querySelector('main').append(voiceSection);if(!$('tabs').querySelector('[data-tab="voice"]')){const voiceNav=document.createElement('button');voiceNav.dataset.tab='voice';voiceNav.innerHTML=icon('voice')+'<span>Voice studio</span>';voiceNav.onclick=()=>showTab('voice');($('tabs').querySelector('.nav-more')||$('tabs').lastElementChild||$('tabs')).append(voiceNav);}
const voiceChoices={edge:['en-US-AriaNeural','en-US-GuyNeural','en-GB-SoniaNeural'],piper:['en_US-lessac-medium'],kittentts:['Jasper','Bella','Luna','Bruno','Rosie','Hugo','Kiki','Leo'],openai:['alloy','echo','fable','onyx','nova','shimmer'],xai:['eve','ara','rex','sal','leo'],gemini:['Kore','Puck','Charon','Aoede'],neutts:[],elevenlabs:[],minimax:['English_expressive_narrator'],mistral:[]};
workspaceHandlers.voice=async()=>{
 const d=await api('/voice'),tts=d.tts;
 $('voice').innerHTML=heading('Voice studio','Choose how your companion sounds. Local engines run on the computer hosting the kit; cloud engines use their connected accounts.')+`<div class="card"><form id="voice-form"><div class="form-grid"><label>Speech engine<select id="voice-provider">${options([['edge','Edge · online, no API key'],['piper','Piper · local'],['kittentts','KittenTTS · local'],['neutts','NeuTTS · local reference voice'],['openai','OpenAI'],['xai','xAI / Grok'],['elevenlabs','ElevenLabs'],['minimax','MiniMax'],['gemini','Gemini'],['mistral','Mistral']],tts.provider||'edge')}</select></label><label id="voice-picker-label">Voice<select id="voice-picker" aria-label="Voice"></select><input id="voice-custom" aria-label="Custom voice name or ID" hidden placeholder="Voice name or ID"></label><label id="voice-speed-label">Speaking speed <output id="speed-value">1</output>×<input id="voice-speed" type="range" min="0.7" max="1.5" step="0.05" value="1"></label></div><label id="voice-pitch-label" hidden>Pitch <output id="pitch-value">0</output><input id="voice-pitch" type="range" min="-12" max="12" step="1" value="0"></label><div id="voice-reference" hidden><p>Use a clear WAV recording, 1–30 seconds, and the exact words spoken. Choose a voice you have permission to use.</p><label>Reference audio<input id="voice-clip" type="file" accept=".wav,audio/wav"></label><label>Words spoken in the clip<textarea id="voice-transcript">${esc(tts.neutts?.ref_text||'')}</textarea></label><p>${tts.neutts?.ref_audio?'A reference clip is configured.':'No reference clip configured; Hermes uses its default sample.'}</p></div><div class="actions"><button class="act">Save voice</button><button type="button" class="quiet" id="install-local-voice">Install selected local engine</button><button type="button" class="quiet" id="voice-install">Full speech setup</button></div></form></div><div class="card"><h2>Try the saved voice</h2><label>Speech verification phrase<input id="voice-sample" type="text" readonly value="Hello! It’s really good to spend a little time together." style="background:color-mix(in srgb,var(--ink) 3%,transparent);color:var(--ink-2);cursor:default"></label><button class="act" id="preview-voice">Generate preview</button><div id="voice-player"></div><p class="dim">Cloud previews may use account credits. Missing local dependencies appear as an error; use Install / configure engines to install them through Hermes setup.</p></div>`;
 const update=()=>{const provider=$('voice-provider').value,cfg=tts[provider]||{},value=cfg.voice||cfg.voice_id||voiceChoices[provider][0]||'';const known=voiceChoices[provider].includes(value);$('voice-picker').innerHTML=options(voiceChoices[provider].map(v=>[v,v]),value)+'<option value="__custom__">Write your own…</option>';$('voice-picker').value=known?value:'__custom__';$('voice-custom').value=known?'':value;$('voice-custom').hidden=known;$('voice-picker-label').hidden=provider==='neutts';$('voice-reference').hidden=provider!=='neutts';$('voice-speed-label').hidden=!['edge','openai','xai','minimax','kittentts'].includes(provider);$('voice-pitch-label').hidden=provider!=='minimax';$('voice-pitch').value=cfg.pitch||0;$('pitch-value').textContent=$('voice-pitch').value;$('install-local-voice').hidden=!['piper','neutts','kittentts'].includes(provider);$('voice-speed').value=cfg.speed||1;$('speed-value').textContent=$('voice-speed').value;};update();$('voice-provider').onchange=update;$('voice-picker').onchange=()=>{$('voice-custom').hidden=$('voice-picker').value!=='__custom__';};$('voice-speed').oninput=()=>{$('speed-value').textContent=$('voice-speed').value;};
 $('voice-pitch').oninput=()=>{$('pitch-value').textContent=$('voice-pitch').value;};$('install-local-voice').onclick=()=>action('/voice/install',{provider:$('voice-provider').value});
 $('voice-form').onsubmit=async e=>{e.preventDefault();const file=$('voice-clip').files[0];if(file&&$('voice-provider').value==='neutts'){const r=await fetch(scoped('/api/voice/reference'),{method:'POST',headers:{'content-type':'application/octet-stream',...(token?{'x-companion-token':token}:{})},body:file});if(!r.ok)throw Error((await r.json()).detail);}await action('/voice',{provider:$('voice-provider').value,voice:$('voice-picker').value==='__custom__'?$('voice-custom').value:$('voice-picker').value,speed:+$('voice-speed').value,pitch:+$('voice-pitch').value,transcript:$('voice-transcript').value});};
 $('voice-install').onclick=async()=>{showTab('environment');await environmentPage();environmentPanel=1;await workspaceHandlers.environment();if($('native-console'))await openConsole('setup');};
 $('preview-voice').onclick=()=>action('/voice/preview',{text:$('voice-sample').value},r=>{$('voice-player').innerHTML=`<audio controls src="${mediaUrl(r.audio+'?t='+Date.now())}"></audio>`;});
};



const settingsWithMedia=workspaceHandlers.settings;
workspaceHandlers.settings=async()=>{
  await settingsWithMedia();if(current!=='settings')return;
  const photosPanel=$('settings').querySelector('[data-preference-panel="photos"]');
  if(!photosPanel)return;
  let box=$('media-privacy-box');
  if(!box){
    box=document.createElement('div');
    box.id='media-privacy-box';
    box.style.marginTop='28px';
    box.style.borderTop='1px solid var(--edge)';
    box.style.paddingTop='24px';
    photosPanel.append(box);
  }
  const prefs=await api('/media/preferences');const scanner=await api('/media/scanner');
  box.innerHTML=`<h2>Media privacy & review</h2><div class="card"><h3>Private image scanner</h3><p>NudeNet runs on this host. The model is about 12 MB and uses roughly 150 MB of memory while scanning. It detects exposed intimate anatomy; it does not check scene accuracy or all sexual content.</p><p class="dim small">${scanner.installed?'Installed':'Optional download · requires internet for installation'}${scanner.selected?' · Selected for this companion':''}</p><button class="quiet" id="install-local-scanner">${scanner.installed?'Check installation':'Install local scanner'}</button> <button class="act" id="use-local-scanner" ${scanner.installed?'':'disabled'}>Use for this companion</button></div><label class="inline-label"><input id="media-blur" type="checkbox" ${prefs.blur_nsfw_initially?'checked':''}>Blur NSFW initially</label><p class="dim small">Sensitive images can be blurred. Unreviewed images stay blurred when the option below is enabled. Open a photo to reveal it.</p><label class="inline-label"><input id="media-blur-unknown" type="checkbox" ${prefs.blur_unknown_initially!==false?'checked':''}>Blur unreviewed images and failed scans</label><label class="inline-label"><input id="media-review" type="checkbox" ${prefs.review_before_delivery?'checked':''}>Review generated images before delivery</label><p class="dim small">Local NudeNet scanning keeps images on this host and detects exposed intimate anatomy. It does not check clothed sexual activity. A remote vision reviewer can also check scene and clothing. Failed scans hold the image for inspection; no remote fallback is used.</p><div class="form-grid"><label>Review provider<input id="media-review-provider" value="${esc(prefs.review_provider)}" placeholder="local-nsfw for private CPU scanning"></label><label>Review model (unused for local-nsfw)<input id="media-review-model" value="${esc(prefs.review_model)}" placeholder="Use configured compression model"></label></div><button class="act" id="save-media-prefs">Save media preferences</button>`;
  $('install-local-scanner').onclick=async()=>{await action('/media/scanner/install',{},()=>render('settings'));};
  $('use-local-scanner').onclick=async()=>{await post('/media/scanner/use',{});await render('settings');notice('Private scanning enabled. Failed scans stay blurred.');};
  $('save-media-prefs').onclick=async()=>{await post('/media/preferences',{blur_nsfw_initially:$('media-blur').checked,blur_unknown_initially:$('media-blur-unknown').checked,review_before_delivery:$('media-review').checked,review_provider:$('media-review-provider').value,review_model:$('media-review-model').value});clearEditorDirty('settings-media');notice('Media preferences saved for this companion.');};
};

const environmentWithUpdates=workspaceHandlers.environment;
workspaceHandlers.environment=async()=>{
  await environmentWithUpdates();
  if(current!=='environment')return;
  const d=await api('/updates').catch(()=>({version:'2.1.0'}));
  const box=document.createElement('div');
  box.id='kit-updates';
  box.className='card';
  box.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px">
    <h2 style="margin:0">Companion Kit Updates · v${esc(d.version)}</h2>
    ${d.has_update?`<span class="pill status-warn">Update v${esc(d.latest_version)} Available</span>`:`<span class="pill status-good">Up to Date</span>`}
  </div>
  ${d.has_update?`<div style="background:color-mix(in srgb,var(--warn) 10%,transparent);border-left:3px solid var(--warn);padding:12px 14px;border-radius:6px;margin-bottom:14px">
    <strong style="color:var(--warn)">A new release (v${esc(d.latest_version)}) is available on GitHub!</strong>
    <p class="dim small" style="margin:4px 0 0">To apply this update cleanly and verify all dependencies, run the turnkey updater on your host machine:</p>
    <pre style="background:var(--bg);padding:8px 12px;border-radius:6px;margin:8px 0;font-size:12.5px;color:var(--good)">./update.sh</pre>
    ${d.release_url?`<a href="${esc(d.release_url)}" target="_blank" class="small" style="color:var(--accent);display:inline-block">View Release Notes on GitHub →</a>`:''}
  </div>`:`<p class="dim small" style="margin:0 0 10px">You are running the latest version of Companion Kit.</p>`}
  <details style="margin-top:14px">
    <summary class="small dim">Terminal update commands</summary>
    <pre style="background:var(--bg);padding:10px 12px;border-radius:6px;margin:6px 0;font-size:12px">./update.sh          # Updates Companion Kit, dependencies, and restarts service\n./update.sh --hermes # Also updates Hermes agent runtime</pre>
  </details>`;
  $('environment').append(box);
};
