/* Push-to-talk; microphone tracks stop before any transcription or playback. */
let browserVoice=null,voiceReplyRequested=false;
function voiceControlsBusy(busy){if($('send-message'))$('send-message').disabled=busy;if($('chat-message'))$('chat-message').readOnly=busy;}
function stopBrowserVoice(){if(browserVoice){browserVoice.cancelled=true;browserVoice.recorder?.state==='recording'&&browserVoice.recorder.stop();browserVoice.stream?.getTracks().forEach(t=>t.stop());browserVoice.audio?.pause();clearTimeout(browserVoice.timer);}voiceReplyRequested=false;if(!activeOperation)voiceControlsBusy(false);}
window.addEventListener('pagehide',stopBrowserVoice);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopBrowserVoice();});
function mountBrowserVoice(){
 const host=$('chat-form');if(!host)return;
 const box=document.createElement('div');box.className='voice-chat-panel';box.innerHTML='<div class="actions"><button type="button" class="quiet" id="voice-record">Talk</button><button type="button" class="quiet" id="voice-cancel" hidden>Cancel recording</button><button type="button" class="quiet" id="voice-stop">Stop playback</button><span id="voice-status" role="status">Push-to-talk · recording stays off until you press Talk</span></div><audio id="voice-reply" controls hidden></audio>';
 host.before(box);const status=$('voice-status');
 $('voice-cancel').onclick=()=>{stopBrowserVoice();$('voice-record').textContent='Talk';$('voice-cancel').hidden=true;status.textContent='Recording discarded. Microphone off.';};
 $('voice-stop').onclick=()=>{stopBrowserVoice();$('voice-record').textContent='Talk';$('voice-cancel').hidden=true;status.textContent='Stopped. A submitted chat turn may still finish.';};
 $('voice-record').onclick=async()=>{
  if(browserVoice?.recorder?.state==='recording'){browserVoice.recorder.stop();return;}
  if(activeOperation||$('send-message').disabled)throw Error('Wait for the current turn to finish.');
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Voice needs HTTPS or localhost and a browser with microphone recording support.');
  stopBrowserVoice();const state={cancelled:false,chunks:[]};browserVoice=state;
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
   if(state.cancelled||current!=='chat'){stream.getTracks().forEach(t=>t.stop());return;}
   voiceControlsBusy(true);state.stream=stream;const mime=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
   state.recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);
   state.recorder.ondataavailable=e=>{if(e.data.size)state.chunks.push(e.data);};
   state.recorder.onstop=async()=>{
    clearTimeout(state.timer);stream.getTracks().forEach(t=>t.stop());if(state.cancelled||current!=='chat')return;
    $('voice-record').disabled=true;$('voice-record').textContent='Talk';$('voice-cancel').hidden=true;status.textContent='Microphone off · transcribing…';
    try{
     const blob=new Blob(state.chunks,{type:state.recorder.mimeType});if(blob.size>12*1024*1024)throw Error('Recording too large. Please use a shorter turn.');
     const response=await fetch(scoped('/api/voice-chat/transcribe'),{method:'POST',headers:{'content-type':blob.type,...(token?{'x-companion-token':token}:{})},body:blob});
     if(!response.ok)throw Error((await response.json()).detail||'Transcription failed');
     const operation=await followOperation(await response.json(),async r=>{if(state.cancelled||current!=='chat'){if(current==='chat')voiceControlsBusy(false);return;}voiceControlsBusy(false);$('chat-message').value=r.transcript;sessionStorage.setItem(chatKey('draft'),r.transcript);voiceReplyRequested=true;$('chat-form').requestSubmit();});
     if(operation.status!=='complete')throw Error(operation.error||'Transcription could not finish. You can type instead.');
    }catch(e){voiceControlsBusy(false);notice(e.message,true);status.textContent='Voice could not finish. You can type instead.';}finally{if($('voice-record'))$('voice-record').disabled=false;}
   };
   state.recorder.onerror=()=>{stopBrowserVoice();status.textContent='Recording failed; microphone off.';};
   state.recorder.start();$('voice-record').textContent='Send recording';$('voice-cancel').hidden=false;status.textContent='● Listening · press Send recording when finished (maximum 90 seconds)';state.timer=setTimeout(()=>{if(state.recorder.state==='recording')state.recorder.stop();},90000);
  }catch(e){stopBrowserVoice();status.textContent='Microphone unavailable. Check site permission or type instead.';throw e;}
 };
}
async function speakBrowserReply(result){
 if(!voiceReplyRequested||current!=='chat')return;voiceReplyRequested=false;
 const state={cancelled:false};browserVoice=state;
 const text=(result.messages||[]).filter(x=>x.role==='assistant').at(-1)?.content||result.response||'';
 if(!text.trim())return;
 const excerpt=text.slice(0,1000);$('voice-status').textContent='Preparing voice…';
 await action('/voice-chat/speak',{text:excerpt},async r=>{
  if(state.cancelled||current!=='chat')return;
  const player=$('voice-reply');state.audio=player;player.src=rawMediaUrl(r.audio);player.hidden=false;
  $('voice-status').textContent=text.length>1000?'Reading the first 1,000 characters; full reply is above.':'Reply ready · microphone off';
  try{await player.play();}catch{$('voice-status').textContent='Press Play to hear the reply.';}
 });
}
