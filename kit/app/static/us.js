/* Us: one page for what has happened between the two of you.

   This replaces two pages that answered neighbouring questions from opposite
   ends — Together (meters, a stage ladder, a milestone checklist) and Memories
   (KPI tiles over a fact ledger). Both read as instruments. The records under
   them are unchanged; only what is put first has moved. How things feel leads,
   shared history is the body, and the exact numbers, the full ledgers and the
   evidence are all still here, one deliberate step further in.

   Everything is composed from existing endpoints and nothing on this page calls
   a model: the summary sentence is picked by threshold from the same meters the
   prompt already carries, so it can never say more than they do. */
const US_LIMITS={story:12,keepsakes:6,memories:5,discoveries:5,threads:5,library:24,moments:20};
const KEEPSAKE_KINDS=['first','joke','ritual','nickname','milestone'];
const MOMENT_TITLE={first:'A first',joke:'An inside joke',ritual:'A shared ritual',
  nickname:'A name between you',milestone:'A milestone',note:'A moment worth keeping'};
const FACT_ICON={likes:'♡',dislikes:'✕',people:'👥',places:'📍',work:'💼',school:'🎓',
  health:'🌿',history:'📜',logistics:'🗓',other:'✦'};
const PREF_MARK={like:['♡','Likes'],dislike:['✕','Not a fan'],curious:['?','Curious about'],mixed:['~','Mixed feelings']};
const ROMANTIC_STAGE_NAMES=['Just Met','Friends','Chemistry','Intimacy','Bonded'];
const usCap=s=>s?s[0].toUpperCase()+s.slice(1):'';
/* The companion's configured pronouns, from /relationship. A she is she and a
   he is he; singular they is for a they, or when the set is not known. */
const US_PRONOUNS={
  she:{subj:'she',obj:'her',poss:'her',possPron:'hers',refl:'herself'},
  he:{subj:'he',obj:'him',poss:'his',possPron:'his',refl:'himself'},
  they:{subj:'they',obj:'them',poss:'their',possPron:'theirs',refl:'themselves'}};
const usPronouns=set=>US_PRONOUNS[set]||US_PRONOUNS.they;

/* A record's own date, or none. `happened_on` is free text, so only a real
   calendar date is trusted with a place in the chronology. */
function usWhen(row){
  if(!row)return '';
  if(/^\d{4}-\d{2}-\d{2}$/.test(row.happened_on||''))return row.happened_on;
  return row.at||row.recorded_at||'';
}
function usDayLabel(key,today){
  if(!key)return '';
  const [y,m,d]=key.split('-').map(Number);
  const base=new Date(Date.UTC(y,m-1,d));
  if(today){
    const [ty,tm,td]=today.split('-').map(Number);
    const diff=Math.round((Date.UTC(ty,tm-1,td)-base)/86400000);
    if(diff===0)return 'Today';
    if(diff===1)return 'Yesterday';
    if(ty!==y)return new Intl.DateTimeFormat(undefined,{timeZone:'UTC',month:'long',day:'numeric',year:'numeric'}).format(base);
  }
  return new Intl.DateTimeFormat(undefined,{timeZone:'UTC',month:'long',day:'numeric'}).format(base);
}
const usShortDate=value=>{const key=dayKey(value);return key?usDayLabel(key,dayKey(new Date().toISOString())):esc(value||'');};

/* ------------------------------------------------------------ how it feels */
/* Words for a meter, or nothing. Warmth and trust always have something to
   say; hurt, friction and missing you only speak when they are really there. */
