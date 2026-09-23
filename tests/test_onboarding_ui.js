// Exercise the creation interview's derivation without a browser.
// The real persona and relationship-frame catalogs are passed in by the Python
// wrapper, so this fails if the interview can ever propose something the
// backend would reject.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assert=require('node:assert/strict');

const source=fs.readFileSync(path.join(__dirname,'../kit/app/static/onboarding.js'),'utf8');
assert.match(source,/id="ob-api-model" value="openrouter\/auto"/);
assert.doesNotMatch(source,/anthropic\/claude-3\.5-sonnet/);
const slice=source.slice(source.indexOf('const QUIZ=['),source.indexOf('/* ------------------------------------------------------------------ helpers */'));
const sandbox={};vm.createContext(sandbox);
// `const` bindings stay lexical inside the script, so publish them explicitly.
vm.runInContext(slice+'\n;globalThis.__exports={QUIZ,PERSONA_AXES,AXES,derive};',sandbox);
const {QUIZ,PERSONA_AXES,derive}=sandbox.__exports;

const personas=JSON.parse(fs.readFileSync(path.join(__dirname,'../kit/personas/personas.json'),'utf8'));
const boundaryKeys=(process.argv[2]||'').split(',').filter(Boolean);
const answerKeys=new Set((process.argv[3]||'').split(',').filter(Boolean));
assert.ok(boundaryKeys.length,'the wrapper must pass the real relationship frames');
assert.ok(answerKeys.size,'the wrapper must pass the real answer keys');
const catalog={personas,boundaries:Object.fromEntries(boundaryKeys.map(k=>[k,{label:k}]))};

// Every personality the interview can land on must exist in the catalog.
for(const key of Object.keys(PERSONA_AXES))
  assert.ok(personas[key],`interview can propose unknown persona: ${key}`);

// Every direct setting an option carries must be a key the backend accepts.
for(const item of QUIZ)
  for(const opt of item.a)
    for(const key of Object.keys(opt[2]||{}))
      assert.ok(answerKeys.has(key),`quiz emits unknown answer key: ${key}`);

const all=(pick)=>derive(QUIZ.map((q,i)=>Math.min(pick,q.a.length-1)),catalog);

// Every personality is reachable by someone who answers like it. Averaging axes
// used to leave twelve of the twenty unreachable.
for(const key of Object.keys(PERSONA_AXES)){
  const picks=QUIZ.map(q=>{const i=q.a.findIndex(o=>(o[3]||[])[0]===key);return i>=0?i:q.a.findIndex(o=>(o[3]||[]).includes(key));});
  assert.equal(derive(picks.map(i=>i<0?null:i),catalog).persona,key,`persona ${key} cannot be reached`);
}

// Skipping every question still produces a complete, valid configuration.
const skipped=derive(new Array(QUIZ.length).fill(null),catalog);
assert.ok(personas[skipped.persona]);
assert.ok(boundaryKeys.includes(skipped.boundary),skipped.boundary);
assert.equal(skipped.agent_type,'companion');
assert.equal(skipped.outreach,'updates_only');
assert.equal(skipped.relationship_pace,'natural');

// Whatever is answered, the frame and persona stay inside the catalogs.
for(let pick=0;pick<4;pick++){
  const got=all(pick);
  assert.ok(personas[got.persona],`pick ${pick} -> unknown persona ${got.persona}`);
  assert.ok(boundaryKeys.includes(got.boundary),`pick ${pick} -> unknown frame ${got.boundary}`);
  assert.ok(['slow','natural','quick'].includes(got.relationship_pace));
  assert.ok(['companion','colleague','worker'].includes(got.agent_type));
}

// "Like a brilliant colleague" must produce a colleague, not a romance.
const colleague=derive(QUIZ.map((q,i)=>i===QUIZ.length-1?3:null),catalog);
assert.equal(colleague.agent_type,'colleague');
assert.notEqual(colleague.boundary,'girlfriend');

// "Like a partner" must not quietly become a colleague.
const partner=derive(QUIZ.map((q,i)=>i===QUIZ.length-1?2:null),catalog);
assert.equal(partner.agent_type,'companion');

// The contact questions set what they say they set.
const quiet=derive(QUIZ.map((q,i)=>i===QUIZ.length-2?2:null),catalog);
assert.equal(quiet.permit_image,'no');
assert.equal(quiet.outreach,'never');
const open=derive(QUIZ.map((q,i)=>i===QUIZ.length-2?0:null),catalog);
assert.equal(open.permit_image,'yes');
assert.equal(open.outreach,'free');
assert.equal(open.outreach_per_day,6);

