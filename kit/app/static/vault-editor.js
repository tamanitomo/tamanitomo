/* Vault editor: note tabs, a CodeMirror Source mode, the existing Reading renderer,
   autosave through the vault's revision tokens, drafts that survive a reload, and a
   conflict state that keeps both versions.

   Rules this file keeps:
   - The server's revision token is the only authority. A save sends the revision its
     text was based on; a 409 is a conflict, never retried over the top.
   - One save in flight per note; edits made meanwhile are saved after it, against the
     revision it returned. A response only ever updates the note it was sent for, and
     never replaces text typed after it was sent.
   - The text is never reserialised. CodeMirror keeps the note's own line separator
     (CRLF stays CRLF), a BOM and every unknown construct as typed; sliceDoc() joins
     lines with that separator.
   - Unsaved text is kept in sessionStorage, per installation and profile, bounded, and
     disclosed in the page. It lives exactly as long as this tab's sign-in token.
   - Protected and non-Markdown files open read-only; the API refuses them anyway. */
(()=>{
const CM=window.TamanitomoCodeMirror;
if(!CM){console.error('Vault editor bundle missing');return;}

// PROFILE can be settled by boot() after this script loads (no profile= in the address),
// so the storage scope is read when used, never captured at load.
const scope=()=>`${INSTALLATION||'existing'}|${PROFILE||'default'}`;
const UI_KEY=()=>'vault-ui:'+scope(), DRAFT_KEY=()=>'vault-drafts:'+scope();
const SAVE_DELAY=1200, READING_DELAY=150;
const DRAFT_BUDGET=1_500_000, DRAFT_NOTES=20;      // characters across all drafts; notes kept
const MAX_TABS=12, REMEMBERED=50;
const UNSAVED=new Set(['dirty','saving','offline','failed','conflict','draft']);
const LABELS={loading:'Opening…',saved:'Saved',dirty:'Unsaved changes',saving:'Saving…',
  offline:'Offline — kept in this tab',failed:'Not saved',conflict:'Changed outside the app',
  draft:'Recovered draft — not saved yet',readonly:'Read-only',missing:'Could not open'};

/* ---------- per-viewer UI memory (localStorage; a convenience, may be unavailable) ---------- */
function loadUI(){
  try{const d=JSON.parse(localStorage.getItem(UI_KEY())||'{}');
    return {tabs:Array.isArray(d.tabs)?d.tabs.filter(p=>typeof p==='string').slice(0,MAX_TABS):[],
      active:typeof d.active==='string'?d.active:null,modes:d.modes||{},places:d.places||{},
      expanded:Array.isArray(d.expanded)?d.expanded:null};}
  catch{return {tabs:[],active:null,modes:{},places:{},expanded:null};}
}
const ui={tabs:[],active:null,modes:{},places:{},expanded:null};
let uiScope=null;
function ensureUI(){
  if(uiScope===scope())return;
  uiScope=scope();Object.assign(ui,loadUI());
  if(ui.expanded)vaultExpanded=new Set(ui.expanded);
}
function trim(map){const keys=Object.keys(map);for(const k of keys.slice(0,Math.max(0,keys.length-REMEMBERED)))delete map[k];}
function saveUI(){
  if(uiScope!==scope())return;
  trim(ui.modes);trim(ui.places);
  try{localStorage.setItem(UI_KEY(),JSON.stringify({...ui,expanded:[...vaultExpanded]}));}catch{}
}

/* ---------- drafts (sessionStorage, bounded) ---------- */
const drafts={
  all(){try{const d=JSON.parse(sessionStorage.getItem(DRAFT_KEY())||'{}');return d&&typeof d==='object'?d:{};}catch{return {};}},
  get(path){return this.all()[path]||null;},
  put(path,text,base){
    const all=this.all();delete all[path];
    if(text.length>DRAFT_BUDGET)return this.write(all)&&false;
    all[path]={text,base,at:Date.now()};
    // Evict the oldest other drafts until this one fits the budget and the note count.
    const order=Object.keys(all).sort((a,b)=>all[a].at-all[b].at);
    const size=()=>Object.values(all).reduce((n,d)=>n+d.text.length,0);
    while((size()>DRAFT_BUDGET||Object.keys(all).length>DRAFT_NOTES)&&order.length){
      const old=order.shift();if(old!==path)delete all[old];
    }
    return this.write(all);
  },
  drop(path){const all=this.all();if(path in all){delete all[path];this.write(all);}},
  clear(){try{sessionStorage.removeItem(DRAFT_KEY());}catch{}},
  write(all){try{sessionStorage.setItem(DRAFT_KEY(),JSON.stringify(all));return true;}catch{return false;}},
};

/* ---------- note models ---------- */
const notes=new Map();
let active=null, view=null, generation=0;
function model(path){
  let m=notes.get(path);
  if(!m){m={path,meta:null,disk:null,base:null,state:null,status:'loading',error:'',inflight:false,again:false,
    timer:null,draftTimer:null,retry:0,conflict:null,reads:0,writes:0,draftKept:true,linksSeq:0};notes.set(path,m);}
  return m;
}
const text=m=>m.state?m.state.sliceDoc():'';
const dirty=m=>!!(m.state&&(!m.disk||text(m)!==m.disk.text));
const editable=m=>!!(m.meta&&m.meta.editable);
const separator=s=>s.includes('\r\n')?'\r\n':'\n';

const readOnly=new CM.Compartment();
function makeState(m,doc,selection){
  const saveKey={key:'Mod-s',preventDefault:true,run:()=>{flush(m);return true;}};
  const modeKey={key:'Mod-e',preventDefault:true,run:()=>{cycleMode();return true;}};
  const len=doc.length;
  return CM.EditorState.create({doc,
    selection:selection?CM.EditorSelection.single(Math.min(selection.anchor,len),Math.min(selection.head,len)):undefined,
    extensions:[
      CM.EditorState.lineSeparator.of(separator(doc)),
      CM.history(),CM.drawSelection(),CM.highlightSpecialChars(),CM.EditorView.lineWrapping,
      CM.markdown(),CM.syntaxHighlighting(CM.noteHighlight),
      CM.keymap.of([saveKey,modeKey,...CM.defaultKeymap,...CM.historyKeymap,CM.indentWithTab]),
      readOnly.of([CM.EditorState.readOnly.of(!editable(m)),CM.EditorView.editable.of(editable(m))]),
      CM.EditorView.editorAttributes.of({class:'vault-cm'}),
      CM.EditorView.contentAttributes.of({'aria-label':'Note source','id':'vault-source-content'}),
      CM.EditorView.updateListener.of(u=>{m.state=u.state;
        // Text taken from disk on purpose (reload, use-disk) is not an edit to save.
        if(u.docChanged&&!u.transactions.some(tr=>tr.annotation(CM.Transaction.remote)))edited(m);
        if(u.selectionSet||u.docChanged)remember(m);}),
    ]});
}
function remember(m){
  if(!m.state)return;
  const place=ui.places[m.path]||{};const sel=m.state.selection.main;
  place.anchor=sel.anchor;place.head=sel.head;
  // Scroll is kept as the document position of the top visible line: a pixel offset is
  // meaningless before CodeMirror has measured a long note again.
  if(!m.restoring&&active===m.path&&view&&view.state===m.state&&view.dom.isConnected&&view.scrollDOM.clientHeight)
    place.top=view.lineBlockAtHeight(view.scrollDOM.scrollTop).from;
  const r=!m.restoring&&active===m.path&&$('vault-preview');if(r&&!r.hidden&&r.clientHeight)place.reading=r.scrollTop;
  ui.places[m.path]=place;clearTimeout(remember.t);remember.t=setTimeout(saveUI,400);
}

/* ---------- reading the disk ---------- */
async function load(m){
  const seq=++m.reads,gen=generation,writes=m.writes;let d;
  try{d=await api('/vault/file?path='+encodeURIComponent(m.path));}
  catch(e){
    if(seq!==m.reads||gen!==generation)return;
    if(!m.state){
      const kept=drafts.get(m.path);
      if(kept&&!e.status){m.disk=null;m.base=kept.base;m.meta=m.meta||{editable:true};m.state=makeState(m,kept.text);m.status='offline';}
      else{m.status='missing';m.error=e.message;}
    }
    return paint(m);
  }
  if(seq!==m.reads||gen!==generation)return;           // an older read answered late
  // A read that started before a save (or while one was in flight) may carry the text that
  // save replaced; the save's own answer is newer. Read again rather than adopt it.
  if(m.state&&(writes!==m.writes||m.inflight)){if(!m.inflight)revalidate(m);return;}
  adopt(m,d);
}
function adopt(m,d){
  const disk={text:d.text,revision:d.revision};
  m.meta={editable:d.editable,protected:d.protected,deletable:d.deletable,protection_reason:d.protection_reason};
  if(!m.state){
    const kept=editable(m)?drafts.get(m.path):null,place=ui.places[m.path];
    if(kept&&kept.text!==d.text){
      m.state=makeState(m,kept.text,place);
      if(kept.base===d.revision){m.disk=disk;m.base=d.revision;m.status='draft';}
      else{m.disk=kept.base&&m.disk?m.disk:{text:null,revision:kept.base};m.base=kept.base;conflict(m,disk);}
    }else{
      if(kept)drafts.drop(m.path);
      m.disk=disk;m.base=d.revision;m.state=makeState(m,d.text,place);m.status=editable(m)?'saved':'readonly';
    }
    return paint(m,true);
  }
  // Revalidation: never overwrite what is in the buffer.
  if(d.revision===m.base){m.disk=disk;return paint(m);}
  if(text(m)===d.text){m.disk=disk;m.base=d.revision;m.conflict=null;m.status=editable(m)?'saved':'readonly';drafts.drop(m.path);return paint(m);}
  if(m.status==='conflict'){m.conflict=disk;return paint(m);}
  if(!dirty(m)&&!m.inflight){
    // Nothing unsaved here: take the new disk text as an undoable change, and say so.
    replaceBuffer(m,d.text);m.disk=disk;m.base=d.revision;m.status=editable(m)?'saved':'readonly';
    if(active===m.path)notice('This note changed outside the app; showing the new version.');
    return paint(m);
  }
  conflict(m,disk);
}
function replaceBuffer(m,doc){
  const tr={changes:{from:0,to:m.state.doc.length,insert:m.state.toText(doc)},
            annotations:CM.Transaction.remote.of(true)};
  if(active===m.path&&view&&view.state===m.state)view.dispatch(tr);
  else m.state=m.state.update(tr).state;
}
function revalidate(m){if(m.state&&!m.inflight&&m.status!=='missing')load(m);}

/* ---------- editing and saving ---------- */
function edited(m){
  if(!editable(m))return;
  clearTimeout(m.draftTimer);
  m.draftTimer=setTimeout(()=>keep(m),300);
  if(m.status==='conflict'){paintStatus(m);return;}
  if(m.status!=='saving'&&m.status!=='offline')m.status=dirty(m)?'dirty':'saved';
  schedule(m,SAVE_DELAY);paintStatus(m);scheduleReading();
}
function keep(m){
  if(!dirty(m)&&m.status!=='conflict'){drafts.drop(m.path);m.draftKept=true;return;}
  m.draftKept=drafts.put(m.path,text(m),m.base);paintStatus(m);
}
function schedule(m,delay){clearTimeout(m.timer);m.timer=setTimeout(()=>save(m),delay);}
function flush(m){clearTimeout(m.timer);return save(m);}
async function save(m){
  if(notes.get(m.path)!==m||!editable(m)||!m.state||m.status==='conflict'||m.status==='missing')return;
  if(m.inflight){m.again=true;return;}
  const body=text(m);
  if(m.disk&&body===m.disk.text){if(UNSAVED.has(m.status)&&m.status!=='conflict'){m.status='saved';drafts.drop(m.path);paintStatus(m);}return;}
  const base=m.base,gen=generation;
  m.inflight=true;m.writes++;m.status='saving';paintStatus(m);keep(m);
  let d;
  try{d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path:m.path,text:body,revision:base||''})});}
  catch(e){
    m.inflight=false;if(gen!==generation||notes.get(m.path)!==m)return;
    if(e.status===409){
      try{const now=await api('/vault/file?path='+encodeURIComponent(m.path));
        if(gen!==generation||notes.get(m.path)!==m)return;
        // Our own earlier save may have landed without its answer reaching us.
        if(now.text===text(m)){m.disk={text:now.text,revision:now.revision};m.base=now.revision;m.status='saved';drafts.drop(m.path);return paintStatus(m);}
        conflict(m,{text:now.text,revision:now.revision});}
      catch(err){if(gen===generation&&notes.get(m.path)===m)conflict(m,{text:null,revision:null});}
      return;
    }
    if(!e.status){m.status='offline';m.retry=Math.min((m.retry||2)*2,60);schedule(m,m.retry*1000);}
    else{m.status='failed';m.error=e.message;}
    keep(m);return paintStatus(m);
  }
  m.inflight=false;if(gen!==generation||notes.get(m.path)!==m)return;
  m.retry=0;m.disk={text:d.text,revision:d.revision};m.base=d.revision;
  if(text(m)===d.text){m.status='saved';drafts.drop(m.path);}
  else{m.status='dirty';schedule(m,SAVE_DELAY);}
  if(m.again){m.again=false;schedule(m,0);}
  paintStatus(m);if(m.path===active){listTreeQuietly(m.path);paintBacklinksPanel(m);}
}
function conflict(m,disk){
  clearTimeout(m.timer);m.conflict=disk;m.status='conflict';keep(m);paint(m);
}

