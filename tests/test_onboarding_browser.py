"""Run the real setup controller through reloads using a small DOM harness."""

from tests.test_chat_dock import run_browser_contract

HARNESS = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map(),storage=new Map(),posts=[];let attempt={};
class Element{
  constructor(){this.dataset={};this.style={};this.value='';this.classList={add(){},remove(){}};}
  set innerHTML(value){
    this.html=value;
    for(const match of value.matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Element());
    this.choices=Array.from(value.matchAll(/data-pick="(\d+)"/g),m=>{const e=new Element();e.dataset.pick=m[1];return e;});
  }
  get innerHTML(){return this.html||'';}
  closest(){return {dataset:{}};}
  scrollIntoView(){}focus(){}
  querySelectorAll(selector){return selector==='[data-pick]'?this.choices||[]:[];}
  querySelector(selector){
    if(selector.includes('channel_pick'))return {value:'web'};
    if(selector.includes('purpose_pick'))return {value:'relational'};
    if(selector.includes('meet_who'))return {value:'she'};
    if(selector.includes('meet_age'))return {value:'35'};
    return null;
  }
}
const host=new Element();nodes.set('onboarding',host);nodes.set('environment-onboarding',new Element());
Object.defineProperty(global,'crypto',{value:require('node:crypto').webcrypto,configurable:true});
Object.assign(global,{window:{},INSTALLATION:'synthetic',PROFILE:'nova',
  $:id=>nodes.get(id),esc:value=>String(value??''),api:async path=>path==='/catalog'?{personas:{},boundaries:{}}:path.startsWith('/onboarding/attempt/')?attempt:{},
  post:async(path,payload)=>{posts.push({path,payload});return {};}, options:()=>'',
  localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
vm.runInThisContext(fs.readFileSync('kit/app/static/onboarding.js','utf8'));
"""


def run_setup_browser(body):
    run_browser_contract(
        HARNESS
        + "\n(async()=>{\n"
        + body
        + "\n})().catch(error=>{console.error(error);process.exitCode=1;});"
    )


def test_questionnaire_resumes_without_secrets_and_start_over_resets_choices():
    run_setup_browser(r"""
  await window.onboarding(false);
  await $('btn-welcome-start').onclick();await $('btn-ch-next').onclick();$('btn-pur-next').onclick();$('btn-meet-next').onclick();
  host.choices[2].onclick();
  assert.match(host.innerHTML,/Question 2 of 26/);
  let saved=JSON.parse([...storage.values()][0]);
  assert.equal(saved.picks[0],2);assert.equal(saved.draft.pronoun_set,'she');assert.equal(saved.draft.age,35);
  assert.equal('api_key' in saved.draft,false);assert.equal('telegram_token' in saved.draft,false);
  const oldRequest=saved.requestId;
  await window.onboarding(false);
  assert.match(host.innerHTML,/Resume saved setup/);await $('btn-welcome-resume').onclick();
  assert.match(host.innerHTML,/Question 2 of 26/);
  $('quiz-back').onclick();assert.match(host.innerHTML,/quiz-option is-chosen" data-pick="2"/);
  await window.onboarding(false);await $('btn-welcome-start').onclick();
  saved=JSON.parse([...storage.values()][0]);
  assert.equal(saved.picks.every(value=>value===null),true);assert.notEqual(saved.requestId,oldRequest);
  assert.equal(saved.draft.pronoun_set,'they');
  assert.equal(posts.at(-1).path,'/onboarding/attempt/'+oldRequest+'/discard');
""")


def test_drafts_are_scoped_to_owner_profile_and_setup_mode():
    run_setup_browser(r"""
  await window.onboarding(false);await $('btn-welcome-start').onclick();
  const original=[...storage.keys()][0];
  PROFILE='rowan';await window.onboarding(false);
  assert.doesNotMatch(host.innerHTML,/Resume saved setup/);
  PROFILE='nova';await window.onboarding(true);
  assert.doesNotMatch($('environment-onboarding').innerHTML,/Resume saved setup/);
  await window.onboarding(false);assert.match(host.innerHTML,/Resume saved setup/);
  assert.equal(storage.has(original),true);
""")


def test_partial_profile_keeps_questionnaire_and_never_offers_blind_retry():
    run_setup_browser(r"""
  await window.onboarding(false);await $('btn-welcome-start').onclick();
  const key=[...storage.keys()][0],saved=JSON.parse(storage.get(key));
  saved.phase='creating';saved.picks[0]=2;saved.derived={};saved.draft.agent='Iris';
  storage.set(key,JSON.stringify(saved));
  attempt={profile:'iris',created:true,profile_exists:true,operation:{status:'failed'}};
  await window.onboarding(false);await $('btn-welcome-resume').onclick();
  assert.match(host.innerHTML,/questionnaire remains saved/);
  assert.doesNotMatch(host.innerHTML,/Retry saved setup/);
  assert.equal(JSON.parse(storage.get(key)).picks[0],2);
  await window.onboarding(false);await $('btn-welcome-start').onclick();
  assert.match(host.innerHTML,/questionnaire remains saved/);
  assert.equal(JSON.parse(storage.get(key)).requestId,saved.requestId);
  attempt={profile:'iris',created:false,profile_exists:true,operation:{status:'failed'}};
  await window.onboarding(false);await $('btn-welcome-resume').onclick();
  assert.match(host.innerHTML,/left a Hermes profile folder/);
  assert.equal(storage.has(key),true);
  attempt={profile:'iris',created:true,profile_exists:true,operation:{status:'complete'}};
  await window.onboarding(false);await $('btn-welcome-resume').onclick();
  assert.equal(storage.has(key),false);
""")


def test_failed_attempt_review_reuses_private_connections_and_staging_id():
    run_setup_browser(r"""
  await window.onboarding(false);await $('btn-welcome-start').onclick();
  $('ob-tg-token').value='1234:synthetic-private-bot-token';$('ob-tg-userid').value='42';
  await $('ob-tg-save-btn').onclick();
  const key=[...storage.keys()][0],saved=JSON.parse(storage.get(key));
  assert.equal(posts.at(-1).payload.request_id,saved.requestId);
  assert.equal(storage.get(key).includes('synthetic-private-bot-token'),false);
  saved.phase='creating';saved.derived={};storage.set(key,JSON.stringify(saved));
  attempt={profile:'iris',created:false,profile_exists:false,operation:{status:'failed',error:'Try again'}};
  await window.onboarding(false);await $('btn-welcome-resume').onclick();
  $('ob-recovered-review').onclick();
  const reviewed=JSON.parse(storage.get(key));
  assert.equal(reviewed.phase,'reveal');assert.equal(reviewed.requestId,saved.requestId);
""")
