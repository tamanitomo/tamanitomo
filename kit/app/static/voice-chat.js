/* Push-to-talk plus explicitly enabled hands-free streaming conversation. */
let browserVoice=null,voiceReplyRequested=false,browserMessageVoice=null;
const browserVoiceOpen=()=>Boolean(window.ChatDock?.isOpen);
function voiceControlsBusy(busy){busy=busy||Boolean(window.ChatDock?.busy||window.ChatDock?.historyLoading);if($('send-message'))$('send-message').disabled=busy;if($('chat-message'))$('chat-message').readOnly=busy;}
function stopBrowserVoice(){stopBrowserRealtimeVoice();if(browserVoice){browserVoice.cancelled=true;browserVoice.recorder?.state==='recording'&&browserVoice.recorder.stop();browserVoice.stream?.getTracks().forEach(t=>t.stop());clearTimeout(browserVoice.timer);browserVoice=null;}stopBrowserMessage();voiceReplyRequested=false;if(!activeOperation&&!window.ChatDock?.busy)voiceControlsBusy(false);}
window.addEventListener('pagehide',stopBrowserVoice);
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopBrowserVoice();});
function mountBrowserVoice(){
 const host=$('chat-form');if(!host)return;
 const box=document.createElement('div');box.className='voice-chat-panel';box.innerHTML='<button type="button" class="voice-conversation" id="voice-conversation" aria-pressed="false" title="Hands-free voice. Use headphones for reliable interruption.">Voice conversation</button><button type="button" class="chat-icon-btn" id="voice-record" title="Record a voice message" aria-label="Record a voice message"></button><button type="button" class="chat-icon-btn is-cancel" id="voice-cancel" hidden title="Discard recording" aria-label="Discard recording"></button><button type="button" class="chat-icon-btn is-stop" id="voice-stop" hidden title="Stop playback" aria-label="Stop playback"></button><span id="voice-status" role="status"></span><audio id="voice-reply" controls hidden aria-label="Message playback"></audio>';
 host.insertBefore(box,$('chat-message'));const status=$('voice-status');
 $('voice-conversation').onclick=()=>startBrowserRealtimeVoice().catch(error=>{speechStatus(error.message);notice(error.message,true);});
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
  .replace(/<(think|thinking|reasoning)>[\s\S]*?(<\/\1>|$)/gi,'')
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


/* Realtime conversation is explicitly opt-in. Microphone PCM stays in this tab
   until an utterance ends; the server uses the selected profile's transcription
   provider. Every async boundary is fenced by the captured voice session. */
let browserRealtimeVoice = null;
const voiceAuthHeaders = () => token ? {'x-tamanitomo-token':token,'x-companion-token':token} : {};
const realtimeVoiceCurrent = state => browserRealtimeVoice === state && !state.cancelled && state.scope === browserSpeechScope() && browserVoiceOpen();
const realtimeVoiceUrl = (state, path) => {
 const url = new URL(path, location.origin);
 url.searchParams.set('installation', state.installation);
 url.searchParams.set('profile', state.profile);
 return url.pathname + url.search;
};

class VoicePCMPlayer {
 constructor(context, current) {
  this.context = context; this.current = current; this.sources = new Set();
  this.next = 0; this.tail = null; this.stopped = false;
 }
 get lead() { return Math.max(0, this.next - this.context.currentTime); }
 push(bytes, sampleRate=24000) {
  if(this.stopped || !this.current()) return;
  if(sampleRate !== 24000) throw Error('The voice stream must be 24 kHz mono PCM.');
  let data = bytes;
  if(this.tail !== null) { data = new Uint8Array(bytes.length+1); data[0]=this.tail; data.set(bytes,1); this.tail=null; }
  if(data.length % 2) { this.tail=data[data.length-1]; data=data.subarray(0,data.length-1); }
  if(!data.length) return;
  const buffer=this.context.createBuffer(1,data.length/2,sampleRate), output=buffer.getChannelData(0);
  const view=new DataView(data.buffer,data.byteOffset,data.byteLength);
  for(let i=0;i<output.length;i++) output[i]=view.getInt16(i*2,true)/32768;
  const source=this.context.createBufferSource(); source.buffer=buffer;
  source.connect(this.context.destination); this.sources.add(source);
  source.onended=()=>{this.sources.delete(source);source.disconnect();};
  this.next=this.next ? Math.max(this.next,this.context.currentTime+0.01) : this.context.currentTime+0.20;
  source.start(this.next); this.next+=buffer.duration;
 }
 endChunk() { if(this.tail !== null) throw Error('The voice stream ended with an incomplete PCM sample.'); }
 stop() {
  this.stopped=true; this.tail=null; this.next=0;
  for(const source of this.sources) { try { source.stop();source.disconnect(); } catch(_) {} }
  this.sources.clear();
 }
}

/* Feed cumulative chat text. Only complete sentences leave the buffer before
   final; incomplete reasoning/code blocks are removed by messageSpeechText. */
class VoiceSentenceBuffer {
 constructor() { this.consumed=''; this.stale=false; }
 update(raw, final=false) {
  const text=messageSpeechText(raw);
  if(this.stale || !text.startsWith(this.consumed)) { this.stale=true; return []; }
  let rest=text.slice(this.consumed.length), chunks=[];
  while(rest.length) {
   let end=0;
   const boundary=/(?:[。！？]["'”’」』)]*|[.!?]["'”’」』)]*(?:\s|$))/u.exec(rest);
   // A trailing English dot can still become a decimal or abbreviation. Wait
   // for a following token; Japanese punctuation is already unambiguous.
   if(boundary && (final || boundary.index+boundary[0].length<rest.length || /[。！？]/u.test(boundary[0]) || /\s$/u.test(boundary[0]))) end=boundary.index+boundary[0].length;
   if(!end && Array.from(rest).length>200) {
    const limited=Array.from(rest).slice(0,200).join('');
    end=Math.max(limited.lastIndexOf(' '),limited.lastIndexOf('、'));
    if(end<80) end=limited.length;
   }
   if(!end && final) end=rest.length;
   if(!end) break;
   const part=rest.slice(0,end); this.consumed+=part; rest=rest.slice(end);
   if(part.trim()) chunks.push(...messageSpeechChunks(part.trim(),200));
  }
  return chunks;
 }
}

class VoiceActivityDetector {
 constructor(sampleRate, {onStart,onEnd}) {
  this.rate=sampleRate;this.onStart=onStart;this.onEnd=onEnd;
  this.noise=0.003;this.pre=[];this.preLength=0;this.frames=[];this.length=0;
  this.hot=0;this.quiet=0;this.active=false;
 }
 reset() { this.pre=[];this.preLength=0;this.frames=[];this.length=0;this.hot=0;this.quiet=0;this.active=false; }
 push(frame) {
  let square=0;for(const sample of frame)square+=sample*sample;
  const rms=Math.sqrt(square/Math.max(1,frame.length));
  const seconds=frame.length/this.rate;
  const loud=rms>Math.max(0.012,this.noise*3.2);
  if(!this.active) {
   if(!loud)this.noise=this.noise*0.98+Math.min(rms,0.02)*0.02;
   this.pre.push(frame);this.preLength+=frame.length;
   while(this.pre.length>1 && this.preLength-this.pre[0].length>this.rate*0.25)this.preLength-=this.pre.shift().length;
   this.hot=loud?this.hot+seconds:0;
   if(this.hot<0.10)return;
   this.active=true;this.frames=this.pre;this.length=this.preLength;this.pre=[];this.preLength=0;this.quiet=0;
   this.onStart();return;
  }
  this.frames.push(frame);this.length+=frame.length;
  this.quiet=loud?0:this.quiet+seconds;
  if(this.quiet>=0.75 || this.length>=this.rate*60) {
   const frames=this.frames;this.reset();this.onEnd(frames);
  }
 }
}

function voiceWav(frames,sampleRate) {
 const count=frames.reduce((sum,frame)=>sum+frame.length,0);
 const bytes=new ArrayBuffer(44+count*2),view=new DataView(bytes);
 const ascii=(offset,text)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i));};
 ascii(0,'RIFF');view.setUint32(4,36+count*2,true);ascii(8,'WAVE');ascii(12,'fmt ');
 view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
 view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
 ascii(36,'data');view.setUint32(40,count*2,true);let offset=44;
 for(const frame of frames)for(const sample of frame) { const value=Math.max(-1,Math.min(1,sample));view.setInt16(offset,Math.round(value*(value<0?32768:32767)),true);offset+=2; }
 return new Blob([bytes],{type:'audio/wav'});
}