/* ---------- conflict resolution: explicit, both versions kept ---------- */
function copyPath(path){
  const stamp=new Date().toISOString().slice(0,19).replace('T',' ').replace(/:/g,'');
  return path.replace(/\.md$/i,'')+` (my copy ${stamp}).md`;
}
async function keepMineAsCopy(m){
  const target=copyPath(m.path),body=text(m),priorConflict=m.conflict,requestScope=scope();
  const d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path:target,text:body,revision:''})});
  // This receipt covers the submitted text, not edits or navigation made while it was pending.
  if(requestScope!==scope()||notes.get(m.path)!==m)return;
  const unchanged=text(m)===body&&m.conflict===priorConflict&&m.status==='conflict';
  if(unchanged){
    if(m.conflict&&m.conflict.text!=null){replaceBuffer(m,m.conflict.text);m.disk=m.conflict;m.base=m.conflict.revision;}
    m.conflict=null;m.status='saved';drafts.drop(m.path);
  }else keep(m);
  const copy=model(d.path);adopt(copy,d);
  if(unchanged&&active===m.path)open(d.path);
  notice('Your submitted version was saved as '+d.path.split('/').pop()+
    (unchanged?'. The original shows the version from disk.':'. Newer edits remain in the original note.'));
}
async function useDisk(m){
  if(!m.conflict||m.conflict.text==null)return load(m);
  replaceBuffer(m,m.conflict.text);m.disk=m.conflict;m.base=m.conflict.revision;m.conflict=null;
  m.status='saved';drafts.drop(m.path);paint(m);
  notice('Showing the version from disk. Undo (Ctrl+Z) brings your text back.');
}
async function keepMine(m){
  if(!m.conflict||!m.conflict.revision)return load(m);
  if(!await confirmReplace())return;
  m.base=m.conflict.revision;m.disk=m.conflict;m.conflict=null;m.status='dirty';paint(m);flush(m);
}
function confirmReplace(){
  return new Promise(resolve=>{
    const d=document.createElement('dialog');d.className='editor-leave-dialog';d.setAttribute('aria-label','Replace the disk version');
    d.innerHTML='<h2>Replace the version on disk?</h2><p>Your text is saved over the version that changed outside the app. That version is kept as an editor backup in the vault.</p><div class="actions"><button class="quiet" data-no autofocus>Cancel</button><button class="act" data-yes>Replace with mine</button></div>';
    const done=v=>{d.close();d.remove();resolve(v);};
    d.querySelector('[data-no]').onclick=()=>done(false);d.querySelector('[data-yes]').onclick=()=>done(true);
    d.addEventListener('cancel',e=>{e.preventDefault();done(false);});document.body.append(d);d.showModal();
  });
}
function lineDiff(a,b){
  const x=a.split(/\r?\n/),y=b.split(/\r?\n/);
  if(x.length*y.length>4_000_000)return null;
  const n=x.length,k=y.length,t=Array.from({length:n+1},()=>new Uint16Array(k+1));
  for(let i=n-1;i>=0;i--)for(let j=k-1;j>=0;j--)t[i][j]=x[i]===y[j]?t[i+1][j+1]+1:Math.max(t[i+1][j],t[i][j+1]);
  const out=[];let i=0,j=0;
  while(i<n||j<k){
    if(i<n&&j<k&&x[i]===y[j]){out.push([' ',x[i]]);i++;j++;}
    else if(j<k&&(i>=n||t[i][j+1]>=t[i+1][j])){out.push(['+',y[j]]);j++;}
    else{out.push(['-',x[i]]);i++;}
  }
  return out;
}
function compare(m){
  const disk=m.conflict&&m.conflict.text!=null?m.conflict.text:'(The disk version could not be read.)';
  const diff=lineDiff(disk,text(m));
  const rows=diff?diff.map(([s,l])=>`<div class="vault-diff-${s==='+'?'add':s==='-'?'del':'same'}"><span aria-hidden="true">${s}</span> ${esc(l)||'&nbsp;'}</div>`).join(''):'';
  dialog('Compare versions',`<p class="dim small">Lines marked − are only on disk; + only in your text. Nothing changes until you choose.</p>
    ${diff?`<div class="vault-diff" role="region" aria-label="Line differences">${rows}</div>`:''}
    <div class="vault-compare"><section><h3>On disk</h3><pre>${esc(disk)}</pre></section><section><h3>Yours</h3><pre>${esc(text(m))}</pre></section></div>`);
}

