/* Complete management editors, using the active Hermes profile at every boundary. */
function addPage(id,label){TABS.push([id,label]);const section=document.createElement('section');section.id=id;section.hidden=true;document.querySelector('main').append(section);}
addPage('local-models','Local models');addPage('companion-edit','Edit companion');addPage('image-studio','Image studio');
// getRandomValues also works on plain HTTP LAN origins; randomUUID requires HTTPS.
const presetSuffix=()=>Array.from(crypto.getRandomValues(new Uint8Array(8)),v=>v.toString(16).padStart(2,'0')).join('');
// Prompt boxes a workflow keeps. The rest describe one moment, are filled per
// render, and are deliberately not written back when a workflow is saved.
const SAVED_PARTS=['quality','identity'];
const TRANSIENT_PARTS=['scene','wardrobe','lighting','camera'];
const formLabel=key=>key.replaceAll('_',' ').replace(/^./,s=>s.toUpperCase());
/* A lane reads faster with a face on it. Unknown lanes fall back to a star. */
const LANE_ICON={portrait:'\u{1F5BC}\uFE0F',anime:'\u{1F338}',realistic:'\u{1F4F7}',landscape:'\u{1F3D4}\uFE0F',other:'\u2728'};
const laneIcon=key=>LANE_ICON[key]||'\u2728';
/* The kit stores a pronoun set, because that is what the text needs. People
   think of it as gender, so that is what the box asks for; the stored value is
   unchanged. */
const FIELD_LABEL={pronoun_set:'Gender',human_pronoun_set:'Your gender'};
const CHOICE_LABEL={pronoun_set:{she:'Female',he:'Male',they:'They / them'},
                    human_pronoun_set:{she:'Female',he:'Male',they:'They / them'}};
const choiceLabel=(key,value)=>(CHOICE_LABEL[key]||{})[value]||formLabel(value);

const profileChoices={agent_type:['companion','colleague','worker'],pronoun_set:['she','he','they'],human_pronoun_set:['she','he','they'],outreach:['updates_only','free','never'],relationship_progression:['off','subtle','milestones'],relationship_pace:['slow','natural','quick'],context_mode:['auto','fixed']};
function fieldHTML(key,value,choices=[],readonly=false){
 if(key==='outreach_per_day')return `<label>Maximum proactive messages per day<input data-config="outreach_per_day" type="number" required min="1" max="100" value="${value||3}" ${value===0?'disabled':''}></label><label class="inline-label"><input id="editor-unlimited" type="checkbox" ${value===0?'checked':''}>No daily limit (unlimited proactive messages)</label>`;
 const disabled=readonly?'disabled':'';
 const input=choices.length?`<select data-config="${esc(key)}" ${disabled}>${options(choices.map(v=>Array.isArray(v)?v:[v,choiceLabel(key,v)]),value)}</select>`:
 typeof value==='boolean'?`<select data-config="${esc(key)}" ${disabled}>${options([['true','Enabled'],['false','Disabled']],String(value))}</select>`:
 typeof value==='object'?`<textarea data-config="${esc(key)}" ${disabled}>${esc(JSON.stringify(value,null,2))}</textarea>`:
 `<input data-config="${esc(key)}" ${disabled} type="${typeof value==='number'?'number':key==='birthdate'?'date':['quiet_start','quiet_end'].includes(key)?'time':'text'}" ${typeof value==='number'?'step="any"':''} value="${esc(value)}">`;
 return `<label>${esc(FIELD_LABEL[key]||formLabel(key))}${input}${readonly?'<span class="dim small">Storage path · managed by installation</span>':''}</label>`;
}
workspaceHandlers['companion-edit']=async()=>{
 const [d,catalog]=await Promise.all([api('/profile/editor'),api('/catalog')]);
 const groups=[['Identity',['agent','human','names','pronoun_set','human_pronoun_set','agent_type','persona','boundary','birthdate','age','timezone']],['Appearance & contact',['image_style','image_timeline','image_mode','content_permissions','outreach','outreach_per_day','quiet_start','quiet_end','share_people']],['More companion settings',Object.keys(d.config).filter(k=>!['agent','human','names','pronoun_set','human_pronoun_set','agent_type','persona','boundary','birthdate','age','timezone','image_style','image_timeline','image_mode','content_permissions','outreach','outreach_per_day','quiet_start','quiet_end','share_people'].includes(k))]];
 const choices={...profileChoices,timezone:[...new Set([d.config.timezone,...catalog.timezones])].map(z=>[z,z]),persona:Object.entries(catalog.personas).map(([k,v])=>[k,v.label]),boundary:Object.entries(catalog.boundaries).map(([k,v])=>[k,v.label]),image_style:Object.entries(catalog.image_styles).map(([k,v])=>[k,v.label])};
 $('companion-edit').innerHTML=heading('Edit '+d.display_name,'Your companion’s current configuration and authored identity, prefilled from their files.')+`<div class="actions"><button class="quiet" data-editor-route="roster">← All companions</button><button class="quiet" data-editor-route="voice">Voice studio</button><button class="quiet" data-editor-route="image-studio">Image studio</button><button class="quiet" data-editor-route="settings">Settings</button></div><form id="companion-edit-form"><div class="card"><label>Display name <span class="dim small">The name shown in this workspace</span><input id="editor-display-name" value="${esc(d.display_name)}" required maxlength="100"></label></div>${groups.map(([label,keys],i)=>`<details class="card" ${i<2?'open':''}><summary>${label}</summary><div class="form-grid">${keys.map(k=>fieldHTML(k,d.config[k],choices[k]||[],d.fixed.includes(k))).join('')}</div></details>`).join('')}<div class="card"><h2>Who they are</h2><p class="dim">Personality, appearance, boundaries and shared history live in their SOUL, which Identity reads as a document and edits a section at a time. This page is for the configuration around it.</p><div class="actions"><button type="button" class="quiet" data-editor-route="identity">Open Identity \u2192</button></div></div><div class="actions"><button class="act">Save companion</button><button type="button" class="quiet" id="reload-companion">Reload current files</button></div></form>`;
 for(const b of $('companion-edit').querySelectorAll('[data-editor-route]'))b.onclick=()=>showTab(b.dataset.editorRoute);
  $('editor-unlimited').onchange=()=>{$('companion-edit').querySelector('[data-config=outreach_per_day]').disabled=$('editor-unlimited').checked;};
 $('reload-companion').onclick=async()=>{if(await confirmEditorLeave('companion-edit'))render('companion-edit');};
 $('companion-edit-form').onsubmit=async e=>{e.preventDefault();const config={...d.config};for(const input of $('companion-edit').querySelectorAll('[data-config]')){if(input.disabled)continue;const key=input.dataset.config,old=d.config[key];config[key]=typeof old==='boolean'?input.value==='true':typeof old==='number'?Number(input.value):typeof old==='object'?JSON.parse(input.value):input.value;}
 config.outreach_per_day=$('editor-unlimited').checked?0:Number($('companion-edit').querySelector('[data-config=outreach_per_day]').value);
 const result=await post('/profile/editor',{revision:d.revision,config,soul:d.soul,display_name:$('editor-display-name').value});clearEditorDirty('companion-edit');if(result.operation){const row=await followOperation(result.operation);if(row.status!=='complete')return;}await boot();notice('Companion saved with a backup.'+(result.operation?' Background jobs synchronized.':''));};
};

// Obsidian-like Knowledge Vault: hierarchical tree, live markdown preview/split, TOC outline, wikilinks.
let vaultTreeData=new Map(),vaultExpanded=new Set(['notes','journal','soul']),vaultFilter='all',vaultQuery='',vaultViewMode='preview';
let vaultStack=[],vaultRequest=0,vaultDirty=false;
async function leaveNote(){return confirmEditorLeave('vault');}

function renderObsidianMarkdown(source){
 if(!source)return '<p class="dim">Empty document.</p>';
 const lines=source.split('\n');let html=[],inCode=false,codeLang='',codeLines=[],inList=false,listType='',hIdx=0;
 for(let i=0;i<lines.length;i++){
  const line=lines[i];
  if(line.startsWith('```')){
   if(inCode){inCode=false;html.push(`<pre><code class="language-${esc(codeLang)}">${esc(codeLines.join('\n'))}</code></pre>`);codeLines=[];}
   else{if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}inCode=true;codeLang=line.slice(3).trim();}
   continue;
  }
  if(inCode){codeLines.push(line);continue;}
  if(/^(---|___|\*\*\*)$/.test(line.trim())){if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}html.push('<hr>');continue;}
  const hMatch=line.match(/^(#{1,6})\s+(.+)$/);
  if(hMatch){
   if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}
   const lvl=hMatch[1].length,text=hMatch[2];
   html.push(`<h${lvl} id="vault-heading-${hIdx++}">${formatInlineMarkdown(text)}</h${lvl}>`);
   continue;
  }
  if(line.startsWith('>')){
   if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}
   html.push(`<blockquote>${formatInlineMarkdown(line.slice(1).trim())}</blockquote>`);
   continue;
  }
  const taskMatch=line.match(/^[-*]\s+\[([ xX])\]\s+(.+)$/);
  if(taskMatch){
   if(!inList||listType!=='ul'){if(inList)html.push(listType==='ol'?'</ol>':'</ul>');html.push('<ul class="task-list">');inList=true;listType='ul';}
   const checked=taskMatch[1].toLowerCase()==='x';
   html.push(`<li class="task-list-item"><input type="checkbox" disabled ${checked?'checked':''}> ${formatInlineMarkdown(taskMatch[2])}</li>`);
   continue;
  }
  const ulMatch=line.match(/^[-*]\s+(.+)$/);
  if(ulMatch){
   if(!inList||listType!=='ul'){if(inList)html.push(listType==='ol'?'</ol>':'</ul>');html.push('<ul>');inList=true;listType='ul';}
   html.push(`<li>${formatInlineMarkdown(ulMatch[1])}</li>`);
   continue;
  }
  const olMatch=line.match(/^(\d+)\.\s+(.+)$/);
  if(olMatch){
   if(!inList||listType!=='ol'){if(inList)html.push(listType==='ol'?'</ol>':'</ul>');html.push('<ol>');inList=true;listType='ol';}
   html.push(`<li>${formatInlineMarkdown(olMatch[2])}</li>`);
   continue;
  }
  if(!line.trim()){if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}continue;}
  if(inList){html.push(listType==='ol'?'</ol>':'</ul>');inList=false;}
  html.push(`<p>${formatInlineMarkdown(line)}</p>`);
 }
 if(inCode)html.push(`<pre><code>${esc(codeLines.join('\n'))}</code></pre>`);
 if(inList)html.push(listType==='ol'?'</ol>':'</ul>');
 return html.join('\n');
}

function formatInlineMarkdown(text){
 let res=esc(text);
 res=res.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,(m,target,label)=>{
  const disp=label||target;
  return `<button class="quiet wiki-link" data-link="${esc(target.trim())}" title="Follow link [[${esc(target.trim())}]]">[[${esc(disp.trim())}]]</button>`;
 });
 res=res.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
 res=res.replace(/`([^`]+)`/g,'<code>$1</code>');
 res=res.replace(/\*\*\*([^*]+)\*\*\*/g,'<strong><em>$1</em></strong>');
 res=res.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 res=res.replace(/\*([^*]+)\*/g,'<em>$1</em>');
 res=res.replace(/~~([^~]+)~~/g,'<del>$1</del>');
 res=res.replace(/==([^=]+)==/g,'<mark>$1</mark>');
 return res;
}

function extractVaultTOC(text){
 const headings=[],lines=(text||'').split('\n');let idx=0;
 for(const line of lines){
  const m=line.match(/^(#{1,3})\s+(.+)$/);
  if(m)headings.push({id:'vault-heading-'+(idx++),level:m[1].length,title:m[2].replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,'$2'||'$1').replace(/[*_`]/g,'')});
 }
 return headings;
}

function filterVaultEntry(f){
 if(f.directory)return true;
 if(vaultQuery){
  const q=vaultQuery.toLowerCase();
  if(!f.name.toLowerCase().includes(q)&&!f.path.toLowerCase().includes(q))return false;
 }
 if(vaultFilter==='all')return true;
 const p=f.path.toLowerCase(),n=f.name.toLowerCase();
 if(vaultFilter==='knowledge')return p.includes('soul')||p.includes('memory')||p.includes('agent')||p.includes('user')||p.includes('fact')||p.includes('companion')||p.includes('config');
 if(vaultFilter==='journals')return p.includes('journal')||p.includes('diary')||p.includes('log')||p.includes('day');
 if(vaultFilter==='notes')return p.includes('notes')||n.endsWith('.md');
 return true;
}

function renderFolderTreeHTML(folderPath,depth=0){
 const entries=vaultTreeData.get(folderPath)||[];
 if(!entries.length)return depth>0?'<p class="dim small" style="padding-left:14px">Empty folder</p>':'';
 return entries.filter(filterVaultEntry).map(f=>{
  if(f.directory){
   const isExp=vaultExpanded.has(f.path);
   return `<div class="vault-folder-group" data-folder-path="${esc(f.path)}">
    <button class="vault-node" data-toggle-folder="${esc(f.path)}">
     <div class="vault-node-left">
      <span class="vault-node-icon">${isExp?'▾':'▸'}</span>
      <span>📁 ${esc(f.name)}</span>
     </div>
    </button>
    <div class="vault-folder-children" id="vault-folder-${CSS.escape(f.path)}" ${isExp?'':'hidden'}>
     ${isExp?renderFolderTreeHTML(f.path,depth+1):''}
    </div>
   </div>`;
  }
  const isActive=openNote?.path===f.path;
  const isProtected=f.protected;
  return `<button class="vault-node ${isActive?'active-file':''}" data-vault-file="${esc(f.path)}">
   <div class="vault-node-left">
    <span class="vault-node-icon">${isProtected?'🔒':'📄'}</span>
    <span>${esc(f.name)}</span>
   </div>
   ${isProtected?'<span class="vault-node-tag is-protected">Read-only</span>':''}
  </button>`;
 }).join('');
}

function renderVaultTree(){
 const tree=$('vault-tree');if(!tree)return;
 tree.innerHTML=renderFolderTreeHTML('',0)||'<p class="dim small" style="padding:12px">No files found matching filter.</p>';
 for(const b of tree.querySelectorAll('[data-toggle-folder]')){
  b.onclick=async()=>{
   const folder=b.dataset.toggleFolder;
   if(vaultExpanded.has(folder)){
    vaultExpanded.delete(folder);
   }else{
    vaultExpanded.add(folder);
    if(!vaultTreeData.has(folder)){
     const d=await api('/vault?path='+encodeURIComponent(folder));
     vaultTreeData.set(folder,d.entries);
    }
   }
   renderVaultTree();
  };
 }
 for(const b of tree.querySelectorAll('[data-vault-file]')){
  b.onclick=()=>readNote(b.dataset.vaultFile);
 }
}

