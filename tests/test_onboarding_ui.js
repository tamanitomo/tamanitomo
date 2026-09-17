// Exercise the creation interview's derivation without a browser.
// The real persona and relationship-frame catalogs are passed in by the Python
// wrapper, so this fails if the interview can ever propose something the
// backend would reject.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assert=require('node:assert/strict');

const source=fs.readFileSync(path.join(__dirname,'../kit/app/static/onboarding.js'),'utf8');
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
const colleague=derive(QUIZ.map((q,i)=>i===7?3:null),catalog);
assert.equal(colleague.agent_type,'colleague');
assert.notEqual(colleague.boundary,'girlfriend');

// "Like a partner" must not quietly become a colleague.
const partner=derive(QUIZ.map((q,i)=>i===7?2:null),catalog);
assert.equal(partner.agent_type,'companion');

// The contact questions set what they say they set.
const quiet=derive(QUIZ.map((q,i)=>i===6?2:null),catalog);
assert.equal(quiet.permit_image,'no');
assert.equal(quiet.outreach,'never');
const open=derive(QUIZ.map((q,i)=>i===6?0:null),catalog);
assert.equal(open.permit_image,'yes');
assert.equal(open.outreach,'free');
assert.equal(open.outreach_per_day,6);

// The interview never emits `explicit`; romance is carried by the frame alone.
for(let pick=0;pick<4;pick++)
  assert.equal(all(pick).explicit,undefined,'interview must not set explicit');

console.log('Creation interview derivation passed');