/* ---------- tabs ---------- */
async function open(path,mode){
  ensureUI();
  if(!ui.tabs.includes(path)){ui.tabs.push(path);while(ui.tabs.length>MAX_TABS){const drop=ui.tabs.find(p=>p!==path&&!UNSAVED.has(model(p).status));if(!drop)break;ui.tabs.splice(ui.tabs.indexOf(drop),1);}}
  if(mode)ui.modes[path]=mode;
  switchTo(path);
  const m=model(path);
  if(!m.state)await load(m);else revalidate(m);
}
function switchTo(path){
  if(active&&active!==path){const old=notes.get(active);if(old)remember(old);}
  active=path;ui.active=path;saveUI();
  const m=model(path);
  openNote={path,...(m.meta||{}),revision:m.base};
  paint(m,true);renderVaultTree();
}
async function close(path){
  const m=notes.get(path);
  if(m&&UNSAVED.has(m.status)){
    if(m.status==='dirty'||m.status==='saving'){await flush(m);}     // a recovered draft is never saved unasked
    if(UNSAVED.has(m.status)&&!await askToDiscard())return;
    drafts.drop(path);
  }
  const i=ui.tabs.indexOf(path);if(i>=0)ui.tabs.splice(i,1);
  if(m){clearTimeout(m.timer);clearTimeout(m.draftTimer);}
  notes.delete(path);delete ui.places[path];
  if(active===path){active=null;ui.active=null;const next=ui.tabs[Math.min(i,ui.tabs.length-1)];if(next)return open(next);openNote=null;}
  saveUI();paint(null,true);renderVaultTree();
}
function cycleMode(){
  if(!active)return;const m=model(active);if(!editable(m))return;
  const order=['preview','edit','split'];setMode(order[(order.indexOf(modeOf(m))+1)%3]);
}
const modeOf=m=>editable(m)?(ui.modes[m.path]||'edit'):'preview';
function setMode(mode){if(!active)return;ui.modes[active]=mode;saveUI();paint(model(active),false,true);}