workspaceHandlers.vault=async()=>{
 $('vault').innerHTML=`<div class="obsidian-layout">
   <div class="vault-sidebar">
     <div class="vault-topbar">
       <div class="vault-actions-row">
         <button class="quiet" id="new-note" title="Create a new Markdown note">+ Note</button>
         <button class="quiet" id="new-folder" title="Create a new folder">+ Folder</button>
         <button class="quiet" id="vault-trash" title="Open trash recovery">Trash</button>
         <a class="quiet" href="${mediaUrl('/api/vault/export')}" download title="Download vault as zip">Export</a>
       </div>
       <div class="vault-search-row">
         <span class="vault-search-icon">🔍</span>
         <input id="vault-query" placeholder="Filter files or search vault…" autocomplete="off" value="${esc(vaultQuery)}">
       </div>
       <div class="vault-filters">
         <button class="vault-filter-pill" data-filter="all" aria-selected="${vaultFilter==='all'}">All</button>
         <button class="vault-filter-pill" data-filter="knowledge" aria-selected="${vaultFilter==='knowledge'}">Knowledge</button>
         <button class="vault-filter-pill" data-filter="journals" aria-selected="${vaultFilter==='journals'}">Journals</button>
         <button class="vault-filter-pill" data-filter="notes" aria-selected="${vaultFilter==='notes'}">Notes</button>
       </div>
     </div>
     <div class="vault-tree-container" id="vault-tree"></div>
   </div>
    <div class="vault-main-pane" id="vault-main">
      <div id="vault-document"><div class="vault-empty-state" style="margin:auto;text-align:center;padding:48px 24px"><div style="font-size:36px;margin-bottom:12px;opacity:0.6">📖</div><p class="dim" style="font-size:15px;margin:0 0 6px">Select a document from the vault or create a new note.</p><span class="dim small">Markdown, notes, and journals stay Obsidian-compatible</span></div></div>
    </div>
 </div>`;

 for(const pill of $('vault').querySelectorAll('.vault-filter-pill')){
  pill.onclick=()=>{
   vaultFilter=pill.dataset.filter;
   for(const other of $('vault').querySelectorAll('.vault-filter-pill'))other.setAttribute('aria-selected',String(other===pill));
   renderVaultTree();
  };
 }

 $('vault-query').oninput=()=>{
  vaultQuery=$('vault-query').value.trim();
  renderVaultTree();
 };
 $('vault-query').onkeydown=async e=>{
  if(e.key==='Enter'&&vaultQuery.length>=2){
   e.preventDefault();
   const d=await api('/vault/search?q='+encodeURIComponent(vaultQuery));
   $('vault-tree').innerHTML=`<div class="actions" style="padding:6px"><button class="quiet" id="vault-clear-search">← Back to tree</button></div>`+
    (d.matches.length?d.matches.map(m=>`<button class="vault-node" data-vault-file="${esc(m.path)}"><div class="vault-node-left"><span class="vault-node-icon">📄</span><span>${esc(m.path)}</span></div></button><p class="dim small" style="padding:0 12px 6px;margin:0">${esc(m.excerpt)}</p>`).join(''):'<p class="dim small" style="padding:12px">No search results.</p>');
   $('vault-clear-search').onclick=()=>renderVaultTree();
   for(const b of $('vault-tree').querySelectorAll('[data-vault-file]'))b.onclick=()=>readNote(b.dataset.vaultFile);
  }
 };

 $('new-note').onclick=async()=>{
  if(!await leaveNote())return;
  dialog('New note',`<form id="new-note-form"><label>Note name or path<input id="new-note-name" required placeholder="My note.md or notes/project.md"></label><button class="act">Create note</button></form>`);
  $('new-note-form').onsubmit=async e=>{
   e.preventDefault();
   let raw=$('new-note-name').value.trim().replace(/\.md$/,'')+'.md';
   if(raw.startsWith('/'))raw=raw.slice(1);
   if(!raw.includes('/')&&vaultTreeData.has('notes'))raw='notes/'+raw;
   const d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path:raw,text:'# '+raw.split('/').pop().replace(/\.md$/,'')+'\n\n',revision:''})});
   $('product-dialog').close();
   vaultDirty=false;
   openNote=d;
   showNote(d,true);
   await listVault(d.path.split('/').slice(0,-1).join('/'),false);
  };
 };

 $('new-folder').onclick=async()=>{
  if(!await leaveNote())return;
  dialog('New folder',`<form id="new-folder-form"><label>Folder name<input id="new-folder-name" required placeholder="journal or research"></label><button class="act">Create folder</button></form>`);
  $('new-folder-form').onsubmit=async e=>{
   e.preventDefault();
   const raw=$('new-folder-name').value.trim().replace(/^\/+|\/+$/g,'');
   if(!raw||raw.includes('..'))throw Error('Invalid folder name');
   const path=raw+'/overview.md';
   const d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path,text:'# '+raw+' overview\n\n',revision:''})});
   $('product-dialog').close();
   vaultDirty=false;
   vaultExpanded.add(raw);
   openNote=d;
   showNote(d,true);
   await listVault('',false);
  };
 };

 $('vault-trash').onclick=showTrash;

 await listVault(vaultPath||'',false);
 if(openNote)showNote(openNote);
};

listVault=async function(path,remember=true){
 const id=++vaultRequest;let d;
 try{d=await api('/vault?path='+encodeURIComponent(path));}
 catch(e){notice(e.message,true);if(path)return listVault('',false);throw e;}
 if(id!==vaultRequest||current!=='vault')return;
 vaultTreeData.set(path||'',d.entries);
 if(path){
  const parts=path.split('/');
  for(let i=1;i<=parts.length;i++)vaultExpanded.add(parts.slice(0,i).join('/'));
 }
 vaultPath=path||'';
 renderVaultTree();
};

readNote=async function(path){
 if(!await leaveNote())return;
 vaultDirty=false;
 clearEditorDirty('vault');
 try{
  openNote=await api('/vault/file?path='+encodeURIComponent(path));
  const parent=path.split('/').slice(0,-1).join('/');
  if(parent&&!vaultExpanded.has(parent)){
   vaultExpanded.add(parent);
   if(!vaultTreeData.has(parent)){
    const pd=await api('/vault?path='+encodeURIComponent(parent));
    vaultTreeData.set(parent,pd.entries);
   }
  }
  showNote(openNote);
  renderVaultTree();
 }catch(e){
  $('vault-document').innerHTML=`<div class="card"><h2>${esc(path)}</h2><p class="dim">${esc(e.message)}</p><a class="act" href="${mediaUrl('/api/vault/download?path='+encodeURIComponent(path))}" download>Download file</a></div>`;
 }
};

showNote=function(note,edit=false){
 openNote=note;
 const parts=note.path.split('/'),fileName=parts.pop(),folderPath=parts.join('/');
 let mode=note.protected?'preview':edit?'edit':vaultViewMode;
 const main=$('vault-document');if(!main)return;

 main.innerHTML=`<div class="vault-doc-header">
  <div>
   <div class="vault-doc-title">
    <span class="dim">📁 ${esc(folderPath||'vault')} /</span>
    <strong>${esc(fileName)}</strong>
    ${note.protected?'<span class="vault-node-tag is-protected">Read-only</span>':'<span class="vault-node-tag">Editable</span>'}
   </div>
   <div class="vault-doc-meta">
    <span id="vault-meta-words">0 words</span>
    <span>·</span>
    <span id="vault-meta-chars">0 chars</span>
    <span>·</span>
    <span id="vault-meta-reading">1 min read</span>
    <span>·</span>
    <span id="vault-save-status" class="dim">Saved</span>
   </div>
  </div>
  <div class="actions">
   <div class="vault-mode-switch">
    <button class="vault-mode-btn ${mode==='preview'?'active':''}" data-vault-mode="preview">Preview</button>
    <button class="vault-mode-btn ${mode==='edit'?'active':''}" data-vault-mode="edit">Edit</button>
    <button class="vault-mode-btn ${mode==='split'?'active':''}" data-vault-mode="split">Split</button>
   </div>
   ${note.editable?'<button class="act" id="save-note">Save</button>':''}
   ${note.deletable?'<button class="quiet" id="trash-open-note">Trash</button>':''}
   <a class="quiet" href="${mediaUrl('/api/vault/download?path='+encodeURIComponent(note.path))}" download>Download</a>
  </div>
 </div>
 ${note.protected?`<div style="padding:10px 18px;background:color-mix(in srgb,var(--warn) 10%,transparent);border-bottom:1px solid color-mix(in srgb,var(--warn) 25%,transparent);color:var(--warn);display:flex;align-items:center;justify-content:space-between;font-size:13px"><span>🔒 <strong>Protected companion record</strong> · ${esc(note.protection_reason||'Read-only in Vault.')}</span><button class="quiet" id="vault-edit-companion-btn" style="font-size:12px;padding:3px 8px">Edit in companion settings →</button></div>`:''}
 <div class="vault-toolbar-editor" id="vault-toolbar" ${mode==='preview'?'hidden':''}>
  <button class="vault-tool-btn" data-tool="bold" title="Bold (**)"><b>B</b></button>
  <button class="vault-tool-btn" data-tool="italic" title="Italic (*)"><i>I</i></button>
  <button class="vault-tool-btn" data-tool="h2" title="Heading 2 (##)">H2</button>
  <button class="vault-tool-btn" data-tool="h3" title="Heading 3 (###)">H3</button>
  <button class="vault-tool-btn" data-tool="link" title="Obsidian wikilink ([[...]])">[[ ]]</button>
  <button class="vault-tool-btn" data-tool="list" title="Bullet list (- )">• List</button>
  <button class="vault-tool-btn" data-tool="task" title="Task list (- [ ])">☑ Task</button>
  <button class="vault-tool-btn" data-tool="code" title="Code block">&lt;/&gt;</button>
  <button class="vault-tool-btn" data-tool="quote" title="Quote block (&gt;)">&ldquo; Quote</button>
  <div style="flex:1"></div>
  <button class="vault-tool-btn" id="vault-toggle-toc" title="Toggle document outline">TOC</button>
 </div>
 <div class="vault-editor-content">
  <div class="vault-split-view" id="vault-views">
   <textarea id="note-text" class="vault-textarea" placeholder="Start typing in Markdown…" ${note.editable?'':'readonly'}></textarea>
   <div class="vault-preview-container document" id="vault-preview"></div>
  </div>
  <div class="vault-toc-panel" id="vault-toc" hidden>
   <div class="vault-toc-header">Document outline</div>
   <div id="vault-toc-list"></div>
  </div>
 </div>`;

 const textarea=$('note-text'),preview=$('vault-preview'),statusLabel=$('vault-save-status');
 textarea.value=note.text||'';
 textarea.defaultValue=note.text||'';
 vaultDirty=false;
 clearEditorDirty('vault');

 function applyMode(newMode){
  mode=newMode;vaultViewMode=newMode;
  for(const b of main.querySelectorAll('[data-vault-mode]'))b.classList.toggle('active',b.dataset.vaultMode===newMode);
  if($('vault-toolbar'))$('vault-toolbar').hidden=newMode==='preview';
  if(newMode==='preview'){textarea.style.display='none';preview.style.display='block';}
  else if(newMode==='edit'){textarea.style.display='block';preview.style.display='none';}
  else{textarea.style.display='block';preview.style.display='block';}
 }
 applyMode(mode);

 for(const b of main.querySelectorAll('[data-vault-mode]')){
  b.onclick=()=>applyMode(b.dataset.vaultMode);
 }

 function updateDocView(){
  const text=textarea.value;
  const words=text.trim()?text.trim().split(/\s+/).length:0;
  $('vault-meta-words').textContent=words+' words';
  $('vault-meta-chars').textContent=text.length+' chars';
  $('vault-meta-reading').textContent=Math.max(1,Math.ceil(words/200))+' min read';
  if(statusLabel)statusLabel.textContent=vaultDirty?'Unsaved changes':'Saved';
  if(statusLabel)statusLabel.className=vaultDirty?'status-warning small':'dim small';

  preview.innerHTML=renderObsidianMarkdown(text);
  for(const b of preview.querySelectorAll('.wiki-link')){
   b.onclick=()=>{
    const target=b.dataset.link.trim();
    const linkPath=target.endsWith('.md')?target:target+'.md';
    const resolved=linkPath.includes('/')?linkPath:(folderPath?folderPath+'/'+linkPath:'notes/'+linkPath);
    readNote(resolved);
   };
  }

  const toc=extractVaultTOC(text);
  $('vault-toc-list').innerHTML=toc.length?toc.map(item=>`<button class="vault-toc-item h${item.level}" data-toc-id="${esc(item.id)}">${esc(item.title)}</button>`).join(''):'<p class="dim small">No headings in document.</p>';
  for(const b of $('vault-toc-list').querySelectorAll('[data-toc-id]')){
   b.onclick=()=>{
    const el=$(b.dataset.tocId);
    if(el)el.scrollIntoView({behavior:'smooth',block:'start'});
   };
  }
 }
 updateDocView();

 textarea.oninput=()=>{
  vaultDirty=true;
  updateDocView();
 };

 textarea.onkeydown=e=>{
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){
   e.preventDefault();
   if($('save-note'))$('save-note').click();
  }
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='e'){
   e.preventDefault();
   applyMode(mode==='preview'?'edit':mode==='edit'?'split':'preview');
  }
  if(e.key==='Tab'){
   e.preventDefault();
   const start=textarea.selectionStart,end=textarea.selectionEnd;
   textarea.value=textarea.value.substring(0,start)+'  '+textarea.value.substring(end);
   textarea.selectionStart=textarea.selectionEnd=start+2;
   vaultDirty=true;
   updateDocView();
  }
 };

 if($('save-note'))$('save-note').onclick=async()=>{
  const d=await api('/vault/file',{method:'PUT',body:JSON.stringify({path:note.path,text:textarea.value,revision:note.revision})});
  openNote=d;note.revision=d.revision;
  clearEditorDirty('vault');
  vaultDirty=false;
  if(statusLabel){statusLabel.textContent='Saved';statusLabel.className='status-good small';}
  notice('Note saved.');
 };

 if($('trash-open-note'))$('trash-open-note').onclick=async()=>{
  await post('/vault/trash',{path:note.path,revision:note.revision});
  clearEditorDirty('vault');
  vaultDirty=false;
  main.innerHTML='<div class="vault-empty-state" style="margin:auto;text-align:center;padding:48px 24px"><div style="font-size:36px;margin-bottom:12px">🗑️</div><p class="dim">Moved to trash. Use Trash recovery at the top left to restore this file.</p></div>';
  await listVault(folderPath||'',false);
  notice('Moved to trash.');
 };

 if($('vault-edit-companion-btn'))$('vault-edit-companion-btn').onclick=()=>showTab('companion-edit');

 if($('vault-toggle-toc'))$('vault-toggle-toc').onclick=()=>{$('vault-toc').hidden=!$('vault-toc').hidden;};

 for(const btn of main.querySelectorAll('[data-tool]')){
  btn.onclick=()=>{
   const tool=btn.dataset.tool;
   const start=textarea.selectionStart,end=textarea.selectionEnd;
   const sel=textarea.value.substring(start,end);
   let rep='',cursor=start;
   if(tool==='bold'){rep='**'+(sel||'bold text')+'**';cursor=start+2+(sel?sel.length:9);}
   else if(tool==='italic'){rep='*'+(sel||'italic text')+'*';cursor=start+1+(sel?sel.length:11);}
   else if(tool==='h2'){rep='\n## '+(sel||'Heading 2')+'\n';cursor=start+4+(sel?sel.length:9);}
   else if(tool==='h3'){rep='\n### '+(sel||'Heading 3')+'\n';cursor=start+5+(sel?sel.length:9);}
   else if(tool==='link'){rep='[['+(sel||'Note')+(sel?'':'') + ']]';cursor=start+2+(sel?sel.length:4);}
   else if(tool==='list'){rep='\n- '+(sel||'List item')+'\n';cursor=start+3+(sel?sel.length:9);}
   else if(tool==='task'){rep='\n- [ ] '+(sel||'New task')+'\n';cursor=start+7+(sel?sel.length:8);}
   else if(tool==='code'){rep='```\n'+(sel||'code')+'\n```';cursor=start+4+(sel?sel.length:4);}
   else if(tool==='quote'){rep='\n> '+(sel||'Quote')+'\n';cursor=start+3+(sel?sel.length:5);}
   textarea.value=textarea.value.substring(0,start)+rep+textarea.value.substring(end);
   textarea.focus();
   textarea.selectionStart=textarea.selectionEnd=cursor;
   vaultDirty=true;
   updateDocView();
  };
 }
};

