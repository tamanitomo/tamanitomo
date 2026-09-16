/* Complete management editors, using the active Hermes profile at every boundary. */
function addPage(id,label){TABS.push([id,label]);const section=document.createElement('section');section.id=id;section.hidden=true;document.querySelector('main').append(section);}
addPage('local-models','Local models');addPage('companion-edit','Edit companion');addPage('image-studio','Image studio');
// getRandomValues also works on plain HTTP LAN origins; randomUUID requires HTTPS.
const presetSuffix=()=>Array.from(crypto.getRandomValues(new Uint8Array(8)),v=>v.toString(16).padStart(2,'0')).join('');
const formLabel=key=>key.replaceAll('_',' ').replace(/^./,s=>s.toUpperCase());
const profileChoices={agent_type:['companion','colleague','worker'],pronoun_set:['she','he'],human_pronoun_set:['she','he'],outreach:['updates_only','free','never'],relationship_progression:['off','subtle','milestones'],relationship_pace:['slow','natural','quick'],context_mode:['auto','fixed']};
function fieldHTML(key,value,choices=[],readonly=false){
 if(key==='outreach_per_day')return `<label>Maximum proactive messages per day<input data-config="outreach_per_day" type="number" required min="1" max="100" value="${value||3}" ${value===0?'disabled':''}></label><label class="inline-label"><input id="editor-unlimited" type="checkbox" ${value===0?'checked':''}>No daily limit (unlimited proactive messages)</label>`;
 const disabled=readonly?'disabled':'';
 const input=choices.length?`<select data-config="${esc(key)}" ${disabled}>${options(choices.map(v=>Array.isArray(v)?v:[v,formLabel(v)]),value)}</select>`:
 typeof value==='boolean'?`<select data-config="${esc(key)}" ${disabled}>${options([['true','Enabled'],['false','Disabled']],String(value))}</select>`:
 typeof value==='object'?`<textarea data-config="${esc(key)}" ${disabled}>${esc(JSON.stringify(value,null,2))}</textarea>`:
 `<input data-config="${esc(key)}" ${disabled} type="${typeof value==='number'?'number':key==='birthdate'?'date':['quiet_start','quiet_end'].includes(key)?'time':'text'}" ${typeof value==='number'?'step="any"':''} value="${esc(value)}">`;
 return `<label>${esc(formLabel(key))}${input}${readonly?'<span class="dim small">Storage path · managed by installation</span>':''}</label>`;
}
workspaceHandlers['companion-edit']=async()=>{
 const [d,catalog]=await Promise.all([api('/profile/editor'),api('/catalog')]);
 const groups=[['Identity',['agent','human','names','pronoun_set','human_pronoun_set','agent_type','persona','boundary','birthdate','age','timezone']],['Appearance & contact',['image_style','image_timeline','image_mode','content_permissions','outreach','outreach_per_day','quiet_start','quiet_end','share_people']],['More companion settings',Object.keys(d.config).filter(k=>!['agent','human','names','pronoun_set','human_pronoun_set','agent_type','persona','boundary','birthdate','age','timezone','image_style','image_timeline','image_mode','content_permissions','outreach','outreach_per_day','quiet_start','quiet_end','share_people'].includes(k))]];
 const choices={...profileChoices,timezone:[...new Set([d.config.timezone,...catalog.timezones])].map(z=>[z,z]),persona:Object.entries(catalog.personas).map(([k,v])=>[k,v.label]),boundary:Object.entries(catalog.boundaries).map(([k,v])=>[k,v.label]),image_style:Object.entries(catalog.image_styles).map(([k,v])=>[k,v.label])};
 $('companion-edit').innerHTML=heading('Edit '+d.display_name,'Your companion’s current configuration and authored identity, prefilled from their files.')+`<div class="actions"><button class="quiet" data-editor-route="roster">← All companions</button><button class="quiet" data-editor-route="voice">Voice studio</button><button class="quiet" data-editor-route="image-studio">Image studio</button><button class="quiet" data-editor-route="environment">Hermes settings</button></div><form id="companion-edit-form"><div class="card"><label>Display name <span class="dim small">The name shown in this workspace</span><input id="editor-display-name" value="${esc(d.display_name)}" required maxlength="100"></label></div>${groups.map(([label,keys],i)=>`<details class="card" ${i<2?'open':''}><summary>${label}</summary><div class="form-grid">${keys.map(k=>fieldHTML(k,d.config[k],choices[k]||[],d.fixed.includes(k))).join('')}</div></details>`).join('')}<div class="card"><h2>Who they are</h2><p class="dim">Personality, appearance, boundaries and shared history live in their SOUL, which Identity reads as a document and edits a section at a time. This page is for the configuration around it.</p><div class="actions"><button type="button" class="quiet" data-editor-route="identity">Open Identity \u2192</button></div></div><div class="actions"><button class="act">Save companion</button><button type="button" class="quiet" id="reload-companion">Reload current files</button></div></form>`;
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

// Keep every native Hermes page and plugin available inside the workspace.
const environmentStudioBase=workspaceHandlers.environment;
workspaceHandlers.environment=async()=>{
 await environmentStudioBase();if(current!=='environment')return;
 const focusGateway=environmentFocus;environmentFocus=false;const page=$('environment'),legacy=document.createElement('details');legacy.className='card';legacy.innerHTML='<summary>Companion environment & native command-line setup</summary>';while(page.firstChild)legacy.append(page.firstChild);page.append(legacy);if(focusGateway)legacy.open=true;
 const host=document.createElement('div');host.innerHTML=heading('Hermes settings','The complete dashboard from your installed Hermes, with its own configuration forms, skills, MCP connections, and system tools.')+`<div class="actions"><button class="quiet" id="dashboard-gateway">Gateway & routine</button><button class="act" id="dashboard-local-models">Local models & weights</button><button class="quiet" id="dashboard-images">Image studio</button><button class="quiet" id="dashboard-voice">Voice studio</button></div><div class="actions" id="hermes-pages">${[['','Overview'],['config','Configuration'],['models','Models'],['env','Credentials'],['skills','Skills'],['mcp','MCP'],['plugins','Plugins'],['sessions','Sessions'],['cron','Jobs'],['logs','Logs'],['analytics','Usage'],['channels','Channels'],['pairing','Pairing'],['webhooks','Webhooks'],['system','System']].map(([path,label])=>`<button class="quiet" data-hermes-page="${path}">${label}</button>`).join('')}</div><div id="hermes-dashboard-frame"><p class="card">Starting the installed Hermes dashboard…</p></div>`;page.prepend(host);if(focusGateway){page.insertBefore(legacy,host);legacy.querySelector('[data-panel="2"]')?.click();}if($('kit-updates'))page.append($('kit-updates'));$('dashboard-gateway').onclick=()=>{legacy.open=true;legacy.querySelector('[data-panel="2"]')?.click();$('gateway-controls')?.scrollIntoView({block:'start'});};$('dashboard-local-models').onclick=()=>showTab('local-models');$('dashboard-images').onclick=()=>showTab('image-studio');$('dashboard-voice').onclick=()=>showTab('voice');
 try{const d=await post('/dashboard/start');if(current!=='environment')return;const iframe=document.createElement('iframe');iframe.title='Hermes dashboard';iframe.className='hermes-dashboard';const open=path=>{iframe.src=d.prefix+'/'+path+(PROFILE&&PROFILE!=='default'?'?profile='+encodeURIComponent(PROFILE):'');};$('hermes-dashboard-frame').replaceChildren(iframe);open('');for(const b of $('hermes-pages').children)b.onclick=()=>{open(b.dataset.hermesPage);for(const other of $('hermes-pages').children)other.setAttribute('aria-pressed',String(other===b));};}
 catch(e){$('hermes-dashboard-frame').innerHTML=`<div class="card"><h3>Dashboard needs attention</h3><p>${esc(e.message)}</p><button class="quiet" id="retry-dashboard">Retry dashboard</button><p>Native command-line setup remains available below.</p></div>`;$('retry-dashboard').onclick=()=>render('environment');legacy.open=true;}
};
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
 $('studio-native-voice').onclick=async()=>{current='environment';await workspaceHandlers.environment();for(const [id] of TABS)$(id).hidden=id!=='environment';$('environment').querySelector('details').open=true;await openConsole('tools');};
 $('voice-studio-form').onsubmit=async e=>{
  e.preventDefault();
  if($('voice-inherit')?.checked){await action('/voice/inherit',{});return;}
  const file=$('studio-voice-clip')?.files[0];
  if(file){
   const response=await fetch(scoped('/api/voice/reference?provider='+encodeURIComponent(selected)),{method:'POST',headers:{'content-type':'application/octet-stream',...(token?{'x-companion-token':token}:{})},body:file});
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

function downloadJSON(name,data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

/* Which studio view is open, kept across a re-render so a portrait change comes
   back to the identity view instead of dropping you on the composer. */
let imageStudioView='compose';

/* The reference portrait used to sit on Identity, where it broke the SOUL into
   pieces and was the one thing on that page that could call a model. It belongs
   beside the appearance prompt it feeds, so it lives in this view instead. */
function wirePortrait(){
 const msg=$('pmsg'),reload=async()=>{
  // The face the rest of the app draws just changed.
  portraitVersion=Date.now();await refreshPortraitState();
  imageStudioView='identity';await render('image-studio');
 };
 $('pfile').onchange=async()=>{
  const file=$('pfile').files[0];if(!file)return;
  msg.textContent='storing\u2026';
  try{await uploadPortrait(file);await reload();}
  catch(e){msg.innerHTML=`<span class="bad">${esc(e.message)}</span>`;}
 };
 $('palbum').onclick=async()=>{
  const content=await api('/content');const images=content.items.filter(x=>x.kind==='image');
  dialog('Choose a reference photo',`<div class="photo-grid">${images.map((x,i)=>`<button class="card" data-reference="${i}"><img ${mediaPrivacy(x)} style="width:100%;height:150px;object-fit:cover" src="${mediaUrl(x.url)}" alt="${esc(x.title)}"><span>${esc(x.title)} \u00b7 ${esc(x.generation||x.source)}${x.blur?' \u00b7 NSFW':''}</span></button>`).join('')||'<p>No saved photos yet.</p>'}</div>`);
  for(const b of $('dialog-body').querySelectorAll('[data-reference]'))b.onclick=async()=>{
   const r=await fetch(rawMediaUrl(images[+b.dataset.reference].url));
   if(!r.ok)throw Error('Photo could not be loaded');
   await uploadPortrait(await r.blob());$('product-dialog').close();await reload();
  };
 };
 if($('pdrop'))$('pdrop').onclick=async()=>{
  try{await api('/portrait',{method:'DELETE'});await reload();}
  catch(e){msg.innerHTML=`<span class="bad">${esc(e.message)}</span>`;}
 };
 if($('pdesc'))$('pdesc').onclick=async()=>{
  msg.textContent='looking\u2026';$('pdesc').disabled=true;
  try{
   const d=await api('/portrait/describe',{method:'POST',body:'{}'});
   msg.textContent='';
   $('pprop').innerHTML=`<p class="dim">Proposed, not saved. Read it, edit anything wrong, then keep it \u2014 or discard it and nothing happens.</p>
     <textarea id="pbody">${esc(d.body)}</textarea>
     <div class="actions"><button class="act" id="pkeep">Save as their appearance</button>
     <button class="quiet" id="pdiscard">Discard</button><span class="dim small" id="pkmsg"></span></div>`;
   $('pdiscard').onclick=()=>{$('pprop').innerHTML='';};
   $('pkeep').onclick=async()=>{
    try{
     await api('/identity/appearance',{method:'POST',body:JSON.stringify({body:$('pbody').value})});
     clearEditorDirty('identity-appearance');
     notice('Appearance saved to the SOUL. Read it on Identity.');
     await reload();
    }catch(e){$('pkmsg').innerHTML=`<span class="bad">${esc(e.message)}</span>`;}
   };
  }catch(e){msg.innerHTML=`<span class="bad">${esc(e.message)}</span>`;}
  finally{if($('pdesc'))$('pdesc').disabled=false;}
 };
}

workspaceHandlers['image-studio']=async()=>{
 const [d,portrait]=await Promise.all([api('/images'),api('/portrait')]);
 let settings=d.settings,revision=d.revision,presetIndex=0;const defaults=d.effective;
 const routeValues={...settings.routes};let defaultId=settings.default_preset||'';
 let activeCategory='portrait';

 $('image-studio').innerHTML=`
 <div class="home-title" style="margin-bottom:12px">
  <div>
   <h2 class="page-title">Image Studio</h2>
   <p class="intro">One identity, specialized workflows. Craft character photos, configure image type lanes, or design modular ComfyUI recipes.</p>
  </div>
  <div class="actions">
   <button class="quiet" id="image-back-identity">← Identity</button>
   <button class="quiet" id="image-template-download">Download template</button>
   <button class="quiet" id="image-import">Import preset</button>
   <input id="image-import-file" type="file" accept=".json,application/json" hidden>
   <button class="quiet" id="image-install-comfy">Install ComfyUI</button>
   <button class="quiet" id="image-start-comfy">Start ComfyUI</button>
   <label class="inline-label switch-container"><input type="checkbox" id="comfy-cpu"><span class="switch-slider"></span><span class="switch-label">CPU mode</span></label>
  </div>
 </div>

 <nav class="studio-subnav" id="image-subnav" aria-label="Image studio navigation">
  <button type="button" class="studio-subnav-btn is-active" data-view="compose">📸 Photo Composer</button>
  <button type="button" class="studio-subnav-btn" data-view="assignments">🔀 Assigned Workflows & Lanes</button>
  <button type="button" class="studio-subnav-btn" data-view="creator">⚡ ComfyUI Lite Workflow Creator</button>
  <button type="button" class="studio-subnav-btn" data-view="presets">⚙️ Presets & Library</button>
  <button type="button" class="studio-subnav-btn" data-view="identity">👤 Identity Prompt</button>
 </nav>

 <!-- VIEW 1: Photo Composer -->
 <div id="view-compose" class="studio-view-pane">
  <div class="composer-lane-bar">
   <span class="dim small" style="text-transform:uppercase;letter-spacing:.05em;font-weight:600">Lane:</span>
   <div class="lane-pills" id="composer-lane-pills">
    ${d.categories.map(cat=>`<button type="button" class="lane-pill ${cat===activeCategory?'is-selected':''}" data-lane="${cat}">${formLabel(cat)}</button>`).join('')}
   </div>
  </div>

  <div class="composer-route-info">
   <div class="composer-active-route">
    <span class="sparkle-icon">⚡</span>
    <span>Active lane: <strong id="composer-lane-label">${formLabel(activeCategory)}</strong> · <span id="composer-assigned-name" class="pill-badge">Loading…</span></span>
    <button type="button" class="link-btn" id="composer-goto-assignments">Change assignment ↗</button>
   </div>
   <div class="composer-override-box">
    <label class="dim small">Workflow override:
     <select id="image-test-preset" class="mini-select"></select>
    </label>
   </div>
  </div>
  <select id="image-test-category" hidden>${options(d.categories.map(v=>[v,formLabel(v)]),activeCategory)}</select>

  <div class="studio-composer-grid">
   <!-- Left: Prompt Director -->
   <div class="composer-deck">
    <div class="composer-prompt-box">
     <div class="composer-box-header">
      <label for="prompt-part-scene" class="composer-box-label">
       <span class="sparkle-icon">✨</span>
       <span>Standard Category Test Prompt</span>
       <span class="dim small">— Verified workflow benchmark scene</span>
      </label>
      <button type="button" class="link-btn" id="reset-scene-btn">Reset to lane default</button>
     </div>
     <textarea id="prompt-part-scene" data-shot-part="scene" class="composer-textarea" rows="3" readonly style="background:color-mix(in srgb,var(--ink) 3%,transparent);cursor:default"></textarea>
     <div class="inspiration-tags-strip" style="margin-top:10px">
      <span class="dim small">Benchmark scenes:</span>
      <div id="lane-test-chips" style="display:inline-flex;gap:6px;flex-wrap:wrap"></div>
     </div>
    </div>

    <div class="card" style="background:color-mix(in srgb,var(--accent) 5%,transparent);border:1px solid color-mix(in srgb,var(--accent) 20%,transparent);padding:14px;border-radius:10px;margin-top:14px">
      <div style="display:flex;align-items:flex-start;gap:10px">
        <span style="font-size:1.2rem">🛡️</span>
        <div>
          <strong style="color:var(--accent);font-size:13px;display:block">Companion Agency & Realism Policy</strong>
          <p class="dim small" style="margin:4px 0 0;line-height:1.45">Image studio test generations verify model workflows, lighting, and rendering using standard benchmark scenes. Guided generation of intimate or unconsented imagery without companion agency is disabled. Intimate photos are shared authentically through mutual relationship progression.</p>
        </div>
      </div>
    </div>

    <!-- Controls & Action Footer -->
    <div class="composer-footer" style="margin-top:16px">
     <div class="composer-actions" style="width:100%;display:flex;justify-content:flex-end;gap:10px">
      <button type="button" class="quiet-action-btn" id="image-compile">
       <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
       <span>Preview Prompt</span>
      </button>
      <button type="button" class="generate-action-btn" id="image-generate">
       <span>✨ Test Render Lane</span>
      </button>
     </div>
    </div>
   </div>

   <!-- Right: Canvas & Results -->
   <div class="canvas-deck">
    <div class="canvas-frame" id="image-canvas-frame">
     <div id="image-output" style="width:100%">
      <div class="canvas-idle-state">
       <div class="idle-icon-ring">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
       </div>
       <h4 style="margin:0 0 4px;color:var(--ink-2)">Studio Canvas Ready</h4>
       <p class="dim small" style="margin:0">Choose a lane, shape your prompt, and click Generate Photo.</p>
      </div>
     </div>
    </div>
    <div id="image-prompt-result" class="prompt-inspector-box" hidden></div>
   </div>
  </div>
 </div>

 <!-- VIEW 2: Assigned Workflows & Lanes (Dedicated Routing Deck) -->
 <div id="view-assignments" class="studio-view-pane" hidden>
  <div class="card lanes-dashboard">
   <div class="lanes-header">
    <div>
     <h3 style="margin:0 0 4px">Workflow Assignments & Fallbacks</h3>
     <p class="dim" style="margin:0">Assign which workflow generates each image type. Change your mappings anytime without creating a new workflow.</p>
    </div>
    <div class="actions">
     <button class="act" id="save-assignments-btn">Save lane assignments</button>
     <button class="quiet" id="assignments-goto-creator">+ Build new workflow</button>
    </div>
   </div>

   <!-- Global Fallback Card -->
   <div class="fallback-hero-card">
    <div class="fallback-hero-icon">🌟</div>
    <div class="fallback-hero-body">
     <h4>Global Fallback Workflow</h4>
     <p class="dim small">Runs whenever an image request has no specific lane assigned or the assigned preset is unavailable.</p>
     <label class="fallback-select-label">
      <select id="image-default-preset" class="prominent-select"></select>
     </label>
    </div>
   </div>

   <h4 style="margin:20px 0 10px;font-size:15px;display:flex;align-items:center;gap:8px">
    <span>Image Type Lanes</span>
    <span class="dim small">(${d.categories.length} lanes)</span>
   </h4>

   <div class="lane-cards-grid" id="image-routes">
    <!-- Rendered dynamically -->
   </div>
  </div>
 </div>

 <!-- VIEW 3: ComfyUI Lite Workflow Creator -->
 <div id="view-creator" class="studio-view-pane" hidden>
  <div id="workflow-creator-root"></div>
 </div>

 <!-- VIEW 4: Presets & Library -->
 <div id="view-presets" class="studio-view-pane" hidden>
  <details class="card" style="margin-bottom:16px"><summary>Where to get image models</summary><p>Browse <a href="https://civitai.com/models" target="_blank" rel="noopener">Civitai</a> for checkpoints, LoRAs, example images, and their recommended settings, or <a href="https://huggingface.co/models?pipeline_tag=text-to-image" target="_blank" rel="noopener">Hugging Face</a> for publisher model weights. Match the checkpoint, LoRA, and workflow family (for example SDXL); different families are not interchangeable.</p><p>Put checkpoint files in <code>companion-engines/comfyui/models/checkpoints</code>, LoRAs in <code>models/loras</code>, and VAEs in <code>models/vae</code> beneath the selected Hermes installation. Prefer safetensors when offered. Downloading a checkpoint does not install custom workflow nodes.</p></details>
  <div class="card">
   <div class="actions" style="justify-content:space-between">
    <h2>Preset & Provider Library</h2>
    <div class="actions">
     <button class="quiet" id="add-comfy-preset">+ ComfyUI workflow</button>
     <button class="quiet" id="add-cloud-preset">+ Image API</button>
     <button class="quiet" id="add-hermes-preset">+ Hermes provider</button>
    </div>
   </div>
   <p class="dim small">Connected Hermes providers appear here automatically, including OAuth providers. ${esc(d.provider_warning||'')}</p>
   <label style="margin:14px 0 10px;display:block">Select preset to edit
    <select id="image-preset-select" style="margin-top:4px"></select>
   </label>
   <div id="image-preset-editor"></div>
  </div>
  <div class="actions" style="margin-top:14px">
   <button class="act" id="save-image-settings">Save all image settings</button>
  </div>
 </div>

 <!-- VIEW 5: Identity & Appearance -->
 <div id="view-identity" class="studio-view-pane" hidden>
  <div class="card">
   <h2>Reference portrait ${portrait.stored?'<span class="pill">stored</span>':''}</h2>
   <div class="portrait-row">
    ${portrait.stored?`<img class="portrait-thumb" src="${mediaUrl('/media/portrait?t='+Date.now())}" alt="Reference portrait">`:'<div class="portrait-thumb portrait-empty">No photo</div>'}
    <div>
     <p class="dim">One photograph, kept in the vault, passed to the providers that accept a reference.
      Describing it asks a model to read the face and propose an appearance section \u2014 that is the only
      thing here that calls a model, and it writes nothing by itself.</p>
     <div class="actions">
      <label class="quiet" style="cursor:pointer">${portrait.stored?'Replace it':'Choose a photo'}<input id="pfile" type="file" accept="image/png,image/jpeg,image/webp" hidden></label>
      <button class="quiet" id="palbum">Pick from your photos</button>
      ${portrait.stored?'<button class="quiet" id="pdesc">Describe this face</button><button class="quiet" id="pdrop">Forget it</button>':''}
      <span class="dim small" id="pmsg"></span>
     </div>
     <div id="pprop"></div>
    </div>
   </div>
  </div>
  <div class="card">
   <h2>Identity sent to the image provider</h2>
   <p class="dim">The appearance from SOUL is used unless you save a studio override. This override is also used by the companion’s portrait prompt helper.</p>
   <label class="inline-label switch-container" style="margin-bottom:12px">
    <input id="image-follow-soul" type="checkbox" ${settings.identity_override===null?'checked':''}>
    <span class="switch-slider"></span>
    <span class="switch-label">Follow the appearance in SOUL</span>
   </label>
   <textarea id="image-identity" aria-label="Image identity prompt" class="composer-textarea">${esc(d.identity)}</textarea>
   <details style="margin-top:12px"><summary>Current SOUL appearance</summary><pre style="white-space:pre-wrap;background:var(--bg);padding:12px;border-radius:8px">${esc(d.appearance||'No appearance section yet. Add one in Identity.')}</pre></details>
   ${PROFILE!=='default'?`<label class="inline-label switch-container" style="margin-top:12px"><input id="image-inherit" type="checkbox" ${settings.inherit?'checked':''}><span class="switch-slider"></span><span class="switch-label">Inherit image settings from the installation’s default profile</span></label>`:''}
   <div class="actions" style="margin-top:14px">
    <button class="act" id="save-identity-settings">Save identity settings</button>
   </div>
  </div>
 </div>`;

 // Subnav Switching
 const showStudioView=(viewName)=>{
  imageStudioView=viewName;
  for(const btn of $('image-subnav').querySelectorAll('.studio-subnav-btn')){btn.classList.toggle('is-active',btn.dataset.view===viewName);}
  for(const id of ['view-compose','view-assignments','view-creator','view-presets','view-identity']){const el=$(id);if(el)el.hidden=id!==('view-'+viewName);}
 };
 showStudioView(imageStudioView);
 for(const btn of $('image-subnav').querySelectorAll('.studio-subnav-btn')){btn.onclick=()=>showStudioView(btn.dataset.view);}
 $('composer-goto-assignments').onclick=()=>showStudioView('assignments');
 $('assignments-goto-creator').onclick=()=>showStudioView('creator');
 $('image-back-identity').onclick=()=>showTab('identity');
 wirePortrait();
 $('image-follow-soul').onchange=()=>{$('image-identity').disabled=$('image-follow-soul').checked;};
 $('image-follow-soul').onchange();

 function readPreset(){
  const p=settings.presets[presetIndex];if(!p||!$('preset-name'))return;
  p.name=$('preset-name').value;p.category=$('preset-category').value;p.endpoint=$('preset-endpoint')?.value||'';p.include_identity=$('preset-include-identity')?.checked??true;
  p.parts={...p.parts};for(const input of $('image-preset-editor').querySelectorAll('[data-preset-part]'))p.parts[input.dataset.presetPart]=input.value;
  p.negative=$('preset-negative')?.value||'';for(const k of ['width','height','steps','cfg','seed','denoise'])if($('preset-'+k))p[k]=Number($('preset-'+k).value);
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
  const rows=settings.presets.map(p=>[p.id,p.name]);
  const allRows=[['', 'Choose a workflow'], ...rows];
  $('image-preset-select').innerHTML=options(settings.presets.map((p,i)=>[String(i),p.name]),String(presetIndex));
  $('image-test-preset').innerHTML=options([['','Use lane assigned workflow'],...(settings.inherit?d.installation_presets.map(p=>[p.id,p.name]):rows)],'');
  $('image-default-preset').innerHTML=options(allRows,defaultId);
  $('image-default-preset').onchange=e=>{defaultId=e.target.value;menus();updateActiveLaneBadge();};

  const defPreset=settings.presets.find(p=>p.id===defaultId);
  const fallbackLabel=defPreset?defPreset.name:'No fallback chosen';

  $('image-routes').innerHTML=d.categories.map(k=>{
   const assigned=routeValues[k]||'';
   const isCustom=Boolean(assigned);
   return `
   <div class="lane-card">
    <div class="lane-card-top">
     <div>
      <h4 class="lane-title">${formLabel(k)}</h4>
      <p class="dim small" style="margin:2px 0 0">${k==='scenery'?'Environments & landscapes (excludes companion identity)':k==='portrait'?'Character portraits and closeups':k==='anime'?'Stylized anime & illustration':k==='realistic'?'Photorealistic captures':'Everyday companion moments'}</p>
     </div>
     <span class="lane-badge ${isCustom?'lane-portrait':'dim'}" style="font-size:10px">${isCustom?'Custom':'Fallback'}</span>
    </div>
    <select class="lane-select" data-image-route="${k}">
     ${options([['','🌟 Use fallback ('+fallbackLabel+')'],...rows],assigned)}
    </select>
   </div>`;
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

 function drawPreset(){
  menus();const p=settings.presets[presetIndex];
  if(!p){$('image-preset-editor').innerHTML='<p class="dim">Add a named workflow or API provider to begin. Each can specialize in a different image style.</p>';return;}
  $('image-preset-editor').innerHTML=`<div class="form-grid"><label>Name<input id="preset-name" value="${esc(p.name)}" placeholder="Comfy – PlantMilk"></label><label>Image type<select id="preset-category">${options(d.categories.map(v=>[v,formLabel(v)]),p.category)}</select></label>${p.provider!=='hermes'?`<label>Endpoint<input id="preset-endpoint" type="url" value="${esc(p.endpoint)}"></label>`:''}${p.provider==='hermes'?`<p class="dim">Hermes provider: ${esc(p.hermes_provider||'Follow current Hermes default')} · ${esc(p.model||'Provider default')}${p.available===false?' · Reconnect this provider in Hermes settings':''}</p>`:''}${p.provider==='openai'?`<label>Model<input id="preset-model" value="${esc(p.model||'')}" placeholder="Model supported by this API"></label><label>API-key environment variable<input id="preset-key-env" value="${esc(p.api_key_env||'OPENAI_API_KEY')}"></label>`:''}${['width','height','steps','cfg','seed','denoise'].filter(k=>(k!=='denoise'||p.requires_reference)&&p.provider==='comfyui'||(p.provider==='openai'&&['width','height'].includes(k))).map(k=>`<label>${formLabel(k)}${k==='seed'?' (−1 random)':''}<input id="preset-${k}" type="number" step="${['cfg','denoise'].includes(k)?'.05':'1'}" value="${p[k]??({width:832,height:1216,steps:18,cfg:5,seed:-1,denoise:.35})[k]}"></label>`).join('')}</div><details open><summary>Structured prompt · PlantMilk-style separation</summary><label class="inline-label switch-container" style="margin:8px 0"><input id="preset-include-identity" type="checkbox" ${p.include_identity!==false?'checked':''}><span class="switch-slider"></span><span class="switch-label">Include the companion’s identity (turn off for scenery)</span></label><div class="form-grid">${d.parts.map(k=>`<label>${formLabel(k)} ${k==='identity'?'<span class="dim small">Blank follows companion identity; use this for model-specific identity tags</span>':''}<textarea data-preset-part="${k}">${esc(p.parts?.[k]||'')}</textarea></label>`).join('')}</div><label ${p.provider!=='comfyui'?'hidden':''}>Negative prompt<textarea id="preset-negative">${esc(p.negative||'')}</textarea></label></details>${p.provider==='comfyui'?`<div class="actions"><button class="quiet" id="check-comfy">Test connection & list models</button><button class="quiet" id="add-workflow-lora">Add LoRA node</button><button class="quiet" id="derive-img2img">Create image-to-image copy</button></div><div id="comfy-models"></div><details><summary>Workflow nodes & control mappings</summary><p class="dim">Use ComfyUI’s Export (API) format. Mappings are [node ID, input name].</p><label>API workflow<textarea id="preset-workflow" class="code-editor">${esc(JSON.stringify(p.workflow,null,2))}</textarea></label><label>Input mappings<textarea id="preset-mappings" class="code-editor">${esc(JSON.stringify(p.mappings,null,2))}</textarea></label></details>`:''}<div class="actions" style="margin-top:14px"><button class="quiet" id="export-image-preset">Download this preset</button><button class="quiet" id="duplicate-image-preset">Duplicate preset</button><button class="quiet" id="remove-image-preset">Remove preset</button></div>`;
  $('preset-name').onchange=()=>{readPreset();menus();};
  $('export-image-preset').onclick=()=>{readPreset();downloadJSON(p.id+'.json',p);};
  $('duplicate-image-preset').onclick=()=>{readPreset();const copy=structuredClone(p);copy.id='preset-'+presetSuffix();copy.name+=' copy';settings.presets.push(copy);presetIndex=settings.presets.length-1;drawPreset();};
  $('remove-image-preset').onclick=()=>{settings.presets.splice(presetIndex,1);for(const k in routeValues)if(routeValues[k]===p.id)delete routeValues[k];if(defaultId===p.id)defaultId='';presetIndex=0;drawPreset();};
  if($('derive-img2img'))$('derive-img2img').onclick=async()=>{const copy=await post('/images/img2img',{preset:p.id,denoise:.35});copy.id='img2img-'+presetSuffix();settings.presets.push(copy);presetIndex=settings.presets.length-1;drawPreset();notice('Created from the saved recipe. Save this copy, then preview it with your reference portrait.');};
  if($('check-comfy'))$('check-comfy').onclick=async()=>{readPreset();const r=await post('/images/check',{endpoint:p.endpoint});$('comfy-models').innerHTML=`<p class="status-good">Connected · ${r.nodes.length} node types available</p><div class="form-grid">${Object.entries(p.workflow).filter(([id,n])=>['CheckpointLoaderSimple','LoraLoader','UpscaleModelLoader'].includes(n.class_type)).map(([id,n])=>Object.entries(n.inputs).filter(([k,v])=>!Array.isArray(v)).map(([k,v])=>`<label>${esc(n.class_type+' '+id+' · '+k)}${r.models[k]?`<select data-node-id="${id}" data-node-input="${k}">${options([['','Choose installed model'],...r.models[k].map(v=>[v,v])],v)}</select>`:`<input data-node-id="${id}" data-node-input="${k}" type="number" step="0.05" value="${esc(v)}">`}</label>`).join('')).join('')}</div>`;for(const input of $('comfy-models').querySelectorAll('[data-node-id]'))input.onchange=()=>{p.workflow[input.dataset.nodeId].inputs[input.dataset.nodeInput]=input.type==='number'?Number(input.value):input.value;$('preset-workflow').value=JSON.stringify(p.workflow,null,2);};};
  if($('add-workflow-lora'))$('add-workflow-lora').onclick=()=>{readPreset();const checkpoints=Object.entries(p.workflow).filter(([id,n])=>n.class_type==='CheckpointLoaderSimple');if(checkpoints.length!==1)throw Error('Use the workflow editor to connect LoRAs in a multi-checkpoint workflow.');const base=checkpoints[0][0],id=String(Math.max(0,...Object.keys(p.workflow).map(Number).filter(Number.isFinite))+1);for(const node of Object.values(p.workflow))for(const [k,v] of Object.entries(node.inputs))if(Array.isArray(v)&&v[0]===base&&[0,1].includes(v[1]))node.inputs[k]=[id,v[1]];p.workflow[id]={class_type:'LoraLoader',inputs:{model:[base,0],clip:[base,1],lora_name:'CHOOSE_YOUR_LORA.safetensors',strength_model:1,strength_clip:1}};$('preset-workflow').value=JSON.stringify(p.workflow,null,2);notice('LoRA added. Test the connection to choose an installed LoRA and set its strengths.');};
 }

 drawPreset();
 $('image-preset-select').onchange=e=>{readPreset();presetIndex=Number(e.target.value);drawPreset();};
 $('add-comfy-preset').onclick=async()=>{readPreset();const p=await api('/images/modular-template');p.id='comfy-'+presetSuffix();settings.presets.push(p);presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 $('add-cloud-preset').onclick=()=>{readPreset();settings.presets.push({id:'api-'+presetSuffix(),name:'Image API',provider:'openai',category:'portrait',endpoint:'https://api.openai.com/v1',api_key_env:'OPENAI_API_KEY',model:'',width:1024,height:1024,parts:{},negative:''});presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 $('add-hermes-preset').onclick=()=>{readPreset();settings.presets.push({id:'hermes-'+presetSuffix(),name:'Hermes image provider',provider:'hermes',category:'portrait',endpoint:'',parts:{},negative:''});presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};
 $('image-template-download').onclick=async()=>downloadJSON('comfy-structured-sdxl-template.json',await api('/images/modular-template'));
 $('image-import').onclick=()=>$('image-import-file').click();
 $('image-import-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>4000000)throw Error('Workflow must be under 4 MB');readPreset();const imported=JSON.parse(await file.text());if(imported.nodes)throw Error('This is a visual-editor workflow. Export it as API format from ComfyUI, then import that file.');let p;if(imported.provider)p=imported;else{p=await api('/images/template');p.workflow=imported;p.mappings={};p.name=file.name.replace(/\.json$/,'');}p.id='import-'+presetSuffix();settings.presets.push(p);presetIndex=settings.presets.length-1;drawPreset();showStudioView('presets');};

 const saveSettings=async(msg='Image settings saved for this companion.')=>{
  readPreset();
  settings.identity_override=$('image-follow-soul').checked?null:$('image-identity').value;
  settings.inherit=$('image-inherit')?.checked||false;
  settings.default_preset=defaultId;
  settings.routes=routeValues;
  const r=await post('/images',{settings,revision});
  revision=r.revision;
  menus();
  notice(msg);
 };

 $('save-image-settings').onclick=()=>saveSettings();
 $('save-assignments-btn').onclick=()=>saveSettings('Lane assignments and fallback saved!');
 $('save-identity-settings').onclick=()=>saveSettings('Identity prompt saved!');
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

 const renderLaneBenchmark = () => {
  const scenes = categoryTestPrompts[activeCategory] || categoryTestPrompts.portrait;
  const chipsHost = $('lane-test-chips');
  if(chipsHost){
   chipsHost.innerHTML = scenes.map(([label, text])=>`<button type="button" class="tag-chip" data-test-scene="${esc(text)}">${esc(label)}</button>`).join('');
   for(const chip of chipsHost.querySelectorAll('[data-test-scene]')){
    chip.onclick = () => {
     $('prompt-part-scene').value = chip.dataset.testScene;
    };
   }
  }
  $('prompt-part-scene').value = scenes[0][1];
 };

 renderLaneBenchmark();

 // Lane Pill Switching in Composer
 for(const pill of $('composer-lane-pills').querySelectorAll('.lane-pill')){
  pill.onclick=()=>{
   for(const p of $('composer-lane-pills').querySelectorAll('.lane-pill'))p.classList.remove('is-selected');
   pill.classList.add('is-selected');
   activeCategory=pill.dataset.lane;
   $('image-test-category').value=activeCategory;
   renderLaneBenchmark();
   updateActiveLaneBadge();
  };
 }

 $('reset-scene-btn').onclick=()=>renderLaneBenchmark();

 const shot=()=>({
  preset:$('image-test-preset').value,
  category:activeCategory,
  parts:{scene:$('prompt-part-scene').value.trim()}
 });

 $('image-compile').onclick=async()=>{
  const r=await post('/images/prompt',shot());
  const box=$('image-prompt-result');
  box.hidden=false;
  box.innerHTML=`
   <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <h4 style="margin:0">Compiled Prompt · ${esc(r.preset.name)}</h4>
    <button type="button" class="link-btn" id="copy-compiled-prompt">Copy</button>
   </div>
   <pre>${esc(r.prompt)}</pre>
   <p style="margin:6px 0 0"><strong>Negative:</strong> ${esc(r.negative||'None')}</p>
   <p class="dim small" style="margin:4px 0 0">Seed: ${r.seed} · Reference: ${r.reference_image?(r.preset.provider==='hermes'?'Sent to Hermes provider':r.preset.mappings?.reference_image?'Mapped to workflow':'Not mapped; text-only generation'):'None'}</p>`;
  $('copy-compiled-prompt').onclick=()=>{navigator.clipboard.writeText(r.prompt);notice('Prompt copied to clipboard!');};
 };

 $('image-generate').onclick=()=>{
  const frame=$('image-output');
  frame.innerHTML=`<div class="canvas-idle-state"><div class="idle-icon-ring" style="animation:spin 2s linear infinite">✨</div><h4 style="color:#fff">Synthesizing photo…</h4><p class="dim small">Sending composition to ${esc(routeValues[activeCategory]||defaultId||'provider')}...</p></div>`;
  return action('/images/generate',shot(),r=>{
   frame.innerHTML=`
    <div class="canvas-result-card">
     <img class="canvas-result-img ${r.blur?'concealed-media':''}" ${r.blur?'data-concealed title="Click to reveal"':''} alt="Generated companion image" src="${mediaUrl(r.image)}">
     <div class="canvas-action-dock">
      <div style="display:flex;align-items:center;gap:6px">
       <span class="pill-badge" style="font-size:11px">${esc(r.provider)}</span>
       <span class="dim small">Seed: ${r.seed}</span>
      </div>
      <div class="actions" style="margin:0">
       <a class="act" href="${mediaUrl(r.image)}" download style="padding:5px 12px;font-size:12px">Download photo</a>
      </div>
     </div>
    </div>`;
  });
 };

 await renderWorkflowCreator($('workflow-creator-root'),(p,lane)=>{
  readPreset();
  settings.presets.push(p);
  if(lane){
   if(lane==='default')defaultId=p.id;
   else routeValues[lane]=p.id;
  }
  presetIndex=settings.presets.length-1;
  drawPreset();
  showStudioView('assignments');
  notice(`Workflow “${p.name}” saved and assigned to ${lane||'default'}!`);
 });
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
      ${diskModels.map(m=>`
        <div class="card" style="margin-bottom:0;display:flex;flex-direction:column;justify-content:space-between;border-color:${m.active?'var(--accent)':'var(--edge)'}">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span class="pill">${esc(m.family)}</span>
              <span class="small dim">${m.size_gb} GB</span>
            </div>
            <h3 style="font-size:14px;word-break:break-all;margin:6px 0 10px">${esc(m.name)}</h3>
            ${m.mmproj ? '<p class="small" style="color:var(--accent);margin:0 0 8px">👁 Multimodal Vision mmproj included</p>' : ''}
          </div>
          <div style="margin-top:14px;display:flex;flex-direction:column;gap:6px">
            ${m.active
              ? '<span class="pill status-good" style="width:100%;text-align:center;display:block">● Active on GPU</span>'
              : `<button type="button" class="act small" style="width:100%" data-quick-switch="${esc(m.path)}" data-quick-alias="${esc(m.alias)}">⚡ Activate & Offload</button>`}
            <button type="button" class="quiet small" style="width:100%" data-quick-assign="${esc(m.alias||m.name)}">Assign to ${esc(companionName)}</button>
          </div>
        </div>
      `).join('')}
    </div>`:'<p class="dim">No GGUF models discovered in storage. Place <code>.gguf</code> files into <code>/mnt/nvme2/models/</code> or <code>~/models/</code> and refresh.</p>'}
  </div>`;

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
                <option value="131072" selected>131,072 tokens (128k - Recommended)</option>
                <option value="65536">65,536 tokens (64k)</option>
                <option value="32768">32,768 tokens (32k)</option>
                <option value="16384">16,384 tokens (16k)</option>
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