/* ---------- drawing ---------- */
function ensureView(){
  if(view)return view;
  view=new CM.EditorView({state:CM.EditorState.create({doc:'',extensions:CM.EditorView.editorAttributes.of({class:'vault-cm'})})});
  return view;
}
function shell(){
  const main=$('vault-main');if(!main)return null;
  if(!$('vault-tabs')){
    main.innerHTML=`<div class="vault-tabs" id="vault-tabs" role="tablist" aria-label="Open notes"></div>
      <div id="vault-document"></div>`;
  }
  return main;
}
function paintTabs(){
  const bar=$('vault-tabs');if(!bar)return;
  bar.innerHTML=ui.tabs.map(p=>{const m=notes.get(p),s=m?m.status:'loading',name=p.split('/').pop();
    return `<div class="vault-tab${p===active?' is-active':''}" data-state="${esc(s)}"><button role="tab" aria-selected="${p===active}" data-tab-path="${esc(p)}" title="${esc(p)}"><span class="vault-tab-dot" aria-hidden="true"></span>${esc(name)}${UNSAVED.has(s)?'<span class="sr-only"> (unsaved)</span>':''}</button><button class="vault-tab-close" data-close-path="${esc(p)}" aria-label="Close ${esc(name)}">×</button></div>`;}).join('');
  for(const b of bar.querySelectorAll('[data-tab-path]'))b.onclick=()=>open(b.dataset.tabPath);
  for(const b of bar.querySelectorAll('[data-close-path]'))b.onclick=()=>close(b.dataset.closePath);
}
function paint(m,rebuild=false,modeOnly=false){
  if(current!=='vault'||!shell())return;
  paintTabs();
  if(m&&m.path!==active)return;
  m=active?model(active):null;
  const doc=$('vault-document');
  if(!m){doc.innerHTML=`<div class="vault-empty-state" style="margin:auto;text-align:center;padding:48px 24px"><div style="font-size:36px;margin-bottom:12px;opacity:0.6">📖</div><p class="dim" style="font-size:15px;margin:0 0 6px">Select a document from the vault or create a new note.</p><span class="dim small">Markdown, notes, and journals stay Obsidian-compatible</span></div>`;return;}
  if(m.status==='missing'){doc.innerHTML=`<div class="card"><h2>${esc(m.path)}</h2><p class="dim">${esc(m.error)}</p><a class="act" href="${mediaUrl('/api/vault/download?path='+encodeURIComponent(m.path))}" download>Download file</a></div>`;return;}
  if(!m.state){doc.innerHTML=`<p class="dim" role="status" style="padding:24px">Opening ${esc(m.path.split('/').pop())}…</p>`;return;}
  if(rebuild||modeOnly||!doc.querySelector('.vault-doc-header')||doc.dataset.path!==m.path)build(m,doc);
  paintStatus(m);
}
function build(m,doc){
  const parts=m.path.split('/'),file=parts.pop(),folder=parts.join('/'),mode=modeOf(m),ed=editable(m);
  const hadFocus=view&&view.hasFocus;
  const place={...(ui.places[m.path]||{})};      // read before detaching fires any scroll event
  m.restoring=true;
  doc.dataset.path=m.path;
  doc.innerHTML=`<div class="vault-doc-header">
   <div>
    <div class="vault-doc-title"><button class="quiet vault-files-toggle" id="vault-files-toggle" aria-controls="vault-folders" title="Show files">☰</button>
     <span class="dim">📁 ${esc(folder||'vault')} /</span><strong>${esc(file)}</strong>
     ${m.meta.protected?'<span class="vault-node-tag is-protected">Read-only</span>':ed?'<span class="vault-node-tag">Editable</span>':'<span class="vault-node-tag">Read-only</span>'}</div>
    <div class="vault-doc-meta"><span id="vault-meta-words">0 words</span><span>·</span><span id="vault-meta-chars">0 chars</span><span>·</span>
     <span id="vault-save-status" role="status" aria-live="polite" class="vault-status"></span></div>
   </div>
   <div class="actions">
    ${ed?`<div class="vault-mode-switch" role="group" aria-label="View">
      <button class="vault-mode-btn ${mode==='preview'?'active':''}" data-vault-mode="preview" aria-pressed="${mode==='preview'}">Reading</button>
      <button class="vault-mode-btn ${mode==='edit'?'active':''}" data-vault-mode="edit" aria-pressed="${mode==='edit'}">Source</button>
      <button class="vault-mode-btn ${mode==='split'?'active':''}" data-vault-mode="split" aria-pressed="${mode==='split'}">Split</button></div>
     <button class="act" id="save-note">Save</button>`:''}
    <button class="quiet" id="vault-toggle-toc" aria-pressed="false" title="Outline, properties &amp; backlinks">Info</button>
    ${m.meta.deletable?'<button class="quiet" id="trash-open-note">Trash</button>':''}
    <a class="quiet" href="${mediaUrl('/api/vault/download?path='+encodeURIComponent(m.path))}" download>Download</a>
   </div>
  </div>
  ${m.meta.protected?`<div class="vault-protected-bar"><span>🔒 <strong>Protected companion record</strong> · ${esc(m.meta.protection_reason||'Read-only in Vault.')}</span><button class="quiet" id="vault-edit-companion-btn">Edit in companion settings →</button></div>`:''}
  <div id="vault-conflict"></div>
  ${ed?`<div class="vault-toolbar-editor" id="vault-toolbar" ${mode==='preview'?'hidden':''}>
   ${[['bold','<b>B</b>','Bold (**)'],['italic','<i>I</i>','Italic (*)'],['h2','H2','Heading 2'],['h3','H3','Heading 3'],['link','[[ ]]','Wikilink'],['list','• List','Bullet list'],['task','☑ Task','Task list'],['code','&lt;/&gt;','Code block'],['quote','&ldquo; Quote','Quote']].map(([t,l,h])=>`<button class="vault-tool-btn" data-tool="${t}" title="${h}">${l}</button>`).join('')}</div>`:''}
  <div class="vault-editor-content">
   <div class="vault-split-view" id="vault-views" data-mode="${mode}">
    <div class="vault-source" id="vault-source" ${mode==='preview'?'hidden':''}></div>
    <div class="vault-preview-container document" id="vault-preview" ${mode==='edit'?'hidden':''}></div>
   </div>
   <div class="vault-toc-panel" id="vault-toc" hidden>
    <div class="vault-toc-section" id="vault-properties-section" hidden><div class="vault-toc-header">Properties</div><div id="vault-properties-list"></div></div>
    <div class="vault-toc-section"><div class="vault-toc-header">Outline</div><div id="vault-toc-list"></div></div>
    <div class="vault-toc-section"><div class="vault-toc-header">Backlinks</div><div id="vault-backlinks-list"><p class="dim small">Loading…</p></div></div>
   </div>
  </div>
  ${ed?`<p class="vault-draft-note dim small" id="vault-draft-note">Unsaved edits are kept in this browser tab until they are saved; they are cleared when the tab closes. <button class="link-button" id="vault-clear-drafts">Clear kept drafts</button></p>`:''}`;
  const v=ensureView();
  if(mode!=='preview'){$('vault-source').append(v.dom);if(v.state!==m.state)v.setState(m.state);}
  else if(v.state!==m.state)v.setState(m.state);
  wire(m);paintReading(m);paintBacklinksPanel(m);
  requestAnimationFrame(()=>{
    if(mode!=='preview'&&place.top!=null&&v.state===m.state)
      v.dispatch({effects:CM.EditorView.scrollIntoView(Math.min(place.top,v.state.doc.length),{y:'start'})});
    const r=$('vault-preview');if(r&&place.reading!=null)r.scrollTop=place.reading;
    if(hadFocus&&mode!=='preview')v.focus();
    requestAnimationFrame(()=>{m.restoring=false;});
  });
  v.scrollDOM.onscroll=()=>remember(m);
  const r=$('vault-preview');if(r)r.onscroll=()=>remember(m);
}
function wire(m){
  for(const b of document.querySelectorAll('#vault-document [data-vault-mode]'))b.onclick=()=>setMode(b.dataset.vaultMode);
  if($('save-note'))$('save-note').onclick=()=>{if(m.status==='conflict')return compare(m);if(m.status==='failed'||m.status==='offline'){m.status='dirty';}flush(m);};
  if($('trash-open-note'))$('trash-open-note').onclick=async()=>{
    if(UNSAVED.has(m.status)&&!await askToDiscard())return;
    await post('/vault/trash',{path:m.path,revision:m.base});drafts.drop(m.path);
    const folder=m.path.split('/').slice(0,-1).join('/');m.status='saved';await close(m.path);
    await listVault(folder||'',false);notice('Moved to trash.');
  };
  if($('vault-edit-companion-btn'))$('vault-edit-companion-btn').onclick=()=>showTab('companion-edit');
  if($('vault-toggle-toc'))$('vault-toggle-toc').onclick=()=>{
    const panel=$('vault-toc'),shown=panel.hidden;panel.hidden=!shown;
    $('vault-toggle-toc').setAttribute('aria-pressed',String(shown));
    paintReading(m);if(shown)paintBacklinksPanel(m);
  };
  if($('vault-clear-drafts'))$('vault-clear-drafts').onclick=()=>{drafts.clear();for(const x of notes.values())x.draftKept=false;paintStatus(m);notice('Drafts kept in this tab were cleared. Open notes still hold their text until you close them.');};
  if($('vault-files-toggle'))$('vault-files-toggle').onclick=()=>document.body.classList.toggle('vault-files-open');
  for(const b of document.querySelectorAll('#vault-document [data-tool]'))b.onclick=()=>tool(m,b.dataset.tool);
}
function tool(m,name){
  if(!view||view.state!==m.state)return;
  const s=view.state,sel=s.selection.main,picked=s.sliceDoc(sel.from,sel.to),nl=s.lineBreak;
  const forms={bold:['**','**','bold text'],italic:['*','*','italic text'],h2:[nl+'## ',nl,'Heading 2'],h3:[nl+'### ',nl,'Heading 3'],
    link:['[[',']]','Note'],list:[nl+'- ',nl,'List item'],task:[nl+'- [ ] ',nl,'New task'],code:['```'+nl,nl+'```','code'],quote:[nl+'> ',nl,'Quote']};
  const [pre,post,fill]=forms[name],inner=picked||fill;
  view.dispatch({changes:{from:sel.from,to:sel.to,insert:pre+inner+post},
    selection:{anchor:sel.from+pre.length,head:sel.from+pre.length+inner.length},userEvent:'input'});
  view.focus();
}
function paintStatus(m){
  if(!m||m.path!==active)return paintTabs();
  const label=$('vault-save-status');
  if(label){
    label.dataset.state=m.status;
    label.textContent=LABELS[m.status]+(m.status==='failed'&&m.error?': '+m.error:'')+
      (UNSAVED.has(m.status)&&!m.draftKept?' — too large to keep as a draft; save to keep it':'');
    label.className='vault-status small status-'+m.status;
  }
  const t=text(m),words=t.trim()?t.trim().split(/\s+/).length:0;
  if($('vault-meta-words'))$('vault-meta-words').textContent=words+' words';
  if($('vault-meta-chars'))$('vault-meta-chars').textContent=t.length+' chars';
  const bar=$('vault-conflict');
  if(bar){
    if(m.status==='conflict'){
      bar.innerHTML=`<div class="vault-conflict-bar" role="alert"><p><strong>This note changed outside the app while you had unsaved edits.</strong> Both versions are kept: yours here, the other on disk. Nothing is saved until you choose.</p>
       <div class="actions"><button class="quiet" id="vault-compare">Compare</button><button class="quiet" id="vault-save-copy">Save mine as a copy</button><button class="quiet" id="vault-use-disk">Use the disk version</button><button class="act" id="vault-keep-mine">Replace disk with mine…</button></div></div>`;
      $('vault-compare').onclick=()=>compare(m);$('vault-save-copy').onclick=()=>keepMineAsCopy(m).catch(e=>notice(e.message,true));
      $('vault-use-disk').onclick=()=>useDisk(m);$('vault-keep-mine').onclick=()=>keepMine(m);
    }else if(m.status==='failed'||m.status==='offline'||m.status==='draft'){
      bar.innerHTML=`<div class="vault-retry-bar"><span>${m.status==='draft'?'Unsaved text from before the page reloaded was recovered.':m.status==='offline'?'The server could not be reached. Your text is kept in this tab and will be saved when the connection returns.':'The save was refused. Your text is kept in this tab.'}</span>
        <span class="actions"><button class="quiet" id="vault-retry">${m.status==='draft'?'Save it':'Try again'}</button>${m.status==='draft'?'<button class="quiet" id="vault-discard">Discard it</button>':''}</span></div>`;
      $('vault-retry').onclick=()=>{m.status='dirty';flush(m);};
      if($('vault-discard'))$('vault-discard').onclick=()=>{replaceBuffer(m,m.disk.text);m.status='saved';drafts.drop(m.path);paint(m);};
    }else bar.innerHTML='';
  }
  if($('save-note'))$('save-note').disabled=m.status==='saved'||m.status==='saving';
  paintTabs();
}
let readingTimer=null;
function scheduleReading(){clearTimeout(readingTimer);readingTimer=setTimeout(()=>{if(active)paintReading(model(active));},READING_DELAY);}
function paintReading(m){
  const pane=$('vault-preview');if(!pane||pane.hidden&&$('vault-toc')?.hidden)return;
  const body=text(m),folder=m.path.split('/').slice(0,-1).join('/');
  if(!pane.hidden){
    pane.innerHTML=renderObsidianMarkdown(body);
    for(const b of pane.querySelectorAll('.wiki-link'))b.onclick=()=>{
      const target=b.dataset.link.trim(),file=target.endsWith('.md')?target:target+'.md';
      open(file.includes('/')?file:(folder?folder+'/'+file:'notes/'+file));
    };
    hydrateVaultEmbeds(pane,m.path);
  }
  const toc=extractVaultTOC(body),list=$('vault-toc-list');
  if(list){
    list.innerHTML=toc.length?toc.map((h,i)=>`<button class="vault-toc-item h${h.level}" data-toc="${i}">${esc(h.title)}</button>`).join(''):'<p class="dim small">No headings in document.</p>';
    for(const b of list.querySelectorAll('[data-toc]'))b.onclick=()=>{
      const h=toc[+b.dataset.toc];
      if(!$('vault-preview').hidden){const el=$(h.id);if(el)el.scrollIntoView({block:'start'});}
      else if(view){let seen=-1;for(let n=1;n<=view.state.doc.lines;n++){const line=view.state.doc.line(n);if(/^#{1,3}\s+/.test(line.text)&&++seen===+b.dataset.toc){view.dispatch({selection:{anchor:line.from},scrollIntoView:true});view.focus();break;}}}
    };
  }
}
let treeTimer=null;
function listTreeQuietly(path){clearTimeout(treeTimer);treeTimer=setTimeout(()=>{if(current==='vault')listVault(path.split('/').slice(0,-1).join('/'),false).catch(()=>{});},800);}

/* ---------- properties & backlinks panel (LINK-04) ---------- */
async function paintBacklinksPanel(m){
  const path=m.path,seq=++m.linksSeq,propSection=$('vault-properties-section'),propList=$('vault-properties-list'),backList=$('vault-backlinks-list');
  if(!backList)return;
  let d;
  try{d=await api('/vault/links/backlinks?path='+encodeURIComponent(path));}
  catch(e){if(seq!==m.linksSeq||active!==path)return;backList.innerHTML='<p class="dim small">Could not load backlinks.</p>';return;}
  if(seq!==m.linksSeq||active!==path)return;
  const props=Object.entries(d.properties||{});
  if(propSection){
    propSection.hidden=!props.length;
    if(propList)propList.innerHTML=props.map(([k,v])=>
      `<div class="vault-property-row"><span class="vault-property-key">${esc(k)}</span><span class="vault-property-value">${esc(Array.isArray(v)?v.join(', '):String(v))}</span></div>`).join('');
  }
  const rows=[...(d.linked||[]).map(r=>({...r,kind:'linked'})),...(d.ambiguous||[]).map(r=>({...r,kind:'ambiguous'})),
              ...(d.unlinked_mentions||[]).map(r=>({...r,kind:'mention'}))];
  backList.innerHTML=rows.length?rows.map(r=>
    `<button class="vault-toc-item" data-backlink="${esc(r.path)}">${r.kind==='mention'?'~ ':r.embed?'⇲ ':''}${esc(r.path)}${r.kind==='ambiguous'?' (ambiguous)':r.kind==='mention'?' (unlinked mention)':''}</button>`).join('')
    :'<p class="dim small">No backlinks yet.</p>';
  for(const b of backList.querySelectorAll('[data-backlink]'))b.onclick=()=>open(b.dataset.backlink);
}

/* ---------- integration with the Vault page ---------- */
async function mount(){
  ensureUI();
  shell();
  // An expanded folder whose listing was never read showed "Empty folder" (the tree only
  // reads the root). Read the remembered expanded folders, parents first, bounded.
  const open=[...vaultExpanded].sort((a,b)=>a.split('/').length-b.split('/').length).slice(0,50);
  for(const folder of open){
    if(vaultTreeData.has(folder))continue;
    const parent=folder.split('/').slice(0,-1).join('/');
    if(!(vaultTreeData.get(parent)||[]).some(e=>e.directory&&e.path===folder)){vaultExpanded.delete(folder);continue;}
    try{vaultTreeData.set(folder,(await api('/vault?path='+encodeURIComponent(folder))).entries);}
    catch{vaultExpanded.delete(folder);}
  }
  renderVaultTree();
  if(!active&&ui.active&&ui.tabs.includes(ui.active))active=ui.active;
  paint(active?model(active):null,true);
  if(active){const m=model(active);if(!m.state)await load(m);else revalidate(m);}
}
readNote=async function(path){await open(path);};
showNote=function(note,edit=false){
  const m=model(note.path);
  if(!m.state&&note.text!=null&&note.revision!=null)adopt(m,note);
  open(note.path,edit?'edit':undefined);
};
const plainTree=renderVaultTree;
renderVaultTree=function(){plainTree();saveUI();};

window.addEventListener('online',()=>{for(const m of notes.values())if(m.status==='offline'){m.status='dirty';flush(m);}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&current==='vault'&&active)revalidate(model(active));});
window.addEventListener('focus',()=>{if(current==='vault'&&active)revalidate(model(active));});
window.addEventListener('beforeunload',e=>{
  // Drafts survive a reload of this tab, but not closing it.
  if([...notes.values()].some(m=>UNSAVED.has(m.status))){for(const m of notes.values())if(dirty(m))keep(m);e.preventDefault();e.returnValue='';}
});

window.VaultEditor=Object.freeze({mount,open,close,
  // Read-only views for tests and diagnostics.
  status:path=>notes.get(path||active)?.status||null,
  text:path=>{const m=notes.get(path||active);return m?text(m):null;},
  active:()=>active,view:()=>view,limits:{DRAFT_BUDGET,DRAFT_NOTES,SAVE_DELAY},
  drafts:()=>Object.keys(drafts.all())});
})();