async function showTrash(){
 const d=await api('/vault/trash');
 dialog('Vault trash',`<p>Files stay here until you restore them. Restoring never overwrites an existing file.</p>${d.files.map(f=>`<div class="actions" style="margin-bottom:8px"><span>📄 <strong>${esc(f.path)}</strong> <small class="dim">${esc(new Date(f.deleted_at).toLocaleString())}</small></span><button class="quiet" data-restore-file="${esc(f.id)}">Restore</button></div>`).join('')||'<p class="dim">Trash is empty.</p>'}`);
 for(const b of $('dialog-body').querySelectorAll('[data-restore-file]')){
  b.onclick=async()=>{
   await post('/vault/restore',{id:b.dataset.restoreFile});
   notice('Restored file.');
   await showTrash();
   await listVault(vaultPath||'',false);
  };
 }
}

/* The installed Hermes's own dashboard, embedded. It is a panel of the unified
   Settings page now rather than a page that swallows the native forms, so the
   chips below choose which Hermes screen the frame shows. */
async function renderHermesDashboardInto(host){
 host.innerHTML=`<h2>Hermes dashboard</h2>
  <p class="dim">The complete dashboard from your installed Hermes, with its own configuration forms, skills, MCP connections and system tools. Everything in the frame is Hermes's own interface.</p>
  <div class="chip-row" id="hermes-pages">${[['','Overview'],['config','Configuration'],['models','Models'],['env','Credentials'],['skills','Skills'],['mcp','MCP'],['plugins','Plugins'],['sessions','Sessions'],['cron','Jobs'],['logs','Logs'],['analytics','Usage'],['channels','Channels'],['pairing','Pairing'],['webhooks','Webhooks'],['system','System']].map(([path,label],i)=>`<button type="button" class="chip" data-hermes-page="${path}" aria-pressed="${String(i===0)}">${label}</button>`).join('')}</div>
  <div id="hermes-dashboard-frame"><p class="dim">Starting the installed Hermes dashboard…</p></div>`;
 const chips=host.querySelector('#hermes-pages');
 try{
  const d=await post('/dashboard/start');
  if(!host.isConnected)return;
  const iframe=document.createElement('iframe');
  iframe.title='Hermes dashboard';iframe.className='hermes-dashboard';
  const open=path=>{iframe.src=d.prefix+'/'+path+(PROFILE&&PROFILE!=='default'?'?profile='+encodeURIComponent(PROFILE):'');};
  host.querySelector('#hermes-dashboard-frame').replaceChildren(iframe);open('');
  for(const b of chips.children)b.onclick=()=>{
   open(b.dataset.hermesPage);
   for(const other of chips.children)other.setAttribute('aria-pressed',String(other===b));
  };
 }catch(e){
  host.querySelector('#hermes-dashboard-frame').innerHTML=`<div class="notice-strip"><p><strong>The dashboard could not start.</strong> ${esc(e.message)}</p><button class="quiet" id="retry-dashboard">Try again</button></div>`;
  host.querySelector('#retry-dashboard').onclick=()=>renderHermesDashboardInto(host);
 }
}
Object.assign(voiceChoices,{chatterbox:[],audio8:[],pockettts:['alba','anna','azelma','cosette','eponine','fantine','javert','marius'],qwen3tts:['Ryan','Aiden','Vivian','Serena','Ono_Anna','Sohee']});
const VOICE_ENGINE_DETAILS={
 edge:{name:'Edge TTS',badge:'Free · Zero setup',cat:'cloud',desc:'High quality cloud neural voices with no setup or API key required.'},
 piper:{name:'Piper',badge:'Local · Ultra-fast',cat:'local',desc:'Lightweight, private local neural TTS running on CPU.'},
 kittentts:{name:'KittenTTS',badge:'Local · Compact',cat:'local',desc:'Compact local speech engine with warm natural timbre.'},
 neutts:{name:'NeuTTS',badge:'Local · Voice cloning',cat:'local',desc:'Neural voice cloning from a 3–30 second WAV recording.'},
 qwen3tts:{name:'Qwen3TTS',badge:'Local / Cloud · Cloning',cat:'local',desc:'Advanced voice cloning and emotive vocal direction.'},
 pockettts:{name:'PocketTTS',badge:'Local · Fast',cat:'local',desc:'Efficient lightweight character voices.'},
 chatterbox:{name:'Chatterbox',badge:'Local · Expressive',cat:'local',desc:'Conversational local speech engine.'},
 audio8:{name:'Audio8',badge:'Local · Pipeline',cat:'local',desc:'Local multi-stage audio synthesizer.'},
 openai:{name:'OpenAI TTS',badge:'Cloud API',cat:'api',desc:'Natural conversational speech from OpenAI (Alloy, Echo, Nova, etc.).'},
 elevenlabs:{name:'ElevenLabs',badge:'Cloud API',cat:'api',desc:'Ultra-realistic, emotive studio-quality voice generation.'},
 xai:{name:'xAI / Grok',badge:'Cloud API',cat:'api',desc:'Expressive speech from xAI models.'},
 minimax:{name:'MiniMax',badge:'Cloud API',cat:'api',desc:'Expressive storytelling and character vocal performance.'},
 gemini:{name:'Gemini',badge:'Cloud API',cat:'api',desc:'Google multimodal vocal speech.'},
 mistral:{name:'Mistral',badge:'Cloud API',cat:'api',desc:'Mistral conversational speech API.'}
};

workspaceHandlers.voice=async()=>{
 const d=await api('/voice'),tts=d.tts;let selected=tts.provider||'edge';const draft={};
 if(!d.labels[selected]){selected='edge';}
 const heroName=chatName();
 $('voice').innerHTML=heading('Voice studio','Give your companion a distinct voice. Local engines run privately on the Hermes host; cloud engines connect instantly.')+`
 <div class="voice-hero-card">
  <div class="voice-hero-wave" aria-hidden="true">
   <span class="wave-bar b1"></span><span class="wave-bar b2"></span><span class="wave-bar b3"></span><span class="wave-bar b4"></span><span class="wave-bar b5"></span>
  </div>
  <div class="voice-hero-info">
   <div class="voice-hero-badge" id="voice-hero-status"><span class="status-dot"></span><span id="voice-engine-badge">${esc(d.labels[selected]||selected)}</span></div>
   <h3 id="voice-hero-title">${esc(heroName)}’s Voice</h3>
   <p class="dim small" id="voice-hero-desc">Used for spoken responses and audio message previews.</p>
  </div>
  <div class="voice-hero-actions">
   <button type="button" class="act" id="hero-quick-test">Generate voice preview</button>
  </div>
 </div>

 <div class="card">
  <form id="voice-studio-form">
   ${PROFILE!=='default'?`<label class="inline-label switch-container" style="margin-bottom:14px"><input id="voice-inherit" type="checkbox" ${tts.provider==='companion-default'?'checked':''}><span class="switch-slider"></span><span class="switch-label">Use the installation’s current voice defaults</span></label>`:''}
   
   <label style="font-weight:600;display:block;margin-bottom:8px">1 · Select Speech Engine</label>
   <div class="actions" style="margin-bottom:10px" id="voice-cat-filter">
    <button type="button" class="quiet is-active" data-cat="all">All engines</button>
    <button type="button" class="quiet" data-cat="local">💻 Local / Private</button>
    <button type="button" class="quiet" data-cat="cloud">🌐 Free & Online</button>
    <button type="button" class="quiet" data-cat="api">☁️ Cloud APIs</button>
   </div>
   <select id="studio-voice-provider" hidden>${options(Object.entries(d.labels),selected)}</select>

   <div class="engine-cards-grid" id="engine-cards-list">
    ${Object.entries(d.labels).map(([key,label])=>{
      const info=VOICE_ENGINE_DETAILS[key]||{name:label,badge:key,cat:'api',desc:''};
      const isSelected=key===selected;
      return `<div class="engine-card ${isSelected?'is-selected':''}" data-engine="${key}" data-cat="${info.cat}">
       <div class="engine-card-title"><span>${esc(info.name)}</span><span class="engine-tag">${esc(info.badge)}</span></div>
       <p class="engine-card-desc">${esc(info.desc)}</p>
       <div style="font-size:11px;color:${isSelected?'var(--accent)':'var(--faint)'}">${isSelected?'✓ Active engine':'Click to select'}</div>
      </div>`;
    }).join('')}
   </div>

   <div style="margin-top:20px">
    <label style="font-weight:600;display:block;margin-bottom:8px">2 · Voice Personality & Controls</label>
    <div id="studio-voice-fields"></div>
   </div>

   <div class="actions" style="margin-top:20px;padding-top:14px;border-top:1px solid var(--edge)">
    <button class="act">Save voice</button>
    <button class="quiet" type="button" id="studio-install-voice">Install engine on Hermes host</button>
    <button class="quiet" type="button" id="studio-native-voice">Native speech setup</button>
   </div>
   <p id="studio-voice-status" class="dim small" style="margin-top:10px"></p>
  </form>
 </div>

 <div class="card" style="margin-top:20px">
  <h2>Try the saved voice</h2>
  <p class="dim small">Type any phrase or choose an inspiration chip below to hear how ${esc(heroName)} sounds.</p>
  <div class="voice-sample-chips">
   <button type="button" class="voice-sample-chip" data-sample="Hello! It’s really wonderful to spend some quiet time together.">👋 Greeting</button>
   <button type="button" class="voice-sample-chip" data-sample="I was just thinking about you! How has your day been going so far?">✨ Friendly</button>
   <button type="button" class="voice-sample-chip" data-sample="The stars were glowing brightly over the quiet water, reflecting the calm night sky.">📖 Storytelling</button>
   <button type="button" class="voice-sample-chip" data-sample="Between you and me, you make every single day feel a lot brighter.">💭 Whisper</button>
   <button type="button" class="voice-sample-chip" data-sample="All systems are online, synchronized, and ready whenever you are.">⚡ Tech check</button>
  </div>
  <textarea id="studio-voice-text" class="composer-textarea" readonly style="min-height:75px;background:color-mix(in srgb,var(--ink) 3%,transparent);cursor:default">Hello! It’s really wonderful to spend some quiet time together.</textarea>
  <div class="actions" style="margin-top:12px">
   <button class="act" id="studio-preview-voice">Generate preview</button>
   <span class="dim small">Local weights download on first use. Cloud previews use connected provider accounts.</span>
  </div>
  <div id="studio-voice-player" style="margin-top:14px"></div>
 </div>`;

 const collect=()=>{const controls={};for(const el of $('studio-voice-fields').querySelectorAll('[data-voice-control]')){const key=el.dataset.voiceControl;controls[key]=d.fields[selected][key].type==='number'?Number(el.value):el.value;}return {controls,voice:$('studio-voice-name')?.value||'',transcript:$('studio-voice-transcript')?.value||''};};
 const draw=()=>{
  const cfg=tts[selected]||{},saved=draft[selected]||{voice:cfg.voice||cfg.voice_id||voiceChoices[selected]?.[0]||'',transcript:cfg.ref_text||'',controls:cfg};
  $('voice-engine-badge').textContent=d.labels[selected]||selected;
  $('studio-voice-fields').innerHTML=`<div class="form-grid">
   <label ${['neutts','chatterbox','audio8'].includes(selected)?'hidden':''}>Voice name or preset
    <input id="studio-voice-name" list="studio-voice-names" value="${esc(saved.voice)}" placeholder="Choose or type voice name">
    <datalist id="studio-voice-names">${(voiceChoices[selected]||[]).map(x=>`<option value="${esc(x)}">`).join('')}</datalist>
   </label>
   ${Object.entries(d.fields[selected]).map(([key,f])=>{
     const v=saved.controls[key]??f.default;
     return `<label>${esc(f.label)}${f.type==='select'?`<select data-voice-control="${key}">${options(f.choices.map(v=>[v,v]),v)}</select>`:`<input data-voice-control="${key}" type="${f.type==='number'?'number':'text'}" value="${esc(v)}" ${f.type==='number'?`min="${f.min}" max="${f.max}" step="${f.step}"`:''}>`}</label>`;
   }).join('')}
  </div>
  ${d.reference.includes(selected)?`
  <div class="voice-clone-box">
   <h4 style="margin:0 0 4px">🎙️ Reference voice audio clip</h4>
   <p class="dim small" style="margin:0 0 10px">Upload a clean 1–30 second WAV audio recording you have permission to use.${selected==='qwen3tts'?' For cloning, choose clone mode and a Qwen Base model; use CustomVoice for preset voices.':''}</p>
   <label style="display:block;margin-bottom:8px">Reference clip (WAV)
    <input id="studio-voice-clip" type="file" accept=".wav,audio/wav" style="margin-top:4px">
   </label>
   <label ${['pockettts','chatterbox'].includes(selected)?'hidden':''}>Exact spoken transcript
    <textarea id="studio-voice-transcript" class="composer-textarea-sm" placeholder="Exact words spoken in the reference audio">${esc(saved.transcript)}</textarea>
   </label>
   <p class="dim small" style="margin:6px 0 0">${cfg.ref_audio?'✓ Reference clip configured.':'No custom reference clip configured yet.'}</p>
  </div>`:''}`;

  $('studio-install-voice').hidden=!d.local.includes(selected)&&!['piper','neutts','kittentts'].includes(selected);
  $('studio-voice-status').textContent=d.local.includes(selected)?(d.installed[selected]?'Engine environment installed on host. Preview verifies model audio output.':'Engine is not installed here yet. Click “Install engine on Hermes host” before generating preview.'):'Saved settings apply to new speech synthesis requests.';
  for(const c of $('engine-cards-list').children){c.classList.toggle('is-selected',c.dataset.engine===selected);}
 };

 draw();
 for(const card of $('engine-cards-list').querySelectorAll('[data-engine]')){
  card.onclick=()=>{
   draft[selected]=collect();
   selected=card.dataset.engine;
   $('studio-voice-provider').value=selected;
   draw();
  };
 }
 for(const btn of $('voice-cat-filter').querySelectorAll('button')){
  btn.onclick=()=>{
   for(const b of $('voice-cat-filter').querySelectorAll('button'))b.classList.remove('is-active');
   btn.classList.add('is-active');
   const cat=btn.dataset.cat;
   for(const card of $('engine-cards-list').children){card.hidden=cat!=='all'&&card.dataset.cat!==cat;}
  };
 }
 for(const chip of $('voice').querySelectorAll('.voice-sample-chip')){
  chip.onclick=()=>{$('studio-voice-text').value=chip.dataset.sample;};
 }
 $('studio-install-voice').onclick=()=>action('/voice/install',{provider:selected});
 $('studio-native-voice').onclick=async()=>{await openSettings(null,'hermes-accounts');await openConsole('tools');};
 $('voice-studio-form').onsubmit=async e=>{
  e.preventDefault();
  if($('voice-inherit')?.checked){await action('/voice/inherit',{});return;}
  const file=$('studio-voice-clip')?.files[0];
  if(file){
    const response=await fetch(scoped('/api/voice/reference?provider='+encodeURIComponent(selected)),{method:'POST',headers:{'content-type':'application/octet-stream',...(token?{'x-tamanitomo-token':token,'x-companion-token':token}:{})},body:file});
   if(!response.ok)throw Error((await response.json()).detail);
  }
  await action('/voice',{provider:selected,...collect()});
 };
 $('studio-preview-voice').onclick=()=>action('/voice/preview',{text:$('studio-voice-text').value},r=>{
  $('studio-voice-player').innerHTML=`
   <div class="canvas-action-dock" style="margin-top:10px">
    <div style="display:flex;align-items:center;gap:10px;flex:1">
     <audio controls autoplay src="${mediaUrl(r.audio)}&v=${Date.now()}" style="width:100%"></audio>
    </div>
    <a class="quiet" href="${mediaUrl(r.audio)}" download>Download audio</a>
   </div>`;
 });
 $('hero-quick-test').onclick=()=>$('studio-preview-voice').click();
};

