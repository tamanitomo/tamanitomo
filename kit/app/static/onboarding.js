/* Interactive First-Visit Onboarding Experience for Tamanitomo.
   Includes communication channel setup (Telegram vs Web), purpose selection
   (Relational vs Worker), twelve story dilemmas and three explicit preference questions,
   companion card reveal (editable name) with Accept or Customize drawer,
   and Model setup (Cloud OAuth device code flow or API Key). */
(function(){

/* ------------------------------------------------------------------ the quiz
   Three parts, in the spirit of Pokémon Mystery Dungeon:
     1. sixteen story scenes that decide the personality. Each answer awards
        points to one or two named personalities (the first gets 2, the second
        1); the highest tally wins, and the five axes below only break a tie.
        Every personality leads at least three answers and appears in five,
        so all twenty can come out -- averaging axes, as this used to, left
        twelve of them unreachable.
     2. seven scenes about their world: work, rhythm, a free afternoon, how you
        met, and how they look. These pick from the catalogue, and the result
        is shown and editable before anything is saved.
     3. three direct questions: pace, contact and the relationship itself.
   Option shape: [text, axes, direct settings, personality tags, world picks]. */
const QUIZ=[
 {q:"After a long journey, you reach a tiny inn. Your travelling companion saves you a seat by the fire. What do you hope they do?",
  sub:"The fire is low, the road was long, and there is finally time to breathe.",
  a:[["Pour something warm and listen to the story of my day.",{warmth:3,energy:-1,candor:-1},{},['warm','nurturing']],
     ["Unroll the map and help me make sense of where things went wrong.",{candor:3,drive:1},{},['pragmatic','analytical']],
     ["Tell me the absurd thing that happened while I was away.",{energy:3,warmth:1},{},['bright','mischievous']],
     ["Keep the seat beside me warm and let me speak when I am ready.",{energy:-2,drive:-1,candor:-1},{},['quiet','shy']]]},
 {q:"At a fork in the forest, you disagree about which path to take. How does your companion handle it?",
  sub:"Two paths, one map, and neither of you is entirely sure.",
  a:[["Be gentle, but tell me what they really think.",{warmth:3,candor:1},{},['protective','romantic']],
     ["Challenge my reasoning directly and explain why.",{candor:3,drive:1},{},['sharp','intense']],
     ["Ask questions so we can work it out together.",{warmth:1,candor:2},{},['social','analytical']],
     ["Give me room, then return to it calmly.",{energy:-2,warmth:1,candor:-1},{},['stoic','steady']]]},
 {q:"A night market appears in a town that was empty a moment ago. You have until sunrise. Where do you go together?",
  sub:"Music drifts over the rooftops. Every stall seems to hold a different possibility.",
  a:[["Follow the lanterns down the alley neither of us can find on the map.",{energy:3,drive:3},{},['adventurous','whimsical']],
     ["Visit the stall where we can invent a tiny world in a bottle.",{warmth:2,energy:2,drive:1},{},['creative','sunny']],
     ["Find a rooftop, share a snack, and watch it all unfold.",{warmth:2,energy:-2,drive:-1},{},['melancholy','romantic']],
     ["Find the clockmaker and ask how this impossible market works.",{candor:2,drive:1,closeness:-1},{},['analytical','sharp']]]},
 {q:"Your little airship refuses to start, and the last ferry leaves soon. What kind of help would you welcome?",
  sub:"The engine gives one indignant cough. Your companion looks from it to you.",
  a:[["Roll up their sleeves and point out the first thing we should check.",{candor:2,drive:2},{},['pragmatic','protective']],
     ["Lay out our options: repair, ferry, or a different adventure.",{candor:2,warmth:1,closeness:-1},{},['steady','analytical']],
     ["Remind me we can figure it out, one small step at a time.",{warmth:3,drive:1},{},['nurturing','sunny']],
     ["Suggest an unusual solution involving the market’s clockmaker.",{energy:2,drive:3},{},['mischievous','creative']]]},
 {q:"Your companion keeps a room above the village bookshop. On your first visit, what catches your eye?",
  sub:"They have gone downstairs to make tea. Their room tells a story of its own.",
  a:[["Half-built inventions and postcards from unexpected adventures.",{energy:3,drive:2},{},['creative','adventurous']],
     ["A favourite cup, a well-tended plant, and a place set for me.",{warmth:2,energy:-1,candor:-1},{},['nurturing','protective']],
     ["Books full of pointed margin notes and one very dry joke.",{candor:3,energy:1},{},['sharp','mischievous']],
     ["A sketchbook by the window, with more inside than they say aloud.",{warmth:1,energy:-2},{},['shy','melancholy']]]},
 {q:"A dragon the size of a teapot has moved into your backpack. It insists it is your guide. What happens next?",
  sub:"It has a very important hat and absolutely no sense of direction.",
  a:[["We appoint it captain and see where the day takes us.",{energy:3,drive:2},{},['whimsical','bright']],
     ["We ask what it knows, then quietly keep our own map.",{candor:2,drive:1,closeness:-1},{},['stoic','pragmatic']],
     ["We make it a comfortable nest. It seems lonely.",{warmth:3,closeness:1},{},['nurturing','shy']],
     ["We share a look and enjoy the joke without a word.",{energy:-1,candor:1},{},['quiet','steady']]]},
 {q:"You find a letter addressed to your future self. Your companion is beside you. How would you like to open it?",
  sub:"The seal is warm, as though it has just been pressed.",
  a:[["Read it together. I want someone to share the feeling.",{warmth:3,closeness:3},{},['romantic','intense']],
     ["Read it privately, then talk when I am ready.",{energy:-1,closeness:-2},{},['quiet','stoic']],
     ["Guess what it says first. Make a game of it.",{energy:3,closeness:1},{},['bright','social']],
     ["Ask them to help turn its advice into a plan.",{candor:2,drive:2,closeness:-1},{},['protective','pragmatic']]]},
 {q:"The village festival needs one last attraction. You have a shed, some string, and an afternoon. What do you build together?",
  sub:"There is no prize. The children have already started queuing.",
  a:[["An impossible puppet theatre with a story we invent as we go.",{energy:2,drive:2},{},['whimsical','creative']],
     ["A quiet corner where anyone can leave a wish.",{warmth:3,energy:-1,closeness:1},{},['shy','romantic']],
     ["A puzzle machine. We will make sure every clue works.",{candor:2,drive:1},{},['analytical','steady']],
     ["A ridiculous obstacle course. We volunteer to go first.",{energy:3,drive:3},{},['social','adventurous']]]},
 {q:"You have spent hours making a gift, but it is not quite working. What would you want your companion to say?",
  sub:"Paint on your sleeves. Glue on the table. A very lopsided little moon.",
  a:[["The care is visible. Let’s keep the part that feels like you.",{warmth:3,candor:-1},{},['warm','romantic']],
     ["Here is what is wrong, and one way we can fix it.",{candor:3,drive:2},{},['sharp','pragmatic']],
     ["What if the crooked moon is the beginning of a better idea?",{energy:2,drive:3},{},['creative','whimsical']],
     ["Want company while you decide? We do not have to solve it now.",{warmth:2,energy:-2,drive:-1,candor:-1},{},['melancholy','quiet']]]},
 {q:"A rainstorm closes the mountain pass. You are safe in an old observatory until morning. How do you pass the time?",
  sub:"The telescope points at clouds. Someone has left a kettle and a chessboard.",
  a:[["Trade stories we have never told each other.",{warmth:2,closeness:3},{},['intense','romantic']],
     ["Work on separate things, comfortably together.",{energy:-2,closeness:-1},{},['stoic','quiet']],
     ["Learn to repair the telescope together.",{candor:2,drive:2,closeness:-1},{},['protective','analytical']],
     ["Invent increasingly unlikely names for the constellations.",{energy:3,warmth:2},{},['bright','social']]]},
 {q:"Your companion remembers something you mentioned weeks ago. What kind of surprise would delight you?",
  sub:"They slide a small parcel across the breakfast table.",
  a:[["A tiny reminder of an ordinary moment we shared.",{warmth:3,closeness:3},{},['sunny','warm']],
     ["A clever tool for the project I keep getting stuck on.",{candor:2,drive:2,closeness:-1},{},['pragmatic','protective']],
     ["A ticket to something neither of us has tried.",{energy:3,drive:3},{},['adventurous','intense']],
     ["A book, with no expectation that I read it immediately.",{energy:-2,warmth:1,closeness:-1},{},['shy','quiet']]]},
 {q:"At the end of the journey, you find a new path behind the inn. Your companion pauses at the gate. What feels right?",
  sub:"There is plenty of time. The next chapter does not need to start today.",
  a:[["Ask what they would choose. I like an independent point of view.",{candor:3,drive:2,closeness:-1},{},['intense','sharp']],
     ["Make a little plan together, with room for surprises.",{warmth:2,drive:1},{},['sunny','social']],
     ["Race them to the first bend.",{energy:3,drive:3},{},['mischievous','bright']],
     ["Sit by the gate for a while. Being here is enough.",{warmth:2,energy:-2,closeness:2},{},['melancholy','stoic']]]},
 {q:"A stranger at the crossroads asks your companion for directions to a town neither of you knows. What do they do?",
  sub:"The signpost has been turned around, possibly on purpose.",
  a:[["Admit they have no idea and help find someone who does.",{candor:2,warmth:1},{},['steady','analytical']],
     ["Point confidently down a road and grin at you.",{energy:3,candor:-1},{},['mischievous','adventurous']],
     ["Walk them there, even though it is well out of the way.",{warmth:3,drive:1},{},['warm','nurturing']],
     ["Say 'no idea, sorry' and keep walking.",{candor:2,energy:-1,closeness:-2},{},['stoic','sharp']]]},
 {q:"It is your companion’s birthday. How do they want to spend it?",
  sub:"You asked. They have clearly been thinking about it.",
  a:[["A big, loud dinner with everyone they love crammed round one table.",{energy:3,warmth:2},{},['social','bright']],
     ["Somewhere quiet, with just you.",{warmth:2,energy:-1,closeness:3},{},['romantic','shy']],
     ["Doing something they have never done before.",{energy:3,drive:3},{},['adventurous','intense']],
     ["Honestly? Like any other day, with better cake.",{energy:-1,candor:1},{},['steady','pragmatic']]]},
 {q:"You have had a terrible day and it shows. What does your companion do first?",
  sub:"You have not said a word yet. They have already noticed.",
  a:[["Makes you eat something, then listens.",{warmth:3,drive:1},{},['nurturing','protective']],
     ["Gets angry on your behalf, loudly.",{energy:2,candor:2,closeness:1},{},['intense','protective']],
     ["Makes you laugh until you forget why you were upset.",{energy:3,warmth:2},{},['sunny','mischievous']],
     ["Sits beside you and says nothing at all.",{energy:-2,warmth:1,candor:-1},{},['quiet','melancholy']]]},
 {q:"The village holds its yearly contest. What does your companion enter?",
  sub:"There is a very small trophy and a very large amount of pride at stake.",
  a:[["The pie contest. They bring enough for everyone.",{warmth:3,energy:1},{},['warm','social']],
     ["Storytelling night, with a tale nobody saw coming.",{energy:2,drive:1},{},['whimsical','creative']],
     ["The puzzle hunt. They have already solved half of it.",{candor:2,drive:2},{},['analytical','sharp']],
     ["Nothing. They would rather watch you and be quietly delighted.",{warmth:2,energy:-2,closeness:2},{},['romantic','steady']]]},
 // ---- their world: picks from the catalogue, shown and editable at the reveal
 {q:"The innkeeper asks your companion what they do when they are not travelling. What do they say, with a grin?",
  sub:"The whole common room leans in a little to hear.",world:true,
  a:[["“I make things people look at.”",{},{},[],{occupation:['4','10','11','18','13']}],
     ["“I look after people.”",{},{},[],{occupation:['1','2','12','17']}],
     ["“I work with my hands — food, wood, engines, plants.”",{},{},[],{occupation:['6','7','8','9','14','15','19']}],
     ["“I figure things out for a living.”",{},{},[],{occupation:['3','16','5','21']}]]},
 {q:"The rooster crows at dawn. Where is your companion?",
  sub:"The village is only just waking up.",world:true,
  a:[["Already up, halfway through a walk.",{},{},[],{daily_rhythm:['1','5']}],
     ["Asleep. They were up past two with a project.",{},{},[],{daily_rhythm:['2','6']}],
     ["Getting ready for a proper day’s work.",{},{},[],{daily_rhythm:['4','11']}],
     ["Somewhere unexpected. They do not really do routines.",{},{},[],{daily_rhythm:['9','14','15']}]]},
 {q:"Your companion has one free afternoon in the village. Where do you find them?",
  sub:"You go looking, and it does not take long.",world:true,
  a:[["In the bookshop, three books deep.",{},{},[],{likes:['2','12','15']}],
     ["Out on the trails, muddy and happy.",{},{},[],{likes:['3','9','19']}],
     ["In a kitchen or a workshop, making something.",{},{},[],{likes:['4','6','13','18']}],
     ["At the café with headphones, a game or a film.",{},{},[],{likes:['5','7','8','20']}]]},
 {q:"How did the two of you first cross paths?",
  sub:"You both tell it slightly differently.",world:true,
  a:[["Over an argument about a book.",{},{},[],{met:['6','17']}],
     ["Rain, a crowded café, and one free seat.",{},{},[],{met:['7','16']}],
     ["Through friends. It took a while to notice each other.",{},{},[],{met:['2','14','11']}],
     ["A message that went to the wrong person.",{},{},[],{met:['13','4','5']}]]},
 {q:"A travelling painter sketches your companion. Which colours does she reach for first, for their hair?",
  sub:"She squints at them, then at her paint box.",world:true,
  a:[["Deep browns and near-black.",{},{},[],{hair_color:['1','2','3','4','15']}],
     ["Warm golds and honey.",{},{},[],{hair_color:['5','8','10','11']}],
     ["Copper, auburn and ginger.",{},{},[],{hair_color:['6','7','12','13']}],
     ["Something bold — silver, or a colour from a bottle.",{},{},[],{hair_color:['16','20','21','22','24']}]]},
 {q:"You spot your companion waiting at the station before they see you. What gives them away?",
  sub:"The platform is busy. You would know them anywhere.",world:true,
  a:[["Small and quick — easy to miss in a crowd.",{},{},[],{frame:'small'}],
     ["Tall — a head above everyone else.",{},{},[],{frame:'tall'}],
     ["Strong shoulders and a solid, easy stance.",{},{},[],{frame:'strong'}],
     ["Soft and relaxed, comfortable in their own skin.",{},{},[],{frame:'soft'}]]},
 {q:"They have dressed for your first proper meeting. What are they wearing?",
  sub:"They pretend they did not think about it. They did.",world:true,
  a:[["Whatever is comfortable — soft, worn-in, cosy.",{},{},[],{look:'comfy'}],
     ["Something sharp and put-together.",{},{},[],{look:'sharp'}],
     ["Something with character — vintage, arty or alternative.",{},{},[],{look:'character'}],
     ["Ready for anything outdoors or on the move.",{},{},[],{look:'active'}]]},
 // ---- direct preferences
 {q:"How quickly would you like familiarity to grow?",
  sub:"This is a setting you control. Warmth does not automatically mean romance.",direct:'pace',
  a:[["Slowly. Let shared experiences earn familiarity.",{},{relationship_pace:'slow'}],
     ["Naturally, with room to discover what works.",{},{relationship_pace:'natural'}],
     ["A warm, familiar tone from the beginning.",{},{relationship_pace:'quick'}]]},
 {q:"When you are away, how would you like them to get in touch?",
  sub:"These are actual contact permissions. Quiet hours still apply; you can review them next.",direct:'contact',
  a:[["Social messages and photos are welcome, up to six messages a day.",{},{permit_image:'yes',outreach:'free',outreach_per_day:6}],
     ["Meaningful updates, up to three a day. Ask before sharing photos.",{},{permit_image:'ask',outreach:'updates_only',outreach_per_day:3}],
     ["Replies only. No messages or photos unless I ask.",{},{permit_image:'no',outreach:'never',outreach_per_day:1}]]},
 {q:"What kind of relationship would you like to begin with?",
  sub:"Only this answer sets the relationship. You can change the proposed frame before creating anyone.",direct:'relationship',
  a:[["A friend, with no romantic expectation.",{},{boundary:'best-friend',agent_type:'companion'}],
     ["A connection with room for flirtation.",{},{boundary:'next-door',agent_type:'companion'}],
     ["A romantic partner.",{},{boundary:'girlfriend',agent_type:'companion'}],
     ["A colleague with personality and shared projects.",{},{boundary:'creative-partner',agent_type:'colleague'}]]}
];

/* Each personality as a point in five-axis space: only used to break a tie. */
const PERSONA_AXES={
  warm:{warmth:3,energy:1,candor:0,drive:1,closeness:1},
  steady:{warmth:1,energy:-1,candor:1,drive:0,closeness:0},
  bright:{warmth:2,energy:3,candor:0,drive:2,closeness:0},
  sharp:{warmth:0,energy:1,candor:3,drive:1,closeness:0},
  quiet:{warmth:1,energy:-2,candor:0,drive:-1,closeness:0},
  adventurous:{warmth:1,energy:3,candor:1,drive:3,closeness:0},
  creative:{warmth:2,energy:2,candor:0,drive:1,closeness:0},
  analytical:{warmth:0,energy:0,candor:1,drive:0,closeness:-1},
  social:{warmth:2,energy:3,candor:0,drive:2,closeness:1},
  romantic:{warmth:3,energy:0,candor:0,drive:1,closeness:3},
  protective:{warmth:2,energy:0,candor:1,drive:2,closeness:1},
  sunny:{warmth:3,energy:2,candor:-1,drive:1,closeness:1},
  mischievous:{warmth:2,energy:2,candor:2,drive:2,closeness:1},
  melancholy:{warmth:2,energy:-1,candor:0,drive:-1,closeness:2},
  intense:{warmth:3,energy:2,candor:3,drive:2,closeness:2},
  nurturing:{warmth:3,energy:0,candor:1,drive:2,closeness:1},
  stoic:{warmth:0,energy:-2,candor:1,drive:0,closeness:-1},
  whimsical:{warmth:1,energy:1,candor:-1,drive:0,closeness:0},
  shy:{warmth:2,energy:-2,candor:-1,drive:-2,closeness:1},
  pragmatic:{warmth:1,energy:0,candor:2,drive:1,closeness:-1}
};
const AXES=['warmth','energy','candor','drive','closeness'];

/* Catalogue entries that suit each personality, for the parts no scene asks
   about directly. Ids refer to personas/catalog.json; one is rolled per person. */
const PERSONA_PICKS={
  warm:{core:['3','19','1','12'],voice:['1','13','15'],flirtation:['1','12','15'],essence:['1','2','9'],texting:3},
  steady:{core:['2','9','10','17'],voice:['7','2','16'],flirtation:['10','17','4'],essence:['4','12'],texting:2},
  bright:{core:['16','7','11'],voice:['5','17','8'],flirtation:['2','9','14'],essence:['9','7'],texting:1},
  sharp:{core:['4','6','18'],voice:['4','14','11','2'],flirtation:['6','16','13'],essence:['11','17'],texting:5},
  quiet:{core:['3','15','1'],voice:['9','18','6'],flirtation:['4','18','10'],essence:['6','4'],texting:5},
  adventurous:{core:['20','13','6'],voice:['5','10','17'],flirtation:['3','9','14'],essence:['7','10'],texting:1},
  creative:{core:['8','11','13'],voice:['8','10','13'],flirtation:['11','1','8'],essence:['8','15'],texting:4},
  analytical:{core:['1','12','17'],voice:['12','2','16'],flirtation:['16','7','6'],essence:['11','13'],texting:4},
  social:{core:['16','12','7'],voice:['1','5','15'],flirtation:['12','2','9'],essence:['9','14'],texting:3},
  romantic:{core:['19','3','10'],voice:['9','6','10'],flirtation:['8','4','15'],essence:['16','15','2'],texting:4},
  protective:{core:['14','9','2'],voice:['7','14','1'],flirtation:['10','15','3'],essence:['12','4'],texting:2},
  sunny:{core:['16','1','10'],voice:['5','1','17'],flirtation:['12','14','2'],essence:['9','15'],texting:3},
  mischievous:{core:['5','7','11'],voice:['8','15','11'],flirtation:['2','13','9'],essence:['3','17'],texting:1},
  melancholy:{core:['18','3','15'],voice:['6','9','10'],flirtation:['4','18','11'],essence:['6','13'],texting:4},
  intense:{core:['13','14','4'],voice:['17','4','14'],flirtation:['3','16','14'],essence:['5','17'],texting:1},
  nurturing:{core:['14','10','19'],voice:['1','7','13'],flirtation:['15','10','12'],essence:['2','12'],texting:3},
  stoic:{core:['2','9','6'],voice:['16','18','11'],flirtation:['18','10','17'],essence:['4','6'],texting:5},
  whimsical:{core:['11','20','8'],voice:['13','10','8'],flirtation:['1','11','9'],essence:['8','18'],texting:1},
  shy:{core:['15','3','1'],voice:['9','6','18'],flirtation:['5','14','4'],essence:['6','13'],texting:1},
  pragmatic:{core:['17','4','9'],voice:['7','2','4'],flirtation:['6','7','10'],essence:['11','12'],texting:5}
};
/* Heights, builds and styles differ by list; these are catalogue ids per list. */
const FRAME={
  female:{small:{height:['3','4','5','6'],build:['12','4','10','17']},tall:{height:['13','14','15','16'],build:['8','13','16']},
          strong:{height:['7','8','9','10','11'],build:['6','9','14','18','1']},soft:{height:['6','7','8','9','10'],build:['2','7','11','15']}},
  male:{small:{height:['3','4','5','6'],build:['12','10','4','2']},tall:{height:['12','13','14','15','16'],build:['7','15','17']},
        strong:{height:['7','8','9','10','11'],build:['3','6','11','14','1','13']},soft:{height:['7','8','9','10'],build:['8','9','16']}}
};
const LOOK={
  female:{comfy:['1','2','19'],sharp:['3','5','7','14','16','20'],character:['4','6','10','11','13','17'],active:['8','9','12','15','18']},
  male:{comfy:['1','2','17'],sharp:['3','4','7','13','14','20'],character:['5','9','10','15','18','19'],active:['6','8','11','12','16']}
};
const NAMES={she:['Mira','Juno','Hazel','Iris','Esme','Nell','Tessa','Clara','Maren','Ivy'],
             he:['Theo','Rowan','Eli','Jonah','Silas','Milo','Arlo','Callum','Ezra','Finn'],
             they:['Sage','River','Ash','Quinn','Rory','Lark','Robin','Emery']};
const AGE_BANDS=[['Early twenties',23],['Late twenties',28],['Thirties',34],['Forties',44],['Fifty and up',54]];

function tally(picks){
  const score={},axis={};for(const k of AXES)axis[k]=0;
  picks.forEach((choice,i)=>{
    const opt=choice==null?null:QUIZ[i]?.a[choice];if(!opt)return;
    (opt[3]||[]).forEach((p,rank)=>{score[p]=(score[p]||0)+(rank===0?2:1);});
    for(const k of AXES)axis[k]+=(opt[1]&&opt[1][k])||0;
  });
  return {score,axis};
}
function cosine(a,b){let d=0,na=0,nb=0;for(const k of AXES){d+=(a[k]||0)*(b[k]||0);na+=(a[k]||0)**2;nb+=(b[k]||0)**2;}return na&&nb?d/Math.sqrt(na*nb):0;}

function derive(picks,catalog){
  const {score,axis}=tally(picks);
  const direct={},world={};
  picks.forEach((choice,i)=>{
    const opt=choice==null?null:QUIZ[i]?.a[choice];if(!opt)return;
    Object.assign(direct,opt[2]||{});Object.assign(world,opt[4]||{});
  });
  let persona='warm',best=-Infinity;
  for(const key of Object.keys(PERSONA_AXES)){
    if(!catalog.personas?.[key])continue;
    const s=(score[key]||0)+0.01*cosine(axis,PERSONA_AXES[key]);
    if(s>best){best=s;persona=key;}
  }
  const frames=Object.keys(catalog.boundaries||{});
  const boundary=frames.includes(direct.boundary)?direct.boundary:'best-friend';
  return Object.assign({
    persona,boundary,relationship_pace:'natural',
    agent_type:'companion',
    outreach:'updates_only',outreach_per_day:3,
    permit_image:'ask',permit_voice:'ask',
    quiet_start:'23:00',quiet_end:'08:00',
    share_people:'no',visual:'set',image_style:'none'
  },direct,{boundary,world,_axis:axis});
}

/* A small seeded generator, so the same answers give the same person and
   "shuffle" is a new seed rather than a different algorithm. */
function seeded(seed){let s=seed>>>0||1;return()=>{s=(s+0x6D2B79F5)>>>0;let t=s;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296;};}
function hashSeed(text){let h=2166136261;for(const ch of String(text)){h^=ch.charCodeAt(0);h=Math.imul(h,16777619);}return h>>>0;}

/* Everything the SOUL needs beyond the personality, as catalogue ids. */
function resolveCompanion(derived,catalog,pronouns,seed){
  const rnd=seeded(seed);
  const oneOf=list=>list[Math.floor(rnd()*list.length)];
  const cats=catalog.catalog?.categories||{};
  const list=pronouns==='he'?'male':'female';
  const ids=key=>(cats[key]?.[list]||cats[key]?.female||[]).map(r=>r.id);
  const w=derived.world||{};
  const P=PERSONA_PICKS[derived.persona]||PERSONA_PICKS.warm;
  const frame=FRAME[list][w.frame||oneOf(['small','tall','strong','soft'])];
  const flawsFor=(cats.flaws?.[list]||[]).filter(r=>(r.personas||[]).includes(derived.persona)).map(r=>r.id);
  const out={
    occupation:oneOf(w.occupation||ids('occupation')),daily_rhythm:oneOf(w.daily_rhythm||ids('daily_rhythm')),
    likes:oneOf(w.likes||ids('likes')),met:oneOf(w.met||ids('met').filter(id=>!['1'].includes(id))),
    hair_color:oneOf(w.hair_color||ids('hair_color')),hair_style:oneOf(ids('hair_style')),
    eyes:oneOf(ids('eyes')),complexion:oneOf(ids('complexion')),
    height:oneOf(frame.height),build:oneOf(frame.build),
    style:oneOf(LOOK[list][w.look||oneOf(['comfy','sharp','character','active'])]),
    marks:rnd()<0.45?oneOf(ids('marks')):'',
    core:oneOf(P.core),voice:oneOf(P.voice),flirtation:oneOf(P.flirtation),essence:oneOf(P.essence),
    flaws:oneOf(flawsFor.length?flawsFor:ids('flaws')),texting_style:P.texting
  };
  if(list==='male')out.facial_hair=rnd()<0.5?oneOf(ids('facial_hair')):'';
  return out;
}

/* ------------------------------------------------------------------ helpers */
const OUTREACH_LABEL={free:'Social messages welcome',updates_only:'Only meaningful updates',never:'Replies only — never writes first'};
const PACE_LABEL={slow:'Slow and gradual',natural:'Natural',quick:'Open to quicker familiarity'};
const PERMIT_LABEL={yes:'Allowed',ask:'Ask first',no:'Never'};
const TYPE_LABEL={companion:'Companion',colleague:'Colleague',worker:'Worker'};

window.onboarding=async function(adopt){
  const catalog=await api('/catalog');
  let envInfo={has_installed_profiles:false,telegram:{configured:false},inference:{configured:false}};
  try{envInfo=await api('/onboarding/environment');}catch(e){}

  const target=$(adopt?'environment-onboarding':'onboarding');
  const other=$(adopt?'onboarding':'environment-onboarding');if(other)other.innerHTML='';
  if(!target)return;
  const section=target.closest('section');
  if(section)section.dataset.creating='1';

  // A neutral placeholder until the owner names this profile.
  const draft={
    profile:'companion',agent:'Companion',human_names:'Friend',pronoun_set:'they',human_pronoun_set:'they',
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',
    birthdate:'',age:25,human_boundary:'',hope:'',vault:'',
    purpose:'relational',
    channel:'web',
    telegram_token:'',telegram_user_id:'',
    inference_mode:'auto',provider:'',model:'',api_key:''
  };

  let picks=new Array(QUIZ.length).fill(null);
  let derived=null,step=0,look=null,lookSeed=0;
  // A worker gets the personality scenes and the pace question; no world, no contact or relationship.
  const order=()=>QUIZ.map((q,i)=>i).filter(i=>draft.purpose!=='worker'||(!QUIZ[i].world&&(!QUIZ[i].direct||QUIZ[i].direct==='pace')));
  let oauthPollInterval=null;
  let scheduleApproved=false;

  const shell=(inner,cls='')=>{
    target.onkeydown=null;
    target.innerHTML=`<div class="card creator ${cls}">${inner}</div>`;
    target.scrollIntoView({behavior:'smooth',block:'start'});
  };

  /* ---------------------------------------------------------- 1. Welcome */
  function welcome(){
    shell(`
      <div class="creator-head reveal" style="text-align:center">
        <span class="eyebrow" style="letter-spacing:0.08em;text-transform:uppercase;color:var(--accent)">✨ Welcome to Tamanitomo</span>
        <h2 style="margin:10px 0 12px;font-size:32px">Bring Your Companion to Life</h2>
        <p class="dim" style="max-width:520px;margin:0 auto 20px;line-height:1.5">
          Each companion is a Hermes profile with its own identity, memories, and routine.
          This workspace belongs to you; you can create more companions later.
        </p>
      </div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0">
        <div style="padding:14px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
          <strong style="display:block;margin-bottom:4px">1. Communication</strong>
          <p class="small dim">Telegram bot on your phone or local web workspace.</p>
        </div>
        <div style="padding:14px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
          <strong style="display:block;margin-bottom:4px">2. Nature & Purpose</strong>
          <p class="small dim">Relational companion with emotions or focused worker.</p>
        </div>
        <div style="padding:14px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
          <strong style="display:block;margin-bottom:4px">3. A little adventure</strong>
          <p class="small dim">Twelve short scenes, then three choices about what you want. Skip any question.</p>
        </div>
        <div style="padding:14px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
          <strong style="display:block;margin-bottom:4px">4. Meet & connect</strong>
          <p class="small dim">Review your companion and connect a conversation model.</p>
        </div>
      </div>
      <div class="creator-actions" style="justify-content:center">
        <button type="button" class="act" id="btn-welcome-start" style="padding:12px 32px;font-size:16px">Begin →</button>
      </div>`);
    $('btn-welcome-start').onclick=()=>channelStep();
  }

  /* ---------------------------------------------------------- 2. Channel Selection */
  function channelStep(){
    const tgConfigured=envInfo?.telegram?.configured;
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 1 of 6 · Channel</span>
        <h2>How will you talk to your companion?</h2>
        <p class="dim">Choose how you'd like to chat. You can connect Telegram now or chat purely in this web browser.</p>
      </div>
      ${tgConfigured?`
        <div class="notice-strip status-good" style="margin-bottom:18px">
          <p><strong>✅ Telegram Gateway Detected</strong></p>
          <p class="small dim">A Telegram bot token is already configured in this environment (${esc(envInfo.telegram.token_preview||'active')}).</p>
        </div>`:''}
      <div class="creator-form">
        <div style="display:grid;gap:12px">
          <label style="display:flex;align-items:flex-start;gap:12px;padding:14px;border:1px solid var(--border);border-radius:8px;cursor:pointer;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
            <input type="radio" name="channel_pick" value="telegram" ${tgConfigured?'checked':''} style="margin-top:4px">
            <div>
              <strong>Telegram Bot (Recommended for 24/7 access)</strong>
              <p class="small dim" style="margin-top:3px">Chat directly with your companion on your phone or desktop, with notifications and voice notes.</p>
            </div>
          </label>
          <label style="display:flex;align-items:flex-start;gap:12px;padding:14px;border:1px solid var(--border);border-radius:8px;cursor:pointer;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
            <input type="radio" name="channel_pick" value="web" ${!tgConfigured?'checked':''} style="margin-top:4px">
            <div>
              <strong>Web Workspace Only</strong>
              <p class="small dim" style="margin-top:3px">Chat right here in this browser tab. You can always configure Telegram later in Settings.</p>
            </div>
          </label>
        </div>

        <div id="tg-guide-box" style="margin-top:14px;padding:16px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px dashed var(--border);display:${draft.channel==='telegram'&&!tgConfigured?'block':'none'}">
          <h4 style="margin:0 0 8px">Telegram Setup Guide (Takes 60 seconds):</h4>
          <ol class="small dim" style="padding-left:18px;margin:0 0 14px;line-height:1.6">
            <li>Open Telegram and chat with <a href="https://t.me/botfather" target="_blank" rel="noopener"><strong>@BotFather</strong></a>. Send <code>/newbot</code>.</li>
            <li>Give your bot a friendly name (e.g. <em>My Companion</em>) and a username ending in <code>bot</code>.</li>
            <li>Copy the <strong>HTTP API Token</strong> BotFather gives you (e.g. <code>123456789:ABCdefGhIJK...</code>).</li>
            <li>Open <a href="https://t.me/userinfobot" target="_blank" rel="noopener"><strong>@userinfobot</strong></a> and press Start to see your numeric <strong>Id</strong> (e.g. <code>987654321</code>).</li>
          </ol>
          <div style="display:grid;gap:10px">
            <label>Telegram Bot Token
              <input type="password" autocomplete="off" id="ob-tg-token" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" value="${esc(draft.telegram_token)}">
            </label>
            <label>Your Numeric User ID
              <input type="text" id="ob-tg-userid" placeholder="987654321" value="${esc(draft.telegram_user_id)}">
              <small class="dim">Ensures only you can talk to your companion.</small>
            </label>
            <button type="button" class="quiet small" id="ob-tg-save-btn" style="justify-self:start;margin-top:4px">Save Telegram Credentials</button>
            <span id="ob-tg-status" class="small" style="margin-top:2px"></span>
          </div>
        </div>

        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-ch-back">← Back</button>
          <button type="button" class="act" id="btn-ch-next">Next: Purpose →</button>
        </div>
      </div>`);

    for(const r of target.querySelectorAll('input[name="channel_pick"]')){
      r.onchange=()=>{
        const isTg=r.value==='telegram';
        $('tg-guide-box').style.display=isTg?'block':'none';
      };
    }

    $('ob-tg-save-btn').onclick=async()=>{
      const token=$('ob-tg-token').value.trim();
      const userId=$('ob-tg-userid').value.trim();
      if(!token){$('ob-tg-status').innerHTML='<span style="color:var(--warn)">Please enter a Bot Token.</span>';return;}
      $('ob-tg-status').innerHTML='<span class="dim">Saving...</span>';
      try{
        const res=await post('/onboarding/telegram',{token,user_id:userId});
        draft.telegram_token=token;draft.telegram_user_id=userId;
        $('ob-tg-status').innerHTML='<span style="color:var(--good)">✅ Saved successfully!</span>';
      }catch(e){
        $('ob-tg-status').innerHTML=`<span style="color:var(--warn)">${esc(e.message||'Failed to save token')}</span>`;
      }
    };

    $('btn-ch-back').onclick=()=>welcome();
    $('btn-ch-next').onclick=async()=>{
      const picked=target.querySelector('input[name="channel_pick"]:checked')?.value||'web';
      draft.channel=picked;
      if(picked==='telegram'){
        const token=$('ob-tg-token').value.trim();
        const userId=$('ob-tg-userid').value.trim();
        if(!token&&!tgConfigured){$('ob-tg-status').textContent='Save your Telegram details, or choose Web Workspace Only.';return;}
        if(token&&(draft.telegram_token!==token||draft.telegram_user_id!==userId)){
          try{
            await post('/onboarding/telegram',{token,user_id:userId});
            draft.telegram_token=token;draft.telegram_user_id=userId;
          }catch(e){$('ob-tg-status').textContent=e.message;return;}
        }
      }
      purposeStep();
    };
  }

  /* ---------------------------------------------------------- 3. Purpose Selection */
  function purposeStep(){
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 2 of 6 · Companion Purpose</span>
        <h2>What kind of companion do you want?</h2>
        <p class="dim">Decide how your companion interacts with you.</p>
      </div>
      <div class="creator-form">
        <div style="display:grid;gap:14px">
          <label style="display:flex;align-items:flex-start;gap:14px;padding:16px;border:1px solid var(--border);border-radius:8px;cursor:pointer;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
            <input type="radio" name="purpose_pick" value="relational" ${draft.purpose==='relational'?'checked':''} style="margin-top:4px">
            <div>
              <strong style="font-size:16px">Relational Companion (Recommended)</strong>
              <p class="small dim" style="margin:4px 0 0;line-height:1.5">
                A companion with a life of their own, inner thoughts, routines, and relationship growth.
                Features emotional meters, daily journals, presence, and friendship that deepens naturally over time.
              </p>
            </div>
          </label>
          <label style="display:flex;align-items:flex-start;gap:14px;padding:16px;border:1px solid var(--border);border-radius:8px;cursor:pointer;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
            <input type="radio" name="purpose_pick" value="worker" ${draft.purpose==='worker'?'checked':''} style="margin-top:4px">
            <div>
              <strong style="font-size:16px">Worker Companion with Continuity</strong>
              <p class="small dim" style="margin:4px 0 0;line-height:1.5">
                A focused assistant with saved context across sessions and projects,
                without emotional meters, feelings, or relationship escalation.
              </p>
            </div>
          </label>
        </div>
        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-pur-back">← Back</button>
          <button type="button" class="act" id="btn-pur-next">Next: Discovery Quiz →</button>
        </div>
      </div>`);

    $('btn-pur-back').onclick=()=>channelStep();
    $('btn-pur-next').onclick=()=>{
      draft.purpose=target.querySelector('input[name="purpose_pick"]:checked')?.value||'relational';
      step=0;
      meetStep();
    };
  }

  /* ---------------------------------------------------------- 3b. Who you are hoping to meet */
  function meetStep(){
    const pron=draft.pronoun_set_chosen?draft.pronoun_set:'';
    const card=(name,value,title,body,checked)=>`<label class="meet-card"><input type="radio" name="${name}" value="${value}" ${checked?'checked':''}><span><strong>${title}</strong>${body?`<small class="dim">${body}</small>`:''}</span></label>`;
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Before the adventure</span>
        <h2>Who are you hoping to meet?</h2>
        <p class="dim">Two quick things the story can’t decide for you. Everything else comes from your answers.</p>
      </div>
      <div class="creator-form">
        <fieldset class="meet-group"><legend>They are…</legend>
          ${card('meet_who','she','A woman','',pron==='she')}
          ${card('meet_who','he','A man','',pron==='he')}
          ${card('meet_who','they','Someone non-binary','They / them',pron==='they')}
          ${card('meet_who','surprise','Surprise me','The quiz decides',!pron)}
        </fieldset>
        <fieldset class="meet-group"><legend>Around what age?</legend>
          ${AGE_BANDS.map(([label,age])=>card('meet_age',String(age),label,'',Number(draft.age)===age)).join('')}
        </fieldset>
        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-meet-back">← Back</button>
          <button type="button" class="act" id="btn-meet-next">Begin the adventure →</button>
        </div>
      </div>`);
    $('btn-meet-back').onclick=()=>purposeStep();
    $('btn-meet-next').onclick=()=>{
      let who=target.querySelector('input[name="meet_who"]:checked')?.value||'surprise';
      if(who==='surprise')who=Math.random()<0.5?'she':'he';
      draft.pronoun_set=who;draft.pronoun_set_chosen=true;
      const age=Number(target.querySelector('input[name="meet_age"]:checked')?.value);
      if(age)draft.age=age;
      step=0;questionStep();
    };
  }

  /* ---------------------------------------------------------- 4. PMD Mystery Dungeon Quiz */
  function questionStep(){
    const seq=order(),total=seq.length,index=seq[step],item=QUIZ[index];
    const part=item.direct?'Make it yours':item.world?'Their world':'Your little adventure';
    shell(`
      <div class="quiz-progress" role="group" aria-label="Question ${step+1} of ${total}">
        ${seq.map((_,i)=>`<span class="${i<step?'is-done':i===step?'is-now':''}"></span>`).join('')}
        <small>${step+1} / ${total}</small>
      </div>
      <div class="quiz-body">
        <span class="eyebrow" style="color:var(--accent)">${part} · Question ${step+1}</span>
        <h2 style="margin-top:6px">${esc(item.q)}</h2>
        <p class="quiz-sub">${esc(item.sub)}</p>
        <div class="quiz-options">
          ${item.a.map((opt,i)=>`<button type="button" class="quiz-option${picks[index]===i?' is-chosen':''}" data-pick="${i}">
            <span class="quiz-key">${String.fromCharCode(65+i)}</span><span>${esc(opt[0])}</span></button>`).join('')}
        </div>
      </div>
      <div class="creator-actions">
        <button type="button" class="quiet" id="quiz-back">${step===0?'← Who you’re meeting':'← Previous'}</button>
        <button type="button" class="link-button" id="quiz-skip">Skip this question</button>
      </div>`,'is-quiz');

    for(const b of target.querySelectorAll('[data-pick]'))b.onclick=()=>{picks[index]=Number(b.dataset.pick);advance();};
    $('quiz-skip').onclick=()=>{picks[index]=null;advance();};
    $('quiz-back').onclick=()=>{if(step===0)meetStep();else{step--;questionStep();}};

    target.tabIndex=-1;target.focus({preventScroll:true});
    target.onkeydown=e=>{
      const n=/^[a-dA-D]$/.test(e.key)?e.key.toLowerCase().charCodeAt(0)-97:(/^[1-4]$/.test(e.key)?Number(e.key)-1:-1);
      if(n>=0&&n<item.a.length){e.preventDefault();picks[index]=n;advance();}
    };
  }

  function advance(){
    if(step<order().length-1){step++;questionStep();}
    else{
      derived=derive(picks,catalog);
      if(draft.purpose==='worker'){
        derived.agent_type='worker';
        derived.boundary='creative-partner';
        derived.outreach='never';derived.permit_image='no';derived.permit_voice='no';
      }
      lookSeed=hashSeed(picks.join(',')+draft.pronoun_set+draft.age);
      look=resolveCompanion(derived,catalog,draft.pronoun_set,lookSeed);
      if(!draft.agent_named){const names=NAMES[draft.pronoun_set]||NAMES.they;draft.agent=names[lookSeed%names.length];}
      revealStep();
    }
  }

  /* ---------------------------------------------------------- 5. Reveal Companion (Editable identity) */
  function revealStep(){
    if(!derived)derived=derive(picks,catalog);
    const p=catalog.personas[derived.persona]||{};
    const b=catalog.boundaries[derived.boundary]||{};
    const companionName=draft.agent||'Companion';

    shell(`
      <div class="creator-head reveal" style="text-align:center">
        <span class="eyebrow" style="color:var(--accent);letter-spacing:0.08em;text-transform:uppercase">✨ Companion Discovered</span>
        <h2 style="font-size:36px;margin:8px 0">${esc(companionName)}</h2>
        <p class="dim" style="max-width:540px;margin:0 auto">
          A suggested communication style. Make it your own below.
        </p>
      </div>

      <div class="card" style="padding:22px;border:1px solid var(--accent);background:color-mix(in srgb,var(--surface) 90%,var(--accent) 10%);border-radius:12px;margin:20px 0">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
          <div style="width:54px;height:54px;border-radius:50%;background:var(--accent);color:var(--on-accent);display:grid;place-items:center;font-size:24px;font-weight:700">
            ${esc(companionName[0]||'S')}
          </div>
          <div>
            <h3 style="margin:0 0 3px;font-size:20px">${esc(companionName)}</h3>
            <span class="pill status-good">${esc(p.label||derived.persona)}</span>
            <span class="pill">${esc(b.label||derived.boundary)}</span>
            <span class="pill">${esc(TYPE_LABEL[derived.agent_type]||derived.agent_type)}</span>
          </div>
        </div>
        <p class="dim" style="margin:0 0 14px;line-height:1.5">${esc(p.blurb||p.description||'A thoughtful presence tuned to your pace.')}</p>
        <dl class="reveal-list">
          <div><dt>Pace</dt><dd>${esc(PACE_LABEL[derived.relationship_pace]||derived.relationship_pace)}</dd></div>
          <div><dt>Writing First</dt><dd>${esc(OUTREACH_LABEL[derived.outreach]||derived.outreach)}</dd></div>
          <div><dt>Quiet Hours</dt><dd>${esc(derived.quiet_start)} – ${esc(derived.quiet_end)}</dd></div>
          <div><dt>Unprompted Photos</dt><dd>${esc(PERMIT_LABEL[derived.permit_image]||derived.permit_image)}</dd></div>
        </dl>
      </div>

      ${derived.agent_type==='worker'?'':lookPanels()}

      <div class="creator-form">
          <label>Companion Name
            <input type="text" id="cust-name" value="${esc(draft.agent)}" maxlength="100">
            <small class="dim"></small>
          </label>
          <label>What should they call you?
            <input type="text" id="cust-human" value="${esc(draft.human_names)}" maxlength="100">
          </label>

        <label>What style of images would you like from this companion?
          <select id="cust-image-style">${options(Object.entries(catalog.image_styles||{}).map(([key,value])=>[key,value.label]),derived.image_style||'none')}</select>
          <small class="dim">They choose the scene. You choose the style.</small>
        </label>
        <label>What would you like this connection to bring to your days?
          <textarea id="cust-hope" rows="3" maxlength="1000" placeholder="A little company after work, someone to make things with, a thoughtful sounding board…">${esc(draft.hope)}</textarea>
          <small class="dim">Optional. Helps them understand what matters to you.</small>
        </label>
        <label>Anything they should never do?
          <textarea id="cust-boundary-note" rows="2" maxlength="1000" placeholder="For example: don’t tease me about being away.">${esc(draft.human_boundary)}</textarea>
          <small class="dim">Optional. They cannot change this boundary.</small>
        </label>
      </div>
      <details class="creator-more"><summary>How your answers shaped this suggestion</summary>
        <p class="dim">This is a preference-based suggestion, not a prediction of compatibility. The story scenes suggest personality. Your last three answers set pace, contact, and relationship; none of the story choices grants permission or chooses romance.</p>
        <ul>${picks.map((choice,i)=>choice==null?'':`<li>${esc(QUIZ[i].a[choice][0])}</li>`).join('')}</ul>
      </details>
      <details id="custom-drawer" class="creator-more" style="margin-bottom:20px">
        <summary style="font-weight:600;color:var(--accent);padding:8px 0;cursor:pointer">✎ Review identity & everyday settings</summary>
        <div class="creator-form" style="margin-top:14px">
          <div class="creator-pair">
            <label>They are
              <select id="cust-pronoun">${options([['she','She / her'],['he','He / him'],['they','They / them']],draft.pronoun_set)}</select>
            </label>
            <label>You are
              <select id="cust-human-pronoun">${options([['he','He / him'],['she','She / her'],['they','They / them']],draft.human_pronoun_set)}</select>
            </label>
          </div>
          <label>Personality Archetype
            <select id="cust-persona">${options(Object.entries(catalog.personas).map(([k,v])=>[k,v.label||k]),derived.persona)}</select>
          </label>
          <label>Relationship Framework
            <select id="cust-boundary">${options(Object.entries(catalog.boundaries).map(([k,v])=>[k,v.label||k]),derived.boundary)}</select>
          </label>
          <label>Pace
            <select id="cust-pace">${options(Object.entries(PACE_LABEL),derived.relationship_pace)}</select>
          </label>
        </div>
          <div class="time-pair">
            <label>Quiet from<input id="cust-quiet-start" type="time" value="${esc(derived.quiet_start)}"></label>
            <label>Quiet until<input id="cust-quiet-end" type="time" value="${esc(derived.quiet_end)}"></label>
          </div>
          <label>Time zone<input id="cust-timezone" value="${esc(draft.timezone)}"></label>
          <label>Writing first<select id="cust-outreach" ${derived.agent_type==='worker'?'disabled':''}>${options(Object.entries(OUTREACH_LABEL),derived.outreach)}</select></label>
          <label>Maximum messages per day<input id="cust-cap" type="number" min="1" max="100" value="${derived.outreach_per_day}"></label>
          <div class="creator-pair">
            <label>Unprompted photos<select id="cust-images">${options(Object.entries(PERMIT_LABEL),derived.permit_image)}</select></label>
            <label>Voice notes<select id="cust-voice">${options(Object.entries(PERMIT_LABEL),derived.permit_voice)}</select></label>
          </div>
      </details>

      <div class="creator-actions is-review">
        <button type="button" class="quiet" id="btn-rev-quiz">← Review my answers</button>
        <button type="button" class="act" id="btn-rev-accept" style="padding:10px 24px">Connect a model →</button>
      </div>`);

    $('btn-rev-quiz').onclick=()=>{captureReview();step=0;questionStep();};
    const reshuffle=keys=>{captureReview();const fresh=resolveCompanion(derived,catalog,draft.pronoun_set,(lookSeed=(lookSeed*31+7)>>>0));
      for(const k of keys)if(k in fresh)look[k]=fresh[k];revealStep();};
    if($('btn-shuffle-look'))$('btn-shuffle-look').onclick=()=>reshuffle(LOOK_FIELDS.map(f=>f[0]));
    if($('btn-shuffle-life'))$('btn-shuffle-life').onclick=()=>reshuffle(LIFE_FIELDS.map(f=>f[0]));
    if($('cust-name'))$('cust-name').oninput=()=>{draft.agent_named=true;};
    function captureReview(){
      for(const el of target.querySelectorAll('[data-look]'))look[el.dataset.look]=el.value;
      const before=draft.pronoun_set;
      draft.hope=$('cust-hope').value.trim();
      draft.human_boundary=$('cust-boundary-note').value.trim();
      derived.quiet_start=$('cust-quiet-start').value||'23:00';
      derived.quiet_end=$('cust-quiet-end').value||'08:00';
      draft.timezone=$('cust-timezone').value.trim()||'UTC';
      derived.outreach=$('cust-outreach').value;
      derived.outreach_per_day=Math.max(1,Math.min(100,Number($('cust-cap').value)||3));
      derived.image_style=$('cust-image-style').value;
      derived.visual='set';
      derived.permit_image=$('cust-images').value;
      derived.permit_voice=$('cust-voice').value;
      // Capture any custom tweaks made in drawer
      const custName=$('cust-name')?.value.trim();
      if(custName)draft.agent=custName;
      const custHuman=$('cust-human')?.value.trim();
      if(custHuman)draft.human_names=custHuman;
      if($('cust-pronoun')?.value)draft.pronoun_set=$('cust-pronoun').value;
      if($('cust-human-pronoun')?.value)draft.human_pronoun_set=$('cust-human-pronoun').value;
      if($('cust-persona'))derived.persona=$('cust-persona').value;
      if($('cust-boundary'))derived.boundary=$('cust-boundary').value;
      if($('cust-pace'))derived.relationship_pace=$('cust-pace').value;
      // The catalogue lists differ by gender, so a changed pronoun re-rolls the look.
      if(draft.pronoun_set!==before)look=resolveCompanion(derived,catalog,draft.pronoun_set,lookSeed);
    }
    $('btn-rev-accept').onclick=()=>{captureReview();derived.agent_type==='worker'?inferenceStep():ownershipStep();};
  }

  /* The look and life the quiz chose, as editable catalogue picks. */
  const LOOK_FIELDS=[['hair_color','Hair colour'],['hair_style','Hair style'],['eyes','Eyes'],['complexion','Skin'],
                     ['height','Height'],['build','Build'],['style','How they dress'],['marks','A detail'],['facial_hair','Facial hair']];
  const LIFE_FIELDS=[['occupation','Work'],['daily_rhythm','Their rhythm'],['likes','Loves'],['met','How you met']];
  function lookPanels(){
    const cats=catalog.catalog?.categories||{};
    const list=draft.pronoun_set==='he'?'male':'female';
    const field=([key,label])=>{
      const rows=cats[key]?.[list];if(!rows)return '';
      const none=['marks','facial_hair'].includes(key)?[['','None']]:[];
      return `<label>${esc(label)}<select data-look="${key}" id="look-${key}">${options(none.concat(rows.map(r=>[r.id,r.label])),look[key]||'')}</select></label>`;
    };
    return `<div class="reveal-panels">
      <section class="card reveal-panel"><div class="reveal-panel-head"><h3>Their look</h3>
        <button type="button" class="link-button" id="btn-shuffle-look">Shuffle</button></div>
        <div class="form-grid">${LOOK_FIELDS.map(field).join('')}</div>
        <small class="dim">Chosen from your answers. Photos are drawn from this, so change anything that isn’t them.</small></section>
      <section class="card reveal-panel"><div class="reveal-panel-head"><h3>Their life</h3>
        <button type="button" class="link-button" id="btn-shuffle-life">Shuffle</button></div>
        <div class="form-grid">${LIFE_FIELDS.map(field).join('')}</div>
        <small class="dim">Their life keeps going between conversations, and they’ll grow it themselves.</small></section>
    </div>`;
  }

  /* ---------------------------------------------------------- 5b. Who keeps what */
  function ownershipStep(){
    const name=esc(draft.agent||'Your companion');
    const sections=[['core','Who '+name+' is','Personality'],['daily-life',name+'’s life','Work, rhythm, the things they love'],
                    ['voice','How '+name+' talks','Tone, texting, pet names'],['heart','Heart and temper','Feelings, flaws, making up'],
                    ['support','Support and humor','Showing up, and what makes them laugh'],['appearance','What '+name+' looks like','Locked unless you open it']];
    draft.soul_locks=draft.soul_locks||{appearance:true};
    shell(`
      <div class="creator-head">
        <span class="eyebrow">One last thing</span>
        <h2>${name} will grow</h2>
        <p class="dim">A companion who never changes is a costume. ${name} rewrites parts of who they are as your relationship deepens — more of them open up over time. You decide what stays exactly as you set it.</p>
      </div>
      <div class="ownership-keys">
        <div><span class="keeper keeper-shared">Shared</span><p>Starts from your answers. ${name} can rewrite it as they change, unless you lock it. You can always edit it too.</p></div>
        <div><span class="keeper keeper-yours">Yours</span><p>What you are to each other, closeness and hard lines. ${name} never changes these.</p></div>
        <div><span class="keeper keeper-hers">Theirs</span><p>${name}’s own words about themselves. You can read them; only they write them.</p></div>
        <div><span class="keeper keeper-private">Private</span><p>What they really think and feel about you. Written only for themselves — you will never see it. It opens up as you grow closer.</p></div>
      </div>
      <div class="creator-form">
        <h3 style="margin:8px 0 4px">Lock anything you want kept exactly as it is</h3>
        ${sections.map(([id,title,hint])=>`<label class="switch-container" data-toggle-row>
          <input type="checkbox" data-lock="${id}" ${draft.soul_locks[id]?'checked':''}>
          <span class="switch-slider" aria-hidden="true"></span>
          <span class="switch-label"><strong>${title}</strong> <small class="dim">${hint}</small></span></label>`).join('')}
        <small class="dim">You can change these any time on the Identity page.</small>
        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-own-back">← Back</button>
          <button type="button" class="act" id="btn-own-next">Connect a model →</button>
        </div>
      </div>`);
    const capture=()=>{for(const el of target.querySelectorAll('[data-lock]'))draft.soul_locks[el.dataset.lock]=el.checked;};
    $('btn-own-back').onclick=()=>{capture();revealStep();};
    $('btn-own-next').onclick=()=>{capture();inferenceStep();};
  }

  /* ---------------------------------------------------------- 5. Model connection */
  function inferenceStep(){
    const infConfigured=envInfo?.inference?.configured;
    const loc=envInfo?.local_models||{};
    const isMobile=Boolean(loc.is_mobile);
    const hostMem=loc.host_memory||{};
    const availRam=hostMem.available_mb ? (hostMem.available_mb/1024).toFixed(1) : (isMobile?'5.0':'8.0');
    const totalRam=hostMem.total_mb ? (hostMem.total_mb/1024).toFixed(1) : (isMobile?'12.0':'16.0');

    const recGguf=loc.recommended_gguf||[
      {id:'qwen2.5-1.5b-instruct-q4_k_m',name:'Qwen 2.5 1.5B Instruct',family:'Qwen',gb:1.1,mobile_recommended:true,description:'Balanced conversational intelligence and speed (~17 tokens/s on Tensor G3).'},
      {id:'smollm2-1.7b-instruct-q4_k_m',name:'SmolLM2 1.7B Instruct',family:'SmolLM',gb:1.0,mobile_recommended:true,description:'Ultra-compact mobile model, highly battery and RAM efficient.'},
      {id:'llama-3.2-1b-instruct-q4_k_m',name:'Llama 3.2 1B Instruct',family:'Llama',gb:0.8,mobile_recommended:true,description:'Smallest memory footprint, fast lightweight responses.'},
      {id:'llama-3.2-3b-instruct-q4_k_m',name:'Llama 3.2 3B Instruct',family:'Llama',gb:2.0,mobile_recommended:true,description:'High capability mobile model (requires ~6-8 GB RAM).'},
      {id:'qwen2.5-3b-instruct-q4_k_m',name:'Qwen 2.5 3B Instruct',family:'Qwen',gb:2.2,mobile_recommended:false,description:'High capability desktop model for Linux, macOS, or Windows.'}
    ];

    const diskModels=loc.available_models||[];

    const mobileAdvisoryHTML=isMobile ? `
      <div class="card" style="border-left:4px solid var(--warn,#f59e0b);background:color-mix(in srgb,var(--warn,#f59e0b) 6%,var(--surface));margin:14px 0;padding:14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:18px">📱</span>
          <strong style="color:var(--warn,#f59e0b)">Mobile Limitations & Hardware Advisory (Android / Termux)</strong>
        </div>
        <p class="small" style="margin:0 0 8px;line-height:1.5">
          Running a conversation model on a phone keeps that inference on-device. Model size still needs to fit the available hardware:
        </p>
        <ul class="small dim" style="margin:0 0 10px;padding-left:18px;line-height:1.6">
          <li><strong>Strict RAM Ceiling:</strong> Models must stay under <strong>2.8 GB</strong> (1.5B–3B parameters). Attempting to load desktop 7B/8B/14B models will exceed available RAM and cause Android's <em>Low Memory Killer (LMK)</em> to terminate Termux immediately.</li>
          <li><strong>Battery Drain & Heat:</strong> On-device text generation uses the phone's CPU/GPU (~15–20 tokens/s on Tensor G3). Continuous background loops and long chats will draw battery faster. Keep your phone connected to power for 24/7 background operation.</li>
          <li><strong>Best Model for Phones:</strong> <strong>Qwen 2.5 1.5B</strong> (~1.1 GB) or <strong>SmolLM2 1.7B</strong> (~1.0 GB) are specifically recommended for phone thermal limits and battery efficiency.</li>
        </ul>
        <div class="small" style="display:inline-block;padding:4px 10px;background:color-mix(in srgb,var(--ink) 6%,transparent);border-radius:6px">
          Device Memory: <strong>${availRam} GB available</strong> of <strong>${totalRam} GB RAM</strong> · Guardrail Active: <strong>max 2.8 GB</strong>
        </div>
      </div>` : `
      <div class="card" style="border-left:4px solid var(--good,#10b981);background:color-mix(in srgb,var(--good,#10b981) 6%,var(--surface));margin:14px 0;padding:14px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:18px">💻</span>
          <strong style="color:var(--good,#10b981)">Desktop / Host Hardware Detected</strong>
        </div>
        <p class="small dim" style="margin:0">
          Device Memory: <strong>${availRam} GB available</strong> of <strong>${totalRam} GB RAM</strong>.
          Vulkan GPU offload supported. You can run 4B to 14B models comfortably.
        </p>
      </div>`;

    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 5 of 6 · AI Engine</span>
        <h2>Connect a model for ${esc(draft.agent||'Companion')}</h2>
        <p class="dim">Choose how to power ${esc(draft.agent||'Companion')}. Use a model on your host or connect a cloud provider. You can set this up now or return later.</p>
      </div>

      ${infConfigured?`
        <div class="notice-strip status-good" style="margin-bottom:18px">
          <p><strong>Saved model configuration</strong></p>
          <p class="small dim">Model <code>${esc(envInfo.inference.model)}</code> via <code>${esc(envInfo.inference.provider)}</code> is active and ready.</p>
        </div>`:''}

      <div class="creator-form">
        <div style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap">
          <button type="button" class="quiet tab-pill is-active" id="tab-local" style="font-weight:600">🏠 Local model</button>
          <button type="button" class="quiet tab-pill" id="tab-oauth" style="font-weight:600">Cloud OAuth (Grok / OpenAI)</button>
          <button type="button" class="quiet tab-pill" id="tab-apikey" style="font-weight:600">API Key (OpenRouter / DeepSeek)</button>
          <button type="button" class="quiet tab-pill" id="tab-skip" style="font-weight:600">Configure Later</button>
        </div>

        <!-- Panel 1: Keep It Local -->
        <div id="panel-local" style="display:block;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
          <h4 style="margin:0 0 6px">Conversation on your own hardware</h4>
          <p class="small dim" style="margin:0 0 12px">Local inference processes conversation on the host. Voice, images, Telegram, and fallback models have their own provider settings; review those separately.</p>

          ${mobileAdvisoryHTML}

          <!-- Engine Status Bar -->
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:14px;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:8px">
            <div>
              <span class="pill ${loc.online?'status-good':'status-bad'}">● ${loc.online ? 'Local Engine Online ('+esc(loc.engine||'llama.cpp')+')' : 'Local Engine Offline'}</span>
              <span class="small dim" style="margin-left:8px">${loc.loaded_model ? 'Active: '+esc(loc.loaded_model.id) : (loc.installed ? 'Engine runtime ready' : 'Ready to configure')}</span>
            </div>
            ${!loc.online ? `<button type="button" class="act small" id="ob-start-engine-btn">▶ Start Engine</button>` : ''}
          </div>

          <!-- Model Download & Installation Section -->
          <h5 style="margin:16px 0 8px;font-size:14px">Recommended Local Models for this Device:</h5>
          <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-bottom:14px">
            ${recGguf.filter(m=>!isMobile || m.mobile_recommended).map(m=>{
              const isPresent=diskModels.some(dm=>dm.name.toLowerCase().includes(m.id.toLowerCase()) || dm.path.toLowerCase().includes(m.filename));
              return `
                <div class="card" style="margin-bottom:0;display:flex;flex-direction:column;justify-content:space-between;padding:14px;border:1px solid var(--border)">
                  <div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                      <span class="pill">${esc(m.family)}</span>
                      <span class="small dim">${m.gb} GB</span>
                    </div>
                    <strong style="display:block;font-size:14px;margin-bottom:4px">${esc(m.name)}</strong>
                    <p class="small dim" style="margin:0 0 10px">${esc(m.description)}</p>
                  </div>
                  <div>
                    ${isPresent ? `
                      <span class="small status-good" style="display:block;margin-bottom:6px">● File present in ~/models</span>
                      <button type="button" class="act small" style="width:100%" data-local-setup="${esc(m.id)}" data-setup-type="gguf">⚡ Use for ${esc(draft.agent||'Companion')}</button>
                    ` : `
                      <button type="button" class="act small" style="width:100%" data-local-setup="${esc(m.id)}" data-setup-type="gguf">📥 Download & Use for ${esc(draft.agent||'Companion')}</button>
                    `}
                  </div>
                </div>`;
            }).join('')}
          </div>

          ${diskModels.length ? `
            <details style="margin-top:10px;padding:10px;background:var(--surface);border-radius:6px;border:1px solid var(--border)">
              <summary class="small" style="cursor:pointer;font-weight:600">📁 Or choose an existing model found on storage (${diskModels.length} discovered)</summary>
              <div style="display:grid;gap:6px;margin-top:10px">
                ${diskModels.map(dm=>`
                  <div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--bg-soft);border-radius:4px">
                    <div>
                      <strong class="small">${esc(dm.name)}</strong>
                      <span class="small dim" style="margin-left:6px">${dm.size_gb} GB</span>
                    </div>
                    <button type="button" class="quiet small" data-local-setup="${esc(dm.alias||dm.name)}" data-setup-type="disk" data-model-path="${esc(dm.path)}">Select</button>
                  </div>
                `).join('')}
              </div>
            </details>
          ` : ''}

          <div id="ob-local-status" style="margin-top:12px"></div>
        </div>

        <!-- Panel 2: Cloud OAuth -->
        <div id="panel-oauth" style="display:none;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
          <h4 style="margin:0 0 6px">1-Click Browser Device Authorization</h4>
          <p class="small dim" style="margin:0 0 12px">Sign in directly via your provider account. No API key creation required.</p>
          <label style="margin-bottom:12px">Select OAuth Provider
            <select id="ob-oauth-provider">
              <option value="xai-oauth">xAI Grok OAuth (SuperGrok / Premium+)</option>
              <option value="openai-codex">OpenAI Codex</option>
            </select>
          </label>
          <button type="button" class="act small" id="ob-oauth-start-btn">Start Device Authorization</button>

          <div id="ob-oauth-flow" style="display:none;margin-top:16px;padding:14px;border-radius:8px;background:var(--surface);border:1px solid var(--accent)">
            <p style="margin:0 0 6px;font-weight:600">Complete Authorization in your browser:</p>
            <p class="small dim" style="margin:0 0 10px">1. Open the verification page and enter your code if prompted:</p>
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
              <a id="ob-oauth-url" href="#" target="_blank" rel="noopener" class="act small" style="text-decoration:none">Open Provider Verification Page ↗</a>
              <span id="ob-oauth-code" style="font-family:monospace;font-size:18px;font-weight:700;padding:4px 10px;background:var(--surface-3);border-radius:6px;letter-spacing:0.1em">----</span>
            </div>
            <p id="ob-oauth-status-text" class="small dim" style="margin:0">⏳ Waiting for approval...</p>
          </div>
        </div>

        <!-- Panel 3: API Key -->
        <div id="panel-apikey" style="display:none;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
          <h4 style="margin:0 0 6px">Direct API Key</h4>
          <p class="small dim" style="margin:0 0 12px">Enter an API key for your favorite inference provider.</p>
          <div style="display:grid;gap:10px">
            <label>Provider
              <select id="ob-api-provider">
                <option value="openrouter">OpenRouter (Recommended)</option>
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="xai">xAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="groq">Groq</option>
              </select>
            </label>
            <label>API Key
              <input type="password" id="ob-api-key" placeholder="sk-...">
            </label>
            <label>Model
              <input type="text" id="ob-api-model" value="openrouter/auto" placeholder="model name">
              <small class="dim">Defaults: OpenRouter (openrouter/auto), DeepSeek (deepseek-chat), OpenAI (gpt-4o).</small>
            </label>
            <button type="button" class="quiet small" id="ob-api-save-btn" style="justify-self:start;margin-top:4px">Save Key & Model</button>
            <span id="ob-api-status" class="small"></span>
          </div>
        </div>

        <!-- Panel 4: Skip / Later -->
        <div id="panel-skip" style="display:none;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
          <h4 style="margin:0 0 6px">Configure Inference Later</h4>
          <p class="small dim" style="margin:0">Save your companion now. Before your first conversation, install Hermes and connect a model in Settings.</p>
        </div>

        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-inf-back">← Back</button>
          <button type="button" class="act" id="btn-inf-finish" style="padding:12px 32px;font-size:16px">Review schedule →</button>
        </div>
      </div>`);

    // Tab switching
    const showTab=(panelId,btnId)=>{
      for(const id of ['panel-local','panel-oauth','panel-apikey','panel-skip']){
        const el=$(id);if(el)el.style.display=id===panelId?'block':'none';
      }
      for(const id of ['tab-local','tab-oauth','tab-apikey','tab-skip']){
        const el=$(id);if(el)el.classList.toggle('is-active',id===btnId);
      }
    };
    if($('tab-local'))$('tab-local').onclick=()=>showTab('panel-local','tab-local');
    if($('tab-oauth'))$('tab-oauth').onclick=()=>showTab('panel-oauth','tab-oauth');
    if($('tab-apikey'))$('tab-apikey').onclick=()=>showTab('panel-apikey','tab-apikey');
    if($('tab-skip'))$('tab-skip').onclick=()=>showTab('panel-skip','tab-skip');

    // Local model setup actions
    for(const b of target.querySelectorAll('[data-local-setup]')){
      b.onclick=async()=>{
        const modelId=b.dataset.localSetup;
        const setupType=b.dataset.setupType||'gguf';
        const modelPath=b.dataset.modelPath||'';
        b.disabled=true;
        const statusDiv=$('ob-local-status');
        if(statusDiv)statusDiv.innerHTML='<span class="dim">Downloading & configuring local model...</span>';
        try{
          await action('/onboarding/local-setup',{model_id:modelId,type:setupType,path:modelPath},r=>{
            draft.inference_mode='local';
            draft.provider=r.provider||'custom:local_llama';
            draft.model=r.model||modelId;
            if(statusDiv){
              statusDiv.innerHTML=`
                <div class="notice-strip status-good" style="margin:10px 0">
                  <p><strong>✅ Local Brain Configured!</strong></p>
                  <p class="small">Your conversation model is <code>${esc(r.model||modelId)}</code> on this host. Review voice, images, and fallbacks separately.</p>
                </div>`;
            }
            const finishBtn=$('btn-inf-finish');
            if(finishBtn)finishBtn.focus();
          });
        }catch(e){
          if(statusDiv)statusDiv.innerHTML=`<span style="color:var(--warn)">Setup failed: ${esc(e.message||'Unknown error')}</span>`;
        }finally{
          b.disabled=false;
        }
      };
    }

    const startBtn=$('ob-start-engine-btn');
    if(startBtn){
      startBtn.onclick=async()=>{
        startBtn.disabled=true;
        try{
          await action('/local-models/start',{},async()=>{
            envInfo=await api('/onboarding/environment');
            inferenceStep();
          });
        }catch(e){
          notice(e.message,true);
        }finally{
          startBtn.disabled=false;
        }
      };
    }

    // Provider change auto-updates default model
    $('ob-api-provider').onchange=()=>{
      const p=$('ob-api-provider').value;
      const modelField=$('ob-api-model');
      if(p==='openrouter')modelField.value='openrouter/auto';
      else if(p==='deepseek')modelField.value='deepseek-chat';
      else if(p==='openai')modelField.value='gpt-4o';
      else if(p==='xai')modelField.value='grok-2';
      else if(p==='anthropic')modelField.value='claude-3-5-sonnet-latest';
    };

    $('ob-api-save-btn').onclick=async()=>{
      const provider=$('ob-api-provider').value;
      const apiKey=$('ob-api-key').value.trim();
      const model=$('ob-api-model').value.trim();
      if(!apiKey){$('ob-api-status').innerHTML='<span style="color:var(--warn)">Please enter an API Key.</span>';return;}
      $('ob-api-status').innerHTML='<span class="dim">Saving...</span>';
      try{
        await post('/onboarding/inference',{provider,api_key:apiKey,model});
        $('ob-api-status').innerHTML='<span style="color:var(--good)">✅ Saved key & model!</span>';
      }catch(e){
        $('ob-api-status').innerHTML=`<span style="color:var(--warn)">${esc(e.message||'Failed to save')}</span>`;
      }
    };

    // Cloud OAuth device flow
    $('ob-oauth-start-btn').onclick=async()=>{
      const provider=$('ob-oauth-provider').value;
      if(oauthPollInterval)clearInterval(oauthPollInterval);
      $('ob-oauth-flow').style.display='block';
      $('ob-oauth-status-text').innerHTML='<span class="dim">Initiating device code...</span>';

      try{
        const res=await post('/onboarding/oauth/start',{provider});
        $('ob-oauth-code').textContent=res.user_code||'—';
        $('ob-oauth-url').href=res.verification_url||'#';
        $('ob-oauth-status-text').innerHTML='⏳ Waiting for your approval in the browser...';

        const sid=res.session_id;
        oauthPollInterval=setInterval(async()=>{
          try{
            const poll=await api(`/onboarding/oauth/poll/${sid}`);
            if(poll.user_code)$('ob-oauth-code').textContent=poll.user_code;
            if(poll.verification_url)$('ob-oauth-url').href=poll.verification_url;
            if(poll.status==='approved'){
              clearInterval(oauthPollInterval);
              $('ob-oauth-status-text').innerHTML='<span style="color:var(--good);font-weight:600">✅ Authorized successfully!</span>';
            }else if(poll.status==='error'){
              clearInterval(oauthPollInterval);
              $('ob-oauth-status-text').innerHTML=`<span style="color:var(--warn)">Authorization failed: ${esc(poll.error||'Unknown error')}</span>`;
            }
          }catch(e){}
        },3000);
      }catch(e){
        $('ob-oauth-status-text').innerHTML=`<span style="color:var(--warn)">${esc(e.message||'Failed to start OAuth')}</span>`;
      }
    };

    $('btn-inf-back').onclick=()=>{if(oauthPollInterval)clearInterval(oauthPollInterval);revealStep();};
    $('btn-inf-finish').onclick=()=>{if(oauthPollInterval)clearInterval(oauthPollInterval);return scheduleStep();};
  }

  async function scheduleStep(){
    shell('<h2>Your companion’s routine</h2><p class="dim">Preparing schedule…</p>');
    try{
      const base=(draft.agent||'companion').toLowerCase().replace(/[^a-z0-9_-]/g,'').slice(0,48)||'companion';
      const roster=await api('/profiles'),ids=new Set(roster.profiles.map(p=>p.id));
      let profile=base,suffix=2;while(ids.has(profile)){const tail='-'+suffix++;profile=base.slice(0,48-tail.length)+tail;}
      draft.profile=adopt?(PROFILE||'default'):profile;
      const plan=await post('/onboarding/schedule',{profile:draft.profile,adopt:Boolean(adopt),agent_type:derived.agent_type,
        quiet_start:derived.quiet_start,quiet_end:derived.quiet_end,timezone:draft.timezone});
      shell(`<h2>A rhythm for their day</h2>
        <p class="dim">${esc(draft.timezone)} · Quiet ${esc(derived.quiet_start)}–${esc(derived.quiet_end)}. Contact: ${esc(OUTREACH_LABEL[derived.outreach])}.</p>
        <p>Small background checks keep their day moving. Reflections run daily, weekly, and monthly; independent projects start at 10:20 and 20:20.</p>
        <p class="dim small">${plan.offset_minutes?`Starts are staggered by ${plan.offset_minutes} minute(s) from the base routine. `:''}Clock-bound quiet hours and project times stay as chosen. Long-running jobs can still overlap.</p>
        <details><summary>View all ${plan.jobs.length} jobs</summary><dl class="fact-list">${plan.jobs.map(j=>`<div><dt>${esc(j.name)}${j.uses_model?'':' · no model'}</dt><dd><code>${esc(scheduleLabel(j.schedule))}</code></dd></div>`).join('')}</dl><p class="dim small">Edit individual times in Companion Continuity settings.</p></details>
        <label class="inline-label"><input id="ob-schedule-approved" type="checkbox" ${adopt?'':'checked'}> Enable this routine after a successful model test</label>
        <p class="dim small">Your host must stay awake and its Hermes gateway must run. They may write first if your contact settings allow it. Automatic photos wait until you connect an image provider and enable them.</p>
        <div class="creator-actions"><button type="button" class="quiet" id="ob-schedule-back">Back</button><button type="button" class="act" id="ob-schedule-create">Create companion</button></div>`);
      $('ob-schedule-back').onclick=inferenceStep;
      $('ob-schedule-create').onclick=()=>{scheduleApproved=$('ob-schedule-approved').checked;return finalizeBirth();};
    }catch(error){
      shell(`<h2>Schedule unavailable</h2><p class="bad">${esc(error.message)}</p><button class="quiet" id="ob-schedule-back">Back</button>`);
      $('ob-schedule-back').onclick=inferenceStep;
    }
  }

  /* ---------------------------------------------------------- 7. Finalize & Birth */
  async function finalizeBirth(){
    shell(`
      <div class="creator-head reveal" style="text-align:center;padding:40px 0">
        <span class="eyebrow" style="color:var(--accent);font-size:16px">Awakening...</span>
        <h2 style="font-size:36px;margin:12px 0">Bringing ${esc(draft.agent||'Companion')} to life</h2>
        <p class="dim">Saving your companion’s identity and preferences...</p>
      </div>`);

    const answers={
      agent:draft.agent||'Companion',
      human_names:draft.human_names||'Friend',
      pronoun_set:draft.pronoun_set||'they',
      human_pronoun_set:draft.human_pronoun_set||'they',
      timezone:draft.timezone||'UTC',
      age:Number(draft.age)||25,
      persona:derived.persona||'warm',
      agent_type:derived.agent_type||'companion',
      boundary:derived.boundary||'best-friend',
      relationship_pace:derived.relationship_pace||'natural',
      outreach:derived.outreach||'updates_only',
      outreach_per_day:Number(derived.outreach_per_day)||3,
      quiet_start:derived.quiet_start||'23:00',
      quiet_end:derived.quiet_end||'08:00',
      permit_image:derived.permit_image||'ask',
      permit_voice:derived.permit_voice||'ask',
      share_people:derived.share_people||'no',
      visual:derived.visual||'edit',
      image_style:derived.image_style||'none'
    };

    // Everything the quiz chose, by catalogue id: stable where a list position is not.
    if(look&&answers.agent_type!=='worker'){
      answers.visual='set';
      for(const [key,value] of Object.entries(look)){
        if(key==='texting_style'){answers.texting_style=String(value);continue;}
        if(key==='flirtation'&&['best-friend','creative-partner'].includes(answers.boundary))continue;
        answers[key]=value?'id:'+value:'skip:none';
      }
      answers.pet_names='develop';
      answers.soul_locks=draft.soul_locks||{appearance:true};
    }
    if(draft.hope)answers.hope=draft.hope;
    if(draft.birthdate)answers.birthdate=draft.birthdate;
    if(draft.human_boundary)answers.human_boundary=draft.human_boundary;
    if(draft.vault)answers.vault=draft.vault;

    const profileId=draft.profile;
    try{
      await action(adopt?'/adopt':'/profiles',adopt?{answers,schedule_approved:scheduleApproved}:{profile:profileId,answers,schedule_approved:scheduleApproved},r=>{
        target.innerHTML=`
          <div class="card creator" style="text-align:center;padding:40px 20px">
            <span style="font-size:48px;display:block;margin-bottom:12px">🎉</span>
            <h2 style="font-size:32px;margin:0 0 10px">${esc(draft.agent||'Companion')} has arrived!</h2>
            <p class="dim" style="max-width:480px;margin:0 auto 24px">${esc(r.schedule_note||"Your profile is saved. Open the workspace to start your first conversation.")}</p>
            ${!['none','unset'].includes(derived.image_style)?`<div class="onboarding-portrait"><h3>Would you like to see what they look like?</h3><p class="dim small">Ask them to choose their look and send a first portrait. An image provider needs to be connected.</p><button type="button" class="quiet" id="ob-first-portrait">Ask for a first portrait</button></div>`:''}
            <button type="button" class="act" id="ob-enter-chat" style="padding:12px 32px;font-size:16px">Enter Workspace →</button>
          </div>`;
        $('ob-enter-chat').onclick=()=>navigateProfile(r.profile||profileId,'chat');
        const portraitButton=$('ob-first-portrait');
        if(portraitButton)portraitButton.onclick=()=>{
          const profile=r.profile||profileId;
          sessionStorage.setItem('chat-draft-'+INSTALLATION+'-'+profile,'I’d like to see what you look like. Choose a look that feels like you and send me a first portrait in our chosen image style. If images aren’t connected yet, help me set that up first.');
          navigateProfile(profile,'chat');
        };
      });
    }catch(e){
      shell(`<div class="notice-strip is-firm"><p>Creation failed: ${esc(e.message)}</p></div><button class="act" onclick="location.reload()">Retry</button>`);
    }
  }

  // Start at welcome
  welcome();
};
})();
