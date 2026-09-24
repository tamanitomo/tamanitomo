// Us: the page that replaced Together and Memories. Drives the shipped helpers
// and the page handler against stubbed endpoints -- no browser, no backend.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const root=path.join(__dirname,'../kit/app/static');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');
const index=read('index.html'),product=read('product.js'),us=read('us.js'),feelings=read('feelings.js'),css=read('product.css');

const sandbox={console,URL,URLSearchParams,Intl,Date,Math,Set,Map,Promise,Event:class{constructor(type){this.type=type;}}};
vm.createContext(sandbox);
const run=code=>vm.runInContext(code,sandbox);
// Values made inside the sandbox belong to another realm; compare their shape.
const same=(actual,expected,message)=>assert.equal(JSON.stringify(actual),JSON.stringify(expected),message);
run(index.match(/^const TABS=.*$/m)[0].replace('const TABS','var TABS'));
run(index.match(/^const esc=.*$/m)[0]);
run(index.match(/^const TAB_ALIASES=.*$/m)[0].replace('const TAB_ALIASES','var TAB_ALIASES'));
run(product.slice(product.indexOf('const primaryDestinations='),product.indexOf('const navigationButtons=')));
run(product.match(/^const stamp=.*$/m)[0]);run(product.match(/^const dayKey=.*$/m)[0]);run(product.match(/^const when=.*$/m)[0]);
run("var profileTimezone='UTC';var current='relationship';var workspaceHandlers={};function ago(){return 'an hour ago';}");
run(feelings);run(us);

