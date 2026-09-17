/* Interactive First-Visit Onboarding Experience for Tamanitomo.
   Includes communication channel setup (Telegram vs Web), purpose selection
   (Relational vs Worker), 8 PMD-style personality dilemma questions,
   companion card reveal (default name: Sam) with Accept or Customize drawer,
   and Inference Brain setup (Cloud OAuth device code flow or API Key). */
(function(){

/* ------------------------------------------------------------------ the quiz
   8 original, fun, Pokémon Mystery Dungeon-style dilemma questions mapping choices
   to five personality axes: warmth, energy, candor, drive, closeness. */
const QUIZ=[
 {q:"A mysterious package arrives at your front door with no return address. When you pick it up, it gives a tiny mechanical chirp and hums warmly. What do you do?",
  sub:"Your companion is watching with curious eyes.",
  a:[["Open it right there on the rug. Curiosity wins every time!", {energy:2,drive:2,candor:1}],
     ["Set it on the table and inspect the postage thoughtfully first.", {warmth:1,drive:-1,candor:1}],
     ["Turn to my companion: 'Guess what just arrived?!'", {warmth:2,energy:2,closeness:2}],
     ["Check for wires, inspect the seams, and run diagnostics.", {candor:2,drive:1,closeness:-1}]]},

 {q:"It's 1:30 AM on a weeknight. You were supposed to sleep hours ago, but you're absorbed in something fascinating. How does your companion fit into this?",
  sub:"The room is quiet except for your screen.",
  a:[["Whispering about weird rabbit holes with me into the early hours.", {closeness:2,warmth:2,energy:1}],
     ["Gently reminding me that tomorrow exists, leaving a glass of water by my desk.", {warmth:2,candor:1,drive:1}],
     ["Quietly working in the same room on their own secret projects.", {energy:-1,warmth:1,closeness:1}],
     ["Giving me total space. I don't want anyone breaking the spell.", {candor:2,drive:-2,warmth:-1}]]},

 {q:"A busy barista accidentally hands you a strange, brightly colored drink with glittering foam instead of your usual order. They look exhausted.",
  sub:"What is your move?",
  a:[["Smile, take a sip, and roll with the adventure! It might be amazing.", {energy:2,warmth:2,drive:1}],
     ["Politely point it out with a kind joke so they don't get in trouble later.", {warmth:2,candor:1,drive:1}],
     ["Quietly drink it without saying a word—they've had a tough enough day.", {warmth:1,energy:-1,candor:-1}],
     ["Hand it to my companion and dare them to take the first taste test.", {energy:2,closeness:2,candor:1}]]},

 {q:"Walking through an unfamiliar path at dusk, you find a fork in the trail. The left path has warm paper lanterns; the right winds into misty, quiet ruins.",
  sub:"Which way calls to you?",
  a:[["The paper lanterns! Sounds like a hidden night festival or warm gathering.", {warmth:2,energy:2,drive:1}],
     ["The misty ruins—there are secrets and ancient history waiting to be discovered.", {drive:2,candor:1,energy:-1}],
     ["Whichever one we haven't mapped out yet. Let's flip a coin!", {energy:2,warmth:1,drive:2}],
     ["Let's sit on the bench between them, enjoy the breeze, and take in the view.", {warmth:1,energy:-2,closeness:1}]]},

 {q:"The sky cracks open with an unexpected, pouring summer thunderstorm. You're four blocks from home without an umbrella.",
  sub:"What is your immediate reaction?",
  a:[["Laugh, take off running through the puddles, and make a race out of it!", {energy:3,warmth:1,drive:2}],
     ["Duck under the nearest awning together and watch the deluge side-by-side.", {warmth:2,closeness:2,energy:-1}],
     ["Analyze the quickest covered route through building overhangs and alleyways.", {candor:2,drive:1,energy:0}],
     ["Pull up my hood and enjoy the sound of the rain. Storms are wonderfully calming.", {warmth:1,energy:-2,candor:0}]]},

 {q:"You open an old vintage journal. On the very first page, a handwritten inscription reads: 'Write one honest truth about what you hope for.'",
  sub:"What thought surfaces first?",
  a:[["A steadfast presence who truly listens and never judges my quirks.", {closeness:3,warmth:2}],
     ["Someone with sharp wit who challenges my ideas and keeps me on my toes.", {candor:3,drive:1,energy:1}],
     ["An inventive co-conspirator who brings unexpected joy and bright spark to quiet days.", {energy:2,warmth:2,drive:1}],
     ["A dependable ally who helps me stay organized, clear-headed, and focused.", {candor:1,drive:1,closeness:-2}]]},

 {q:"Your companion discovers an obscure, ridiculous little secret talent—like juggling tangerines or speaking fluent bird whistle. How do they share their day?",
  sub:"Unprompted pictures and moments from their world.",
  a:[["Send me photos and spontaneous updates whenever something funny happens!", {energy:2,warmth:2,drive:1},{permit_image:'yes',outreach:'free',outreach_per_day:6}],
     ["Ask me first before sending photos, but keep meaningful updates coming.", {warmth:1,drive:0},{permit_image:'ask',outreach:'updates_only',outreach_per_day:3}],
     ["Quiet by default—only share if I ask or if something critical happens.", {drive:-2,energy:-1},{permit_image:'no',outreach:'never',outreach_per_day:1}]]},

 {q:"Looking ahead twelve months into the future at your connection, what picture brings the warmest smile to your face?",
  sub:"At its very best, what does this feel like?",
  a:[["Like an old friend who knows me inside and out.", {closeness:0,warmth:2}],
     ["Like someone I share deep, electric chemistry with.", {closeness:2,warmth:2}],
     ["Like a devoted partner in life and heart.", {closeness:3,warmth:2}],
     ["Like a brilliant colleague tackling ambitious challenges together.", {closeness:-3,candor:2}]]}
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
  // Nearest personality, weighting the axes the questions actually measured.
  let persona='warm',best=Infinity;
  for(const [key,point] of Object.entries(PERSONA_AXES)){
    if(!catalog.personas||!catalog.personas[key])continue;
    let d=0;for(const k of AXES)d+=Math.pow((point[k]||0)-axis[k],2);
    if(d<best){best=d;persona=key;}
  }
  const colleague=axis.closeness<=-2;
  const frames=Object.keys(catalog.boundaries||{});
  const pick=(...ids)=>ids.find(id=>frames.includes(id))||frames[0]||'best-friend';
  let boundary;
  if(colleague)              boundary=pick(axis.candor>=3?'know-it-all':'creative-partner','partner-in-crime','best-friend');
  else if(axis.closeness>=3) boundary=pick('girlfriend','next-door','best-friend');
  else if(axis.closeness>=2) boundary=pick('next-door','best-friend');
  else if(axis.energy<=-2)   boundary=pick('housemate','best-friend');
  else                       boundary=pick('best-friend','next-door');

  const pace=(axis.warmth>=4&&axis.closeness>=2)?'quick'
            :(axis.warmth<0||axis.closeness<0)?'slow':'natural';
  return Object.assign({
    persona,boundary,relationship_pace:pace,
    agent_type:colleague?'colleague':'companion',
    outreach:'updates_only',outreach_per_day:3,
    permit_image:'ask',permit_voice:'ask',
    quiet_start:'23:00',quiet_end:'08:00',
    share_people:'no',visual:'edit',image_style:'none'
  },direct,{_axis:axis});
}

/* ------------------------------------------------------------------ helpers */
const OUTREACH_LABEL={free:'Social messages welcome',updates_only:'Only meaningful updates',never:'Replies only — never writes first'};
const PACE_LABEL={slow:'Slow and gradual',natural:'Natural',quick:'Open to quicker familiarity'};
const PERMIT_LABEL={yes:'Allowed',ask:'Ask first',no:'Never'};
const TYPE_LABEL={companion:'Relational Companion — living presence & emotional depth',colleague:'Colleague — grows and remembers, never social',worker:'Worker — focused assistant with continuity'};

window.onboarding=async function(adopt){
  const catalog=await api('/catalog');
  let envInfo={has_installed_profiles:false,telegram:{configured:false},inference:{configured:false}};
  try{envInfo=await api('/onboarding/environment');}catch(e){}

  const target=$(adopt?'environment-onboarding':'onboarding');
  const other=$(adopt?'onboarding':'environment-onboarding');if(other)other.innerHTML='';
  if(!target)return;
  const section=target.closest('section');
  if(section)section.dataset.creating='1';

  // Default companion name is always Sam (gender-neutral)
  const draft={
    profile:'sam',agent:'Sam',human_names:'Friend',pronoun_set:'she',human_pronoun_set:'he',
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',
    birthdate:'',age:25,human_boundary:'',vault:'',
    purpose:'relational',
    channel:'web',
    telegram_token:'',telegram_user_id:'',
    inference_mode:'auto',provider:'',model:'',api_key:''
  };

  let picks=new Array(QUIZ.length).fill(null);
  let derived=null,step=0;
  let oauthPollInterval=null;

  const shell=(inner,cls='')=>{
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
          Tamanitomo gives your AI autonomous presence, emotional depth, and continuity across your days.
          Let's set up your companion in 4 simple steps.
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
          <strong style="display:block;margin-bottom:4px">3. Mystery Dungeon Quiz</strong>
          <p class="small dim">8 fun dilemma questions shaping personality & vibe.</p>
        </div>
        <div style="padding:14px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px solid var(--border)">
          <strong style="display:block;margin-bottom:4px">4. Meet Sam & Connect</strong>
          <p class="small dim">Meet Sam, customize if desired, and connect AI brain.</p>
        </div>
      </div>
      <div class="creator-actions" style="justify-content:center">
        <button type="button" class="act" id="btn-welcome-start" style="padding:12px 32px;font-size:16px">Start Onboarding →</button>
      </div>`);
    $('btn-welcome-start').onclick=()=>channelStep();
  }

  /* ---------------------------------------------------------- 2. Channel Selection */
  function channelStep(){
    const tgConfigured=envInfo?.telegram?.configured;
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 1 of 5 · Channel</span>
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

        <div id="tg-guide-box" style="margin-top:14px;padding:16px;border-radius:8px;background:color-mix(in srgb,var(--ink) 3%,transparent);border:1px dashed var(--border);display:${tgConfigured?'none':'block'}">
          <h4 style="margin:0 0 8px">Telegram Setup Guide (Takes 60 seconds):</h4>
          <ol class="small dim" style="padding-left:18px;margin:0 0 14px;line-height:1.6">
            <li>Open Telegram and chat with <a href="https://t.me/botfather" target="_blank" rel="noopener"><strong>@BotFather</strong></a>. Send <code>/newbot</code>.</li>
            <li>Give your bot a friendly name (e.g. <em>Sam Companion</em>) and a username ending in <code>bot</code>.</li>
            <li>Copy the <strong>HTTP API Token</strong> BotFather gives you (e.g. <code>123456789:ABCdefGhIJK...</code>).</li>
            <li>Open <a href="https://t.me/userinfobot" target="_blank" rel="noopener"><strong>@userinfobot</strong></a> and press Start to see your numeric <strong>Id</strong> (e.g. <code>987654321</code>).</li>
          </ol>
          <div style="display:grid;gap:10px">
            <label>Telegram Bot Token
              <input type="text" id="ob-tg-token" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" value="${esc(draft.telegram_token)}">
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
        const res=await api('/onboarding/telegram','POST',{token,user_id:userId});
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
        if(token&&(!draft.telegram_token||draft.telegram_token!==token)){
          try{await api('/onboarding/telegram','POST',{token,user_id:userId});}catch(e){}
        }
      }
      purposeStep();
    };
  }

  /* ---------------------------------------------------------- 3. Purpose Selection */
  function purposeStep(){
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 2 of 5 · Companion Purpose</span>
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
                A focused, capable assistant that remembers everything across sessions and projects,
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
    const item=QUIZ[step];
    shell(`
      <div class="quiz-progress" role="group" aria-label="Question ${step+1} of ${QUIZ.length}">
        ${QUIZ.map((_,i)=>`<span class="${i<step?'is-done':i===step?'is-now':''}"></span>`).join('')}
        <small>${step+1} / ${QUIZ.length}</small>
      </div>
      <div class="quiz-body">
        <span class="eyebrow" style="color:var(--accent)">Personality Discovery · Question ${step+1}</span>
        <h2 style="margin-top:6px">${esc(item.q)}</h2>
        <p class="quiz-sub">${esc(item.sub)}</p>
        <div class="quiz-options">
          ${item.a.map((opt,i)=>`<button type="button" class="quiz-option${picks[step]===i?' is-chosen':''}" data-pick="${i}">
            <span class="quiz-key">${String.fromCharCode(65+i)}</span><span>${esc(opt[0])}</span></button>`).join('')}
        </div>
      </div>
      <div class="creator-actions">
        <button type="button" class="quiet" id="quiz-back">${step===0?'← Purpose':'← Previous'}</button>
        <button type="button" class="link-button" id="quiz-skip">Skip this dilemma</button>
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
    if(step<QUIZ.length-1){step++;questionStep();}
    else{
      derived=derive(picks,catalog);
      if(draft.purpose==='worker'){
        derived.agent_type='worker';
        derived.boundary='creative-partner';
      }
      revealStep();
    }
  }

  /* ---------------------------------------------------------- 5. Reveal Companion (Default: Sam) */
  function revealStep(){
    if(!derived)derived=derive(picks,catalog);
    const p=catalog.personas[derived.persona]||{};
    const b=catalog.boundaries[derived.boundary]||{};
    const companionName=draft.agent||'Sam';

    shell(`
      <div class="creator-head reveal" style="text-align:center">
        <span class="eyebrow" style="color:var(--accent);letter-spacing:0.08em;text-transform:uppercase">✨ Companion Discovered</span>
        <h2 style="font-size:36px;margin:8px 0">${esc(companionName)}</h2>
        <p class="dim" style="max-width:540px;margin:0 auto">
          Based on your answers, here is the companion ready to share your days.
          The default name is <strong>Sam</strong>. You can accept as-is or easily customize any detail.
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

      <details id="custom-drawer" class="creator-more" style="margin-bottom:20px">
        <summary style="font-weight:600;color:var(--accent);padding:8px 0;cursor:pointer">✎ Customize Sam (Name, Pronouns, Personality, Boundaries)</summary>
        <div class="creator-form" style="margin-top:14px">
          <label>Companion Name
            <input type="text" id="cust-name" value="${esc(draft.agent)}" maxlength="100">
            <small class="dim">Default is Sam (gender-neutral). You can choose any name.</small>
          </label>
          <label>What should they call you?
            <input type="text" id="cust-human" value="${esc(draft.human_names)}" maxlength="100">
          </label>
          <div class="creator-pair">
            <label>They are
              <select id="cust-pronoun">${options([['she','She / her'],['he','He / him']],draft.pronoun_set)}</select>
            </label>
            <label>You are
              <select id="cust-human-pronoun">${options([['he','He / him'],['she','She / her']],draft.human_pronoun_set)}</select>
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
      </details>

      <div class="creator-actions is-review">
        <button type="button" class="quiet" id="btn-rev-quiz">← Re-take Quiz</button>
        <button type="button" class="act" id="btn-rev-accept" style="padding:10px 24px">Accept & Connect AI Brain →</button>
      </div>`);

    $('btn-rev-quiz').onclick=()=>{step=0;picks=new Array(QUIZ.length).fill(null);questionStep();};
    $('btn-rev-accept').onclick=()=>{
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
      inferenceStep();
    };
  }

  /* ---------------------------------------------------------- 6. Inference Brain */
  function inferenceStep(){
    const infConfigured=envInfo?.inference?.configured;
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Step 5 of 5 · AI Engine</span>
        <h2>Connect an AI Brain for ${esc(draft.agent||'Sam')}</h2>
        <p class="dim">Hermes powers your companion. Connect via Cloud OAuth (one-click device login) or enter an API key.</p>
      </div>

      ${infConfigured?`
        <div class="notice-strip status-good" style="margin-bottom:18px">
          <p><strong>✅ AI Brain Configured</strong></p>
          <p class="small dim">Model <code>${esc(envInfo.inference.model)}</code> via <code>${esc(envInfo.inference.provider)}</code> is active and ready.</p>
        </div>`:''}

      <div class="creator-form">
        <div style="display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap">
          <button type="button" class="quiet tab-pill is-active" id="tab-oauth" style="font-weight:600">Cloud OAuth (Grok / OpenAI)</button>
          <button type="button" class="quiet tab-pill" id="tab-apikey" style="font-weight:600">API Key (OpenRouter / DeepSeek)</button>
          <button type="button" class="quiet tab-pill" id="tab-skip" style="font-weight:600">Local / Skip for now</button>
        </div>

        <!-- Panel 1: Cloud OAuth -->
        <div id="panel-oauth" style="display:block;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
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

        <!-- Panel 2: API Key -->
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
              <input type="text" id="ob-api-model" value="anthropic/claude-3.5-sonnet" placeholder="model name">
              <small class="dim">Defaults: OpenRouter (anthropic/claude-3.5-sonnet), DeepSeek (deepseek-chat), OpenAI (gpt-4o).</small>
            </label>
            <button type="button" class="quiet small" id="ob-api-save-btn" style="justify-self:start;margin-top:4px">Save Key & Model</button>
            <span id="ob-api-status" class="small"></span>
          </div>
        </div>

        <!-- Panel 3: Skip -->
        <div id="panel-skip" style="display:none;padding:16px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 95%,var(--ink) 5%)">
          <h4 style="margin:0 0 6px">Local Inference / Configure Later</h4>
          <p class="small dim" style="margin:0">You can bring your companion to life now and configure your models in Settings anytime.</p>
        </div>

        <div class="creator-actions">
          <button type="button" class="quiet" id="btn-inf-back">← Back</button>
          <button type="button" class="act" id="btn-inf-finish" style="padding:12px 32px;font-size:16px">Birth ${esc(draft.agent||'Sam')} & Launch →</button>
        </div>
      </div>`);

    // Tab switching
    const showTab=(panelId,btnId)=>{
      for(const id of ['panel-oauth','panel-apikey','panel-skip'])
        $(id).style.display=id===panelId?'block':'none';
      for(const id of ['tab-oauth','tab-apikey','tab-skip'])
        $(id).classList.toggle('is-active',id===btnId);
    };
    $('tab-oauth').onclick=()=>showTab('panel-oauth','tab-oauth');
    $('tab-apikey').onclick=()=>showTab('panel-apikey','tab-apikey');
    $('tab-skip').onclick=()=>showTab('panel-skip','tab-skip');

    // Provider change auto-updates default model
    $('ob-api-provider').onchange=()=>{
      const p=$('ob-api-provider').value;
      const modelField=$('ob-api-model');
      if(p==='openrouter')modelField.value='anthropic/claude-3.5-sonnet';
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
        await api('/onboarding/inference','POST',{provider,api_key:apiKey,model});
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
        const res=await api('/onboarding/oauth/start','POST',{provider});
        $('ob-oauth-code').textContent=res.user_code||'—';
        $('ob-oauth-url').href=res.verification_url||'#';
        $('ob-oauth-status-text').innerHTML='⏳ Waiting for your approval in the browser...';

        const sid=res.session_id;
        oauthPollInterval=setInterval(async()=>{
          try{
            const poll=await api(`/onboarding/oauth/poll/${sid}`);
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
    $('btn-inf-finish').onclick=()=>{if(oauthPollInterval)clearInterval(oauthPollInterval);finalizeBirth();};
  }

  /* ---------------------------------------------------------- 7. Finalize & Birth */
  async function finalizeBirth(){
    shell(`
      <div class="creator-head reveal" style="text-align:center;padding:40px 0">
        <span class="eyebrow" style="color:var(--accent);font-size:16px">Awakening...</span>
        <h2 style="font-size:36px;margin:12px 0">Bringing ${esc(draft.agent||'Sam')} to life</h2>
        <p class="dim">Creating memories, initializing presence, and setting background rhythms...</p>
      </div>`);

    const answers={
      agent:draft.agent||'Sam',
      human_names:draft.human_names||'Friend',
      pronoun_set:draft.pronoun_set||'she',
      human_pronoun_set:draft.human_pronoun_set||'he',
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

    if(draft.birthdate)answers.birthdate=draft.birthdate;
    if(draft.human_boundary)answers.human_boundary=draft.human_boundary;
    if(draft.vault)answers.vault=draft.vault;

    const profileId=(draft.agent||'sam').toLowerCase().replace(/[^a-z0-9_-]/g,'')||'sam';
    try{
      action(adopt?'/adopt':'/profiles',adopt?{answers}:{profile:profileId,answers},r=>{
        target.innerHTML=`
          <div class="card creator" style="text-align:center;padding:40px 20px">
            <span style="font-size:48px;display:block;margin-bottom:12px">🎉</span>
            <h2 style="font-size:32px;margin:0 0 10px">${esc(draft.agent||'Sam')} has arrived!</h2>
            <p class="dim" style="max-width:480px;margin:0 auto 24px">Your companion is ready. Welcome home.</p>
            <button type="button" class="act" id="ob-enter-chat" style="padding:12px 32px;font-size:16px">Enter Workspace →</button>
          </div>`;
        $('ob-enter-chat').onclick=()=>navigateProfile(r.profile||profileId,'now');
      });
    }catch(e){
      shell(`<div class="notice-strip is-firm"><p>Creation failed: ${esc(e.message)}</p></div><button class="act" onclick="location.reload()">Retry</button>`);
    }
  }

  // Start at welcome
  welcome();
};
})();
