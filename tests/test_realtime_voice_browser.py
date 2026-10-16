"""Exercise streamed playback, microphone boundaries, and explicit interruption."""

from tests.test_chat_dock import run_browser_contract
from tests.test_chat_sync_browser import HARNESS as DOCK_HARNESS
from tests.test_message_voice import VOICE_HARNESS

PCM_HARNESS = VOICE_HARNESS + r"""
class AudioContextFake {
 constructor(){this.currentTime=0;this.sampleRate=48000;this.destination={};this.sources=[];this.closed=false;}
 createBuffer(channels,length,rate){const data=new Float32Array(length);return {duration:length/rate,getChannelData:()=>data};}
 createBufferSource(){const source={connect(){},disconnect(){},start(time){this.started=time;},stop(){this.stopped=true;}};this.sources.push(source);return source;}
 async resume(){}
 async close(){this.closed=true;}
}
const makeState=()=>({scope:browserSpeechScope(),installation:INSTALLATION,profile:PROFILE,controller:new AbortController(),context:new AudioContextFake(),settings:{language:'auto'},cancelled:false});
"""


def voice_case(body):
    run_browser_contract(
        PCM_HARNESS
        + "\n(async()=>{\n"
        + body
        + "\n})().catch(error=>{console.error(error);process.exitCode=1;});"
    )


def test_pcm_preserves_split_samples_continuity_and_stops_scheduled_sources():
    voice_case(r"""
const context=new AudioContextFake();let current=true;
const player=new VoicePCMPlayer(context,()=>current);
player.push(Uint8Array.from([0,128,255]));
assert.deepEqual([...context.sources[0].buffer.getChannelData(0)],[-1]);
context.currentTime=0.1;
player.push(Uint8Array.from([127,0,0]));player.endChunk();
assert.deepEqual([...context.sources[1].buffer.getChannelData(0)],[32767/32768,0]);
assert.equal(context.sources[1].started,context.sources[0].started+1/24000);
player.stop();
assert.ok(context.sources.every(source=>source.stopped));
player.push(new Uint8Array(8));assert.equal(context.sources.length,2);
const other=new VoicePCMPlayer(context,()=>current);
other.push(new Uint8Array([7]));assert.throws(()=>other.endChunk(),/incomplete PCM/);
current=false;other.push(new Uint8Array(8));assert.equal(context.sources.length,2);
""")


def test_sentence_stream_starts_before_final_and_preserves_english_japanese():
    voice_case(r"""
const text=new VoiceSentenceBuffer();
assert.deepEqual(text.update('<think>Never speak this.'),[]);
assert.deepEqual(text.update('<think>Never speak this.</think>Hello there. Let'),['Hello there.']);
assert.deepEqual(text.update('<think>Never speak this.</think>Hello there. Let us play!'),[]);
assert.deepEqual(text.update('<think>Never speak this.</think>Hello there. Let us play!',true),['Let us play!']);
const thinking=new VoiceSentenceBuffer();
assert.deepEqual(thinking.update('<thi'),[]);
assert.deepEqual(thinking.update('<thinking>Private reasoning. Do not read.'),[]);
assert.deepEqual(thinking.update('<thinking>Private reasoning. Do not read.</thinking>Real reply. More'),['Real reply.']);
const ja=new VoiceSentenceBuffer();
assert.deepEqual(ja.update('来てくれた！一緒に遊ぼう。'),['来てくれた！','一緒に遊ぼう。']);
const long=new VoiceSentenceBuffer();
const chunks=long.update('🌿'.repeat(501),true);
assert.deepEqual(chunks.map(value=>Array.from(value).length),[200,200,101]);
assert.equal(chunks.join(''),'🌿'.repeat(501));
const rewritten=new VoiceSentenceBuffer();rewritten.update('First line. More');
assert.deepEqual(rewritten.update('Entirely replaced response.',true),[]);
""")


def test_vad_ignores_short_click_retains_preroll_and_emits_one_wav_utterance():
    voice_case(r"""
let starts=0,finished=[];
const detector=new VoiceActivityDetector(1000,{onStart:()=>starts++,onEnd:frames=>finished.push(frames)});
const quiet=()=>new Float32Array(20),speech=()=>new Float32Array(20).fill(0.1);
for(let i=0;i<15;i++)detector.push(quiet());
detector.push(speech());detector.push(speech());detector.push(quiet());
assert.equal(starts,0);
for(let i=0;i<7;i++)detector.push(speech());
assert.equal(starts,1);
for(let i=0;i<38;i++)detector.push(quiet());
assert.equal(finished.length,1);assert.equal(detector.active,false);
assert.ok(finished[0].length>45,'Includes the onset and pre-roll before detected speech');
const wav=voiceWav([Float32Array.from([-1,0,1])],24000);
const bytes=await wav.arrayBuffer(),view=new DataView(bytes);
assert.equal(wav.type,'audio/wav');assert.equal(view.getUint32(24,true),24000);
assert.equal(view.getUint32(40,true),6);
assert.deepEqual([44,46,48].map(offset=>view.getInt16(offset,true)),[-32768,0,32767]);
""")