/* ------------------------------------------------------------ navigation */
const tabs=run('TABS');
same(tabs.find(([id])=>id==='relationship'),['relationship','Us'],'1: the destination is called Us');
assert.equal(run("navShort.relationship"),'Us');
assert.ok(!tabs.some(([id])=>id==='knows'),'2: Memories is not a separate tab');
assert.ok(!run("navDestinations").includes('knows'),'2: not in the rail or More');
assert.equal(run("navBlurb.knows"),undefined);assert.equal(run("navShort.knows"),undefined);
assert.doesNotMatch(index,/id="knows"/,'2: no orphaned Memories section');
const keywords=vm.runInContext('('+product.match(/\(\{relationship:'[^}]*\}/)[0].slice(1)+')',sandbox);
const search=q=>tabs.filter(t=>t[0]!=='more').filter(t=>(t[1]+' '+t[0]+' '+(keywords[t[0]]||'')).toLowerCase().includes(q)).map(t=>t[0]);
for(const q of ['memories','memory','remembered','together','us','feelings','milestones'])
  assert.ok(search(q).includes('relationship'),`3: searching "${q}" finds Us`);
assert.ok(!search('memories').includes('knows'));

// 4: a saved pin, an old link, or an old call to 'knows' lands on Us.
sandbox.window={Appearance:{state:{nav_pins:['knows','relationship','photos','knows']}}};
run(product.match(/^const NAV_FREE_SLOTS=.*$/m)[0]);
run(product.slice(product.indexOf('const navPins=()=>{'),product.indexOf('function renderTabbar(')));
same(run('navPins()'),['relationship','photos'],'4: a Memories pin becomes Us, once');
(async()=>{
const rendered=[];
Object.assign(sandbox,{confirmEditorLeave:async()=>true,history:{replaceState(){}},location:{pathname:'/',search:''},
  render:name=>{rendered.push(name);},
  $:id=>id==='tabs'?{querySelectorAll:()=>[]}:{hidden:false,textContent:'x',innerHTML:''}});
sandbox.window.productNavigate=()=>{};
run(index.slice(index.indexOf('async function showTab(name){'),index.indexOf("$('tabs').innerHTML=TABS")));
await run("showTab('knows')");
assert.equal(run('current'),'relationship','4: legacy knows commits as relationship');
assert.deepEqual(rendered,['relationship']);
assert.match(read('workspace.js'),/initial=TAB_ALIASES\[initial\]\|\|initial/,'4: a #knows URL on load is redirected too');

/* ------------------------------------------------------------------ hero */
const romantic={stage:2,stage_name:'Chemistry',score:63,points:63,romantic_progression:true,pace:'natural',violations_count:0,description:'Sparks.'};
const warm={meters:{warmth:.82,trust:.8,hurt:0,irritation:0,longing:.55},personality:'steady',mood:'content',mood_at:'2026-09-23T10:00:00Z'};
const hero=sandbox.relationshipHero({intimacy:romantic},warm,'Nova');
assert.doesNotMatch(hero,/\d+%/,'5: no percentage in the hero');
assert.match(hero,/class="us-stage">Chemistry</);
assert.match(hero,/Things feel warm and secure\./);
assert.match(hero,/Very warm/);assert.match(hero,/Strong trust/);assert.match(hero,/Missing you/);
assert.doesNotMatch(hero,/Some hurt|friction/,'5: quiet meters stay quiet');
const details=sandbox.relationshipDetails({intimacy:romantic},warm,[],'Nova');
assert.match(details,/<details class="us-details">[\s\S]*63%[\s\S]*<\/details>/,'6: the exact score is kept, inside details');
assert.match(details,/meter-grid/,'6: the five meters are kept, inside details');
assert.doesNotMatch(details,/<details class="us-details" open/);
assert.match(sandbox.relationshipHero({intimacy:romantic},{meters:{warmth:.7,trust:.5,hurt:.6,irritation:0,longing:null}},'Nova'),/Something is still hurting between you\. Underneath it/);

const platonic={stage:2,stage_name:'Trusted',score:50,romantic_progression:false,connection_label:'Friendship',pace:'natural',violations_count:0};
const friendly=sandbox.relationshipHero({intimacy:platonic},warm,'Nova')+sandbox.relationshipDetails({intimacy:platonic},warm,[],'Nova');
assert.doesNotMatch(friendly,/Chemistry|Intimacy|Bonded/,'7: no romantic stages for a friendship');
assert.doesNotMatch(friendly,/us-stage-track/);
assert.match(friendly,/Friendship/);assert.match(friendly,/Trusted/);

const outsideDetails=html=>html.replace(/<details[\s\S]*?<\/details>/g,'');
const locked=sandbox.relationshipHero({intimacy:{...romantic,permanent_friend:true,violations_count:2}},warm,'Nova');
assert.match(outsideDetails(locked),/data-standing="permanent_friend"[\s\S]*Friendship established/,'8: permanent friendship stays in the open');
const revoked=sandbox.relationshipHero({intimacy:{...romantic,nsfw_revoked:true}},warm,'Nova');
assert.match(outsideDetails(revoked),/data-standing="nsfw_revoked"[\s\S]*Stepped back to friendship/,'9: revocation stays in the open');
assert.match(outsideDetails(sandbox.relationshipHero({intimacy:{...romantic,violations_count:1}},warm,'Nova')),/A boundary was crossed/);

/* -------------------------------------------------------------- the page */
const day=n=>new Date(Date.UTC(2026,8,23-n,12)).toISOString();
const moment=(id,kind,n,status='active')=>({id,kind:'moment',moment:kind,text:'Moment '+id,happened_on:'',status,recorded_at:day(n)});
function dataset({facts=0,moments=[],experiences=[],prefs=0,questions=0,loops=0,standing=0,intimacy=romantic,held=[]}={}){
  const cats=['likes','people','places','work','history','other'];
  return {
    '/relationship':{bars:{feelings:warm},pronoun_set:'she',intimacy,moments,kinds:{first:'Firsts'},milestones:[{label:'A first to remember',earned:true},{label:'An inside joke',earned:false}],settings:{relationship_progression:'milestones'}},
    '/ledgers':{facts:Array.from({length:facts},(_,i)=>({id:'f'+i,category:cats[i%cats.length],statement:(i===3?'You drink coffee black':'Fact number '+i),evidence:'Said so on day '+i,recorded_at:day(i%30)})),
      standing:Array.from({length:standing},(_,i)=>({instruction:'Please do not message before 8am',evidence:'asked'})),
      questions:Array.from({length:questions},(_,i)=>({text:'Why did you stop playing guitar? '+i})),
      preferences:Array.from({length:prefs},(_,i)=>({valence:['like','dislike','curious','mixed'][i%4],subject:'Subject '+i,text:'Detail '+i,recorded_at:day(i)}))},
    '/overview':{loops:Array.from({length:loops},(_,i)=>({title:'Show the old photograph '+i,detail:'promised'}))},
    '/feelings/experiences':{experiences,total:experiences.length,next_cursor:null},
    '/facts/held':{held}};
}
let calls=[],page;
const elements={};
const element=id=>elements[id]||(elements[id]={id,innerHTML:'',hidden:true,value:'',setAttribute(){},isConnected:true});
async function renderPage(data){
  calls=[];for(const k of Object.keys(elements))delete elements[k];
  Object.assign(sandbox,{$:element,chatName:()=>'Nova',
    api:async(p,opts)=>{calls.push([p,opts&&opts.method||'GET',opts&&opts.body]);if(p.includes('/forget')||p.endsWith('/decide'))return {};if(!(p in data))throw Error('unexpected '+p);return data[p];},
    notice:()=>{},dialog:(title,html)=>{element('dialog-body').innerHTML=html;element('dialog-title').textContent=title;}});
  run("current='relationship'");
  await run('workspaceHandlers.relationship()');
  page=element('relationship').innerHTML;
  return page;
}
const click=async(action,data={})=>{
  const target={dataset:{usAction:action,...data},disabled:false,setAttribute(){}};
  await element('relationship').onclick({target:{closest:()=>target}});
  return target;
};

// Headings, one h1, and the old checklist gone.
const busyMoments=[moment('m1','first',1),moment('m2','joke',3),moment('m3','ritual',5,'retired'),moment('m4','note',2),moment('m5','nickname',9)];
const experiences=[
  {id:'e1',kind:'connection',text:'Talked late',evidence:'"worth being tired"',at:day(0)},
  {id:'e2',kind:'rupture',text:'Something landed badly',evidence:'the argument',at:day(4)},
  {id:'e3',kind:'repair',text:'Came back to it',evidence:'apology',at:day(4),related:'e2'},
  {id:'e4',kind:'connection',text:'Was wrong',evidence:'x',at:day(6)},
  {id:'e5',kind:'correction',text:'Never happened',evidence:'x',at:day(5),related:'e4'}];
await renderPage(dataset({facts:40,moments:busyMoments,experiences,prefs:12,questions:3,loops:4,standing:3}));
assert.equal((page.match(/<h1/g)||[]).length,1);assert.match(page,/<h1 class="page-title">Our story<\/h1>/);
for(const h of ['Recently','Things that became ours','Remembered about you','Things Nova has discovered','Still between you'])
  assert.match(page,new RegExp('<h2[^>]*>'+h+'</h2>'),'section: '+h);
assert.doesNotMatch(page,/\d+ of \d+ earned|milestone-badge|In progress/,'11: no achievement checklist');
assert.doesNotMatch(page,/memory-kpi|About you<\/span>/,'no KPI strip');

// 10: keepsakes are only things that happened, and never retired ones.
const keepHtml=page.slice(page.indexOf('id="us-keepsakes"'),page.indexOf('id="us-memories"'));
assert.match(keepHtml,/Moment m1/);assert.match(keepHtml,/Moment m2/);assert.match(keepHtml,/Moment m5/);
assert.doesNotMatch(keepHtml,/Moment m3/,'10: a retired moment is not a keepsake');
assert.doesNotMatch(keepHtml,/Moment m4/,'10: notes are story, not keepsakes');
assert.doesNotMatch(keepHtml,/○/);

// The story: moments not already shown as keepsakes, feelings minus corrected ones.
const storyHtml=page.slice(page.indexOf('id="us-recent"'),page.indexOf('id="us-keepsakes"'));
assert.match(storyHtml,/Moment m4/);assert.doesNotMatch(storyHtml,/Moment m1/,'no event told twice');
assert.match(storyHtml,/You felt closer/);assert.match(storyHtml,/A rough moment/);assert.match(storyHtml,/Things softened/);
assert.doesNotMatch(storyHtml,/Was wrong|Never happened/,'corrections and what they corrected stay out');
assert.match(storyHtml,/<details class="us-story-evidence"><summary>Context &amp; evidence<\/summary><p>&quot;worth being tired&quot;/,'16: evidence available');
assert.doesNotMatch(page,/<details[^>]* open/,'16: and collapsed by default');
assert.doesNotMatch(page,/What moved the feelings/,'19: the full history is not dumped onto the page');

// 12: a preview, not the ledger.
assert.equal((page.match(/class="us-memory-row"/g)||[]).length,5,'12: memory preview is limited');
assert.match(page,/View all 40 memories/);
const cats=[...page.matchAll(/us-memory-icon" aria-hidden="true">([^<]+)</g)].map(m=>m[1]);
assert.ok(new Set(cats).size>=4,'the preview spreads across categories');

// 17: the companion's own preferences are read-only.
const prefHtml=page.slice(page.indexOf('id="us-discoveries"'),page.indexOf('id="us-threads"'));
assert.equal((prefHtml.match(/class="us-discovery /g)||[]).length,5);
assert.doesNotMatch(prefHtml,/<input|<textarea|data-us-action="(forget|edit|retire)"/,'17: no controls on their preferences');
await click('discoveries-all');
assert.equal((element('us-discoveries').innerHTML.match(/class="us-discovery /g)||[]).length,12);

// 18: questions and carried threads together.
const threadHtml=element('us-threads').innerHTML;
assert.match(threadHtml,/Wants to ask[\s\S]*Why did you stop playing guitar/);assert.match(threadHtml,/Still carrying[\s\S]*Show the old photograph/);
assert.equal((threadHtml.match(/class="us-thread /g)||[]).length,5);
assert.match(threadHtml,/data-us-action="threads-all"/);

// Plain notes lead with their own words, not a repeated label.
assert.doesNotMatch(storyHtml,/A moment worth keeping/);
assert.match(storyHtml,/class="us-story-text is-lead">Moment m4</);

// The preview prefers statements about a person to verbatim quotes and dated episodes.
const picked=sandbox.usMemoryPreview([
  {id:'q1',category:'likes',statement:'Robin said: "nah"',recorded_at:day(0)},
  {id:'q2',category:'other',statement:'On 2026-09-21 Robin cleaned',recorded_at:day(0)},
  {id:'g1',category:'likes',statement:'Robin likes Fire Emblem',recorded_at:day(9)},
  {id:'g2',category:'people',statement:'Robin has a sister',recorded_at:day(9)}],2).map(f=>f.id);
same(picked,['g1','g2'],'readable facts first');
assert.equal(sandbox.usMemoryPreview([{id:'q',category:'other',statement:'Robin said: "hi"'}],5).length,1,'quotes still fill an otherwise empty preview');
// A fact filed twice in different words takes one preview slot, and the other
// stays readable under it as a Similar memory -- neither is hidden.
{
  const rows=sandbox.usMemoryPreview([
    {id:'a',category:'logistics',statement:'Robin has an older 4 GB GTX 1050 Ti available to install in a spare PC.'},
    {id:'b',category:'other',statement:'Robin has an older 4 GB GTX 1050 Ti available for the spare PC.'},
    {id:'c',category:'likes',statement:'Robin likes tea'}],5);
  same(rows.map(f=>f.id),['c','a'],'one slot for the pair');
  same(rows[1].similar.map(f=>f.id),['b'],'the other is grouped, not dropped');
  const html=sandbox.memoryRowHTML(rows[1]);
  assert.match(html,/Similar memory \(1\)/);assert.match(html,/available for the spare PC/);
  assert.match(html,/data-fact="b"/,'a grouped memory can still be marked incorrect');
}
// Word order is meaning: both are shown.
{
  const rows=sandbox.usMemoryPreview([{id:'a',category:'people',statement:'Robin introduced Alice to Kit.'},
    {id:'b',category:'people',statement:'Robin introduced Kit to Alice.'}],5);
  const shown=rows.flatMap(f=>[f.id,...f.similar.map(g=>g.id)]);
  same(shown.sort(),['a','b'],'neither introduction is discarded');
  assert.ok(rows.flatMap(f=>[f,...f.similar]).every(f=>f.statement.includes('introduced')));
}
// Only the same text collapses, by the same rule the ledger uses to refuse a duplicate.
{
  const cases=JSON.parse(fs.readFileSync(path.join(__dirname,'canonical_statement_cases.json'),'utf8'));
  for(const [a,b] of cases.same)
    assert.equal(sandbox.usFactKey({statement:a}),sandbox.usFactKey({statement:b}),`same: ${a} / ${b}`);
  for(const [a,b] of [...cases.different,...cases.revised])
    assert.notEqual(sandbox.usFactKey({statement:a}),sandbox.usFactKey({statement:b}),`different: ${a} / ${b}`);
  same(sandbox.usMemoryPreview([{id:'a',category:'likes',statement:'Robin likes tea.'},{id:'b',category:'other',statement:' Robin  likes tea.'}],5).map(f=>f.id).length,1);
}
// Pairs that only open alike are separate memories, each in its own slot.
for(const [a,b] of [['Robin likes Fire Emblem.','Robin dislikes Fire Emblem.'],
  ["Robin's sister Alice lives in Raleigh.","Robin's sister Beth lives in Raleigh."],
  ['Robin has a GTX 1050 Ti in the first spare PC.','Robin has a GTX 1050 Ti in the second spare PC.'],
  ['Robin has a 4 GB GTX 1050 Ti in the spare PC.','Robin has an 8 GB GTX 1050 Ti in the spare PC.'],
  ['Robin has a GTX 1050 Ti in the spare PC.','Robin has a GTX 1060 in the spare PC.'],
  ['Robin keeps a GTX 1050 Ti in the spare PC at home.','Robin keeps a GTX 1050 Ti in the spare PC at the office.'],
  ['Robin likes tea.','Robin does not like tea.'],['Robin likes tea.','Robin never likes tea.']])
  assert.equal(sandbox.usMemoryPreview([{id:'a',category:'likes',statement:a},{id:'b',category:'likes',statement:b}],5).length,2,`distinct: ${a} / ${b}`);
// The library lists every active record.
{
  const pair=[{id:'a',category:'logistics',statement:'Robin has an older 4 GB GTX 1050 Ti available to install in a spare PC.'},
    {id:'b',category:'other',statement:'Robin has an older 4 GB GTX 1050 Ti available for the spare PC.'}];
  assert.equal(sandbox.renderMemoryLibrary(pair).matches,2,'the library lists every active record');
  assert.equal(pair[0].similar,undefined,'the preview does not mutate the records it was given');
}
assert.match(us,/never hides a memory because it looks like another one/);
// A written statement says it is a summary; a recorded one says nothing extra.
assert.match(sandbox.memoryRowHTML({id:'p',category:'likes',statement:'Robin likes tea.',evidence:'I love tea',statement_origin:'model_paraphrase'}),
  /Summed up from what you said; the quote below is exact/);
assert.doesNotMatch(sandbox.memoryRowHTML({id:'p',category:'likes',statement:'Robin likes tea.',evidence:'I love tea'}),/Summed up/);
assert.doesNotMatch(us,/Worded by (?:her|him)\b/,'no fixed pronoun for the companion');
// A long list of questions does not hide every carried thread.
same(sandbox.usOpenThreads([{text:'q1'},{text:'q2'},{text:'q3'}],[{title:'t1'}]).map(x=>x.text),['q1','t1','q2','q3']);

// Standing instructions are not memories.
assert.doesNotMatch(page.slice(page.indexOf('id="us-memories"'),page.indexOf('id="us-discoveries"')),/before 8am/);
assert.match(page,/3 standing preferences or boundaries are being kept\./);
assert.match(page,/<ul class="us-standing-list" id="us-standing-list" hidden>/);

// 15: marking a memory incorrect still calls the correction endpoint.
await click('forget',{fact:'f3'});
assert.deepEqual(calls.at(-1).slice(0,2),['/facts/f3/forget','POST'],'15: correction endpoint');
assert.match(element('us-memories').innerHTML,/View all 39 memories/);

// 13 and 14: the full library searches and filters.
const facts=dataset({facts:60})['/ledgers'].facts;
assert.equal(sandbox.renderMemoryLibrary(facts,{query:'coffee'}).matches,1,'13: search by statement');
assert.equal(sandbox.renderMemoryLibrary(facts,{query:'day 7'}).matches,1,'13: search by evidence');
assert.equal(sandbox.renderMemoryLibrary(facts,{category:'people'}).matches,10,'14: category filter');
assert.equal((sandbox.renderMemoryLibrary(facts).html.match(/class="memory-card"/g)||[]).length,24,'library pages too');
await click('library');
assert.equal(element('dialog-title').textContent,'All memories');
element('memory-search').value='number 7';element('memory-search').oninput();
assert.match(element('memory-library-results').innerHTML,/Fact number 7/);
element('memory-search').value='coffee';element('memory-search').oninput();
assert.match(element('memory-library-results').innerHTML,/Nothing matches/,'a fact marked incorrect has left the library');
element('memory-search').value='number 7';element('memory-search').oninput();
assert.equal((element('memory-library-results').innerHTML.match(/class="memory-card"/g)||[]).length,1);

// 19: Talk about this drafts, never sends.
const box={value:'',focused:false,dispatched:[],focus(){this.focused=true;},dispatchEvent(e){this.dispatched.push(e.type);},setSelectionRange(){},
  requestSubmit(){throw Error('must not submit');},form:{requestSubmit(){throw Error('must not submit');}}};
const store=new Map();let posted=0;
Object.assign(sandbox,{chatKey:k=>'chat-'+k,sessionStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)},
  post:async()=>{posted++;},showTab:async name=>{run(`current=${JSON.stringify(name)}`);elements['chat-message']=box;},
  requestAnimationFrame:fn=>fn()});
assert.equal(sandbox.threadDraft({kind:'question',text:'Why did you stop playing guitar?'}),'You had this question for me: “Why did you stop playing guitar?”','legacy and new questions share one neutral wrapper');
await click('talk',{draft:'You had this question for me: “Why did you stop playing guitar?”'});
assert.equal(run('current'),'chat');
assert.equal(store.get('chat-draft'),'You had this question for me: “Why did you stop playing guitar?”','19: the composer holds the draft');
assert.equal(box.value,store.get('chat-draft'));assert.ok(box.focused);assert.deepEqual(box.dispatched,['input']);
assert.equal(posted,0,'19: nothing was sent');
assert.equal(calls.filter(([p])=>p.includes('chat')).length,0);
store.set('chat-draft','half a thought');box.value='';
await click('talk',{draft:'Can we come back to “x”?'});
assert.equal(store.get('chat-draft'),'half a thought\n\nCan we come back to “x”?','an unsent draft is kept, not overwritten');

// The page draws before the slow /overview arrives, then fills in carried threads.
{
  const data=dataset({questions:1,loops:1});let release;
  const slow=new Promise(r=>release=r);
  for(const k of Object.keys(elements))delete elements[k];
  Object.assign(sandbox,{api:async p=>p==='/overview'?slow:data[p]});
  run("current='relationship'");
  const done=run('workspaceHandlers.relationship()');
  for(let i=0;i<20&&!element('relationship').innerHTML.includes('Our story');i++)await new Promise(r=>setImmediate(r));
  assert.match(element('relationship').innerHTML,/Our story/,'drawn without waiting for /overview');
  assert.doesNotMatch(element('us-threads').innerHTML,/Show the old photograph/);
  release(data['/overview']);await done;
  assert.match(element('us-threads').innerHTML,/Still carrying[\s\S]*Show the old photograph/,'threads arrive after');
}

// 20: a brand-new companion reads as new, not broken.
await renderPage(dataset({intimacy:{...romantic,stage:0,stage_name:'Just Met'}}));
for(const copy of ['Your shared story is still beginning','Firsts, rituals, nicknames and little traditions','Nothing has been written down about you yet',
  'Nova has not recorded any preferences of her own yet','Nothing is hanging between conversations right now'])
  assert.ok(page.includes(copy),'20: empty state: '+copy);
assert.doesNotMatch(page,/See all shared moments|View all 0/);
// Experiences failing must not take the page down.
const partial=dataset({facts:2});delete partial['/feelings/experiences'];delete partial['/overview'];
await renderPage(partial);assert.match(page,/Remembered about you/);assert.match(page,/Your shared story is still beginning/);

// 21: a long history stays a page, not a dump.
const many=Array.from({length:200},(_,i)=>moment('x'+i,['first','joke','note','ritual'][i%4],i%60));
const feel=Array.from({length:100},(_,i)=>({id:'k'+i,kind:'connection',text:'c'+i,evidence:'e',at:day(i%40)}));
await renderPage(dataset({facts:500,moments:many,experiences:feel,prefs:40,questions:30,loops:30,standing:10}));
assert.equal((page.match(/class="us-story-event /g)||[]).length,12,'21: story is paged');
assert.equal((page.match(/class="us-keepsake"/g)||[]).length,6);
assert.equal((page.match(/class="us-memory-row"/g)||[]).length,5);
assert.ok(page.length<60000,'21: page stays small with 500 facts ('+page.length+' chars)');
await click('story-more');
assert.equal((element('us-recent').innerHTML.match(/class="us-story-event /g)||[]).length,24,'Show earlier adds a page');

// 22: copy about the companion uses the configured pronouns, not a flattened they.
for(const [set,name,poss] of [['she','Nova','her'],['he','Kit','his'],['they','Alex','their']]){
  assert.match(sandbox.usDiscoveriesHTML([],5,name,set),new RegExp(`${name} has not recorded any preferences of ${poss} own yet\\.`),'22: '+set);
  assert.match(sandbox.relationshipDetails({intimacy:romantic,pronoun_set:set},warm,[],name),
    new RegExp(`${name} holds genuine agency and has preferences and boundaries of ${poss} own\\.`),'22: '+set);
  if(set!=='they'){
    assert.doesNotMatch(sandbox.usDiscoveriesHTML([],5,name,set),/of their own/,'22: a '+set+' is not flattened to they');
    assert.doesNotMatch(sandbox.relationshipDetails({intimacy:romantic,pronoun_set:set},warm,[],name),/of their own/);
  }
}
// Unknown pronouns fall back to singular they.
assert.match(sandbox.usDiscoveriesHTML([],5,'Nova'),/Nova has not recorded any preferences of their own yet/);
// The page reads the set from /relationship.
{
  const he=dataset({intimacy:romantic});he['/relationship'].pronoun_set='he';
  await renderPage(he);
  assert.match(page,/Nova has not recorded any preferences of his own yet/,'22: from the endpoint');
  assert.match(page,/boundaries of his own/);
}

// 23: Us touches no media and makes no profile-less requests.
assert.doesNotMatch(us,/mediaUrl|rawMediaUrl|\.src=|fetch\(/,'23: no media or raw fetches on Us');
assert.ok(calls.every(([p])=>p.startsWith('/')),'23: every request goes through the profile-scoped api()');

// 24: nothing on Us needs a hover to reach.
const usCss=css.slice(css.indexOf('/* Us / shared relationship story'));
assert.doesNotMatch(usCss,/:hover/,'24: no hover-only affordances');
assert.doesNotMatch(us,/title="/,'24: no tooltip-only explanations');
assert.doesNotMatch(us,/<div[^>]*onclick|<div[^>]*data-us-action/,'actions are buttons, not clickable divs');

// Similar grouping keeps symbol suffixes: C, C++ and C# are different languages.
for(const [a,b] of [['Robin writes C.','Robin writes C++.'],['Robin writes C#.','Robin writes C.'],['Robin writes C++.','Robin writes C#.']])
  assert.equal(sandbox.usLikelySameFact({statement:a},{statement:b}),false,`not similar: ${a} / ${b}`);
assert.equal(sandbox.usLikelySameFact({statement:'Robin writes C++ at work.'},{statement:'Robin writes C++ at work'}),true);
// A big similar group is paged, not dumped into the first markup.
{
  const group={id:'g',category:'other',statement:'Robin has a GTX 1050 Ti for the spare PC.',
    similar:Array.from({length:8},(_,i)=>({id:'s'+i,category:'other',statement:'Similar '+i,evidence:'quote '+i}))};
  const html=sandbox.memoryRowHTML(group);
  assert.equal((html.match(/class="us-similar-row"/g)||[]).length,3,'first page only');
  assert.doesNotMatch(html,/quote 5/,'later evidence is not in the initial markup');
  assert.match(html,/Similar memories \(8\)/);assert.match(html,/data-us-action="similar-more"[^>]*data-shown="3"/);
  assert.equal((sandbox.usSimilarRowsHTML(group,6).match(/class="us-similar-row"/g)||[]).length,6);
  assert.doesNotMatch(sandbox.usSimilarRowsHTML(group,8),/similar-more/);
}

// Needs review: a count, a queue that says when it failed, and explicit decisions.
{
  const held=[{id:'held-1',statement:'Robin loves hiking.',evidence:'2026-09-20: My sister loves hiking.',source:'session:a message:2',
               category:'likes',reasons:['the quote is about someone else']},
              {id:'held-2',statement:'Robin said: "I like tea."',evidence:'2026-09-20: I like tea.',source:'session:a message:3',
               category:'likes',reasons:['transcript_wrapper']}];
  await renderPage(dataset({facts:4,held}));
  assert.match(page,/data-us-action="review">Needs review \(2\)</,'the count is on the page');
  assert.doesNotMatch(page,/Robin loves hiking/,'held statements are not in the preview');
  await click('review');
  const queue=element('memory-library-results').innerHTML;
  assert.match(queue,/Robin loves hiking\./);assert.match(queue,/Your exact words<\/span><br>“2026-09-20: My sister loves hiking\.”/);
  assert.match(queue,/Source: session:a message:2/);assert.match(queue,/about someone else/);
  assert.match(queue,/worded as a transcript/);
  const lib=element('memory-library');
  await lib.onclick({target:{closest:()=>({dataset:{usAction:'held-dismiss',held:'held-2'},disabled:false})}});
  same(calls.at(-1).slice(0,3),['/facts/held/held-2/decide','POST',JSON.stringify({decision:'dismiss'})]);
  assert.doesNotMatch(element('memory-library-results').innerHTML,/I like tea/,'a decided item leaves the queue');
  assert.match(element('us-memories').innerHTML,/Needs review \(1\)/);

  const broken=dataset({facts:4});delete broken['/facts/held'];
  await renderPage(broken);
  assert.match(page,/Could not load memories that need review/,'a failed load is not an empty queue');
  assert.doesNotMatch(page,/Needs review \(0\)/);
  await renderPage(dataset({facts:4}));
  assert.doesNotMatch(page,/Needs review|need review/,'an empty queue is quiet');
}

console.log('Us page regressions passed');
})().catch(error=>{console.error(error);process.exit(1);});