/* A model's own terms travel with the weights, not with this kit. Civitai
   publishes four permission flags per model; show them before downloading,
   and say plainly that they summarise rather than replace the model card. */
const licenceNotice = (licence, page) => {
    if (!licence) return '';
    const rows = [['allowCommercialUse', 'Commercial use'], ['allowDerivatives', 'Derivatives'],
                  ['allowNoCredit', 'Use without credit'], ['allowDifferentLicense', 'Relicensing']];
    const read = v => Array.isArray(v) ? (v.length ? v.join(', ') : 'None') :
                      v === true ? 'Allowed' : v === false ? 'Not allowed' : 'Not stated';
    const restricted = v => v === false || (Array.isArray(v) && !v.length);
    const strict = rows.some(([k]) => restricted(licence[k]));
    return `<div class="card licence-note${strict ? ' is-restricted' : ''}">
      <strong>The publisher's terms for these weights</strong>
      <dl>${rows.map(([k, label]) => `<div><dt>${esc(label)}</dt><dd${restricted(licence[k]) ? ' class="bad"' : ''}>${esc(read(licence[k]))}</dd></div>`).join('')}</dl>
      <p class="dim small">A summary published by Civitai, not the licence itself.${page ? ' Read the <a href="' + esc(page) + '" target="_blank" rel="noopener noreferrer">model card</a> before relying on it.' : ''} These terms bind your use of the weights regardless of Companion Kit's own licence.</p>
    </div>`;
  };

/* Weights are never fetched until their terms have been put in front of
   someone. Resolves true when the download should go ahead. */
