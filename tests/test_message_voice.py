"""Read completed replies with scoped TTS, without replaying chat or opening a mic."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.support import WorkspaceFixture
from tests.test_chat_dock import run_browser_contract

VOICE_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
global.window = new EventTarget();
window.ChatDock = {isOpen:true,busy:false,historyLoading:false};
global.document = new EventTarget();
document.hidden = false;
global.INSTALLATION = 'existing'; global.PROFILE = 'nova'; global.token = 'test-token';
global.location = {origin:'http://localhost'};
global.activeOperation = null;
global.navigator = {mediaDevices:{getUserMedia(){throw Error('Playback requested a microphone');}}};
global.action = global.followOperation = ()=>{throw Error('Playback used global operation locking');};
class Element extends EventTarget {
 constructor(){super();this.hidden=false;this.disabled=false;this.readOnly=false;this.attributes={};this.textContent='';}
 setAttribute(name,value){this.attributes[name]=value;}
 removeAttribute(name){delete this.attributes[name];if(name==='src')this.src='';}
}
class Player extends Element {
 constructor(){super();this.played=[];this.pauses=0;this.loads=0;}
 async play(){this.played.push(this.src);}
 pause(){this.pauses++;}
 load(){this.loads++;}
}
const elements = new Map(['send-message','chat-message','voice-status','voice-stop'].map(key=>[key,new Element()]));
const player = new Player();elements.set('voice-reply',player);
global.$ = id=>elements.get(id);
global.scoped = path=>{const u=new URL(path,location.origin);u.searchParams.set('installation',INSTALLATION);u.searchParams.set('profile',PROFILE);return u.pathname+u.search;};
const response = body=>({ok:true,json:async()=>body});
const completed = (profile='nova')=>({id:'speech-1',profile,status:'complete',result:{audio:'/api/voice-chat/audio?name='+'a'.repeat(32)+'.wav'}});
const tick = ()=>new Promise(resolve=>setImmediate(resolve));
vm.runInThisContext(fs.readFileSync('kit/app/static/voice-chat.js','utf8'));
"""


def browser_case(body):
    run_browser_contract(
        VOICE_HARNESS
        + "\n(async()=>{\n"
        + body
        + "\n})().catch(error=>{console.error(error);process.exitCode=1;});"
    )


def test_speech_markdown_cleanup_preserves_prose_and_announces_omitted_code():
    browser_case(r"""
const original = '# A small thought\n\n**Hello**, café 🌿. [Read more](https://example.com).\n\n```python\nsecret()\n```\n\n> The ending matters.\n\n![A garden](garden.png)\n\n<reasoning>private</reasoning>';
const spoken = messageSpeechText(original);
assert.equal(spoken,'A small thought Hello, café 🌿. Read more. Code block omitted. The ending matters. Image: A garden.');
const unbroken='🌿'.repeat(2201), chunks=messageSpeechChunks(unbroken);
assert.deepEqual(chunks.map(chunk=>Array.from(chunk).length),[900,900,401]);
assert.equal(chunks.join(''),unbroken);
for(const chunk of chunks)assert.ok(!/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(chunk));
""")


def test_long_message_plays_every_chunk_in_order_without_locking_the_composer():
    browser_case(r"""
const text='A little story about café and 茶🌿. '.repeat(90)+'The ending is still here.';
const requests=[];
global.fetch=async(url,options)=>{requests.push([url,JSON.parse(options.body)]);return response(completed());};
const button=new Element(), done=playBrowserMessage(text,button);
await tick();
const expected=messageSpeechChunks(messageSpeechText(text));
assert.ok(expected.length>2);
for(let index=0;index<expected.length;index++){
 assert.equal(requests.length,index+1,'Only synthesize the next chunk after this audio ends');
 assert.equal(player.played.length,index+1);
 assert.equal($('send-message').disabled,false);
 assert.equal($('chat-message').readOnly,false);
 assert.equal(activeOperation,null);
 assert.equal(button.textContent,'Stop');
 const url=new URL(player.played[index],location.origin);
 assert.equal(url.searchParams.get('profile'),'nova');
 assert.equal(url.searchParams.get('installation'),'existing');
 player.dispatchEvent(new Event('ended'));
 await tick();
}
await done;
assert.deepEqual(requests.map(([,body])=>body.text),expected);
assert.equal(requests.map(([,body])=>body.text).join(''),messageSpeechText(text));
assert.ok(requests.every(([url,body])=>url.startsWith('/api/voice-chat/speak?')&&Array.from(body.text).length<=900));
assert.equal(button.textContent,'Play');
assert.equal($('voice-status').textContent,'Finished reading the message.');
""")