def test_live_pcm_plays_before_stream_finishes_and_abort_fences_late_bytes():
    voice_case(r"""
const state=makeState();browserRealtimeVoice=state;
let upstream,signal,cancelled=false;
global.fetch=async(url,options)=>{
 signal=options.signal;
 assert.equal(new URL(url,location.origin).searchParams.get('profile'),'nova');
 assert.equal(JSON.parse(options.body).text,'Hello there.');
 return {ok:true,headers:new Headers({'X-Audio-Sample-Rate':'24000'}),body:new ReadableStream({start(controller){upstream=controller;},cancel(){cancelled=true;}})};
};
const turn=beginBrowserRealtimeReply();
updateBrowserRealtimeReply(turn,'Hello there. The rest is still arriving');
await tick();upstream.enqueue(new Uint8Array(4800));await tick();
assert.equal(state.context.sources.length,1,'Playback starts without a final chat event or completed audio response');
assert.equal(turn.final,false);
cancelBrowserRealtimeReply();await tick();
assert.equal(signal.aborted,true);assert.equal(cancelled,true);
assert.ok(state.context.sources[0].stopped);
updateBrowserRealtimeReply(turn,'Hello there. Do not speak this late tail.',true);await tick();
assert.equal(state.context.sources.length,1);
browserRealtimeVoice=null;
""")


def test_stream_response_after_profile_switch_cannot_schedule_audio():
    voice_case(r"""
const state=makeState();browserRealtimeVoice=state;let finish,cancelled=false;
global.fetch=()=>new Promise(resolve=>{finish=resolve;});
const turn=beginBrowserRealtimeReply();updateBrowserRealtimeReply(turn,'A complete sentence. More');
PROFILE='rowan';
finish({ok:true,headers:new Headers(),body:new ReadableStream({start(c){c.enqueue(new Uint8Array(4800));},cancel(){cancelled=true;}})});
await tick();assert.equal(state.context.sources.length,0);assert.equal(cancelled,true);
browserRealtimeVoice=null;
""")


def test_microphone_permission_resolving_after_stop_releases_all_tracks():
    voice_case(r"""
window.isSecureContext=true;window.AudioWorkletNode=function(){};window.AudioContext=AudioContextFake;
let allow,stopped=0;
Object.defineProperty(global,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>new Promise(resolve=>{allow=resolve;})}}});
global.fetch=async()=>response({enabled:true,configured:true});
const starting=startBrowserRealtimeVoice();await tick();
const context=browserRealtimeVoice.context;
stopBrowserRealtimeVoice();
allow({getTracks:()=>[{stop(){stopped++;}}]});await starting;
assert.equal(stopped,1);assert.equal(context.closed,true);assert.equal(browserRealtimeVoice,null);
""")