function cancelBrowserRealtimeReply() {
 const state=browserRealtimeVoice,turn=state?.turn;
 if(!turn)return;
 turn.cancelled=true;turn.controller.abort();turn.player.stop();turn.queue=[];
 turn.reader?.cancel().catch(()=>{});
 if(state.turn===turn)state.turn=null;
}
function syncRealtimeVoiceButton() {
 const button=$('voice-conversation');if(!button)return;
 const on=Boolean(browserRealtimeVoice&&!browserRealtimeVoice.cancelled);
 button.textContent=on?'Mic on · End':'Voice conversation';
 button.setAttribute('aria-pressed',String(on));
 button.setAttribute('aria-label',on?'End voice conversation and turn microphone off':'Start hands-free voice conversation');
 button.classList.toggle('is-listening',on);
 if($('voice-record'))$('voice-record').disabled=on;
}
function stopBrowserRealtimeVoice() {
 const state=browserRealtimeVoice;if(!state)return;
 cancelBrowserRealtimeReply();state.cancelled=true;state.controller.abort();
 state.capture?.disconnect();state.source?.disconnect();state.silent?.disconnect();
 if(state.capture)state.capture.port.onmessage=null;
 state.stream?.getTracks().forEach(track=>track.stop());state.context?.close().catch(()=>{});
 state.vad?.reset();browserRealtimeVoice=null;syncRealtimeVoiceButton();
 // Closing a live microphone is an explicit stop for its current voice turn.
 if(state.chatTurn)window.ChatDock?.interrupt?.().catch(()=>{});
 speechStatus('Microphone off.');
}

