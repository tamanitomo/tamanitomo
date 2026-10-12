/* Push-to-talk; microphone tracks stop before any transcription or playback. */
let browserVoice=null,voiceReplyRequested=false,browserMessageVoice=null;
const browserVoiceOpen=()=>Boolean(window.ChatDock?.isOpen);
function voiceControlsBusy(busy){busy=busy||Boolean(window.ChatDock?.busy||window.ChatDock?.historyLoading);if($('send-message'))$('send-message').disabled=busy;if($('chat-message'))$('chat-message').readOnly=busy;}
function stopBrowserVoice(){if(browserVoice){browserVoice.cancelled=true;browserVoice.recorder?.state==='recording'&&browserVoice.recorder.stop();browserVoice.stream?.getTracks().forEach(t=>t.stop());clearTimeout(browserVoice.timer);browserVoice=null;}stopBrowserMessage();voiceReplyRequested=false;if(!activeOperation&&!window.ChatDock?.busy)voiceControlsBusy(false);}
window.addEventListener('pagehide',stopBrowserVoice);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopBrowserVoice();});
function mountBrowserVoice(){
 const host=$('chat-form');if(!host)return;
 const box=document.createElement('div');box.className='voice-chat-panel';box.innerHTML='<button type="button" class="chat-icon-btn" id="voice-record" title="Record a voice message" aria-label="Record a voice message"></button><button type="button" class="chat-icon-btn is-cancel" id="voice-cancel" hidden title="Discard recording" aria-label="Discard recording"></button><button type="button" class="chat-icon-btn is-stop" id="voice-stop" hidden title="Stop playback" aria-label="Stop playback"></button><span id="voice-status" role="status"></span><audio id="voice-reply" controls hidden aria-label="Message playback"></audio>';
 host.insertBefore(box,$('chat-message'));const status=$('voice-status');
 $('voice-cancel').onclick=()=>{stopBrowserVoice();$('voice-record').classList.remove('is-recording');$('voice-cancel').hidden=true;status.textContent='Recording discarded. Microphone off.';};
 $('voice-stop').onclick=()=>{stopBrowserVoice();$('voice-record').classList.remove('is-recording');$('voice-cancel').hidden=true;status.textContent='Playback stopped.';};
 $('voice-record').onclick=async()=>{
  if(browserVoice?.recorder?.state==='recording'){browserVoice.recorder.stop();return;}
  if(activeOperation||window.ChatDock?.busy||$('send-message').disabled)throw Error('Wait for the current turn to finish.');
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Voice needs HTTPS or localhost and a browser with microphone recording support.');
  stopBrowserVoice();const state={cancelled:false,chunks:[]};browserVoice=state;
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
   if(state.cancelled||!browserVoiceOpen()){stream.getTracks().forEach(t=>t.stop());return;}
   voiceControlsBusy(true);state.stream=stream;const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
   state.recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);
   state.recorder.ondataavailable=e=>{if(e.data.size)state.chunks.push(e.data);};
   state.recorder.onstop=async()=>{
    clearTimeout(state.timer);stream.getTracks().forEach(t=>t.stop());if(state.cancelled||!browserVoiceOpen())return;
    $('voice-record').disabled=true;$('voice-record').classList.remove('is-recording');$('voice-cancel').hidden=true;status.textContent='Microphone off · transcribing…';
    try{
     const blob=new Blob(state.chunks,{type:state.recorder.mimeType});if(blob.size>12*1024*1024)throw Error('Recording too large. Please use a shorter turn.');
     const response=await fetch(scoped('/api/voice-chat/transcribe'),{method:'POST',headers:{'content-type':blob.type,...(token?{'x-tamanitomo-token':token,'x-companion-token':token}:{})},body:blob});
     if(!response.ok)throw Error((await response.json()).detail||'Transcription failed');
     const operation=await followOperation(await response.json(),async r=>{if(state.cancelled||!browserVoiceOpen()){if(browserVoiceOpen())voiceControlsBusy(false);return;}voiceControlsBusy(false);$('chat-message').value=r.transcript;sessionStorage.setItem(chatKey('draft'),r.transcript);voiceReplyRequested=true;$('chat-form').requestSubmit();});
     if(operation.status!=='complete')throw Error(operation.error||'Transcription could not finish. You can type instead.');
    }catch(e){voiceControlsBusy(false);notice(e.message,true);status.textContent='Voice could not finish. You can type instead.';}finally{if($('voice-record'))$('voice-record').disabled=false;}
   };
   state.recorder.onerror=()=>{stopBrowserVoice();status.textContent='Recording failed; microphone off.';};
   state.recorder.start();$('voice-record').classList.add('is-recording');$('voice-cancel').hidden=false;status.textContent='● Listening · press Send recording when finished (maximum 90 seconds)';state.timer=setTimeout(()=>{if(state.recorder.state==='recording')state.recorder.stop();},90000);
  }catch(e){stopBrowserVoice();status.textContent='Microphone unavailable. Check site permission or type instead.';throw e;}
 };
}
async function speakBrowserReply(result){
 if(!voiceReplyRequested||!browserVoiceOpen())return;voiceReplyRequested=false;
 const text=(result.messages||[]).filter(x=>x.role==='assistant').at(-1)?.content||result.response||'';
 await playBrowserMessage(text);
}

