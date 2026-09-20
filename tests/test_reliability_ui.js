// Exercise shipped functions with rejected requests and real URL parsing.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const root=path.join(__dirname,'../kit/app/static');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');
const index=read('index.html'),workspace=read('workspace.js'),settings=read('settings.js');
assert.match(settings,/\{group:'Companion',id:'rhythm',title:'Daily rhythm'/,'daily rhythm belongs to Companion settings');
assert.doesNotMatch(settings,/Schedule & usage/,'empty Schedule & usage group is removed');
const stored=new Map(),elements={operation:{innerHTML:'',hidden:true},'dismiss-notice':{}};
const events={},windowEvents={};
let confirmResult=false,rendered=0,posted=0;
const sandbox={URL,console,setTimeout:fn=>fn(),location:{origin:'http://localhost'},
  document:{addEventListener:(name,fn)=>events[name]=fn},window:{addEventListener:(name,fn)=>windowEvents[name]=fn},
  confirm:()=>confirmResult,
  sessionStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value),removeItem:key=>stored.delete(key)},
  $:id=>elements[id],render:async()=>{rendered++;},post:async()=>{posted++;},
  api:async()=>{throw Error('Offline');}};
vm.createContext(sandbox);
vm.runInContext("const INSTALLATION='existing',PROFILE='nova',token='private-token';let current='now',activeOperation=null,chatSession=null,vaultDirty=false;const chatKey=k=>'chat-'+k;",sandbox);
vm.runInContext(index.match(/^const esc=.*$/m)[0],sandbox);
for(const name of ['scoped','rawMediaUrl','mediaUrl'])vm.runInContext(index.match(new RegExp('^function '+name+'.*$','m'))[0],sandbox);
vm.runInContext(read('editing.js'),sandbox);
sandbox.askToDiscard=async()=>confirmResult;
vm.runInContext(workspace.match(/^function inlineMedia.*$/m)[0],sandbox);
vm.runInContext(workspace.slice(workspace.indexOf('const operationKey='),workspace.indexOf('async function navigateProfile')),sandbox);
vm.runInContext(workspace.slice(workspace.indexOf('async function followOperation'),workspace.indexOf('function bindAction')),sandbox);

