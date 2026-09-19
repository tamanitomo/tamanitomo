/* One leave guard for persisted editors, including refresh and browser close. */
const dirtyEditors=new Set();
const trackedEditorFields='#note-text, #full-soul, #feelings-controls input, #feelings-controls select, #feelings-controls textarea, #companion-edit-form input, #companion-edit-form select, #companion-edit-form textarea, #settings-panel input:not([type=search]), #settings-panel select, #settings-panel textarea, #identity textarea, #voice-studio-form input, #voice-studio-form select, #voice-studio-form textarea';
function editorScope(element){
  if(element.closest('#product-dialog'))return 'dialog';
  if(element.closest('#feelings-settings-form'))return 'relationship-settings';
  if(element.closest('#feelings-experience-form'))return 'relationship-experience';
  if(element.closest('#identity'))return 'identity-'+(element.dataset.section||'appearance');
  // Related settings share a page, but each section owns its save scope.
  if(element.closest('#settings-panel')){
    const job=element.closest('.job-row[data-job-id]');
    return job?'settings-main-job-'+job.dataset.jobId:'settings-main-'+(element.closest('[data-settings-section]')?.dataset.settingsSection||'general');
  }
  return element.closest('section')?.id;
}
function recordEditorChange(event){
  if(!event.target.matches(trackedEditorFields)||['job-filter','hermes-existing-path'].includes(event.target.id))return;
  const scope=editorScope(event.target);if(scope)dirtyEditors.add(scope);updateEditorStatus();
}
document.addEventListener('input',recordEditorChange);
document.addEventListener('change',recordEditorChange);
function hasEditorChanges(scope){
  // Also compare the rendered note value. Browser autofill, accessibility tools,
  // and programmatic input can change a field without dispatching input events.
  const note=typeof $==='function'?$('note-text'):null;
  if((!scope||scope==='vault')&&note&&note.value!==note.defaultValue)return true;
  if(!scope)return dirtyEditors.size>0||(typeof vaultDirty!=='undefined'&&vaultDirty);
  return [...dirtyEditors].some(key=>key===scope||key.startsWith(scope+'-'))||scope==='vault'&&typeof vaultDirty!=='undefined'&&vaultDirty;
}
function updateEditorStatus(){const status=typeof $==='function'?$('editor-status'):null;if(status)status.hidden=!hasEditorChanges();}
function clearEditorDirty(scope){
  dirtyEditors.delete(scope);
  if(scope==='vault'){
    if(typeof vaultDirty!=='undefined')vaultDirty=false;
    const note=typeof $==='function'?$('note-text'):null;
    if(note)note.defaultValue=note.value;
  }
  updateEditorStatus();
}
function askToDiscard(){
  return new Promise(resolve=>{
    const prompt=document.createElement('dialog');prompt.className='editor-leave-dialog';
    prompt.setAttribute('aria-label','Unsaved changes');
    prompt.innerHTML='<h2>Keep your unsaved changes?</h2><p>Stay here to save your work, or discard these edits and continue.</p><div class="actions"><button class="act" data-stay autofocus>Stay and keep editing</button><button class="quiet" data-discard>Discard changes and continue</button></div>';
    const finish=discard=>{prompt.close();prompt.remove();resolve(discard);};
    prompt.querySelector('[data-stay]').onclick=()=>finish(false);
    prompt.querySelector('[data-discard]').onclick=()=>finish(true);
    prompt.addEventListener('cancel',event=>{event.preventDefault();finish(false);});
    document.body.append(prompt);prompt.showModal();
  });
}
async function confirmEditorLeave(scope){
  if(!hasEditorChanges(scope))return true;
  if(!await askToDiscard())return false;
  for(const key of [...dirtyEditors])if(key===scope||key.startsWith(scope+'-'))clearEditorDirty(key);
  if(scope==='vault')clearEditorDirty(scope);
  return true;
}
window.addEventListener('beforeunload',event=>{
  if(hasEditorChanges()){event.preventDefault();event.returnValue='';}
});