def test_chat_interrupt_waits_for_server_completion_and_does_not_replay_turn():
    run_browser_contract(DOCK_HARNESS + r"""
(async()=>{
 global.location={origin:'http://localhost'};
 const calls=[];let output;
 dock.open();await flush();
 global.fetch=async(url,options)=>{
  calls.push(url);
  if(url.includes('/interrupt'))return {ok:true,json:async()=>({status:'running'})};
  return {ok:true,body:new ReadableStream({start(controller){output=controller;}})};
 };
 node('chat-message').value='Hello';
 const pending=node('chat-form').onsubmit({preventDefault(){}});await flush();
 let ended=false;
 const interrupted=dock.interrupt().then(()=>{ended=true;});
 assert.equal(ended,false);assert.equal(calls.length,1,'Wait for the operation identifier without replay');
 output.enqueue(new TextEncoder().encode('event: operation\ndata: {"id":"'+'a'.repeat(32)+'"}\n\n'));
 await flush();assert.equal(calls.length,2);assert.match(calls[1],/\/interrupt$/);
 assert.equal(dock.busy,true);assert.equal(ended,false);
 output.enqueue(new TextEncoder().encode('event: final\ndata: {"response":"Partial reply","interrupted":true}\n\n'));
 output.close();await pending;await interrupted;
 assert.equal(dock.busy,false);assert.equal(ended,true);assert.equal(calls.length,2);
 assert.equal(storage.get('nova:operation'),'');
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_chat_deltas_feed_realtime_speech_and_final_flush_without_replaying_audio():
    run_browser_contract(DOCK_HARNESS + r"""
(async()=>{
 const updates=[];let output;
 global.beginBrowserRealtimeReply=()=>({voice:true});
 global.updateBrowserRealtimeReply=(turn,text,final=false)=>updates.push([text,final]);
 global.speakBrowserReply=()=>{throw Error('A live reply was replayed as buffered speech');};
 dock.open();await flush();
 global.fetch=async()=>({ok:true,body:new ReadableStream({start(controller){output=controller;}})});
 node('chat-message').value='Hello';
 const pending=node('chat-form').onsubmit({preventDefault(){}});await flush();
 output.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"First sentence. "}\n\n'));
 await flush();assert.deepEqual(updates,[['First sentence. ',false]]);
 output.enqueue(new TextEncoder().encode('event: final\ndata: {"response":"First sentence. Last sentence."}\n\n'));
 output.close();await pending;
 assert.deepEqual(updates.at(-1),['First sentence. Last sentence.',true]);
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_barge_in_transcribes_only_after_chat_cleanup_and_submits_once():
    voice_case(r"""
const state=makeState();browserRealtimeVoice=state;state.vad={reset(){}};
let release,transcriptions=0,submissions=0;
state.interruptPending=new Promise(resolve=>{release=resolve;});
window.ChatDock.busy=true;
elements.set('chat-form',{requestSubmit(){submissions++;assert.equal(voiceReplyRequested,true);}});
$('chat-message').value='';
global.sessionStorage={setItem(){}};global.chatKey=kind=>'nova:'+kind;
global.fetch=async(url,options)=>{
 transcriptions++;assert.ok(url.startsWith('/api/voice-chat/transcribe'));
 assert.equal(options.body.type,'audio/wav');
 return response({profile:'nova',status:'complete',result:{transcript:'Wait, I have a question.'}});
};
const utterance=realtimeVoiceUtterance(state,[new Float32Array(960)]);
await tick();assert.equal(transcriptions,0);assert.equal(submissions,0);
window.ChatDock.busy=false;release();await utterance;
assert.equal(transcriptions,1);assert.equal(submissions,1);
assert.equal($('chat-message').value,'Wait, I have a question.');
assert.equal(state.transcribing,false);browserRealtimeVoice=null;
""")


def test_recognized_speech_does_not_overwrite_an_existing_typed_draft():
    voice_case(r"""
const state=makeState();browserRealtimeVoice=state;state.vad={reset(){}};
$('chat-message').value='My unsent typed draft';
elements.set('chat-form',{requestSubmit(){throw Error('A typed draft was submitted automatically');}});
global.fetch=async()=>response({profile:'nova',status:'complete',result:{transcript:'Recognized speech'}});
await realtimeVoiceUtterance(state,[new Float32Array(960)]);
assert.equal($('chat-message').value,'My unsent typed draft');
assert.match($('voice-status').textContent,/typed draft is still here/);
browserRealtimeVoice=null;
""")


def test_old_voice_session_cannot_submit_transcription_into_new_session():
    voice_case(r"""
const old=makeState();old.vad={reset(){}};browserRealtimeVoice=old;let finish;
$('chat-message').value='';
global.fetch=()=>new Promise(resolve=>{finish=resolve;});
const utterance=realtimeVoiceUtterance(old,[new Float32Array(960)]);await tick();
const next=makeState();browserRealtimeVoice=next;
finish(response({profile:'nova',status:'complete',result:{transcript:'Stale voice input'}}));
await utterance;
assert.equal($('chat-message').value,'');assert.equal(browserRealtimeVoice,next);
browserRealtimeVoice=null;
""")


def test_worklet_batches_actual_pcm_without_playing_microphone_audio():
    run_browser_contract(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sent=[];let Processor;
global.sampleRate=48000;
global.AudioWorkletProcessor=class {constructor(){this.port={postMessage(frame,transfer){sent.push([...frame]);assert.equal(transfer[0],frame.buffer);}};}};
global.registerProcessor=(name,processor)=>{assert.equal(name,'tamanitomo-voice-capture');Processor=processor;};
vm.runInThisContext(fs.readFileSync('kit/app/static/voice-capture-worklet.js','utf8'));
const processor=new Processor(),silence=new Float32Array(128);
for(let i=0;i<15;i++)assert.equal(processor.process([[new Float32Array(128).fill(0.25)]],[[silence]]),true);
assert.equal(sent.length,2);assert.equal(sent[0].length,960);
assert.ok(sent.flat().every(value=>value===0.25));
assert.ok(silence.every(value=>value===0),'Microphone samples never echo to the speaker');
""")