(async()=>{
  const raw=vm.runInContext("rawMediaUrl('/api/voice-chat/audio?name=sample.wav')",sandbox);
  const params=new URL(raw,'http://localhost').searchParams;
  assert.equal(params.get('token'),'private-token');assert.equal(params.get('profile'),'nova');
  assert.equal(params.get('name'),'sample.wav');assert.equal(params.has('amp;token'),false);
  assert.match(vm.runInContext("mediaUrl('/api/content/file?path=image.png')",sandbox),/&amp;token=/);
  const hidden=vm.runInContext("inlineMedia({kind:'image',url:'/api/content/file?path=image.png',title:'Test',blur:true})",sandbox);
  assert.match(hidden,/^<details class="media-reveal">/);assert.match(hidden,/concealed-media/);
  assert.match(hidden,/Reveal sensitive or unreviewed image/);assert.doesNotMatch(hidden,/<details[^>]* open/);

  await assert.rejects(vm.runInContext("followOperation({id:'nova-op',profile:'nova',label:'Generate image',status:'running',progress:'Working'})",sandbox),/Offline/);
  assert.equal(vm.runInContext('activeOperation',sandbox),null);
  assert.equal(stored.get('operation-existing-nova'),'nova-op');
  sandbox.api=async()=>({id:'nova-op',profile:'nova',label:'Generate image',status:'complete',result:{}});
  await assert.rejects(vm.runInContext("action('/images/generate')",sandbox),/previous action has been checked/);
  assert.equal(posted,0,'reconnecting must not resubmit a mutation');
  assert.equal(stored.has('operation-existing-nova'),false);
  assert.equal(rendered,1);
  await assert.rejects(vm.runInContext("followOperation({id:'other',profile:'rowan',label:'Chat with Rowan',status:'complete',result:{response:'private'}})",sandbox),/another companion/);
  assert.equal(elements.operation.innerHTML.includes('private'),false);

  sandbox.post=async()=>({id:'save-failed',profile:'nova',label:'Save job',status:'failed',error:'Write failed'});
  await assert.rejects(vm.runInContext("action('/jobs/example/edit')",sandbox),/Write failed/);
  assert.equal(stored.has('operation-existing-nova'),false);

  vm.runInContext("current='chat';",sandbox);
  await vm.runInContext("followOperation({id:'chat-done',profile:'nova',label:'Chat with Nova',status:'complete',result:{session:'saved'}})",sandbox);
  assert.equal(elements.operation.hidden,true,'a successful reply must not cover the next Send click');
  await vm.runInContext("followOperation({id:'chat-failed',profile:'nova',label:'Chat with Nova',status:'failed',error:'Provider unavailable'})",sandbox);
  assert.equal(elements.operation.hidden,false,'chat failures remain visible');
  vm.runInContext("current='now';",sandbox);
  await vm.runInContext("followOperation({id:'chat-away',profile:'nova',label:'Chat with Nova',status:'complete',result:{session:'saved'}})",sandbox);
  assert.equal(elements.operation.hidden,false,'completion away from chat still notifies the user');

  events.input({target:{matches:()=>true,closest:selector=>selector==='section'?{id:'vault'}:null}});
  assert.equal(await vm.runInContext("confirmEditorLeave('vault')",sandbox),false);
  assert.equal(vm.runInContext("hasEditorChanges('vault')",sandbox),true);
  let prevented=false;
  windowEvents.beforeunload({preventDefault:()=>prevented=true});assert.equal(prevented,true);
  confirmResult=true;
  assert.equal(await vm.runInContext("confirmEditorLeave('vault')",sandbox),true);
  assert.equal(vm.runInContext('hasEditorChanges()',sandbox),false);
  elements['note-text']={value:'Changed without input events',defaultValue:'Original'};
  confirmResult=false;
  assert.equal(await vm.runInContext("confirmEditorLeave('vault')",sandbox),false);
  assert.equal(elements['note-text'].value,'Changed without input events');
  confirmResult=true;
  assert.equal(await vm.runInContext("confirmEditorLeave('vault')",sandbox),true);
  assert.equal(vm.runInContext("hasEditorChanges('vault')",sandbox),false);
  delete elements['note-text'];
  vm.runInContext("dirtyEditors.add('settings-main');dirtyEditors.add('settings-media');clearEditorDirty('settings-main');",sandbox);
  assert.equal(vm.runInContext("hasEditorChanges('settings')",sandbox),true,'saving contact settings must not mark media edits saved');
  const settingField=id=>({matches:()=>true,closest:selector=>selector==='#settings-panel'?{}:selector==='[data-settings-section]'?{dataset:{settingsSection:id}}:null});
  events.input({target:settingField('contact')});
  events.input({target:settingField('awareness')});
  vm.runInContext("clearEditorDirty('settings-main-contact')",sandbox);
  assert.equal(vm.runInContext("hasEditorChanges('settings-main-awareness')",sandbox),true,'saving one section preserves another section’s unsaved edits');
  confirmResult=false;
  assert.equal(await vm.runInContext("confirmEditorLeave('settings-main')",sandbox),false);
  confirmResult=true;
  assert.equal(await vm.runInContext("confirmEditorLeave('settings-main')",sandbox),true);
  // A server-side transcription failure is a returned terminal operation, not
  // a rejected HTTP request. It must still release all composer controls.
  const voice=read('voice-chat.js');
  vm.runInContext(voice.match(/^function voiceControlsBusy.*$/m)[0],sandbox);
  for(const id of ['send-message','chat-message','voice-record','voice-cancel','voice-stop'])elements[id]={disabled:true,readOnly:true,hidden:false,classList:{add(){},remove(){},toggle(){}}};
  sandbox.clearTimeout=()=>{};sandbox.Blob=Blob;
  sandbox.stream={getTracks:()=>[{stop(){}}]};
  sandbox.state={chunks:[new Uint8Array(32)],recorder:{mimeType:'audio/webm'},cancelled:false};
  sandbox.status={textContent:''};sandbox.notice=()=>{};
  sandbox.fetch=async()=>({ok:true,json:async()=>({id:'voice-failed',profile:'nova',label:'Transcribe voice',status:'failed',error:'No speech recognized'})});
  vm.runInContext("current='chat';",sandbox);
  vm.runInContext(voice.slice(voice.indexOf('state.recorder.onstop=async'),voice.indexOf('state.recorder.onerror=')),sandbox);
  await sandbox.state.recorder.onstop();
  assert.equal(elements['send-message'].disabled,false);
  assert.equal(elements['chat-message'].readOnly,false);
  assert.equal(elements['voice-record'].disabled,false);
  assert.match(sandbox.status.textContent,/You can type instead/);
  // Refresh must cancel capture before replacing its visible controls.
  let stoppedTracks=0,stoppedRecorder=0,pausedAudio=0,replacedControls=0;
  sandbox.recording={cancelled:false,recorder:{state:'recording',stop(){stoppedRecorder++;}},stream:{getTracks:()=>[{stop(){stoppedTracks++;}}]},audio:{pause(){pausedAudio++;}}};
  vm.runInContext('let browserVoice=recording,voiceReplyRequested=true;',sandbox);
  vm.runInContext(voice.match(/^function stopBrowserVoice.*$/m)[0],sandbox);
  sandbox.workspaceHandlers={chat:async()=>{assert.equal(sandbox.recording.cancelled,true);assert.equal(stoppedTracks,1);replacedControls++;}};
  vm.runInContext(index.slice(index.indexOf('async function render(name)'),index.indexOf('async function renderNow()')),sandbox);
  await sandbox.render('chat');
  assert.equal(stoppedRecorder,1);assert.equal(pausedAudio,1);assert.equal(replacedControls,1);
  assert.equal(vm.runInContext('voiceReplyRequested',sandbox),false);

  console.log('Reliability UI regressions passed: media, reconnect, ownership, unsaved edits.');
})().catch(error=>{console.error(error);process.exitCode=1;});