async function confirmWeightTerms(versionId){
 let terms;
 try{terms=await api('/images/resource-terms?version_id='+encodeURIComponent(versionId));}
 catch(error){return confirm('Could not read this model\u2019s terms from Civitai ('+error.message+
   ').\n\nDownload the weights anyway?');}
 const size=terms.size_bytes?(terms.size_bytes/1024**3).toFixed(2)+' GB':'unknown size';
 const dialog=document.createElement('dialog');
 dialog.className='terms-dialog';
 dialog.innerHTML=`<h3>${esc(terms.name)}</h3>
   <p class="dim small">${esc([terms.type,terms.base_model,size].filter(Boolean).join(' \u00b7 '))}</p>
   ${licenceNotice(terms.license,terms.page)||
     '<p class="dim small">Civitai published no permissions for this model. Read the model card before relying on it.</p>'}
   ${terms.trigger_words.length?`<p class="small">Triggers: ${esc(terms.trigger_words.join(', '))}</p>`:''}
   <div class="studio-actions">
     <button class="act" value="go">Accept and download</button>
     <button class="quiet" value="stop">Cancel</button>
   </div>`;
 document.body.append(dialog);
 const answer=await new Promise(resolve=>{
  for(const button of dialog.querySelectorAll('button'))
   button.onclick=()=>{resolve(button.value);dialog.close();};
  dialog.addEventListener('cancel',()=>resolve('stop'));
  dialog.showModal();
 });
 dialog.remove();
 return answer==='go';
}
const fileSlug=name=>String(name||'workflow').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,60)||'workflow';
function downloadJSON(name,data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

/* Which studio view is open, kept across a re-render so a portrait change comes
   back to the identity view instead of dropping you on the composer. */
let imageStudioView='assignments';


/* ------------------------------------------------- workflow controls, humanely

   A ComfyUI workflow is a graph of nodes, and editing one used to mean editing
   its JSON by hand in a textarea — impossible on a phone and unpleasant
   anywhere. The parts a person actually turns are few and well known: which
   checkpoint, which LoRAs and how strongly, how many steps, how hard the
   guidance, what size. Those are lifted out of the graph and given real
   controls; the JSON stays underneath, authoritative, and is written back.   */

let comfyModelCache={};
let missingVersions={};
let modelFamilies={};

/* Ways of framing and lighting a shot, for people who do not think in these
   terms. Picking one adds its tags; they can still be typed by hand. */
const CAMERA_LOOKS=[
  ['close-up portrait, shallow depth of field, 85mm','Close portrait'],
  ['upper body shot, eye level, 50mm','Head and shoulders'],
  ['full body shot, standing, 35mm','Full body'],
  ['wide shot, environment visible, 24mm','Wide, room visible'],
  ['over the shoulder, candid framing','Over the shoulder'],
  ['low angle, looking up','From below'],
  ['high angle, looking down','From above'],
  ['dutch angle, slight tilt','Tilted'],
];
const LIGHTING_LOOKS=[
  ['soft natural window light, overcast','Soft daylight'],
  ['golden hour, warm rim light','Golden hour'],
  ['blue hour, cool ambient','Dusk'],
  ['candlelight, warm low key','Candlelit'],
  ['neon signage, cyan and magenta rim light','Neon'],
  ['harsh midday sun, strong shadows','Harsh sun'],
  ['studio three point lighting, softbox key','Studio'],
  ['single lamp, dark room, high contrast','One lamp, dark room'],
];

/* What each installed file says it was trained for, read from its own header.
   Cached on the server, so this is one small request. */
async function loadModelFamilies(refresh){
  try{
    const data=await api('/images/model-families'+(refresh?'?refresh=1':''));
    modelFamilies=data.models||{};
    return data;
  }catch(error){return null;}
}

/* Compatible first, then everything we could not place, with a line between.
   Nothing is hidden: a LoRA whose header is silent still works, and 61% of a
   real library has no base model recorded. */
function groupedModelOptions(files,current,wanted){
  const family=name=>(modelFamilies[name]||{}).family||'';
  const fits=name=>!wanted||!family(name)||family(name)===wanted;
  const label=name=>name.replace(/\.safetensors$/,'');
  const known=files.filter(f=>family(f)&&fits(f));
  const unknown=files.filter(f=>!family(f));
  const mismatched=files.filter(f=>family(f)&&!fits(f));
  const group=(rows,title)=>rows.length
    ? `<optgroup label="${esc(title)}">${rows.map(f=>
        `<option value="${esc(f)}" ${f===current?'selected':''}>${esc(label(f))}</option>`).join('')}</optgroup>`:'';
  return group(known,wanted?wanted+' \u00b7 fits this model':'Identified')
    +group(unknown,'Not recorded \u2014 probably fine')
    +group(mismatched,'Built for something else')
    +((current&&!files.includes(current))
      ? `<option value="${esc(current)}" selected>${esc(label(current))} (not installed)</option>`:'');
}
async function comfyModels(endpoint){
  if(!endpoint)return {};
  if(comfyModelCache[endpoint])return comfyModelCache[endpoint];
  try{
    const r=await post('/images/check',{endpoint});
    comfyModelCache[endpoint]=r.models||{};
  }catch(error){comfyModelCache[endpoint]={};}
  return comfyModelCache[endpoint];
}

/* Nodes of a class, in graph order, so the list is stable between renders. */
const nodesOfClass=(workflow,...classes)=>Object.entries(workflow||{})
  .filter(([,node])=>classes.includes(node?.class_type))
  .sort((a,b)=>Number(a[0])-Number(b[0]));

/* A slider and its number, kept in step, for a value that has a sensible range. */
function sliderRow(id,label,value,min,max,step,hint){
  return `<label class="studio-slider" for="${id}">
    <span class="studio-slider-head"><span>${esc(label)}</span>
      <output for="${id}" id="${id}-out">${esc(String(value))}</output></span>
    <input type="range" id="${id}" min="${min}" max="${max}" step="${step}" value="${value}">
    ${hint?`<small class="dim">${esc(hint)}</small>`:''}
  </label>`;
}
function wireSliders(root){
  for(const range of root.querySelectorAll('input[type=range]')){
    const out=root.querySelector('#'+range.id+'-out');
    if(out)range.addEventListener('input',()=>{out.textContent=range.value;});
  }
}

/* Prompt parts are comma-separated tags. They are shown as tags and written
   back as `a, b, c`, so what reaches the model is never a run-on line. */
/* Split on commas, but not on the ones inside a weight: `(white dress, ivory:1.3)`
   is one tag. Splitting it into fragments lets a single ✕ leave an unbalanced
   bracket behind, which the sampler then reads as literal punctuation. Mirrors
   companion_media.split_terms. */
function tagsFromText(text){
  const tags=[];let depth=0,current='';
  for(const ch of String(text||'')){
    if(ch==='('||ch==='[')depth++;
    else if(ch===')'||ch===']')depth=Math.max(0,depth-1);
    if(ch===','&&depth===0){tags.push(current.trim());current='';}
    else current+=ch;
  }
  tags.push(current.trim());
  return tags.filter(Boolean);
}
function tagFieldHTML(key,label,text,hint,collapsed,vocabulary){
  const tags=tagsFromText(text);
  return `<details class="tag-field" data-tag-field="${esc(key)}" ${collapsed?'':'open'}>
    <summary class="tag-field-head"><strong>${esc(label)}</strong>
      <span class="tag-count">${tags.length}</span>
      ${hint?`<small class="dim">${esc(hint)}</small>`:''}</summary>
    <div class="tag-list" data-tags>${tags.map((t,i)=>
      `<span class="tag-chip">${esc(t)}<button type="button" class="tag-remove" data-remove="${i}" aria-label="Remove ${esc(t)}">✕</button></span>`).join('')}
    </div>
    ${vocabulary?`<select class="tag-vocab" data-tag-vocab aria-label="Add a ${esc(label.toLowerCase())} to ${esc(label)}">
      <option value="">Pick a ${esc(label.toLowerCase())}\u2026</option>
      ${vocabulary.map(([value,name])=>`<option value="${esc(value)}">${esc(name)}</option>`).join('')}
    </select>`:''}
    <input class="tag-input" data-tag-input placeholder="Add a tag, then Enter" aria-label="Add a tag to ${esc(label)}">
  </details>`;
}
/* One delegated handler for every tag field on the page. */
function wireTagFields(root,onChange){
  root.addEventListener('click',event=>{
    const remove=event.target.closest('[data-remove]');
    if(!remove)return;
    const field=remove.closest('[data-tag-field]');
    const tags=readTags(field);
    tags.splice(Number(remove.dataset.remove),1);
    writeTags(field,tags);onChange&&onChange();
  });
  root.addEventListener('change',event=>{
    const picker=event.target.closest('[data-tag-vocab]');
    if(!picker||!picker.value)return;
    const field=picker.closest('[data-tag-field]');
    writeTags(field,[...readTags(field),...tagsFromText(picker.value)]);
    picker.value='';onChange&&onChange();
  });
  root.addEventListener('keydown',event=>{
    const input=event.target.closest('[data-tag-input]');
    if(!input)return;
    const field=input.closest('[data-tag-field]');
    if(event.key===','||event.key==='Enter'){
      event.preventDefault();
      const value=input.value.trim().replace(/,+$/,'');
      if(!value)return;
      const added=tagsFromText(value).filter(t=>!warnIfInFloor(t,field));
      if(added.length)writeTags(field,[...readTags(field),...added]);
      input.value='';onChange&&onChange();
    }else if(event.key==='Backspace'&&!input.value){
      const tags=readTags(field);
      if(!tags.length)return;
      tags.pop();writeTags(field,tags);onChange&&onChange();
    }
  });
  // A tag typed and then left behind should not be lost on save.
  root.addEventListener('blur',event=>{
    const input=event.target.closest('[data-tag-input]');
    if(!input||!input.value.trim())return;
    const field=input.closest('[data-tag-field]');
    writeTags(field,[...readTags(field),...tagsFromText(input.value)]);
    input.value='';onChange&&onChange();
  },true);
}
/* The protective floor applies to every render already, so a copy of one of
   its terms in a preset does nothing except invite someone to edit the copy and
   believe they changed something. Said once, when it happens, rather than as a
   paragraph nobody reads. */
let safetyFloor=[];
function warnIfInFloor(term,field){
  if(!safetyFloor.length)return false;
  const bare=String(term||'').trim().toLowerCase().replace(/^[([]|[)\]]$/g,'');
  if(!safetyFloor.includes(bare))return false;
  const where=field?.dataset.tagField==='__modesty'?'modesty':'this workflow';
  notice(`\u201c${term}\u201d is already in the protective negatives that apply to every `+
    `render, and cannot be switched off. Adding it to ${where} would change nothing.`);
  return true;
}

const readTags=field=>[...field.querySelectorAll('.tag-chip')].map(chip=>chip.firstChild.textContent.trim());
function writeTags(field,tags){
  const unique=[...new Set(tags.filter(Boolean))];
  const count=field.querySelector('.tag-count');
  if(count)count.textContent=String(unique.length);
  field.querySelector('[data-tags]').innerHTML=unique.map((t,i)=>
    `<span class="tag-chip">${esc(t)}<button type="button" class="tag-remove" data-remove="${i}" aria-label="Remove ${esc(t)}">✕</button></span>`).join('');
}
const tagFieldValue=field=>readTags(field).join(', ');

workspaceHandlers['image-studio']=async()=>{
 const [d,portrait]=await Promise.all([api('/images'),api('/portrait'),loadModelFamilies(false)]);
 safetyFloor=(d.safety_floor||[]).map(t=>String(t).toLowerCase());
 let settings=d.settings,revision=d.revision,presetIndex=0;const defaults=d.effective;
 const routeValues={...settings.routes};let defaultId=settings.default_preset||'';
 let activeCategory='portrait';

 $('image-studio').innerHTML=`

 <!-- The setup controls still exist for the wiring below; Preferences owns them. -->
 <div hidden>
  <button class="quiet" id="image-back-identity"></button>
  <button class="quiet" id="image-template-download"></button>
  <button class="quiet" id="image-import"></button>
  <input id="image-import-file" type="file" accept=".json,application/json" hidden>
  <button class="quiet" id="image-install-comfy"></button>
  <button class="quiet" id="image-start-comfy"></button>
  <label><input type="checkbox" id="comfy-cpu"></label>
 </div>


 <!-- VIEW 2: Assigned Workflows & Lanes (Dedicated Routing Deck) -->
 <div id="view-assignments" class="studio-view-pane">
  <div class="card lanes-dashboard">
   <div class="lanes-header">
    <h3 style="margin:0">🎯 Lanes</h3>
   </div>

   <div class="lane-cards-grid" id="image-routes">
    <!-- Rendered dynamically -->
   </div>
   <label class="fallback-row">
    <span><span class="lane-ico">✨</span>Fallback</span>
    <select id="image-default-preset"></select>
   </label>
   <p class="dim small" style="margin:6px 2px 16px">Used when a lane has nothing of its own.</p>
   <div class="studio-actions">
    <button class="act" id="save-assignments-btn">Save lanes</button>
    <button class="quiet" id="assignments-goto-creator">⚙️ Manage workflows</button>
   </div>
  </div>
 </div>

 <!-- VIEW 3: ComfyUI Lite Workflow Creator -->

 <!-- Workflows: create one, edit one, or read one out of a picture -->
 <div id="view-presets" class="studio-view-pane" hidden>
  <div class="workflow-bar">
   <button type="button" class="icon-button workflow-back" id="workflows-back-lanes"
     title="Back to lanes" aria-label="Back to lanes">\u2190</button>
   <button type="button" class="chip-button" id="workflow-show-import">\u{1F5BC}\uFE0F Import from an image</button>
  </div>

  <div class="card workflow-mode-panel" id="workflow-import-panel" hidden>
   <h3>Import from an image</h3>
   <p class="dim">A picture rendered by ComfyUI carries its whole workflow. One downloaded from
    <a href="https://civitai.com" target="_blank" rel="noopener">civitai.com</a> or civitai.red usually
    carries its prompt and settings instead. Whatever is there gets read; whatever is not, you finish by hand.</p>
   <label class="import-url-row">
    <input id="workflow-import-url" type="url" placeholder="https://civitai.com/images/12345678" aria-label="Civitai image address">
    <button type="button" class="act" id="workflow-import-go">Read it</button>
   </label>
   <div class="actions">
    <label class="quiet" style="cursor:pointer">…or choose a file<input id="workflow-import-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label>
    <span class="dim small" id="workflow-import-status" role="status"></span>
   </div>
   <div id="workflow-import-report"></div>
  </div>

  <div class="card workflow-mode-panel" id="workflow-edit-panel">
   <div class="workflow-pick">
    <label for="image-preset-select">Workflow</label>
    <div class="workflow-pick-row">
     <select id="image-preset-select"></select>
     <button type="button" class="icon-button" id="download-interactive"
       title="Download interactive workflow \u2014 opens in ComfyUI"
       aria-label="Download interactive workflow">\u2b07</button>
    </div>
    <span class="dim small" id="download-interactive-status" role="status"></span>
   </div>
   <div id="image-preset-editor"></div>
  </div>
  <div class="actions" style="margin-top:14px">
   <button class="act" id="save-image-settings">Save all image settings</button>
  </div>
 </div>

`;

 // Subnav Switching
 const showStudioView=(viewName)=>{
  imageStudioView=viewName;
  if(viewName==='assignments')showStudioSection('lanes');
  else if(viewName==='presets'||viewName==='identity')showStudioSection('workflows');
 };
 showStudioView(imageStudioView);

 /* One half of the page at a time: the assignments, or the workflows. */
 function showStudioSection(which){
  $('view-assignments').hidden=which!=='lanes';
  $('view-presets').hidden=which!=='workflows';
  window.scrollTo({top:0});
 }
 $('assignments-goto-creator').onclick=()=>{showStudioSection('workflows');setWorkflowMode('edit');};
 $('workflows-back-lanes').onclick=()=>showStudioSection('lanes');
 $('image-back-identity').onclick=()=>showTab('identity');

 function readPreset(){
  const p=settings.presets[presetIndex];if(!p||!$('preset-name'))return;
  // The endpoint is one setting for the whole kit, not a per-workflow field;
  // it is shown here and changed in Preferences.
  p.name=$('preset-name').value;p.category=$('preset-category').value;
  // Tags are stored the way the model wants them: comma separated, no strays.
  p.parts={...p.parts};
  for(const field of $('image-preset-editor').querySelectorAll('[data-tag-field]')){
    const key=field.dataset.tagField,value=tagFieldValue(field);
    if(key==='__negative')p.negative=value;
    else if(key==='__modesty')p.modesty_negative=value;
    else p.parts[key]=value;
  }
  for(const k of ['width','height'])if($('preset-'+k))p[k]=Number($('preset-'+k).value)||p[k];
  for(const k of ['steps','cfg','seed','denoise'])if($('preset-'+k))p[k]=Number($('preset-'+k).value);
  if(p.provider==='comfyui'){try{p.workflow=JSON.parse($('preset-workflow').value);p.mappings=JSON.parse($('preset-mappings').value);}catch(e){}}
  else if(p.provider==='openai'){p.model=$('preset-model').value;p.api_key_env=$('preset-key-env').value;}
 }

 function updateActiveLaneBadge(){
  const assignedId=routeValues[activeCategory]||defaultId;
  const match=settings.presets.find(p=>p.id===assignedId)||(settings.inherit?d.installation_presets.find(p=>p.id===assignedId):null);
  const badge=$('composer-assigned-name');
  if(badge){
   if(match)badge.textContent=match.name;
   else if(defaultId){const defMatch=settings.presets.find(p=>p.id===defaultId);badge.textContent=defMatch?'Fallback: '+defMatch.name:'Default fallback';}
   else badge.textContent='None assigned';
  }
  const label=$('composer-lane-label');if(label)label.textContent=formLabel(activeCategory);
 }

 function menus(){
  const rows=settings.presets.filter(p=>!p.incomplete).map(p=>[p.id,p.name]);
  const draftCount=settings.presets.filter(p=>p.incomplete).length;
  const allRows=[['', 'Choose a workflow'], ...rows];
  $('image-preset-select').innerHTML=options(
    [...settings.presets.map((p,i)=>[String(i),p.name+(p.incomplete?' \u00b7 draft':'')]),
     ['__new__','\u002b Create a new workflow\u2026']],String(presetIndex));
  $('image-default-preset').innerHTML=options(allRows,defaultId);
  $('image-default-preset').onchange=e=>{defaultId=e.target.value;menus();updateActiveLaneBadge();};

  const defPreset=settings.presets.find(p=>p.id===defaultId);
  const fallbackLabel=defPreset?defPreset.name:'No fallback chosen';

  $('image-routes').innerHTML=d.categories.map(k=>{
   const assigned=routeValues[k]||'';
   return `
   <label class="lane-row">
    <span class="lane-row-name"><span class="lane-ico">${laneIcon(k)}</span>${formLabel(k)}</span>
    <select class="lane-select" data-image-route="${k}">
     ${options([['','Fallback · '+fallbackLabel],...rows],assigned)}
    </select>
   </label>`;
  }).join('');

  for(const s of $('image-routes').querySelectorAll('[data-image-route]')){
   s.onchange=()=>{
    if(s.value)routeValues[s.dataset.imageRoute]=s.value;
    else delete routeValues[s.dataset.imageRoute];
    menus();
    updateActiveLaneBadge();
   };
  }
  updateActiveLaneBadge();
 }

 async function drawPreset(){
  menus();const p=settings.presets[presetIndex];
  if(!p){$('image-preset-editor').innerHTML='<p class="dim">Add a named workflow or API provider to begin. Each can specialize in a different image style.</p>';return;}
  const comfy=p.provider==='comfyui';
  const models=comfy?await comfyModels(p.endpoint):{};
  const loras=models.lora_name||[];
  const checkpoints=models.ckpt_name||[];
  const loraNodes=comfy?nodesOfClass(p.workflow,'LoraLoader'):[];
  const ckptNodes=comfy?nodesOfClass(p.workflow,'CheckpointLoaderSimple'):[];
  const SIZES=[[832,1216,'Portrait 832×1216'],[1216,832,'Landscape 1216×832'],[1024,1024,'Square 1024'],
    [768,1152,'Portrait 768×1152'],[1152,768,'Landscape 1152×768'],[512,768,'Small portrait']];
  const sizeValue=`${p.width||832}×${p.height||1216}`;
  const clipNode=comfy?nodesOfClass(p.workflow,'CLIPSetLastLayer')[0]:null;
  // Every other node that names a file the host has a list for.
  const LOADERS=[
    ['VAELoader','vae_name','VAE','vae_name'],
    ['CLIPLoader','clip_name','Text encoder','clip_name'],
    ['DualCLIPLoader','clip_name1','Text encoder 1','clip_name'],
    ['DualCLIPLoader','clip_name2','Text encoder 2','clip_name'],
    ['UNETLoader','unet_name','UNET','unet_name'],
    ['UnetLoaderGGUF','unet_name','UNET','unet_name'],
  ];
  const loaderRows=comfy?LOADERS.flatMap(([cls,field,title,pool])=>
    nodesOfClass(p.workflow,cls)
      .filter(([,node])=>node.inputs&&field in node.inputs)
      .map(([id,node])=>[id,node,field,title,models[pool]||[]])):[];
  const checkpointName=ckptNodes.length?ckptNodes[0][1].inputs.ckpt_name:'';
  const checkpointFamily=(modelFamilies[checkpointName]||{}).family||'';
  const clipSkipValue=clipNode?Math.abs(Number(clipNode[1].inputs.stop_at_clip_layer??-2)):2;
  const knownSize=SIZES.some(([w,h])=>`${w}×${h}`===sizeValue);
  /* A workflow keeps its quality, identity and negatives; the rest describes
     one moment and is filled per render, so saving does not keep it. The lock
     says which is which without a paragraph explaining it. */
  const PART_HINT={quality:'Rendering quality, not subject',identity:'Leave empty to follow '+chatName(),
    scene:'Filled per render',wardrobe:'Filled per render',
    lighting:'Filled per render',camera:'Filled per render'};

  $('image-preset-editor').innerHTML=`
    <div class="form-grid">
      <label>Name<input id="preset-name" value="${esc(p.name)}" placeholder="Comfy – PlantMilk"></label>
      <label>Image type
        <select id="preset-category">
          <option value="">Not assigned yet</option>
          ${options(d.categories.map(v=>[v,formLabel(v)]),p.category||'')}
        </select>
        <small class="dim">Assign it to a lane once you have tested it.</small>
      </label>
      ${p.provider!=='hermes'?`<p class="dim small endpoint-note">Renders on <code>${esc(p.endpoint||'the address in Preferences')}</code></p>`:''}
      ${p.provider==='hermes'?`<p class="dim">Hermes provider: ${esc(p.hermes_provider||'Follow current Hermes default')} · ${esc(p.model||'Provider default')}${p.available===false?' · Reconnect this provider in Hermes settings':''}</p>`:''}
      ${p.provider==='openai'?`<label>Model<input id="preset-model" value="${esc(p.model||'')}" placeholder="Model supported by this API"></label>
        <label>API-key environment variable<input id="preset-key-env" value="${esc(p.api_key_env||'OPENAI_API_KEY')}"></label>`:''}
    </div>

    ${comfy?`
    <div class="card studio-block">
      <h3>1 · Model</h3>
      ${ckptNodes.length?ckptNodes.map(([id,node])=>`
        <label>Checkpoint
          <select data-ckpt-node="${esc(id)}">
            ${checkpoints.length?groupedModelOptions(checkpoints,node.inputs.ckpt_name,'')
              :`<option value="${esc(node.inputs.ckpt_name||'')}">${esc(node.inputs.ckpt_name||'—')}</option>`}
          </select>
        </label>`).join(''):'<p class="dim small">This workflow loads its model another way.</p>'}
      ${loaderRows.map(([id,node,field,title,pool])=>`
        <label>${esc(title)}
          <select data-loader-node="${esc(id)}" data-loader-field="${esc(field)}">
            ${pool.length?groupedModelOptions(pool,node.inputs[field],'')
              :`<option value="${esc(node.inputs[field]||'')}">${esc(node.inputs[field]||'\u2014')}</option>`}
          </select>
        </label>`).join('')}
      <p class="model-family" data-family-badge hidden></p>
      ${!checkpoints.length?'<p class="dim small">Connect to ComfyUI to choose from the models it has.</p>':''}
    </div>

    <div class="card studio-block">
      <div class="studio-block-head"><h3>2 · LoRAs</h3>
        <button type="button" class="quiet small" id="add-lora-row" ${loras.length?'':'disabled'}>Add LoRA</button></div>
      ${loraNodes.length?`<div class="lora-stack">${loraNodes.map(([id,node])=>{
        const file=node.inputs.lora_name||'';
        const absent=loras.length&&file&&!loras.includes(file);
        const version=missingVersions[file];
        return `
        <div class="lora-line ${absent?'is-absent':''}" data-lora-node="${esc(id)}">
          <div class="lora-line-main">
            <select data-lora-name aria-label="LoRA file">
              ${loras.length?groupedModelOptions(loras,file,checkpointFamily)
                :(file?`<option value="${esc(file)}" selected>${esc(file.replace(/\.safetensors$/,''))}</option>`:'')}
            </select>
            <input type="number" data-lora-model step="0.05" min="-2" max="2" value="${Number(node.inputs.strength_model??1)}" title="Model strength" aria-label="Model strength">
            <input type="number" data-lora-clip step="0.05" min="-2" max="2" value="${Number(node.inputs.strength_clip??1)}" title="Text strength" aria-label="Text strength">
            ${absent&&version
              ? `<button type="button" class="lora-get" data-get-lora="${esc(file)}" title="Download this LoRA" aria-label="Download ${esc(file)}">↓</button>`
              : `<button type="button" class="lora-x" data-drop-lora="${esc(id)}" title="Remove" aria-label="Remove this LoRA">✕</button>`}
          </div>
          ${absent?`<small class="lora-absent-note">${esc(file.replace(/\.safetensors$/,''))} — ${version?'needs to be downloaded':'not on this ComfyUI'}</small>`:''}
        </div>`;}).join('')}</div>`
        :'<p class="dim small">No LoRAs in this workflow yet.</p>'}
      ${loras.length?`<p class="dim small">${loras.length} available${checkpointFamily?' \u00b7 sorted for '+esc(checkpointFamily):''}.
        <button type="button" class="link-button small" id="rescan-models">Re-read what they are</button></p>`
        :'<p class="dim small">Connect to ComfyUI to load its LoRAs.</p>'}
    </div>

    <div class="card studio-block">
      <h3>3 · Sampling &amp; output</h3>
      <div class="shape-row" role="group" aria-label="Shape">
        ${[['portrait','Portrait',832,1216],['square','Square',1024,1024],['landscape','Landscape',1216,832]]
          .map(([key,label,w,h])=>`<button type="button" class="shape-btn ${p.width===w&&p.height===h?'is-on':''}"
            data-shape="${w}x${h}">${label}</button>`).join('')}
      </div>
      <div class="dims-row">
        <label>Width<input id="preset-width" type="number" min="256" max="2048" step="64" value="${p.width||832}"></label>
        <label>Height<input id="preset-height" type="number" min="256" max="2048" step="64" value="${p.height||1216}"></label>
      </div>
      <div class="form-grid">
        <label>Seed
          <span class="seed-row">
            <input id="preset-seed" type="number" step="1" value="${p.seed??-1}">
            <button type="button" class="quiet small" id="preset-seed-random" title="Random each render">↻</button>
          </span>
          <small class="dim">−1 picks a new one every time.</small>
        </label>
      </div>
      <div class="tight-numbers">
        <label>Steps<input id="preset-steps" type="number" min="4" max="60" step="1" value="${p.steps??18}">
          <small class="hint" data-hint="steps"></small></label>
        <label>Guidance<input id="preset-cfg" type="number" min="1" max="12" step="0.1" value="${p.cfg??5}">
          <small class="hint" data-hint="cfg"></small></label>
        <label>CLIP skip<input id="preset-clip-skip" type="number" min="1" max="4" step="1" value="${clipSkipValue}">
          <small class="hint" data-hint="clip_skip"></small></label>
      </div>
      ${p.requires_reference?sliderRow('preset-denoise','Change from the reference',p.denoise??0.35,0.05,1,0.05,'Low keeps the original; high reinvents it.'):''}
    </div>

    <div class="card studio-block">
      <div class="studio-block-head"><h3>4 · Prompt</h3>
        <button type="button" class="chip-button" id="insert-companion"
          title="Fill these boxes from ${esc(chatName())}\u2019s saved image identity and what she is doing now"
          >\u21e5 Fill from ${esc(chatName())}</button></div>
      <div class="tag-fields">
        ${d.parts.map(k=>tagFieldHTML(k,SAVED_PARTS.includes(k)?'\u{1F512} '+formLabel(k):formLabel(k),
          p.parts?.[k]||'',PART_HINT[k]||'',false,
          k==='camera'?CAMERA_LOOKS:k==='lighting'?LIGHTING_LOOKS:null)).join('')}
        ${tagFieldHTML('__negative','\u{1F512} Always on',p.negative||'','Quality, anatomy, wardrobe',true)}
        ${tagFieldHTML('__modesty','\u{1F512} Modesty',p.modesty_negative||'',
          esc(chatName())+' may set these aside',true)}
      </div>
    </div>

    <div class="studio-actions">
      <button type="button" class="act" id="test-preset">Test render</button>
      <button type="button" class="quiet" id="assign-lane-here">Assign to a lane</button>
      <button type="button" class="quiet" id="derive-img2img">Image-to-image copy</button>
    </div>
    <p class="dim small" id="test-preset-status" role="status"></p>
    <div id="test-preset-result"></div>
    <div id="comfy-models"></div>

    <details class="studio-advanced">
      <summary>The raw workflow</summary>
      <p class="dim small">ComfyUI's Export (API) format. The controls above write into this.</p>
      <label>API workflow<textarea id="preset-workflow" class="code-editor">${esc(JSON.stringify(p.workflow,null,2))}</textarea></label>
      <label>Input mappings<textarea id="preset-mappings" class="code-editor">${esc(JSON.stringify(p.mappings,null,2))}</textarea></label>
    </details>`
    :`<div class="card studio-block">
      <div class="studio-block-head"><h3>Prompt</h3>
        <button type="button" class="chip-button" id="insert-companion-simple"
          title="Fill these boxes from ${esc(chatName())}\u2019s saved image identity and what she is doing now"
          >\u21e5 Fill from ${esc(chatName())}</button></div>
      <div class="tag-fields">
        ${d.parts.map(k=>tagFieldHTML(k,formLabel(k),p.parts?.[k]||'',PART_HINT[k]||'')).join('')}
      </div>
    </div>
    <div class="studio-block-actions"><button type="button" class="act" id="test-preset">Test render</button>
      <span class="dim small" id="test-preset-status" role="status"></span></div>
    <div id="test-preset-result"></div>`}

    <details class="studio-manage">
      <summary>Manage this workflow</summary>
      <div class="studio-actions">
        <button type="button" class="quiet" id="export-image-preset">Download</button>
        <button type="button" class="quiet" id="duplicate-image-preset">Duplicate</button>
      </div>
      <div class="studio-actions studio-danger">
        <button type="button" class="quiet is-danger" id="remove-image-preset">Delete this workflow</button>
      </div>
    </details>`;

  wireSliders($('image-preset-editor'));
  wirePresetControls(p);
 }

 /* Every control writes straight into the preset, so the raw JSON underneath is
    always what the sliders say. */
 let checkComfyConnection=()=>{};

 /* What this family of model usually wants, beside the field it applies to.
    A suggestion from a built-in table, never applied on its own, and labelled
    as a guess because the family is guessed from the checkpoint's filename. */
 async function showRecommendations(p){
  const root=$('image-preset-editor');if(!root)return;
  const node=nodesOfClass(p.workflow||{},'CheckpointLoaderSimple')[0];
  const checkpoint=node?node[1].inputs.ckpt_name:'';
  let advice={};
  try{advice=await api('/images/recommendations?checkpoint='+encodeURIComponent(checkpoint||''));}
  catch(error){return;}
  const range=key=>{
    const pair=advice[key];
    if(!Array.isArray(pair))return '';
    return pair[0]===pair[1]?String(pair[0]):pair[0]+'\u2013'+pair[1];
  };
  for(const hint of root.querySelectorAll('[data-hint]')){
    const text=range(hint.dataset.hint);
    hint.textContent=text?`${advice.family} likes ${text}`:'';
    hint.hidden=!text;
  }
  const badge=root.querySelector('[data-family-badge]');
  if(badge){
    badge.textContent=advice.family?advice.family+' \u00b7 guessed from the filename':'Family not recognised';
    badge.hidden=false;
  }
 }
 function wirePresetControls(p){
  const root=$('image-preset-editor');
  const clipNode=nodesOfClass(p.workflow||{},'CLIPSetLastLayer')[0];
  if($('preset-name'))$('preset-name').onchange=()=>{readPreset();menus();};
  if($('preset-seed-random'))$('preset-seed-random').onclick=()=>{$('preset-seed').value=-1;readPreset();};
  for(const select of root.querySelectorAll('[data-loader-node]'))select.onchange=()=>{
    p.workflow[select.dataset.loaderNode].inputs[select.dataset.loaderField]=select.value;
    syncWorkflowText(p);};
  for(const select of root.querySelectorAll('[data-ckpt-node]'))select.onchange=()=>{
    p.workflow[select.dataset.ckptNode].inputs.ckpt_name=select.value;
    syncWorkflowText(p);drawPreset();};
  for(const row of root.querySelectorAll('[data-lora-node]')){
    const id=row.dataset.loraNode,node=p.workflow[id];
    row.querySelector('[data-lora-name]').onchange=e=>{node.inputs.lora_name=e.target.value;drawPreset();};
    const model=row.querySelector('[data-lora-model]'),clip=row.querySelector('[data-lora-clip]');
    if(model)model.onchange=()=>{node.inputs.strength_model=Number(model.value);syncWorkflowText(p);};
    if(clip)clip.onchange=()=>{node.inputs.strength_clip=Number(clip.value);syncWorkflowText(p);};
  }
  for(const drop of root.querySelectorAll('[data-drop-lora]'))drop.onclick=()=>{
    const node=p.workflow[drop.dataset.dropLora];
    const name=(node?.inputs?.lora_name||'this LoRA').replace(/\.safetensors$/,'');
    if(!confirm('Remove '+name+' from this workflow?'))return;
    removeLoraNode(p,drop.dataset.dropLora);drawPreset();};
  for(const get of root.querySelectorAll('[data-get-lora]'))get.onclick=async()=>{
    const file=get.dataset.getLora,version=missingVersions[file];
    if(!version)return;
    if(!await confirmWeightTerms(version))return;
    get.disabled=true;get.textContent='\u2026';
    try{
      await followOperation(await post('/images/fetch-resource',{version_id:version,kind:'lora'}));
      delete comfyModelCache[p.endpoint];
      await comfyModels(p.endpoint);
      drawPreset();notice(file+' downloaded.');
    }catch(error){get.disabled=false;get.textContent='\u2193';notice('Download failed: '+error.message);}
  };
  /* Fill the boxes from who she is and what she is doing. Identity comes from
     the saved image block, which is the whole reason a likeness holds still
     between pictures; the rest is this moment and is replaced, not appended,
     because yesterday's outfit is not a tag you want to keep collecting. */
  const fillFromCompanion=async button=>{
    button.disabled=true;
    try{
      const parts=await api('/images/companion-parts');
      const filled=[];
      for(const key of ['identity','scene','wardrobe','lighting','camera']){
        const value=(parts[key]||'').trim();
        const field=root.querySelector(`[data-tag-field="${key}"]`);
        if(!value||!field)continue;
        const tags=tagsFromText(value);
        if(JSON.stringify(readTags(field))===JSON.stringify(tags))continue;
        writeTags(field,tags);
        field.open=true;filled.push(formLabel(key));
      }
      readPreset();
      if(!filled.length){notice('Those boxes already match her.');return;}
      notice(`Filled ${filled.join(', ')} from ${chatName()}\u2019s current state.`);
      if(!parts.identity_saved)
        notice('Identity is the raw SOUL prose \u2014 write her image identity on the '+
          'Identity page for a likeness that holds still between pictures.');
    }catch(error){notice('Could not read their details: '+error.message);}
    finally{button.disabled=false;}
  };
  for(const id of ['insert-companion','insert-companion-simple'])
    if($(id))$(id).onclick=()=>fillFromCompanion($(id));
  if($('rescan-models'))$('rescan-models').onclick=async()=>{
    const button=$('rescan-models');
    button.disabled=true;button.textContent='Reading headers\u2026';
    const data=await loadModelFamilies(true);
    notice(data?`Read ${data.total} files \u00b7 ${data.known} say what they were trained for.`
      :'Could not read the model files. Check the Comfy host in Preferences.');
    drawPreset();
  };
  if($('add-lora-row'))$('add-lora-row').onclick=async()=>{
    const models=await comfyModels(p.endpoint);
    addLoraNode(p,(models.lora_name||[])[0]);drawPreset();};
  // Shape sets the two numbers; the numbers stay editable afterwards.
  for(const button of root.querySelectorAll('[data-shape]'))button.onclick=()=>{
    const [w,h]=button.dataset.shape.split('x').map(Number);
    $('preset-width').value=w;$('preset-height').value=h;
    for(const other of root.querySelectorAll('[data-shape]'))other.classList.toggle('is-on',other===button);
    readPreset();
  };
  const markShape=()=>{
    const value=$('preset-width').value+'x'+$('preset-height').value;
    for(const button of root.querySelectorAll('[data-shape]'))
      button.classList.toggle('is-on',button.dataset.shape===value);
  };
  for(const id of ['preset-width','preset-height'])
    if($(id))$(id).oninput=()=>{markShape();readPreset();};
  // CLIP skip lives on a node, and is written back as a negative layer index.
  if($('preset-clip-skip')&&clipNode)$('preset-clip-skip').onchange=()=>{
    p.workflow[clipNode[0]].inputs.stop_at_clip_layer=-Math.abs(Number($('preset-clip-skip').value)||2);
    syncWorkflowText(p);
  };
  showRecommendations(p);

  wireTagFields(root,()=>readPreset());

  $('export-image-preset').onclick=()=>{readPreset();downloadJSON(fileSlug(p.name)+'-api.json',p);};
  $('duplicate-image-preset').onclick=()=>{readPreset();const copy=structuredClone(p);
    copy.id='preset-'+presetSuffix();copy.name+=' copy';settings.presets.push(copy);
    presetIndex=settings.presets.length-1;drawPreset();};
  $('remove-image-preset').onclick=()=>{
    if(!confirm('Delete "'+p.name+'"? Any lane pointing at it falls back to the default.'))return;
    settings.presets.splice(presetIndex,1);
    for(const k in routeValues)if(routeValues[k]===p.id)delete routeValues[k];
    if(defaultId===p.id)defaultId='';
    presetIndex=Math.max(0,presetIndex-1);drawPreset();
    notice('Workflow deleted. Save to keep the change.');};
  if($('derive-img2img'))$('derive-img2img').onclick=async()=>{
    const copy=await post('/images/img2img',{preset:p.id,denoise:.35});
    copy.id='img2img-'+presetSuffix();settings.presets.push(copy);
    presetIndex=settings.presets.length-1;drawPreset();};
  checkComfyConnection=async()=>{
    readPreset();delete comfyModelCache[p.endpoint];
    $('comfy-models').innerHTML='<p class="dim small">Checking…</p>';
    try{
      const r=await post('/images/check',{endpoint:p.endpoint});
      comfyModelCache[p.endpoint]=r.models||{};
      $('comfy-models').innerHTML=`<p class="status-good">Connected · ${(r.models?.ckpt_name||[]).length} models · ${(r.models?.lora_name||[]).length} LoRAs</p>`;
      drawPreset();
    }catch(error){$('comfy-models').innerHTML=`<p class="bad">${esc(error.message)}</p>`;}
  };
  if($('test-preset'))$('test-preset').onclick=async()=>testPreset(p);
  if($('assign-lane-here'))$('assign-lane-here').onclick=()=>{readPreset();showStudioView('assignments');};
 }

 /* A LoRA loader sits in a chain: model and clip come from the node before it,
    and whatever consumed the last one now consumes this. Adding or removing one
    has to mend that chain or the graph stops rendering. */
 function loraChain(workflow){return nodesOfClass(workflow,'LoraLoader').map(([id])=>id);}
 function rewire(workflow,fromId,toRef){
  for(const node of Object.values(workflow)){
    for(const [key,value] of Object.entries(node.inputs||{})){
      if(Array.isArray(value)&&String(value[0])===String(fromId))node.inputs[key]=[toRef[0],value[1]];
    }
  }
 }
 function addLoraNode(p,name){
  if(!name)return;
  const chain=loraChain(p.workflow);
  const lastId=chain[chain.length-1];
  const source=lastId||(nodesOfClass(p.workflow,'CheckpointLoaderSimple')[0]||[])[0];
  if(!source)return;
  const newId=String(Math.max(0,...Object.keys(p.workflow).map(Number))+1);
  // Everything that read from the end of the chain now reads from the new node.
  rewire(p.workflow,source,[newId]);
  p.workflow[newId]={class_type:'LoraLoader',inputs:{
    model:[source,0],clip:[source,lastId?1:1],
    lora_name:name,strength_model:0.8,strength_clip:0.8}};
  syncWorkflowText(p);
 }
 function removeLoraNode(p,id){
  const node=p.workflow[id];if(!node)return;
  const modelSource=node.inputs.model,clipSource=node.inputs.clip;
  for(const other of Object.values(p.workflow)){
    for(const [key,value] of Object.entries(other.inputs||{})){
      if(!Array.isArray(value)||String(value[0])!==String(id))continue;
      other.inputs[key]=value[1]===1?[...clipSource]:[...modelSource];
    }
  }
  delete p.workflow[id];
  syncWorkflowText(p);
 }
 function syncWorkflowText(p){
  if($('preset-workflow'))$('preset-workflow').value=JSON.stringify(p.workflow,null,2);
 }

 /* Renders this workflow as it stands: unsaved, unassigned, and sent as a draft
    so the library is untouched until the result is worth keeping. */
 async function testPreset(p){
  readPreset();
  const status=$('test-preset-status'),out=$('test-preset-result');
  status.textContent='Rendering\u2026';out.innerHTML='';
  $('test-preset').disabled=true;
  try{
   await action('/images/generate',{draft:p,category:p.category||'portrait',parts:p.parts||{}},r=>{
     out.innerHTML=r.image
       ? `<img class="studio-test-shot ${r.blur?'concealed-media':''}" src="${mediaUrl(r.image)}" alt="Test render">`
       : '<p class="dim small">Rendered. It is in Photos.</p>';
     status.innerHTML='Rendered from the draft \u00b7 <strong>nothing saved yet</strong>';
   });
  }catch(error){
   status.innerHTML=`<span class="bad">${esc(error.message)}</span> `+
     `<button type="button" class="link-button small" id="check-comfy">Check the connection</button>`;
   if($('check-comfy'))$('check-comfy').onclick=checkComfyConnection;
  }
  finally{$('test-preset').disabled=false;}
 }

 await drawPreset();
 /* The plain Download hands back the API graph the server runs. This one asks
    ComfyUI for its node definitions and rebuilds the editor graph, so the file
    can be dropped straight onto the ComfyUI canvas. */
 $('download-interactive').onclick=async()=>{
  const button=$('download-interactive'),status=$('download-interactive-status');
  readPreset();
  const preset=settings.presets[presetIndex];
  if(!preset)return;
  button.disabled=true;status.textContent='Asking ComfyUI for its node list\u2026';
  try{
   const graph=await post('/images/interactive-workflow',{preset});
   downloadJSON(fileSlug(preset.name)+'-interactive.json',graph);
   status.textContent='';
   notice('Interactive workflow downloaded. Drop it onto the ComfyUI canvas to edit it.');
  }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
  finally{button.disabled=false;}
 };
 $('image-preset-select').onchange=async e=>{
  readPreset();
  if(e.target.value==='__new__'){
   const blank=await api('/images/modular-template');
   blank.id='comfy-'+presetSuffix();
   blank.name='New workflow';
   blank.category='';
   blank.incomplete=true;
   try{blank.endpoint=(await api('/workflows')).settings?.endpoint||blank.endpoint;}catch(error){}
   settings.presets.push(blank);
   presetIndex=settings.presets.length-1;
   setWorkflowMode('edit');await drawPreset();
   notice('New workflow started. Choose a model, then test it before saving.');
   return;
  }
  presetIndex=Number(e.target.value);setWorkflowMode('edit');drawPreset();
 };
 /* Create, edit or import: one of three, and only one on screen. */
 /* Edit what exists, or make a new one; importing is a way of making one. */
 function setWorkflowMode(mode){
  for(const [name,id] of [['edit','workflow-edit-panel'],['import','workflow-import-panel']]){
   const panel=$(id);if(panel)panel.hidden=name!==mode;
  }
 }
 if($('workflow-show-import'))$('workflow-show-import').onclick=()=>setWorkflowMode('import');

 /* Reading a workflow back out of a picture. What cannot be read is reported
    rather than guessed, and the result is saved either way. */
 function showImportResult(result){
  const report=$('workflow-import-report');
  {
   $('workflow-import-status').textContent='';
   const found=result.found||{},rows=[
    ['Read from',found.source],
    ['Nodes',found.nodes],
    ['Checkpoint',(found.checkpoints||[]).join(', ')],
    ['LoRAs',(found.loras||[]).join(', ')],
    ['Steps',found.steps],['Guidance',found.cfg],['Seed',found.seed],
    ['Size',found.width&&found.height?found.width+'\u00d7'+found.height:'']
   ].filter(([,value])=>value!==undefined&&value!==''&&value!==null);
   const resources=found.resources||[];
   const missing=resources.filter(r=>r.file&&!r.installed&&r.version_id);
   report.innerHTML=`<div class="import-report">
     <dl>${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(String(v))}</dd></div>`).join('')}</dl>
     ${resources.length?`<div class="resource-list">
       <span class="eyebrow">What it used</span>
       ${resources.map((r,i)=>`<div class="resource-row ${r.installed?'is-here':''}">
         <span class="resource-kind">${esc(r.kind||'file')}</span>
         <span class="resource-name">${esc(r.file||r.name||'unknown')}${r.base_model?` <small class="dim">${esc(r.base_model)}</small>`:''}</span>
         ${r.installed?'<span class="resource-state">installed</span>'
           :r.version_id?`<button type="button" class="quiet small" data-fetch="${i}">Download</button>`
           :'<span class="resource-state dim">not on Civitai</span>'}
       </div>`).join('')}
       ${missing.length?`<button type="button" class="quiet" id="fetch-all-missing">Download all ${missing.length} missing</button>`:''}
     </div>`:''}
     ${(result.notes||[]).map(n=>`<p class="dim small">${esc(n)}</p>`).join('')}
     <div class="studio-actions">
       <button class="act" id="keep-imported">${result.preset.incomplete?'Save as a draft':'Add this workflow'}</button>
       <button class="quiet" id="discard-imported">Discard</button>
     </div></div>`;
   for(const row of resources){
     if(row.file&&row.version_id&&!row.installed)missingVersions[row.file]=row.version_id;
     else if(row.file&&row.installed)delete missingVersions[row.file];
   }
   const fetchOne=async row=>{
     const status=$('workflow-import-status');
     if(!await confirmWeightTerms(row.version_id))return;
     status.textContent=`Downloading ${row.file}\u2026`;
     try{
       await followOperation(await post('/images/fetch-resource',{version_id:row.version_id,kind:row.kind}));
       row.installed=true;status.textContent='';showImportResult(result);
     }catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
   };
   for(const button of report.querySelectorAll('[data-fetch]'))
     button.onclick=()=>fetchOne(resources[Number(button.dataset.fetch)]);
   if($('fetch-all-missing'))$('fetch-all-missing').onclick=async()=>{
     for(const row of missing)await fetchOne(row);
   };
   $('discard-imported').onclick=()=>{report.innerHTML='';$('workflow-import-file').value='';};
   $('keep-imported').onclick=()=>{
    readPreset();
    const preset={...result.preset,id:'import-'+presetSuffix()};
    settings.presets.push(preset);
    presetIndex=settings.presets.length-1;
    report.innerHTML='';$('workflow-import-file').value='';
    setWorkflowMode('edit');drawPreset();
    notice(preset.incomplete
      ? 'Saved as a draft. Choose a checkpoint before it can serve a lane.'
      : 'Workflow imported. Test it, then assign it to a lane.');
   };
  }
 }

 async function runImport(read){
  const status=$('workflow-import-status');
  status.textContent='Reading\u2026';$('workflow-import-report').innerHTML='';
  try{showImportResult(await read());}
  catch(error){status.innerHTML=`<span class="bad">${esc(error.message)}</span>`;}
 }

 $('workflow-import-file').onchange=()=>{
  const file=$('workflow-import-file').files[0];if(!file)return;
  runImport(async()=>{
   const headers={'content-type':'application/octet-stream','x-image-name':file.name.replace(/[^\w.\- ]/g,'')};
    if(token){
      headers['x-tamanitomo-token']=token;
      headers['x-companion-token']=token;
    }
   const response=await fetch(scoped('/api/images/import'),{method:'POST',headers,body:file});
   if(!response.ok)throw Error((await response.json().catch(()=>({}))).detail||'That image could not be read');
   return response.json();
  });
 };
 $('workflow-import-go').onclick=()=>runImport(()=>post('/images/import-url',{url:$('workflow-import-url').value}));
 $('workflow-import-url').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('workflow-import-go').click();}};

 const addComfyPreset=async()=>{readPreset();const p=await api('/images/modular-template');p.id='comfy-'+presetSuffix();settings.presets.push(p);presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 const addCloudPreset=()=>{readPreset();settings.presets.push({id:'api-'+presetSuffix(),name:'Image API',provider:'openai',category:'portrait',endpoint:'https://api.openai.com/v1',api_key_env:'OPENAI_API_KEY',model:'',width:1024,height:1024,parts:{},negative:''});presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 const addHermesPreset=()=>{readPreset();settings.presets.push({id:'hermes-'+presetSuffix(),name:'Hermes image provider',provider:'hermes',category:'portrait',endpoint:'',parts:{},negative:''});presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 $('image-template-download').onclick=async()=>downloadJSON('comfy-structured-sdxl-template.json',await api('/images/modular-template'));
 $('image-import').onclick=()=>$('image-import-file').click();
 $('image-import-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>4000000)throw Error('Workflow must be under 4 MB');readPreset();const imported=JSON.parse(await file.text());if(imported.nodes)throw Error('This is a visual-editor workflow. Export it as API format from ComfyUI, then import that file.');let p;if(imported.provider)p=imported;else{p=await api('/images/template');p.workflow=imported;p.mappings={};p.name=file.name.replace(/\.json$/,'');}p.id='import-'+presetSuffix();settings.presets.push(p);presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};

 const saveSettings=async(msg='Image settings saved for this companion.')=>{
  readPreset();
  // identity_override is the image identity block, written on the Identity
  // page. Saving a workflow must never overwrite it.
  settings.inherit=$('image-inherit')?.checked||false;
  settings.default_preset=defaultId;
  settings.routes=routeValues;
  // A workflow describes how to render, not what was happening at one moment.
  // The moment's boxes are filled per render and are dropped on the way out,
  // which is what the unlocked labels in the editor promise.
  const saved={...settings,presets:settings.presets.map(preset=>({...preset,
    parts:Object.fromEntries(Object.entries(preset.parts||{})
      .filter(([key])=>!TRANSIENT_PARTS.includes(key)))}))};
  const r=await post('/images',{settings:saved,revision});
  settings.presets=saved.presets;
  revision=r.revision;
  menus();
  notice(msg);
 };

 $('save-image-settings').onclick=()=>saveSettings();
 $('save-assignments-btn').onclick=()=>saveSettings('Lane assignments and fallback saved!');
 $('image-install-comfy').onclick=()=>action('/images/install',{});
 $('image-start-comfy').onclick=()=>action('/images/start',{cpu:$('comfy-cpu').checked});

 const categoryTestPrompts = {
  portrait: [
   ['Serene Daylight', 'A serene studio portrait of the companion in casual everyday attire, soft daylight, neutral background.'],
   ['Candid Outdoors', 'A candid eye-level outdoor portrait with natural sunlight and soft background bokeh.'],
   ['Window Reading', 'A relaxed indoor portrait reading a book by a sunlit window, warm ambient light.']
  ],
  landscape: [
   ['Green Hills', 'A wide scenic landscape of rolling green hills under a bright sunlit blue sky with soft clouds.'],
   ['Sunset Shore', 'A serene coastline with gentle ocean waves meeting a quiet sandy shore at sunset.']
  ],
  anime: [
   ['City Sunset', 'A vibrant stylized illustration of a character walking through an animated city street at golden hour.'],
   ['Tea Shop', 'A stylized warm illustration sitting at a quiet cafe counter with tea, soft cel shading.']
  ],
  realistic: [
   ['Studio Lighting', 'A high fidelity photographic test shot with balanced studio key lighting and natural textures.'],
   ['Architecture', 'A clean architectural photograph with natural daylight and crisp geometric lines.']
  ],
  other: [
   ['Color Balance', 'A clean compositional color calibration test featuring geometric forms and natural daylight.'],
   ['Still Life', 'A still life arrangement on a rustic wooden table with fresh fruit and ceramic cup.']
  ]
 };


};
workspaceHandlers['local-models']=async()=>{
 const d=await api('/local-models');
 const isOnline=Boolean(d.online);
 const srv=d.service||{};
 const loaded=d.loaded_model;
 const diskModels=d.available_models||[];
 const recommendations=d.recommendations||[];
 const companionName=chatName();

  const statusBadge=isOnline
    ? `<span class="pill status-good">● Online · ${esc(d.engine||'Local Engine')}</span>`
    : `<span class="pill status-bad">● Offline</span>`;

  const memText=srv.memory_mb ? `${srv.memory_mb} MB RAM` : '';
  const serviceText=srv.found
    ? `${esc(srv.unit || 'companion-llama.service')} · PID ${srv.main_pid || 'N/A'}${memText ? ' · ' + memText : ''} · ${srv.active_state || ''}`
    : (d.endpoint ? esc(d.endpoint) : 'No system service found');

  let heroCard='';
  if(loaded){
    const ctxStr=(loaded.ctx_size||0).toLocaleString()+' tokens context';
    const quantStr=loaded.quant ? 'Quant: '+loaded.quant : '';
    const paramStr=loaded.params ? (loaded.params/1e9).toFixed(1)+'B params' : '';
    const sizeStr=loaded.size ? (loaded.size/(1024**3)).toFixed(1)+' GB weights' : '';
    const metaItems=[ctxStr, quantStr, paramStr, sizeStr].filter(Boolean).join(' · ');

    heroCard=`<div class="card">
      <div class="section-heading" style="margin-top:0">
        <div>
          <span class="eyebrow">Active Local Model</span>
          <h2 style="font-size:22px;margin:4px 0">${esc(loaded.id||'Loaded Model')}</h2>
        </div>
        ${statusBadge}
      </div>
      <p class="dim" style="margin-bottom:8px">${esc(metaItems)}</p>
      <p class="dim small" style="margin-bottom:16px">${esc(serviceText)} · <code>${esc(d.endpoint||'')}</code></p>
      <div class="actions">
        <button class="act" id="assign-loaded-btn">Use ${esc(loaded.id)} for ${esc(companionName)}</button>
        <button class="quiet" id="srv-restart-btn">🔄 Restart</button>
        <button class="quiet" id="srv-stop-btn">⏹ Stop</button>
      </div>
    </div>`;
  } else {
    heroCard=`<div class="card">
      <div class="section-heading" style="margin-top:0">
        <div>
          <span class="eyebrow">Local Inference Engine</span>
          <h2 style="font-size:22px;margin:4px 0">${isOnline ? 'Engine Ready · No Model Loaded' : 'Local Engine Offline'}</h2>
        </div>
        ${statusBadge}
      </div>
      <p class="dim" style="margin-bottom:8px">${isOnline ? 'Engine is active and listening on '+esc(d.endpoint)+'. Select any model below to activate GPU offload.' : (esc(d.error)||'Inference service is stopped. Start engine or select a model below to run.')}</p>
      <p class="dim small" style="margin-bottom:16px">${esc(serviceText)}</p>
      <div class="actions">
        ${isOnline
          ? `<button class="quiet" id="srv-restart-btn">🔄 Restart</button><button class="quiet" id="srv-stop-btn">⏹ Stop</button>`
          : `<button class="act" id="srv-start-btn">▶ Start Engine</button>`}
      </div>
    </div>`;
  }

  const libraryHTML=`<div class="card">
    <div class="section-heading" style="margin-top:0">
      <div>
        <span class="eyebrow">Storage Library</span>
        <h2 style="font-size:18px;margin:4px 0">Discovered Model Weights</h2>
      </div>
      <span class="pill">${diskModels.length} models found</span>
    </div>
    <p class="dim small" style="margin-bottom:18px">GGUF weights discovered on storage (<code>/mnt/nvme2/models/</code> and <code>~/models/</code>). 1-click activate automatically applies Vulkan GPU offloading and pairs vision projectors.</p>
    ${diskModels.length?`<div class="grid">
      ${diskModels.map(m=>{
        const dangerous = Boolean(d.safety_limit_gb && m.size_gb > d.safety_limit_gb);
        return `
        <div class="card" style="margin-bottom:0;display:flex;flex-direction:column;justify-content:space-between;border-color:${m.active?'var(--accent)':(dangerous?'var(--bad)':'var(--edge)')}">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span class="pill">${esc(m.family)}</span>
              <span class="small ${dangerous?'status-bad':'dim'}">${m.size_gb} GB${dangerous?' · ⚠️ Danger':''}</span>
            </div>
            <h3 style="font-size:14px;word-break:break-all;margin:6px 0 10px">${esc(m.name)}</h3>
            ${m.mmproj ? '<p class="small" style="color:var(--accent);margin:0 0 8px">👁 Multimodal Vision mmproj included</p>' : ''}
            ${dangerous ? `<p class="small" style="color:var(--bad);margin:0 0 8px">⚠️ Exceeds ${d.safety_limit_gb} GB mobile limit (causes Android LMK crash)</p>` : ''}
          </div>
          <div style="margin-top:14px;display:flex;flex-direction:column;gap:6px">
            ${m.active
              ? '<span class="pill status-good" style="width:100%;text-align:center;display:block">● Active on GPU</span>'
              : (dangerous
                  ? `<button type="button" class="quiet small" style="width:100%;opacity:0.6;cursor:not-allowed" disabled>⚠️ Exceeds Mobile Limit</button>`
                  : `<button type="button" class="act small" style="width:100%" data-quick-switch="${esc(m.path)}" data-quick-alias="${esc(m.alias)}">⚡ Activate & Offload</button>`)}
            <button type="button" class="quiet small" style="width:100%" data-quick-assign="${esc(m.alias||m.name)}" ${dangerous?'disabled':''}>Assign to ${esc(companionName)}</button>
          </div>
        </div>
      `;}).join('')}
    </div>`:'<p class="dim">No GGUF models discovered in storage. Place <code>.gguf</code> files into <code>/mnt/nvme2/models/</code> or <code>~/models/</code> and refresh.</p>'}
  </div>`;

  const ctxOptions = d.is_mobile ? `
    <option value="4096" selected>4,096 tokens (4k - Mobile Recommended)</option>
    <option value="2048">2,048 tokens (2k - Low Memory)</option>
    <option value="8192">8,192 tokens (8k - Extended Context)</option>
  ` : `
    <option value="131072" selected>131,072 tokens (128k - Recommended)</option>
    <option value="65536">65,536 tokens (64k)</option>
    <option value="32768">32,768 tokens (32k)</option>
    <option value="16384">16,384 tokens (16k)</option>
  `;

  const advancedHTML=`<details class="card">
    <summary><strong>Advanced Engine Parameters & Custom Offload</strong></summary>
    <div style="margin-top:16px">
      <form id="model-switch-form">
        <div class="form-grid">
          <div class="wide">
            <label>Model File
              <select id="model-switch-select">
                ${diskModels.map(m=>`<option value="${esc(m.path)}" data-alias="${esc(m.alias)}" ${m.active?'selected':''}>${esc(m.family)} · ${esc(m.name)} (${m.size_gb} GB)${m.active?' [ACTIVE]':''}</option>`).join('')}
              </select>
            </label>
          </div>
          <div>
            <label>Model Identifier / Alias
              <input id="model-switch-alias" value="${esc(diskModels.find(m=>m.active)?.alias||diskModels[0]?.alias||'local-model')}" placeholder="e.g. local-model" required maxlength="32">
            </label>
          </div>
          <div>
            <label>Context Window Size
              <select id="model-switch-ctx">
                ${ctxOptions}
              </select>
            </label>
          </div>
        </div>
        <div class="actions">
          <button type="submit" class="act" id="model-switch-submit">Apply & Restart Engine</button>
          <button type="button" class="quiet" id="models-refresh-btn">Rescan Storage</button>
        </div>
      </form>
    </div>
  </details>`;

  const mobileBanner = d.is_mobile ? `<div class="card" style="border-left:4px solid var(--accent);background:var(--bg-soft, #1e2025);margin-bottom:16px">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <span style="font-size:16px">📱</span>
      <strong style="font-size:14px">Mobile Hardware Guardrails Active (Android / Termux)</strong>
    </div>
    <p class="small dim" style="margin:0">
      Available RAM: <strong>${d.host_memory ? (d.host_memory.available_mb/1024).toFixed(1)+' GB' : 'Android'}</strong>
      (Total: ${d.host_memory ? (d.host_memory.total_mb/1024).toFixed(1)+' GB' : 'N/A'}).
      Safety limit enforced: models capped at <strong>${d.safety_limit_gb || 2.8} GB</strong> to prevent Android Low Memory Killer (LMK) termination. Thermal concurrency capped at 4 threads.
    </p>
  </div>` : '';

  const ollamaHTML=`<details class="card">
    <summary><strong>Ollama Engine & Catalog Downloads</strong> (Optional)</summary>
    <div style="margin-top:14px">
      <p class="dim small">${d.installed ? 'Ollama runtime is present.' : 'Ollama runtime is not installed.'} Standard catalog models can be pulled below if you prefer Ollama over Vulkan llama.cpp.</p>
      <div class="actions">
        <button class="act" id="local-install" ${d.installed?'disabled':''}>${d.installed?'Ollama installed':'Install Ollama on Hermes host'}</button>
        <button class="quiet" id="local-start">Start Ollama</button>
      </div>
      ${recommendations.length?`<div class="grid" style="margin-top:14px">
        ${recommendations.map(m=>`
          <div class="card" style="margin-bottom:0">
            <h3>${esc(m.name)}</h3>
            <p class="dim small">${m.gb} GB download · Q4_K_M</p>
            <p class="dim small">${esc(m.memory)}</p>
            <div class="actions">
              <button class="quiet small" data-pull-model="${esc(m.id)}">Download weights</button>
            </div>
          </div>
        `).join('')}
      </div>`:''}
    </div>
  </details>`;

  $('local-models').innerHTML=heading('Local Models & Hardware Engine','Configure your Vulkan-accelerated local inference engine, switch GGUF weights, and assign models to '+esc(companionName)+'.')+`
    ${mobileBanner}
    ${heroCard}
    ${libraryHTML}
    ${advancedHTML}
    ${ollamaHTML}
  `;

  const wireEngineActions=()=>{
    const refresh=()=>render('local-models');
    bindAction('srv-restart-btn','/local-models/server/control',{action:'restart'},refresh);
    bindAction('srv-stop-btn','/local-models/server/control',{action:'stop'},refresh);
    bindAction('srv-start-btn','/local-models/server/control',{action:'start'},refresh);
    for(const id of ['bar-refresh-btn','models-refresh-btn']) {
      const b=$(id);
      if(b)b.onclick=refresh;
    }
    const assignLoaded=$('assign-loaded-btn');
    if(assignLoaded&&loaded) {
      assignLoaded.onclick=()=>action('/local-models/assign',{model:loaded.id},refresh);
    }
    const switchSel=$('model-switch-select');
    if(switchSel) {
      switchSel.onchange=()=>{
        const opt=switchSel.options[switchSel.selectedIndex];
        if(opt&&opt.dataset.alias)$('model-switch-alias').value=opt.dataset.alias;
      };
    }
    const switchForm=$('model-switch-form');
    if(switchForm) {
      switchForm.onsubmit=async e=>{
        e.preventDefault();
        const path=$('model-switch-select').value;
        const alias=$('model-switch-alias').value;
        const ctx_size=Number($('model-switch-ctx').value)||131072;
        if(!path)throw Error('Please select a model file.');
        await action('/local-models/server/switch',{path,alias,ctx_size},refresh);
      };
    }
    for(const b of $('local-models').querySelectorAll('[data-quick-switch]')) {
      b.onclick=async()=>{
        const path=b.dataset.quickSwitch;
        const alias=b.dataset.quickAlias;
        await action('/local-models/server/switch',{path,alias,ctx_size:131072},refresh);
      };
    }
    for(const b of $('local-models').querySelectorAll('[data-quick-assign]')) {
      b.onclick=async()=>{
        const model=b.dataset.quickAssign;
        if(!model)return;
        await action('/local-models/assign',{model},refresh);
      };
    }
    bindAction('local-install','/local-models/install',{},refresh);
    bindAction('local-start','/local-models/start',{},refresh);
    for(const b of $('local-models').querySelectorAll('[data-pull-model]')) {
      b.onclick=()=>action('/local-models/pull',{model:b.dataset.pullModel},refresh);
    }
  };
  wireEngineActions();
};
boot().catch(e=>{notice(e.message,true);$('who').textContent='Connection needed';});