function feelingChip(key,value){
  if(value==null||!isFinite(value))return null;
  if(key==='warmth')return ['🔥',value>=.75?'Very warm':value>=.5?'Warm':value>=.25?'Warming up':'Still cool'];
  if(key==='trust')return ['🛡',value>=.75?'Strong trust':value>=.5?'Trusting':value>=.25?'Building trust':'Still guarded'];
  if(key==='hurt')return value>=.15?['🩹',value>=.5?'Hurting':'Some hurt']:null;
  if(key==='irritation')return value>=.15?['⚡',value>=.5?'Real friction':'A little friction']:null;
  if(key==='longing')return value>=.35?['⏳',value>=.7?'Missing you a lot':'Missing you']:null;
  return null;
}
function relationshipStateSummary(meters,companionName){
  if(!meters)return '';
  const v=k=>typeof meters[k]==='number'?meters[k]:0;
  const w=v('warmth'),t=v('trust'),h=v('hurt'),i=v('irritation'),l=meters.longing;
  const lines=[];
  if(h>=.4)lines.push('Something is still hurting between you.');
  else if(i>=.4)lines.push('There is some friction that has not fully settled.');
  else if(w>=.65&&t>=.6)lines.push('Things feel warm and secure.');
  else if(w>=.65)lines.push('Things feel warm lately.');
  else if(t>=.6)lines.push('There is a steady trust here.');
  else if(w<.3&&t<.3)lines.push('Things are still new, and finding their footing.');
  else lines.push('Things feel easy and steady.');
  if((h>=.4||i>=.4)&&w>=.5)lines.push('Underneath it, there is still a lot of warmth.');
  else if(lines[0]==='Things feel warm lately.'&&t<.4)lines.push('Trust is still being built.');
  if(typeof l==='number'&&l>=.5)lines.push(l>=.7?`${companionName} has really been missing you.`:'Your absence has been felt lately.');
  return lines.join(' ');
}
/* The boundary states are real states of the relationship, so they stand in
   the open on the hero rather than behind a disclosure. */
function usStanding(intimacy,companionName){
  if(!intimacy)return '';
  if(intimacy.permanent_friend)return `<div class="notice-strip rel-standing is-firm us-standing" data-standing="permanent_friend"><p><strong>Friendship established.</strong>
    After repeated boundary violations, ${esc(companionName)} has stepped back to friendship. This does not reopen.</p></div>`;
  if(intimacy.nsfw_revoked)return `<div class="notice-strip rel-standing us-standing" data-standing="nsfw_revoked"><p><strong>Stepped back to friendship.</strong>
    Your relationship is rooted in friendship and affectionate companionship.</p></div>`;
  const n=intimacy.violations_count|0;
  if(n>0)return `<div class="notice-strip rel-standing us-standing" data-standing="violation"><p><strong>A boundary was crossed${n>1?` ${n} times`:''}.</strong>
    Mutual respect is the condition of closeness here; repeated violations step the relationship back to friendship for good.</p></div>`;
  return '';
}
function usStageTrack(intimacy){
  if(!intimacy||intimacy.romantic_progression===false)return '';
  const stage=intimacy.stage|0;
  return `<ol class="us-stage-track" aria-label="Where things are">${ROMANTIC_STAGE_NAMES.map((name,i)=>
    `<li class="${i<stage?'is-reached':i===stage?'is-current':''}"${i===stage?' aria-current="step"':''}><span>${esc(name)}</span></li>`).join('')}</ol>`;
}
function relationshipHero(relationship,feelings,companionName){
  const intimacy=relationship?.intimacy||null;
  const meters=feelings?.meters||null;
  const platonic=intimacy?.romantic_progression===false;
  const stageName=intimacy?(intimacy.stage_name||(platonic?'':ROMANTIC_STAGE_NAMES[intimacy.stage|0])):'';
  const summary=relationshipStateSummary(meters,companionName)||
    (platonic?'Shared experience has made this connection more familiar.':'Your story together is still being written.');
  const chips=meters?['warmth','trust','hurt','irritation','longing'].map(k=>[k,feelingChip(k,meters[k])]).filter(([,c])=>c):[];
  return `<section class="us-hero" aria-label="How things are between you">
    <p class="us-hero-identity"><span>${esc(companionName)}</span> <span aria-hidden="true">+</span> <span>You</span></p>
    ${platonic?`<p class="eyebrow us-connection">${esc(intimacy.connection_label||'Friendship')}</p>`:''}
    ${stageName?`<p class="us-stage">${esc(stageName)}</p>`:''}
    <p class="us-state-summary">${esc(summary)}</p>
    ${chips.length?`<ul class="us-state-chips" aria-label="How it feels">${chips.map(([k,[mark,word]])=>
      `<li class="us-state-chip chip-${k}"><span aria-hidden="true">${mark}</span> ${esc(word)}</li>`).join('')}</ul>`:''}
    ${feelings?.mood?`<p class="dim small us-mood">${esc(companionName)}’s mood lately: ${esc(feelings.mood)}</p>`:''}
    ${usStageTrack(intimacy)}
    ${usStanding(intimacy,companionName)}
  </section>`;
}