// Editing an interval must preserve an existing profile's staggered phase.
{
  const source=read('settings.js'),context={};vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function scheduleShape('),source.indexOf('/* ------------------------------------------------------------------ panels */'))+'\nglobalThis.schedules={scheduleShape,readSchedule};',context);
  const {scheduleShape,readSchedule}=context.schedules;
  assert.equal(scheduleShape('1,16,31,46 * * * *').mode,'15');
  assert.equal(scheduleShape('20 9 * * 1').mode,'weekly');
  const fieldValues={'[data-schedule-mode]':'15','[data-schedule-time]':'17:20','[data-schedule-day]':'2','[data-field=schedule]':'every 2h'};
  const editor={dataset:{mode:'15',original:'1,16,31,46 * * * *'},querySelector:key=>({value:fieldValues[key]})};
  assert.equal(readSchedule(editor),'1,16,31,46 * * * *');
  fieldValues['[data-schedule-mode]']='weekly';
  assert.equal(readSchedule(editor),'20 17 * * 2');
  fieldValues['[data-schedule-mode]']='custom';
  assert.equal(readSchedule(editor),'every 2h');
}

// Hosted OAuth connections must never retain a custom endpoint.
{
  const source=read('settings.js'),context={};vm.createContext(context);
  vm.runInContext(source.match(/^function providerNeedsURL.*$/m)[0],context);
  assert.equal(context.providerNeedsURL('openai-codex','http://old-server/v1'),false);
  assert.equal(context.providerNeedsURL('custom'),true);
  assert.equal(context.providerNeedsURL('openrouter'),false);
  assert.equal(context.providerNeedsURL('openai','https://my-gateway/v1'),true);
}