/* Reading a saved message never submits a chat turn or opens the microphone.
   Each chunk uses the selected profile's Hermes TTS; only the next chunk is
   synthesized, so Stop also stops further requests. */
function messageSpeechText(value){
 return String(value||'')
  .replace(/<(think|reasoning)>[\s\S]*?(<\/\1>|$)/gi,'')
  .replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)/g,' Code block omitted. ')
  .replace(/^(?:(?: {4}|\t)[^\n]*(?:\n|$))+/gm,' Code block omitted. ')
  .replace(/!\[([^\]]*)\]\([^\n]*?\)/g,(_,alt)=>alt?' Image: '+alt+'. ':' Image omitted. ')
  .replace(/\[([^\]]+)\]\([^\n]*?\)/g,'$1')
  .replace(/\[([^\]]+)\]\[[^\]]*\]/g,'$1')
  .replace(/^\s*\[[^\]]+\]:\s+\S+.*$/gm,'')
  .replace(/<\/?[a-z][^>]*>/gi,' ')
  .replace(/`([^`\n]+)`/g,'$1')
  .replace(/^\s{0,3}(?:#{1,6}\s+|>\s*|[-+*]\s+|\d+[.)]\s+)/gm,'')
  .replace(/^\s*[-*_]{3,}\s*$/gm,'')
  .replace(/(\*\*|__|~~)([^\n]*?)\1/g,'$2')
  .replace(/([*_])([^\n]*?)\1/g,'$2')
  .replace(/&(?:amp|lt|gt|quot|apos|nbsp);/g,entity=>({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&apos;':"'",'&nbsp;':' '})[entity])
  .replace(/\s+/g,' ').trim();
}

function messageSpeechChunks(text,limit=900){
 const characters=Array.from(text),chunks=[];
 while(characters.length){
  let end=Math.min(limit,characters.length);
  if(end<characters.length){
   let boundary=0;
   for(let i=end;i>Math.floor(end/2);i--){
    if(/[.!?。！？]/u.test(characters[i-1])&&(!characters[i]||/\s/u.test(characters[i])||/[。！？]/u.test(characters[i-1]))){boundary=i;break;}
   }
   if(!boundary)for(let i=end;i>Math.floor(end/2);i--)if(/\s/u.test(characters[i-1])){boundary=i;break;}
   if(boundary)end=boundary;
  }
  chunks.push(characters.splice(0,end).join(''));
 }
 return chunks;
}

const browserSpeechScope=()=>INSTALLATION+':'+(PROFILE||'default');
const browserSpeechCurrent=state=>browserMessageVoice===state&&!state.cancelled&&state.scope===browserSpeechScope()&&browserVoiceOpen();
function speechStatus(text){if($('voice-status'))$('voice-status').textContent=text;}
function syncBrowserMessageButton(button,text){
 const playing=Boolean(browserMessageVoice&&browserSpeechCurrent(browserMessageVoice)&&browserMessageVoice.text===messageSpeechText(text));
 button.textContent=playing?'Stop':'Play';
 button.setAttribute('aria-label',playing?'Stop reading this message':'Play this message aloud');
 button.setAttribute('aria-pressed',String(playing));
}
function speechButtonsChanged(){window.dispatchEvent(new Event('message-voice-change'));}

function stopBrowserMessage(){
 const state=browserMessageVoice;
 if(!state)return;
 state.cancelled=true;state.controller.abort();
 clearTimeout(state.pollTimer);state.resumePoll?.();state.finishPlayback?.(false);
 state.player.pause();state.player.removeAttribute('src');state.player.load();state.player.hidden=true;
 browserMessageVoice=null;
 if(state.button)syncBrowserMessageButton(state.button,'');
 if($('voice-stop'))$('voice-stop').hidden=true;
 speechButtonsChanged();
}

async function speechRequest(state,url,options={}){
 if(!browserSpeechCurrent(state))return null;
 const response=await fetch(url,{...options,headers:{'content-type':'application/json',...(token?{'x-tamanitomo-token':token,'x-companion-token':token}:{}),...(options.headers||{})},signal:state.controller.signal});
 if(!browserSpeechCurrent(state))return null;
 const body=await response.json();
 if(!browserSpeechCurrent(state))return null;
 if(!response.ok)throw Error(body.detail||body.error||'Voice request failed');
 return body;
}

async function synthesizeMessageChunk(state,text){
 let operation=await speechRequest(state,state.speakUrl,{method:'POST',body:JSON.stringify({text})});
 while(operation&&browserSpeechCurrent(state)){
  if(operation.profile!==state.profile)throw Error('Voice operation belongs to another companion.');
  if(operation.status==='complete')return operation.result;
  if(operation.status!=='running'||operation.error)throw Error(operation.error||'Speech could not finish.');
  await new Promise(resolve=>{state.resumePoll=resolve;state.pollTimer=setTimeout(resolve,500);});
  state.resumePoll=null;
  if(!browserSpeechCurrent(state))return null;
  const url=new URL(state.operationsUrl,location.origin);
  url.pathname+='/'+encodeURIComponent(operation.id);
  operation=await speechRequest(state,url.pathname+url.search);
 }
 return null;
}

async function playMessageChunk(state,result,index,total){
 if(!browserSpeechCurrent(state))return false;
 if(typeof result?.audio!=='string'||!result.audio.startsWith('/api/voice-chat/audio?'))throw Error('Speech returned an invalid audio URL.');
 const player=state.player;
 const url=new URL(result.audio,location.origin);
 url.searchParams.set('installation',state.installation);url.searchParams.set('profile',state.profile);
 if(token)url.searchParams.set('token',token);
 player.src=url.pathname+url.search;player.hidden=false;
 speechStatus(`Reading message${total>1?' · part '+index+' of '+total:''}. Pause or seek with the player.`);
 let playbackError=null;
 const finished=new Promise(resolve=>{
  const cleanup=()=>{player.removeEventListener('ended',ended);player.removeEventListener('error',failed);state.finishPlayback=null;};
  const ended=()=>{cleanup();resolve(true);};
  const failed=()=>{cleanup();playbackError=Error('Audio playback failed. Try Play again.');resolve(false);};
  state.finishPlayback=completed=>{cleanup();resolve(completed);};
  player.addEventListener('ended',ended);player.addEventListener('error',failed);
 });
 // Browser autoplay rules can require a second gesture after synthesis. Keep
 // the native controls live and wait for the user, instead of skipping a part.
 try{await player.play();}catch(error){
  if(browserSpeechCurrent(state)){
   if(error.name==='NotAllowedError')speechStatus('Press Play in the audio player to hear this message.');
   else{state.finishPlayback?.(false);throw error;}
  }
 }
 const completed=await finished;
 if(playbackError)throw playbackError;
 return completed;
}

async function playBrowserMessage(value,button=null){
 const text=messageSpeechText(value);
 if(!text||!browserVoiceOpen())return;
 if(browserMessageVoice&&browserSpeechCurrent(browserMessageVoice)&&browserMessageVoice.text===text){stopBrowserMessage();speechStatus('Playback stopped.');return;}
 stopBrowserVoice();
 const player=$('voice-reply');if(!player)throw Error('Open chat to play this message.');
 const state={text,button,player,cancelled:false,controller:new AbortController(),scope:browserSpeechScope(),installation:INSTALLATION,profile:PROFILE||'default',speakUrl:scoped('/api/voice-chat/speak'),operationsUrl:scoped('/api/operations')};
 browserMessageVoice=state;
 if(button)syncBrowserMessageButton(button,value);
 if($('voice-stop'))$('voice-stop').hidden=false;
 speechButtonsChanged();
 const chunks=messageSpeechChunks(text);
 try{
  for(let i=0;i<chunks.length&&browserSpeechCurrent(state);i++){
   speechStatus(`Preparing voice${chunks.length>1?' · part '+(i+1)+' of '+chunks.length:''}…`);
   const result=await synthesizeMessageChunk(state,chunks[i]);
   if(!browserSpeechCurrent(state)||!result)return;
   if(!await playMessageChunk(state,result,i+1,chunks.length)||!browserSpeechCurrent(state))return;
  }
  if(browserSpeechCurrent(state))speechStatus('Finished reading the message.');
 }catch(error){
  if(browserSpeechCurrent(state)){speechStatus('Voice unavailable: '+error.message);throw error;}
 }finally{
  if(browserMessageVoice===state)stopBrowserMessage();
 }
}