def test_stop_interrupts_audio_and_prevents_the_next_synthesis():
    browser_case(r"""
let calls=0;
global.fetch=async()=>{calls++;return response(completed());};
const text='A full reply. '.repeat(200), button=new Element();
const done=playBrowserMessage(text,button);await tick();
assert.equal(calls,1);assert.equal(player.played.length,1);
await playBrowserMessage(text,button);await done;
assert.equal(calls,1);assert.equal(player.src,'');assert.equal(player.hidden,true);
assert.equal(button.textContent,'Play');assert.ok(player.pauses>0);
""")


@pytest.mark.parametrize("change", ["stopBrowserVoice();", "PROFILE='rowan';"])
def test_late_synthesis_result_cannot_play_after_stop_or_profile_change(change):
    browser_case(
        r"""
let finish,calls=0;
global.fetch=()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
const done=playBrowserMessage('A long reply. '.repeat(200));
"""
        + change
        + r"""
finish(response(completed()));await done;
assert.equal(player.played.length,0);assert.equal(calls,1);
"""
    )


@pytest.mark.parametrize(
    "event",
    [
        "window.dispatchEvent(new Event('pagehide'));",
        "document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));",
        "window.ChatDock.isOpen=false;stopBrowserVoice();",
    ],
)
def test_navigation_and_closed_chat_stop_playback(event):
    browser_case(
        r"""
let calls=0;
global.fetch=async()=>{calls++;return response(completed());};
const done=playBrowserMessage('A full reply. '.repeat(200));await tick();
assert.equal(player.played.length,1);
"""
        + event
        + r"""
await done;
assert.equal(calls,1);assert.equal(player.src,'');assert.equal(player.hidden,true);
"""
    )


def test_polling_is_scoped_and_cancellable_without_global_operation_state():
    browser_case(r"""
const urls=[];
global.fetch=async(url,options)=>{
 urls.push(url);
 return response({id:'speech-1',profile:'nova',status:'running'});
};
const done=playBrowserMessage('A full reply. '.repeat(200));
await new Promise(resolve=>setTimeout(resolve,550));
assert.equal(urls.length,2);
assert.ok(urls[1].startsWith('/api/operations/speech-1?'));
assert.equal(new URL(urls[1],location.origin).searchParams.get('profile'),'nova');
stopBrowserVoice();await done;
await tick();assert.equal(urls.length,2);assert.equal(activeOperation,null);
""")


def test_wrong_profile_operation_is_rejected_before_audio_playback():
    browser_case(r"""
global.fetch=async()=>response(completed('rowan'));
await assert.rejects(playBrowserMessage('Hello.'),/another companion/);
assert.equal(player.played.length,0);assert.equal(player.src,'');
""")


def test_autoplay_denial_keeps_manual_controls_and_waits_for_the_whole_part():
    browser_case(r"""
let calls=0;
global.fetch=async()=>{calls++;return response(completed());};
player.play=async()=>{throw new DOMException('User gesture needed','NotAllowedError');};
const done=playBrowserMessage('A full reply. '.repeat(200));await tick();
assert.equal(calls,1);assert.equal(player.hidden,false);
assert.match($('voice-status').textContent,/Press Play in the audio player/);
stopBrowserMessage();await done;
assert.equal(calls,1);
""")


