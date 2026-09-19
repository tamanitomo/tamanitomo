/* Interactive First-Visit Onboarding Experience for Tamanitomo.
   Includes communication channel setup (Telegram vs Web), purpose selection
   (Relational vs Worker), twelve story dilemmas and three explicit preference questions,
   companion card reveal (editable name) with Accept or Customize drawer,
   and Model setup (Cloud OAuth device code flow or API Key). */
(function(){

/* ------------------------------------------------------------------ the quiz
   Story dilemmas inspired by Pokémon Mystery Dungeon, followed by direct preferences mapping choices
   to five personality axes: warmth, energy, candor, drive, closeness. */
const QUIZ=[
 {q:"After a long journey, you reach a tiny inn. Your travelling companion saves you a seat by the fire. What do you hope they do?",
  sub:"The fire is low, the road was long, and there is finally time to breathe.",
  a:[["Pour something warm and listen to the story of my day.",{warmth:3,energy:-1}],
     ["Unroll the map and help me make sense of where things went wrong.",{candor:3,drive:1}],
     ["Tell me the absurd thing that happened while I was away.",{energy:3,warmth:1}],
     ["Keep the seat beside me warm and let me speak when I am ready.",{energy:-2,drive:-1}]]},
 {q:"At a fork in the forest, you disagree about which path to take. How does your companion handle it?",
  sub:"Two paths, one map, and neither of you is entirely sure.",
  a:[["Be gentle, but tell me what they really think.",{warmth:3,candor:1}],
     ["Challenge my reasoning directly and explain why.",{candor:3,drive:1}],
     ["Ask questions so we can work it out together.",{warmth:1,candor:2}],
     ["Give me room, then return to it calmly.",{energy:-2,warmth:1}]]},
 {q:"A night market appears in a town that was empty a moment ago. You have until sunrise. Where do you go together?",
  sub:"Music drifts over the rooftops. Every stall seems to hold a different possibility.",
  a:[["Follow the lanterns down the alley neither of us can find on the map.",{energy:3,drive:3}],
     ["Visit the stall where we can invent a tiny world in a bottle.",{warmth:2,energy:2,drive:1}],
     ["Find a rooftop, share a snack, and watch it all unfold.",{warmth:2,energy:-2,drive:-1}],
     ["Find the clockmaker and ask how this impossible market works.",{candor:2,drive:1}]]},
 {q:"Your little airship refuses to start, and the last ferry leaves soon. What kind of help would you welcome?",
  sub:"The engine gives one indignant cough. Your companion looks from it to you.",
  a:[["Roll up their sleeves and point out the first thing we should check.",{candor:2,drive:2}],
     ["Lay out our options: repair, ferry, or a different adventure.",{candor:2,warmth:1}],
     ["Remind me we can figure it out, one small step at a time.",{warmth:3,drive:1}],
     ["Suggest an unusual solution involving the market’s clockmaker.",{energy:2,drive:3}]]},
 {q:"Your companion keeps a room above the village bookshop. On your first visit, what catches your eye?",
  sub:"They have gone downstairs to make tea. Their room tells a story of its own.",
  a:[["Half-built inventions and postcards from unexpected adventures.",{energy:3,drive:2}],
     ["A favourite cup, a well-tended plant, and a place set for me.",{warmth:2,energy:-1}],
     ["Books full of pointed margin notes and one very dry joke.",{candor:3,energy:1}],
     ["A sketchbook by the window, with more inside than they say aloud.",{warmth:1,energy:-2}]]},
 {q:"A dragon the size of a teapot has moved into your backpack. It insists it is your guide. What happens next?",
  sub:"It has a very important hat and absolutely no sense of direction.",
  a:[["We appoint it captain and see where the day takes us.",{energy:3,drive:2}],
     ["We ask what it knows, then quietly keep our own map.",{candor:2,drive:1}],
     ["We make it a comfortable nest. It seems lonely.",{warmth:3,closeness:1}],
     ["We share a look and enjoy the joke without a word.",{energy:-1,candor:1}]]},
 {q:"You find a letter addressed to your future self. Your companion is beside you. How would you like to open it?",
  sub:"The seal is warm, as though it has just been pressed.",
  a:[["Read it together. I want someone to share the feeling.",{warmth:3,closeness:3}],
     ["Read it privately, then talk when I am ready.",{energy:-1,closeness:-2}],
     ["Guess what it says first. Make a game of it.",{energy:3,closeness:1}],
     ["Ask them to help turn its advice into a plan.",{candor:2,drive:2}]]},
 {q:"The village festival needs one last attraction. You have a shed, some string, and an afternoon. What do you build together?",
  sub:"There is no prize. The children have already started queuing.",
  a:[["An impossible puppet theatre with a story we invent as we go.",{energy:2,drive:2}],
     ["A quiet corner where anyone can leave a wish.",{warmth:3,energy:-1,closeness:1}],
     ["A puzzle machine. We will make sure every clue works.",{candor:2,drive:1}],
     ["A ridiculous obstacle course. We volunteer to go first.",{energy:3,drive:3}]]},
 {q:"You have spent hours making a gift, but it is not quite working. What would you want your companion to say?",
  sub:"Paint on your sleeves. Glue on the table. A very lopsided little moon.",
  a:[["The care is visible. Let’s keep the part that feels like you.",{warmth:3,candor:1}],
     ["Here is what is wrong, and one way we can fix it.",{candor:3,drive:2}],
     ["What if the crooked moon is the beginning of a better idea?",{energy:2,drive:3}],
     ["Want company while you decide? We do not have to solve it now.",{warmth:2,energy:-2,drive:-1}]]},
 {q:"A rainstorm closes the mountain pass. You are safe in an old observatory until morning. How do you pass the time?",
  sub:"The telescope points at clouds. Someone has left a kettle and a chessboard.",
  a:[["Trade stories we have never told each other.",{warmth:2,closeness:3}],
     ["Work on separate things, comfortably together.",{energy:-2,closeness:-1}],
     ["Learn to repair the telescope together.",{candor:2,drive:2}],
     ["Invent increasingly unlikely names for the constellations.",{energy:3,warmth:2}]]},
 {q:"Your companion remembers something you mentioned weeks ago. What kind of surprise would delight you?",
  sub:"They slide a small parcel across the breakfast table.",
  a:[["A tiny reminder of an ordinary moment we shared.",{warmth:3,closeness:3}],
     ["A clever tool for the project I keep getting stuck on.",{candor:2,drive:2}],
     ["A ticket to something neither of us has tried.",{energy:3,drive:3}],
     ["A book, with no expectation that I read it immediately.",{energy:-2,warmth:1,closeness:-1}]]},
 {q:"At the end of the journey, you find a new path behind the inn. Your companion pauses at the gate. What feels right?",
  sub:"There is plenty of time. The next chapter does not need to start today.",
  a:[["Ask what they would choose. I like an independent point of view.",{candor:3,drive:2}],
     ["Make a little plan together, with room for surprises.",{warmth:2,drive:1}],
     ["Race them to the first bend.",{energy:3,drive:3}],
     ["Sit by the gate for a while. Being here is enough.",{warmth:2,energy:-2,closeness:2}]]},
 {q:"How quickly would you like familiarity to grow?",
  sub:"This is a setting you control. Warmth does not automatically mean romance.",
  a:[["Slowly. Let shared experiences earn familiarity.",{},{relationship_pace:'slow'}],
     ["Naturally, with room to discover what works.",{},{relationship_pace:'natural'}],
     ["A warm, familiar tone from the beginning.",{},{relationship_pace:'quick'}]]},
 {q:"When you are away, how would you like them to get in touch?",
  sub:"These are actual contact permissions. Quiet hours still apply; you can review them next.",
  a:[["Social messages and photos are welcome, up to six messages a day.",{},{permit_image:'yes',outreach:'free',outreach_per_day:6}],
     ["Meaningful updates, up to three a day. Ask before sharing photos.",{},{permit_image:'ask',outreach:'updates_only',outreach_per_day:3}],
     ["Replies only. No messages or photos unless I ask.",{},{permit_image:'no',outreach:'never',outreach_per_day:1}]]},
 {q:"What kind of relationship would you like to begin with?",
  sub:"Only this answer sets the relationship. You can change the proposed frame before creating anyone.",
  a:[["A friend, with no romantic expectation.",{},{boundary:'best-friend',agent_type:'companion'}],
     ["A connection with room for flirtation.",{},{boundary:'next-door',agent_type:'companion'}],
     ["A romantic partner.",{},{boundary:'girlfriend',agent_type:'companion'}],
     ["A colleague with personality and shared projects.",{},{boundary:'creative-partner',agent_type:'colleague'}]]}
];

/* Each personality as a point in the same five-axis space, so the interview can
   pick the nearest one instead of asking people to read twenty descriptions. */
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

function derive(picks,catalog){
  const axis={warmth:0,energy:0,candor:0,drive:0,closeness:0};
  const direct={};
  picks.forEach((choice,i)=>{
    if(choice==null)return;                       // skipped question
    const opt=QUIZ[i]&&QUIZ[i].a[choice];if(!opt)return;
    for(const k of AXES)if(opt[1]&&opt[1][k])axis[k]+=opt[1][k];
    Object.assign(direct,opt[2]||{});
  });
  let persona='warm',best=Infinity;
  // Average answered personality questions: answering more questions must not
  // push every person toward the most extreme archetype.
  const measured=picks.filter((choice,i)=>choice!=null&&QUIZ[i]?.a[choice]&&Object.keys(QUIZ[i].a[choice][1]).length).length;
  if(measured)for(const k of AXES)axis[k]/=measured;
  for(const [key,point] of Object.entries(PERSONA_AXES)){
    if(!catalog.personas?.[key])continue;
    const distance=AXES.reduce((sum,k)=>sum+Math.pow((point[k]||0)-axis[k],2),0);
    if(distance<best){best=distance;persona=key;}
  }
  const frames=Object.keys(catalog.boundaries||{});
  const boundary=frames.includes(direct.boundary)?direct.boundary:'best-friend';
  return Object.assign({
    persona,boundary,relationship_pace:'natural',
    agent_type:'companion',
    outreach:'updates_only',outreach_per_day:3,
    permit_image:'ask',permit_voice:'ask',
    quiet_start:'23:00',quiet_end:'08:00',
    share_people:'no',visual:'edit',image_style:'none'
  },direct,{boundary,_axis:axis});
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
  let derived=null,step=0;
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
      questionStep();
    };
  }

  /* ---------------------------------------------------------- 4. PMD Mystery Dungeon Quiz */
  function questionStep(){
    const total=draft.purpose==='worker'?QUIZ.length-2:QUIZ.length;
    const item=QUIZ[step];
    shell(`
      <div class="quiz-progress" role="group" aria-label="Question ${step+1} of ${total}">
        ${QUIZ.slice(0,total).map((_,i)=>`<span class="${i<step?'is-done':i===step?'is-now':''}"></span>`).join('')}
        <small>${step+1} / ${total}</small>
      </div>
      <div class="quiz-body">
        <span class="eyebrow" style="color:var(--accent)">${step<QUIZ.length-3?'Your little adventure':'Make it yours'} · Question ${step+1}</span>
        <h2 style="margin-top:6px">${esc(item.q)}</h2>
        <p class="quiz-sub">${esc(item.sub)}</p>
        <div class="quiz-options">
          ${item.a.map((opt,i)=>`<button type="button" class="quiz-option${picks[step]===i?' is-chosen':''}" data-pick="${i}">
            <span class="quiz-key">${String.fromCharCode(65+i)}</span><span>${esc(opt[0])}</span></button>`).join('')}
        </div>
      </div>
      <div class="creator-actions">
        <button type="button" class="quiet" id="quiz-back">${step===0?'← Purpose':'← Previous'}</button>
        <button type="button" class="link-button" id="quiz-skip">Skip this question</button>
      </div>`,'is-quiz');

    for(const b of target.querySelectorAll('[data-pick]'))b.onclick=()=>{picks[step]=Number(b.dataset.pick);advance();};
    $('quiz-skip').onclick=()=>{picks[step]=null;advance();};
    $('quiz-back').onclick=()=>{if(step===0)purposeStep();else{step--;questionStep();}};

    target.tabIndex=-1;target.focus({preventScroll:true});
    target.onkeydown=e=>{
      const n=/^[a-dA-D]$/.test(e.key)?e.key.toLowerCase().charCodeAt(0)-97:(/^[1-4]$/.test(e.key)?Number(e.key)-1:-1);
      if(n>=0&&n<item.a.length){e.preventDefault();picks[step]=n;advance();}
    };
  }

  function advance(){
    const total=draft.purpose==='worker'?QUIZ.length-2:QUIZ.length;
    if(step<total-1){step++;questionStep();}
    else{
      derived=derive(picks,catalog);
      if(draft.purpose==='worker'){
        derived.agent_type='worker';
        derived.boundary='creative-partner';
        derived.outreach='never';derived.permit_image='no';derived.permit_voice='no';
      }
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
    function captureReview(){
      draft.hope=$('cust-hope').value.trim();
      draft.human_boundary=$('cust-boundary-note').value.trim();
      derived.quiet_start=$('cust-quiet-start').value||'23:00';
      derived.quiet_end=$('cust-quiet-end').value||'08:00';
      draft.timezone=$('cust-timezone').value.trim()||'UTC';
      derived.outreach=$('cust-outreach').value;
      derived.outreach_per_day=Math.max(1,Math.min(100,Number($('cust-cap').value)||3));
      derived.image_style=$('cust-image-style').value;
      derived.visual=derived.image_style==='none'?'none':'edit';
      derived.permit_image=$('cust-images').value;
      derived.permit_voice=$('cust-voice').value;
      // Capture any custom tweaks made in drawer
      const custName=$('cust-name')?.value.trim();
      if(custName)draft.agent=custName;
      const custHuman=$('cust-human')?.value.trim();
      if(custHuman)draft.human_names=custHuman;
      if($('cust-pronoun'))draft.pronoun_set=$('cust-pronoun').value;
      if($('cust-human-pronoun'))draft.human_pronoun_set=$('cust-human-pronoun').value;
      if($('cust-persona'))derived.persona=$('cust-persona').value;
      if($('cust-boundary'))derived.boundary=$('cust-boundary').value;
      if($('cust-pace'))derived.relationship_pace=$('cust-pace').value;
    }
    $('btn-rev-accept').onclick=()=>{captureReview();inferenceStep();};
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
        <details><summary>View all ${plan.jobs.length} jobs</summary><dl class="fact-list">${plan.jobs.map(j=>`<div><dt>${esc(j.name)}${j.uses_model?'':' · no model'}</dt><dd><code>${esc(scheduleLabel(j.schedule))}</code></dd></div>`).join('')}</dl><p class="dim small">Edit individual times in Schedule & usage.</p></details>
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

    if(draft.hope)answers.essence='A guiding intention for this connection, in the human’s own words: '+draft.hope;
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