/* --------------------------------------------------------- shared history */
/* Only what has actually happened, newest first, and only kinds that became
   something between you. Nothing unearned is listed, so nothing reads as a
   checklist to complete. */
function usKeepsakes(moments,limit=US_LIMITS.keepsakes){
  const active=(moments||[]).filter(m=>m.status==='active'&&KEEPSAKE_KINDS.includes(m.moment));
  const sorted=active.slice().sort((a,b)=>String(usWhen(b)).localeCompare(String(usWhen(a))));
  return {shown:sorted.slice(0,limit),total:active.length};
}
function keepsakeDate(m){
  if(/^\d{4}-\d{2}-\d{2}$/.test(m.happened_on||''))return usShortDate(m.happened_on);
  return m.happened_on?esc(m.happened_on):usShortDate(m.recorded_at);
}
function usKeepsakesHTML(keep,allMoments){
  const more=(allMoments||[]).length;
  return `<div class="us-keepsakes">${keep.shown.map(m=>`<article class="us-keepsake">
      <p class="us-keepsake-kind"><span aria-hidden="true">✦</span> ${esc(MOMENT_TITLE[m.moment]||'A moment')}</p>
      <p class="us-keepsake-text">${esc(m.text)}</p>
      <p class="dim small">${keepsakeDate(m)}</p>
    </article>`).join('')}</div>`+
    (keep.shown.length?'':'<p class="dim us-empty">Firsts, rituals, nicknames and little traditions will collect here over time.</p>')+
    (more?`<button type="button" class="link-button" data-us-action="moments">See all shared moments →</button>`:'');
}
/* The story feed. Moments already shown as keepsakes are left out of it, and
   corrected experiences (and the corrections themselves) never appear, so no
   one event is told twice on one screen. */
function normalizeUsStory({moments=[],experiences=[],exclude=new Set()}={}){
  const events=[];
  for(const m of moments){
    if(m.status!=='active'||exclude.has(m.id))continue;
    const at=usWhen(m);if(!at)continue;
    // Most moments are plain notes; a label repeated down the feed says nothing,
    // so a note's own words are its headline.
    const note=!MOMENT_TITLE[m.moment]||m.moment==='note';
    events.push({id:'moment:'+m.id,type:'moment',at,label:'✦',title:note?'':MOMENT_TITLE[m.moment],
      text:m.text,evidence:'',source:'moment',photos:[]});
  }
  const corrected=new Set(experiences.filter(x=>x.kind==='correction').map(x=>x.related));
  const copy={connection:['♥','You felt closer'],rupture:['🩹','A rough moment'],repair:['♥','Things softened']};
  for(const x of experiences){
    if(!copy[x.kind]||corrected.has(x.id)||!x.at)continue;
    events.push({id:'feeling:'+x.id,type:x.kind,at:x.at,label:copy[x.kind][0],title:copy[x.kind][1],
      text:x.text,evidence:x.evidence||'',source:'feelings',photos:[]});
  }
  return events.sort((a,b)=>{
    const ka=dayKey(a.at),kb=dayKey(b.at);
    return ka===kb?String(b.at).localeCompare(String(a.at)):kb.localeCompare(ka);
  });
}
function renderUsStory(events,shown=US_LIMITS.story){
  if(!events.length)return '<p class="dim us-empty">Your shared story is still beginning. Meaningful moments will appear here as they happen.</p>';
  const page=events.slice(0,shown),today=dayKey(new Date().toISOString());
  const days=[];
  for(const e of page){const key=dayKey(e.at);if(!days.length||days.at(-1).key!==key)days.push({key,items:[]});days.at(-1).items.push(e);}
  return `<div class="us-story">${days.map(day=>`<div class="us-story-day">
      <h3 class="us-story-date">${esc(usDayLabel(day.key,today))}</h3>
      <ol class="us-story-events">${day.items.map(e=>`<li class="us-story-event is-${esc(e.type)}">
        <span class="us-story-marker" aria-hidden="true">${e.label}</span>
        <div class="us-story-content">
          ${e.title?`<p class="us-story-title">${esc(e.title)}</p>`:''}
          ${e.text?`<p class="us-story-text${e.title?'':' is-lead'}">${esc(e.text)}</p>`:''}
          ${e.evidence?`<details class="us-story-evidence"><summary>Context &amp; evidence</summary><p>${esc(e.evidence)}</p></details>`:''}
        </div>
      </li>`).join('')}</ol>
    </div>`).join('')}</div>`+
    (events.length>page.length?`<button type="button" class="quiet" data-us-action="story-more">Show earlier</button>`:'');
}