async function realtimeVoiceRequest(state,path,options={}) {
 if(!realtimeVoiceCurrent(state))throw new DOMException('Voice session ended','AbortError');
 const response=await fetch(realtimeVoiceUrl(state,path),{...options,headers:{...voiceAuthHeaders(),...(options.headers||{})},signal:state.controller.signal});
 if(!realtimeVoiceCurrent(state))throw new DOMException('Voice session ended','AbortError');
 const body=await response.json();
 if(!response.ok)throw Error(body.detail||body.error||'Voice request failed');
 return body;
}
async function realtimeVoiceUtterance(state,frames) {
 if(!realtimeVoiceCurrent(state)||state.transcribing)return;
 state.transcribing=true;state.vad.reset();
 speechStatus('Mic on · finishing the interruption, then transcribing…');
 try {
  await state.interruptPending;
  if(!realtimeVoiceCurrent(state))return;
  if(window.ChatDock?.busy)throw Error('The previous reply is still finishing. Please try again.');
  speechStatus('Mic on · transcribing your last sentence…');
  let row=await realtimeVoiceRequest(state,'/api/voice-chat/transcribe',{method:'POST',headers:{'content-type':'audio/wav'},body:voiceWav(frames,state.context.sampleRate)});
  while(realtimeVoiceCurrent(state)) {
   if(row.profile!==state.profile)throw Error('Transcription belongs to another companion.');
   if(row.status==='complete')break;
   if(row.status!=='running'||row.error)throw Error(row.error||'Transcription did not finish.');
   await new Promise(resolve=>setTimeout(resolve,300));
   row=await realtimeVoiceRequest(state,'/api/operations/'+encodeURIComponent(row.id));
  }
  if(!realtimeVoiceCurrent(state))return;
  const text=String(row.result?.transcript||'').trim();
  if(!text)throw Error('No speech recognized. Try again or type your message.');
  // Never overwrite a typed draft with automatically recognized microphone text.
  if($('chat-message').value.trim())throw Error('Your typed draft is still here. Send or clear it before speaking.');
  $('chat-message').value=text;
  sessionStorage.setItem(chatKey('draft'),text);
  voiceReplyRequested=true;$('chat-form').requestSubmit();
  speechStatus('Mic on · waiting for a reply. Speak to interrupt.');
 } catch(error) {
  if(realtimeVoiceCurrent(state)&&error.name!=='AbortError')speechStatus('Mic on · '+error.message);
 } finally { state.transcribing=false;state.interruptPending=null;state.vad?.reset(); }
}