// The interview never emits `explicit`; romance is carried by the frame alone.
for(let pick=0;pick<4;pick++)
  assert.equal(all(pick).explicit,undefined,'interview must not set explicit');

console.log('Creation interview derivation passed');

// Story choices must never override a direct relationship or pace preference.
for(let story=0;story<4;story++){
  const picks=QUIZ.map((q,i)=>i<QUIZ.length-3?Math.min(story,q.a.length-1):null);
  assert.equal(derive(picks,catalog).boundary,'best-friend');
  picks[QUIZ.length-1]=0;picks[QUIZ.length-3]=0;
  const friend=derive(picks,catalog);
  assert.equal(friend.boundary,'best-friend');
  assert.equal(friend.relationship_pace,'slow');
  picks[QUIZ.length-1]=3;
  assert.equal(derive(picks,catalog).agent_type,'colleague');
}

// Exercise real onboarding event handlers through the real fetch helper. The
// previous three-argument api calls silently sent GET without the credentials.
(async()=>{
  const elements=new Map(),requests=[];
  const element=id=>{
    if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',style:{},dataset:{},
      classList:{toggle(){}},scrollIntoView(){},focus(){},closest(){return {dataset:{}};},
      querySelectorAll(){return [];},querySelector(){return null;}});
    return elements.get(id);
  };
  const page={window:{},$:element,esc:x=>String(x??''),options:()=>'',
    PROFILE:'nova',INSTALLATION:'existing',scheduleLabel:x=>x,
    action:async(path,payload)=>{requests.push({url:'/api'+path,method:'POST',body:JSON.stringify(payload)});},
    token:'fixture',scoped:x=>x,setInterval:()=>1,clearInterval(){},
    fetch:async(url,opts)=>{
      requests.push({url,...opts});
      return {ok:true,json:async()=>url.endsWith('/catalog')?catalog:
        url.endsWith('/environment')?{}:url.endsWith('/profiles')?{profiles:[]}:url.endsWith('/onboarding/schedule')?{jobs:[],offset_minutes:0}:{session_id:'fixture-session',status:'pending'}};
    }};
  vm.createContext(page);
  const html=fs.readFileSync(path.join(__dirname,'../kit/app/static/index.html'),'utf8');
  const apiSource=html.slice(html.indexOf('async function api('),html.indexOf('\nfunction showPinModal'));
  vm.runInContext(apiSource+"\nconst post=(path,payload={})=>api(path,{method:'POST',body:JSON.stringify(payload)});\n"+source,page);
  await page.window.onboarding(false);
  element('btn-welcome-start').onclick();
  element('ob-tg-token').value='fixture-bot-token';
  element('ob-tg-userid').value='123';
  await element('ob-tg-save-btn').onclick();
  let request=requests.find(r=>r.url.endsWith('/telegram'));
  assert.equal(request.method,'POST');
  assert.deepEqual(JSON.parse(request.body),{token:'fixture-bot-token',user_id:'123'});
  await element('btn-ch-next').onclick();
  element('btn-pur-next').onclick();
  element('btn-meet-next').onclick();                  // "surprise me", no age band
  for(let i=0;i<QUIZ.length;i++)element('quiz-skip').onclick();
  element('cust-image-style').value='anime-soft';
  element('btn-rev-accept').onclick();
  element('btn-own-next').onclick();                   // who keeps what
  element('ob-api-provider').value='openrouter';
  element('ob-api-key').value='fixture-key';
  element('ob-api-model').value='fixture-model';
  await element('ob-api-save-btn').onclick();
  request=requests.find(r=>r.url.endsWith('/inference'));
  assert.equal(request.method,'POST');
  assert.equal(JSON.parse(request.body).api_key,'fixture-key');
  element('ob-oauth-provider').value='openai-codex';
  await element('ob-oauth-start-btn').onclick();
  request=requests.find(r=>r.url.endsWith('/oauth/start'));
  assert.equal(request.method,'POST');
  assert.equal(JSON.parse(request.body).provider,'openai-codex');
  await element('btn-inf-finish').onclick();
  element('ob-schedule-approved').checked=false;
  await element('ob-schedule-create').onclick();
  const created=requests.find(r=>r.url==='/api/profiles'&&r.method==='POST');
  assert.equal(JSON.parse(created.body).answers.image_style,'anime-soft','explicit image style survives profile creation');
  const answers=JSON.parse(created.body).answers;
  // The quiz now chooses a look and shows it for editing before anything is saved.
  assert.equal(answers.visual,'set','the look chosen by the quiz reaches setup');
  assert.equal(answers.soul_locks.appearance,true,'appearance is locked unless opened');
  assert.ok(['she','he'].includes(answers.pronoun_set),'"surprise me" settles on a pronoun');
  console.log('Onboarding request contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