/* ----------------------------------------------------------------- memories */
/* A handful, not the ledger: the newest from each category in turn, so the
   preview says a little about several parts of a life rather than five things
   about one. */
/* Many facts are verbatim quotes ("X said: …") or one dated episode. They are
   kept, and the library shows them, but a preview of five reads better from
   statements about a person than from transcript. Deterministic, no model. */
const PREVIEW_CATEGORY_BONUS={likes:1,dislikes:1,people:1,places:1,history:1,health:.5,school:.5};
function memoryPreviewScore(f){
  const text=String(f.statement||'');let score=PREVIEW_CATEGORY_BONUS[f.category]||0;
  if(/\bsaid:|^["“']/i.test(text))score-=3;
  if(/\d{4}-\d{2}-\d{2}/.test(text))score-=2;
  if(text.length>140)score-=1;
  return score;
}
/* The same fact is sometimes filed twice in different words or categories;
   one of each is enough for a preview. This is legacy display protection, not
   the authoritative duplicate definition: it only hides a preview row, the
   library still lists every active record, and the ledger is never touched.
   Conservative on purpose -- two statements count as one only when every
   content word of one appears in the other and they differ by no number,
   ordinal or negation, so "likes"/"dislikes", Alice/Beth, or the first and
   second spare PC stay two memories. A statement that only adds detail to
   another (the same card, "to install in" it) may be hidden behind it here. */
const US_FILLER=new Set(['a','an','the','to','in','into','for','of','on','at','by','from','with','and','his','her','their','its','my','your']);
const US_DISTINCT=/^(\d.*|no|not|never|none|nor|doesn|don|didn|isn|wasn|won|can|cannot|t|first|second|third|fourth|fifth|last|next|previous|other|another|former|latter|one|two|three|four|five|six|seven|eight|nine|ten)$/;
const usFactWords=f=>new Set(String(f.statement||'').toLowerCase().normalize('NFKC').replace(/[’']s\b/g,'').split(/[^\p{L}\p{N}.]+/u)
  .map(w=>w.replace(/^\.+|\.+$/g,'')).filter(w=>w&&!US_FILLER.has(w)));
function usLikelySameFact(a,b){
  const x=usFactWords(a),y=usFactWords(b);
  const [small,big]=x.size<=y.size?[x,y]:[y,x];
  if(small.size<4)return small.size===big.size&&[...small].every(w=>big.has(w));
  if(![...small].every(w=>big.has(w)))return false;
  return ![...big].some(w=>!small.has(w)&&US_DISTINCT.test(w));
}
function usMemoryPreview(facts,limit=US_LIMITS.memories){
  const byCat=new Map();
  const ranked=(facts||[]).map(f=>[memoryPreviewScore(f),f]).sort((a,b)=>b[0]-a[0]||String(b[1].recorded_at||'').localeCompare(String(a[1].recorded_at||''))).map(([,f])=>f);
  for(const f of ranked){
    const key=f.category||'other';if(!byCat.has(key))byCat.set(key,[]);byCat.get(key).push(f);
  }
  const lanes=[...byCat.values()],out=[];
  for(let round=0;out.length<limit&&lanes.some(l=>l.length>round);round++)
    for(const lane of lanes){
      const f=lane[round];if(!f||out.length>=limit||out.some(g=>usLikelySameFact(f,g)))continue;
      out.push(f);
    }
  return out;
}
function memoryDetailHTML(f){
  return `<div class="us-memory-detail">
    <p class="us-memory-meta"><span class="dim small">Category</span> ${esc(usCap(f.category||'other'))}</p>
    ${f.evidence?`<details class="us-evidence"><summary>Why this is remembered</summary><p>“${esc(f.evidence)}”</p></details>`:''}
    <button type="button" class="quiet small-btn" data-us-action="forget" data-fact="${esc(f.id)}">Mark incorrect</button>
  </div>`;
}
function memoryRowHTML(f){
  return `<details class="us-memory-row">
    <summary><span class="us-memory-icon" aria-hidden="true">${FACT_ICON[f.category]||FACT_ICON.other}</span><span class="us-memory-text">${esc(f.statement)}</span></summary>
    ${memoryDetailHTML(f)}
  </details>`;
}
function usMemoryPreviewHTML(facts){
  const rows=usMemoryPreview(facts);
  if(!rows.length)return '<p class="dim us-empty">Nothing has been written down about you yet.</p>';
  return `<div class="us-memory-preview">${rows.map(memoryRowHTML).join('')}</div>
    <button type="button" class="link-button" data-us-action="library">View all ${facts.length} ${facts.length===1?'memory':'memories'} →</button>`;
}
/* The full library: the old Memories page's search, category filter, paging
   and correction, in a dialog for when you mean to audit rather than browse. */
function renderMemoryLibrary(facts,{query='',category='all',shown=US_LIMITS.library}={}){
  const q=query.toLowerCase();
  const matches=facts.filter(f=>(category==='all'||f.category===category)&&
    (!q||(f.statement+' '+(f.evidence||'')+' '+(f.category||'')).toLowerCase().includes(q)));
  const page=matches.slice(0,shown);
  return {matches:matches.length,html:`<p class="dim small" role="status">${matches.length===facts.length?`${facts.length} remembered`:`${matches.length} of ${facts.length}`}</p>
    <div class="memory-grid">${page.map(f=>`<div class="memory-card">
        <div class="memory-card-header">
          <span class="pill">${esc(f.category||'other')}</span>
          <button type="button" class="quiet small-btn" data-us-action="forget" data-fact="${esc(f.id)}">Mark incorrect</button>
        </div>
        <div class="memory-statement">${esc(f.statement)}</div>
        ${f.evidence?`<details class="us-evidence"><summary>Why this is remembered</summary><p>“${esc(f.evidence)}”</p></details>`:''}
      </div>`).join('')||'<p class="dim small" style="grid-column:1/-1;padding:24px;text-align:center">Nothing matches this filter.</p>'}</div>
    ${matches.length>page.length?'<div class="vault-recent-more"><button type="button" class="quiet" data-us-action="library-more">Show more</button></div>':''}`};
}
function openMemoryLibrary(facts,onForget){
  const categories=['all',...new Set(facts.map(f=>f.category).filter(Boolean))];
  const state={query:'',category:'all',shown:US_LIMITS.library};
  dialog('All memories',`<div id="memory-library">
    <div class="memory-filters">
      <input type="search" id="memory-search" placeholder="Search memories and why they are remembered…" aria-label="Search memories">
      <select id="memory-category" aria-label="Category">${categories.map(c=>`<option value="${esc(c)}">${c==='all'?'All categories':esc(usCap(c))}</option>`).join('')}</select>
    </div>
    <div id="memory-library-results"></div>
    <p class="dim small">Marking something incorrect records a superseding correction. The original evidence is kept.</p>
  </div>`);
  const paint=()=>{$('memory-library-results').innerHTML=renderMemoryLibrary(facts,state).html;};
  $('memory-search').oninput=()=>{state.query=$('memory-search').value;state.shown=US_LIMITS.library;paint();};
  $('memory-category').onchange=()=>{state.category=$('memory-category').value;state.shown=US_LIMITS.library;paint();};
  $('memory-library').onclick=async e=>{
    const b=e.target.closest?.('[data-us-action]');if(!b)return;
    if(b.dataset.usAction==='library-more'){state.shown+=US_LIMITS.library;paint();}
    if(b.dataset.usAction==='forget'){b.disabled=true;await onForget(b.dataset.fact);facts=facts.filter(f=>f.id!==b.dataset.fact);paint();}
  };
  paint();
  return {paint,state};
}

/* ----------------------------------------------- the companion's own tastes */
/* Read-only by design: these are theirs to write, not yours to edit. */
function usDiscoveriesHTML(prefs,limit=US_LIMITS.discoveries,companionName='Your companion',pronounSet=''){
  if(!prefs.length)return `<p class="dim us-empty">${esc(companionName)} has not recorded any preferences of ${usPronouns(pronounSet).poss} own yet.</p>`;
  const rows=prefs.slice(0,limit);
  return `<ul class="us-discoveries">${rows.map(p=>{const [mark,word]=PREF_MARK[p.valence]||PREF_MARK.mixed;return `<li class="us-discovery pref-${esc(p.valence||'mixed')}">
      <span class="us-discovery-mark" aria-label="${esc(word)}">${mark}</span>
      <div><p class="us-discovery-subject">${esc(p.subject||p.text)}</p>${p.text&&p.text!==p.subject?`<p class="dim small">${esc(p.text)}</p>`:''}</div>
    </li>`;}).join('')}</ul>`+
    (prefs.length>rows.length?`<button type="button" class="link-button" data-us-action="discoveries-all">See all ${prefs.length} →</button>`:'');
}

/* ------------------------------------------------------ still between you */
/* Alternated, so a long list of questions never hides every carried thread
   from the first few rows. */
function usOpenThreads(questions,loops){
  const asks=(questions||[]).map(q=>({kind:'question',text:q.text,detail:''})).filter(x=>x.text);
  const carried=(loops||[]).map(l=>({kind:'thread',text:l.title,detail:l.detail||l.gentle_use||''})).filter(x=>x.text);
  const out=[];
  for(let i=0;i<Math.max(asks.length,carried.length);i++){if(asks[i])out.push(asks[i]);if(carried[i])out.push(carried[i]);}
  return out;
}
function threadDraft(x){
  // New questions are stored as she would ask them; older ones may describe
  // you in the third person. Quoting either reads fine, so neither is rewritten.
  return x.kind==='question'?`You had this question for me: “${x.text}”`:`Can we come back to “${x.text}”?`;
}
function usOpenThreadsHTML(threads,limit=US_LIMITS.threads){
  if(!threads.length)return '<p class="dim us-empty">Nothing is hanging between conversations right now.</p>';
  const rows=threads.slice(0,limit);
  return `<ul class="us-open-threads">${rows.map(x=>`<li class="us-thread is-${x.kind}">
      <p class="us-thread-kind"><span aria-hidden="true">${x.kind==='question'?'💭':'↗'}</span> ${x.kind==='question'?'Wants to ask':'Still carrying'}</p>
      <p class="us-thread-text">${esc(x.text)}</p>
      ${x.detail?`<p class="dim small">${esc(x.detail)}</p>`:''}
      <button type="button" class="link-button" data-us-action="talk" data-draft="${esc(threadDraft(x))}">Talk about this →</button>
    </li>`).join('')}</ul>`+
    (threads.length>rows.length?`<button type="button" class="link-button" data-us-action="threads-all">See all ${threads.length} →</button>`:'');
}
/* Never sends. The draft goes where the composer already keeps unsent text,
   so Chat opens with it in the box and the person decides what happens next. */
async function openChatWithDraft(text){
  const key=chatKey('draft');let existing='';
  try{existing=sessionStorage.getItem(key)||'';}catch(error){}
  const draft=existing.trim()?existing.replace(/\s+$/,'')+'\n\n'+text:text;
  try{sessionStorage.setItem(key,draft);}catch(error){}
  const stale=$('chat-message');
  await showTab('chat');
  let tries=0;
  const settle=()=>{
    const box=$('chat-message');
    if(current==='chat'&&box&&box!==stale){
      if(!box.value)box.value=draft;
      box.dispatchEvent(new Event('input'));box.focus();
      try{box.setSelectionRange(box.value.length,box.value.length);}catch(error){}
      return;
    }
    if(current==='chat'&&++tries<120)requestAnimationFrame(settle);
  };
  requestAnimationFrame(settle);
}

/* ------------------------------------------------------ the details, kept */
function relationshipDetails(relationship,feelings,standing,companionName){
  const intimacy=relationship?.intimacy||null;
  const platonic=intimacy?.romantic_progression===false;
  const pace=intimacy?({slow:'Gradual',natural:'Natural',quick:'Quick'}[intimacy.pace]||intimacy.pace):'';
  const facts=[
    intimacy?['Stage',esc(intimacy.stage_name||'')]:null,
    intimacy&&!platonic?['Closeness score',`${intimacy.score|0}%`]:null,
    intimacy&&pace?['Pace',esc(pace)]:null,
    feelings?['Temperament',esc(feelings.personality||'—')]:null,
    feelings?.mood?['Mood',esc(feelings.mood)+(feelings.mood_at?` · ${esc(ago(feelings.mood_at))}`:'')]:null,
    intimacy?['Boundary violations',String(intimacy.violations_count|0)]:null,
  ].filter(Boolean);
  return `${standing.length?`<p class="dim small us-standing-line">${standing.length} standing ${standing.length===1?'preference or boundary is':'preferences or boundaries are'} being kept.
      <button type="button" class="link-button" data-us-action="standing" aria-expanded="false" aria-controls="us-standing-list">Review them</button></p>
    <ul class="us-standing-list" id="us-standing-list" hidden>${standing.map(r=>`<li><p>${esc(r.instruction)}</p>${r.evidence?`<details class="us-evidence"><summary>Why this is kept</summary><p>${esc(r.evidence)}</p></details>`:''}</li>`).join('')}</ul>`:''}
  <details class="us-details">
    <summary>How things work between you</summary>
    ${intimacy?.description?`<p class="dim">${esc(intimacy.description)}</p>`:''}
    ${facts.length?`<dl class="fact-list">${facts.map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>`:''}
    ${feelings?feelingMeters(feelings.meters):''}
    <div class="actions"><button type="button" class="quiet" data-us-action="history">View emotional history</button></div>
    ${platonic?'<p class="dim small">Shared experience builds familiarity and trust. This connection has no romantic stages.</p>'
      :'<p class="dim small">Closeness grows through shared experience over time. Companions banter, tease and reciprocate affection as mutual trust deepens; at Bonded, warmth is expressed freely and naturally.</p>'}
    <p class="dim small">${esc(companionName)} holds genuine agency and has preferences and boundaries of ${usPronouns(relationship?.pronoun_set).poss} own. Mutual respect is the condition of all of it — repeated boundary violations step the relationship back to friendship permanently.</p>
  </details>`;
}
function openEmotionalHistory(){
  dialog('Emotional history','<div id="us-history"><p class="dim">Loading…</p></div>');
  return mountFeelingHistory($('us-history')).catch(error=>{if($('us-history'))$('us-history').innerHTML=`<p class="bad">${esc(error.message)}</p>`;});
}
/* Every moment, retired ones too, with the retire action the old page had. */
function openSharedMoments(relationship){
  const kinds=relationship.kinds||{},all=(relationship.moments||[]).slice().reverse();
  let shown=US_LIMITS.moments;
  dialog('Shared moments',`<div id="us-moments">
    ${all.length>8?'<div class="memory-filters"><input type="search" id="moment-search" placeholder="Search moments…" aria-label="Search moments"></div>':''}
    <div class="moment-timeline" id="moment-timeline"></div>
  </div>`);
  const paint=()=>{
    const q=($('moment-search')?.value||'').toLowerCase();
    const hits=all.filter(m=>!q||(m.text+' '+(kinds[m.moment]||m.moment)).toLowerCase().includes(q));
    const page=hits.slice(0,shown);
    $('moment-timeline').innerHTML=(page.map(m=>`<div class="moment-card">
        <div class="moment-card-meta">
          <span class="pill">${esc(MOMENT_TITLE[m.moment]||kinds[m.moment]||m.moment)}</span>
          <span class="dim small">${keepsakeDate(m)}</span>
          <div style="flex:1"></div>
          ${m.status==='active'?`<button type="button" class="quiet small-btn" data-us-action="retire" data-moment="${esc(m.id)}">Retire</button>`:'<span class="dim small">Retired</span>'}
        </div>
        <p style="margin:0;font-size:13.5px;line-height:1.5;color:var(--ink)">${esc(m.text)}</p>
      </div>`).join('')||`<p class="dim small">${q?'No moment matches that.':'No shared moments yet.'}</p>`)+
      (hits.length>page.length?'<button type="button" class="quiet" data-us-action="moments-more">Show earlier moments</button>':'');
  };
  if($('moment-search'))$('moment-search').oninput=()=>{shown=US_LIMITS.moments;paint();};
  $('us-moments').onclick=async e=>{
    const b=e.target.closest?.('[data-us-action]');if(!b)return;
    if(b.dataset.usAction==='moments-more'){shown+=US_LIMITS.moments;paint();}
    if(b.dataset.usAction==='retire'){
      b.disabled=true;
      await post('/relationship/'+encodeURIComponent(b.dataset.moment)+'/retire');
      $('product-dialog').close();notice('Moment retired.');await render('relationship');
    }
  };
  paint();
}

/* ------------------------------------------------------------------ the page */
let usGeneration=0;
workspaceHandlers.relationship=async()=>{
  // Carried threads come from /overview, which is by far the slowest of these
  // (it assembles all of Home). The page draws without it and fills them in.
  const overviewLoad=api('/overview').catch(()=>({loops:[]}));
  const [relationship,ledgers,experiences]=await Promise.all([
    api('/relationship'),
    api('/ledgers'),
    api('/feelings/experiences').catch(()=>({experiences:[],total:0,next_cursor:null}))
  ]);
  if(current!=='relationship')return;
  const generation=++usGeneration;
  const companionName=chatName()||'Your companion';
  const feelings=relationship.bars?.feelings||null;
  let facts=(ledgers.facts||[]).slice();
  const prefs=(ledgers.preferences||[]).slice().reverse();
  let threads=usOpenThreads(ledgers.questions,[]);
  const keep=usKeepsakes(relationship.moments);
  const story=normalizeUsStory({moments:relationship.moments||[],experiences:experiences.experiences||[],
    exclude:new Set(keep.shown.map(m=>m.id))});
  let storyShown=US_LIMITS.story;
  const section=(id,title,intro,body)=>`<section class="us-section" aria-labelledby="${id}-h">
      <div class="us-section-heading"><h2 id="${id}-h">${title}</h2>${intro?`<p class="dim">${intro}</p>`:''}</div>
      <div id="${id}">${body}</div>
    </section>`;

  $('relationship').innerHTML=`<div class="us-page">
    <div class="us-head">
      <h1 class="page-title">Our story</h1>
      <p class="intro">The things that have become part of you two — what happened, what stayed, and what still matters.</p>
    </div>
    ${relationshipHero(relationship,feelings,companionName)}
    ${section('us-recent','Recently','',renderUsStory(story,storyShown))}
    ${section('us-keepsakes','Things that became ours','',usKeepsakesHTML(keep,relationship.moments))}
    ${section('us-memories','Remembered about you','',usMemoryPreviewHTML(facts))}
    ${section('us-discoveries',`Things ${esc(companionName)} has discovered`,'Preferences and little opinions that have emerged along the way.',usDiscoveriesHTML(prefs,US_LIMITS.discoveries,companionName,relationship.pronoun_set))}
    ${section('us-threads','Still between you','Questions, promises, and loose threads that have carried into another conversation.',usOpenThreadsHTML(threads))}
    <div class="us-section us-advanced" id="us-advanced">${relationshipDetails(relationship,feelings,ledgers.standing||[],companionName)}</div>
  </div>`;

  const forget=async id=>{
    await api('/facts/'+encodeURIComponent(id)+'/forget',{method:'POST'});
    notice('Marked incorrect. The original is kept as history.');
    facts=facts.filter(f=>f.id!==id);
    if($('us-memories'))$('us-memories').innerHTML=usMemoryPreviewHTML(facts);
  };
  $('relationship').onclick=async e=>{
    const b=e.target.closest?.('[data-us-action]');if(!b)return;
    const act=b.dataset.usAction;
    if(act==='story-more'){storyShown+=US_LIMITS.story;$('us-recent').innerHTML=renderUsStory(story,storyShown);}
    else if(act==='moments')openSharedMoments(relationship);
    else if(act==='library')openMemoryLibrary(facts,forget);
    else if(act==='forget'){b.disabled=true;await forget(b.dataset.fact);}
    else if(act==='discoveries-all')$('us-discoveries').innerHTML=usDiscoveriesHTML(prefs,Infinity,companionName,relationship.pronoun_set);
    else if(act==='threads-all')$('us-threads').innerHTML=usOpenThreadsHTML(threads,Infinity);
    else if(act==='talk')await openChatWithDraft(b.dataset.draft);
    else if(act==='history')openEmotionalHistory();
    else if(act==='standing'){const list=$('us-standing-list'),open=list.hidden;list.hidden=!open;b.setAttribute('aria-expanded',String(open));}
  };
  const overview=await overviewLoad;
  if(current!=='relationship'||generation!==usGeneration||!$('us-threads'))return;
  threads=usOpenThreads(ledgers.questions,overview.loops);
  $('us-threads').innerHTML=usOpenThreadsHTML(threads);
};