async function startBrowserRealtimeVoice() {
 if(browserRealtimeVoice){stopBrowserVoice();return;}
 if(activeOperation||window.ChatDock?.busy||window.ChatDock?.historyLoading)throw Error('Wait for the current operation to finish before starting voice.');
 if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.AudioWorkletNode)throw Error('Voice conversation needs HTTPS or localhost and a browser with AudioWorklet support.');
 stopBrowserVoice();
 const AudioContextClass=window.AudioContext||window.webkitAudioContext;
 if(!AudioContextClass)throw Error('This browser does not support streamed audio.');
 const state={scope:browserSpeechScope(),installation:INSTALLATION,profile:PROFILE||'default',controller:new AbortController(),cancelled:false,transcribing:false,turn:null};
 browserRealtimeVoice=state;syncRealtimeVoiceButton();
 try {
  // Resume inside the initiating click, before network/microphone prompts.
  state.context=new AudioContextClass();await state.context.resume();
  state.settings=await realtimeVoiceRequest(state,'/api/voice-chat/settings');
  if(!state.settings.enabled||!state.settings.configured)throw Error('Configure and enable realtime speech in Voice studio first.');
  speechStatus('Starting microphone… Use headphones so game audio does not interrupt her.');
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1},video:false});
  if(!realtimeVoiceCurrent(state)){stream.getTracks().forEach(track=>track.stop());return;}
  state.stream=stream;
  for(const track of stream.getAudioTracks())track.addEventListener('ended',()=>{if(realtimeVoiceCurrent(state))stopBrowserVoice();});
  await state.context.audioWorklet.addModule('/static/voice-capture-worklet.js');
  if(!realtimeVoiceCurrent(state))return;
  state.vad=new VoiceActivityDetector(state.context.sampleRate,{
   onStart:()=>{
    if(!realtimeVoiceCurrent(state))return;
    cancelBrowserRealtimeReply();
    if(window.ChatDock?.busy)state.interruptPending=window.ChatDock.interrupt();
    // Attach immediately: a failed cancellation must not become an unhandled
    // rejection during the utterance; the original promise is awaited at end.
    state.interruptPending?.catch(()=>{});
    speechStatus('● Mic on · listening…');
   },
   onEnd:frames=>{realtimeVoiceUtterance(state,frames);}
  });
  state.source=state.context.createMediaStreamSource(stream);
  state.capture=new AudioWorkletNode(state.context,'tamanitomo-voice-capture');
  state.silent=state.context.createGain();state.silent.gain.value=0;
  state.source.connect(state.capture);state.capture.connect(state.silent);state.silent.connect(state.context.destination);
  state.capture.port.onmessage=event=>{
   if(!realtimeVoiceCurrent(state)){if(browserRealtimeVoice===state)stopBrowserRealtimeVoice();return;}
   if(!state.transcribing)state.vad.push(event.data);
  };
  speechStatus('● Mic on · speak naturally. Use headphones; speak again to interrupt.');
 } catch(error) {
  if(browserRealtimeVoice===state)stopBrowserRealtimeVoice();
  if(error.name!=='AbortError')throw error;
 }
}