def test_player_error_stops_the_queue_and_restores_the_play_button():
    browser_case(r"""
let calls=0;
global.fetch=async()=>{calls++;return response(completed());};
const button=new Element();const done=playBrowserMessage('A full reply. '.repeat(200),button);
const failed=assert.rejects(done,/Audio playback failed/);
await tick();player.dispatchEvent(new Event('error'));await failed;
assert.equal(calls,1);assert.equal(button.textContent,'Play');
""")


def test_message_buttons_exclude_human_and_incomplete_assistant_messages():
    run_browser_contract(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
global.esc=String;global.chatLastDay='';global.channelOf=()=>({key:'desktop'});
global.extractMediaFromContent=content=>({text:content,extractedMedia:[]});
global.richText=String;global.faceHtml=()=>'';global.chatName=()=>'';global.inlineMedia=()=>'';
const source=fs.readFileSync('kit/app/static/workspace.js','utf8');
vm.runInThisContext(source.slice(source.indexOf('function chatMessagesHtml('),source.indexOf('\nfunction inlineMedia(')));
const html=chatMessagesHtml([
 {role:'user',content:'My message'},
 {role:'assistant',content:'Complete reply'},
 {role:'assistant',content:'Streaming partial',pending:true},
 {role:'assistant',content:'Earlier complete reply'}
]);
assert.deepEqual([...html.matchAll(/data-speech-index="(\d+)"/g)].map(match=>Number(match[1])),[1,3]);
""")


def test_speech_click_uses_search_context_or_feed_rows_and_rejects_pending():
    run_browser_contract(r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('kit/app/static/chat-dock.js','utf8');
global.rows=[{role:'assistant',content:'Current conversation'},{role:'assistant',content:'Unfinished',pending:true}];
global.searchContextRows=[{role:'assistant',content:'The earlier conversation'}];
const requests=[];
global.playBrowserMessage=async text=>{requests.push(text);};global.notice=()=>{};
global.root={contains:()=>true};
vm.runInThisContext(source.slice(source.indexOf('  function speechRow('),source.indexOf('  function syncSpeechButtons(')));
const handler=source.split("root.addEventListener('click', ")[1].split('\n    });')[0];
const click=vm.runInThisContext('('+handler+'\n})');
const event=(index,search=false)=>{const button={dataset:{speechIndex:String(index)},closest:()=>search?{}:null};return {target:{closest:()=>button}};};
click(event(0));click(event(0,true));click(event(1));click(event(9));click(event(-1));
assert.deepEqual(requests,['Current conversation','The earlier conversation']);
""")


class MessageVoiceApiTests(WorkspaceFixture):
    def test_synthesis_and_audio_stay_in_the_selected_profile(self):
        from kit.app import voice_chat

        seen = []

        def synthesize(rt, home, mode, payload):
            seen.append((home, mode, payload["text"]))
            path = Path(payload["path"])
            path.write_bytes(b"RIFF" + b"\0" * 60)
            return {"success": True, "file_path": str(path)}

        with patch.object(voice_chat, "bridge", side_effect=synthesize):
            for profile, companion in (("nova", self.c), ("rowan", self.other)):
                text = "茶🌿" * 450
                response = self.post("/api/voice-chat/speak", {"text": text}, profile)
                result = self.wait(response, profile)
                assert result["status"] == "complete"
                assert result["profile"] == profile
                assert seen[-1] == (companion.home, "speak", text)
                audio = result["result"]["audio"]
                assert (
                    self.client.get(
                        audio + "&profile=" + profile, headers=self.headers
                    ).status_code
                    == 200
                )
                other = "rowan" if profile == "nova" else "nova"
                assert (
                    self.client.get(
                        audio + "&profile=" + other, headers=self.headers
                    ).status_code
                    == 404
                )
                assert (
                    self.get("/api/operations/" + result["id"], other).status_code
                    == 404
                )

    def test_oversized_chunk_is_rejected_before_calling_the_provider(self):
        from kit.app import voice_chat

        with patch.object(voice_chat, "bridge") as bridge:
            response = self.post("/api/voice-chat/speak", {"text": "🌿" * 1001})
        assert response.status_code == 400
        bridge.assert_not_called()