function beginBrowserRealtimeReply() {
 const state=browserRealtimeVoice;
 if(!state||!realtimeVoiceCurrent(state))return null;
 cancelBrowserRealtimeReply();voiceReplyRequested=false;
 const turn={cancelled:false,controller:new AbortController(),sentences:new VoiceSentenceBuffer(),queue:[],pumping:false,final:false};
 turn.current=()=>realtimeVoiceCurrent(state)&&state.turn===turn&&!turn.cancelled;
 turn.player=new VoicePCMPlayer(state.context,turn.current);
 state.turn=turn;state.chatTurn=turn;
 return turn;
}
function updateBrowserRealtimeReply(turn,text,final=false) {
 const state=browserRealtimeVoice;
 if(!state||!turn?.current())return;
 turn.queue.push(...turn.sentences.update(text,final));turn.final=final;
 pumpBrowserRealtimeReply(state,turn);
}
async function pumpBrowserRealtimeReply(state,turn) {
 if(turn.pumping||!turn.current())return;
 turn.pumping=true;
 try {
  while(turn.queue.length&&turn.current()) {
   const text=turn.queue.shift();
   let response;
   for(let attempt=0;attempt<6;attempt++) {
    response=await fetch(realtimeVoiceUrl(state,'/api/voice-chat/stream'),{method:'POST',headers:{'content-type':'application/json',...voiceAuthHeaders()},body:JSON.stringify({text,language:state.settings.language||'auto'}),signal:turn.controller.signal});
    if(response.status!==409||attempt===5||!turn.current())break;
    await response.body?.cancel();
    await new Promise(resolve=>setTimeout(resolve,200));
    if(!turn.current())return;
   }
   if(!turn.current()){await response.body?.cancel();return;}
   if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.detail||'Speech stream unavailable');}
   if(!response.body)throw Error('This browser cannot read streaming speech.');
   const rate=Number(response.headers.get('X-Audio-Sample-Rate')||24000);
   const reader=response.body.getReader();turn.reader=reader;
   try {
    while(turn.current()) {
     // Bound scheduled sound and upstream work when a reply is much faster
     // than playback; abort clears both this queue and all scheduled sources.
     while(turn.current()&&turn.player.lead>3)await new Promise(resolve=>setTimeout(resolve,40));
     if(!turn.current())break;
     const {value,done}=await reader.read();if(done)break;
     if(turn.current())turn.player.push(value,rate);
    }
    if(turn.current())turn.player.endChunk();
   } finally { if(!turn.current())await reader.cancel().catch(()=>{});reader.releaseLock();turn.reader=null; }
  }
  if(turn.final&&turn.current()) {
   while(turn.current()&&turn.player.lead>0)await new Promise(resolve=>setTimeout(resolve,50));
   if(turn.current()) { state.turn=null;state.chatTurn=null;speechStatus('● Mic on · listening. Speak whenever you are ready.'); }
  }
 } catch(error) {
  if(turn.current()) { cancelBrowserRealtimeReply();speechStatus('Mic on · voice unavailable: '+error.message); }
 } finally { turn.pumping=false;if(turn.queue.length&&turn.current())pumpBrowserRealtimeReply(state,turn); }
}

/* Starting points only; every field stays editable. Each service must return
   raw 24 kHz mono PCM from its OpenAI-shaped speech endpoint. */
const REALTIME_SPEECH_PRESETS=[
 ['qwen','Local Qwen3-TTS (Gufo)',{base_url:'http://127.0.0.1:8771/v1',model:'qwen3-tts-12hz-1.7b-base',voice_en:'companion-en',voice_ja:'companion-ja',api_key_env:''},'Register the companion-en and companion-ja voices on your Gufo server, then save.'],
 ['openai','OpenAI (paid, needs a key)',{base_url:'https://api.openai.com/v1',model:'gpt-4o-mini-tts',voice_en:'coral',voice_ja:'coral',api_key_env:'OPENAI_API_KEY'},'OpenAI bills each spoken reply. The key comes from this companion’s OPENAI_API_KEY.'],
 ['kokoro','Kokoro (local, free)',{base_url:'http://127.0.0.1:8880/v1',model:'kokoro',voice_en:'af_heart',voice_ja:'jf_alpha',api_key_env:''},'Run Kokoro-FastAPI on this computer first (see docs/REALTIME_VOICE.md), then save.'],
];

async function mountRealtimeVoiceSettings(host) {
 if(!host)return;
 const scope=browserSpeechScope(),url=scoped('/api/voice-chat/settings');
 const current=()=>host.isConnected&&scope===browserSpeechScope();
 host.textContent='Loading realtime voice settings…';
 try {
  const response=await fetch(url,{headers:voiceAuthHeaders()});
  const settings=await response.json();
  if(!current())return;
  if(!response.ok)throw Error(settings.detail||'Could not load realtime voice settings.');
  host.innerHTML=`<h2>Hands-free conversation</h2>
   <p class="dim small">Stream spoken replies as they arrive, and interrupt by speaking. Start the microphone explicitly from chat. Use headphones to keep game and speaker audio out of the microphone.</p>
   <form data-realtime-settings>
    <label class="inline-label"><input name="enabled" type="checkbox" ${settings.enabled?'checked':''}> Enable realtime speech for this companion</label>
    <label>Fill in for<select name="preset"><option value="">Keep these settings</option>${REALTIME_SPEECH_PRESETS.map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join('')}</select></label>
    <div class="form-grid">
     <label>Speech server URL<input name="base_url" type="url" value="${esc(settings.base_url||'')}" placeholder="http://127.0.0.1:8771/v1"></label>
     <label>Speech model<input name="model" value="${esc(settings.model||'')}" placeholder="qwen3-tts-12hz-1.7b-base"></label>
     <label>English voice<input name="voice_en" value="${esc(settings.voice_en||'')}" placeholder="companion-en"></label>
     <label>Japanese voice<input name="voice_ja" value="${esc(settings.voice_ja||'')}" placeholder="companion-ja"></label>
     <label>Spoken language<select name="language">${options([['auto','Match the reply'],['English','English'],['Japanese','Japanese']],settings.language||'auto')}</select></label>
     <label>API-key environment variable<input name="api_key_env" value="${esc(settings.api_key_env||'')}" placeholder="Not needed for a local server" pattern="[A-Z][A-Z0-9_]*"></label>
    </div>
    <p class="dim small" data-realtime-key>${settings.api_key_env?(settings.has_api_key?esc(settings.api_key_env)+' is set for this companion.':esc(settings.api_key_env)+' is not set for this companion. Add it on the Models page or in its .env file.'):''}</p>
    <p class="dim small">The URL is reached from the companion’s Hermes host. Microphone recognition uses that profile’s transcription provider; choose a multilingual provider for Japanese input.</p>
    <button class="act" type="submit">Save realtime voice</button>
    <p data-realtime-status class="dim small" role="status">${settings.configured?'Speech connection configured. Start Voice conversation in chat to try it.':'Enter the speech server and voices before starting a voice conversation.'}</p>
   </form>`;
  const form=host.querySelector('[data-realtime-settings]'),status=host.querySelector('[data-realtime-status]');
  form.elements.preset.onchange=()=>{
   const preset=REALTIME_SPEECH_PRESETS.find(([id])=>id===form.elements.preset.value);
   if(!preset)return;
   for(const [name,value] of Object.entries(preset[2]))form.elements[name].value=value;
   status.textContent=preset[3];
  };
  form.onsubmit=async event=>{
   event.preventDefault();const submit=form.querySelector('button');submit.disabled=true;
   try {
    const body={enabled:form.elements.enabled.checked};
    for(const name of ['base_url','model','voice_en','voice_ja','language','api_key_env'])body[name]=form.elements[name].value.trim();
    const saved=await fetch(url,{method:'POST',headers:{'content-type':'application/json',...voiceAuthHeaders()},body:JSON.stringify(body)});
    const result=await saved.json();if(!current())return;
    if(!saved.ok)throw Error(result.detail||'Could not save realtime voice settings.');
    stopBrowserRealtimeVoice();status.textContent=result.api_key_env&&!result.has_api_key?'Saved, but '+result.api_key_env+' is not set for this companion yet.':'Saved. Open chat and start Voice conversation.';
   } catch(error) { if(current())status.textContent=error.message; }
   finally { if(current())submit.disabled=false; }
  };
 } catch(error) { if(current())host.textContent='Realtime voice settings unavailable: '+error.message; }
}
