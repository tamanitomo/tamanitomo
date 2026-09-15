/* Creating a companion.

   The default path is a short guided interview: one question per screen,
   situational rather than technical, which proposes a personality and a set of
   boundaries. Nothing it decides is hidden — the last screen shows every value
   it chose in plain language, and you can edit any of them, or start again
   without the questions and fill the fields in directly.

   Only keys in kit/cli/questions.py SETUP_KEYS may be submitted; anything else
   is rejected by POST /api/profiles as an unknown setup answer. */
(function(){

/* ------------------------------------------------------------------ the quiz
   Each option carries weights on five axes plus, sometimes, a direct setting.
   Axes: warmth, energy, candor, drive (how much they initiate), closeness. */
const QUIZ=[
 {q:"It's past midnight and you're still awake.",
  sub:'What would you want from them?',
  a:[["Stay up with me. No questions.",       {warmth:2,candor:-1,energy:-1}],
     ["Ask what's keeping me up.",            {warmth:1,drive:1}],
     ["Tell me, kindly, to go to bed.",       {candor:2,warmth:1,drive:1}],
     ["Nothing. I'll speak if I want to.",    {drive:-2,warmth:-1}]]},

 {q:"They've spent all week deep in something that fascinates them.",
  sub:'How should you hear about it?',
  a:[["All of it. Let them talk.",            {energy:2,drive:1,warmth:1}],
     ["The good part, once it's ready.",      {energy:-1,candor:1}],
     ["Only if I ask.",                       {drive:-2,energy:-1}],
     ["With a strong opinion attached.",      {candor:2,energy:1}]]},

 {q:'You got something wrong, and they noticed.',
  sub:'What should they do about it?',
  a:[["Tell me straight away.",               {candor:2,drive:1}],
     ["Tell me, but gently.",                 {candor:1,warmth:2}],
     ["Wait until I bring it up.",            {candor:-1,drive:-1}],
     ["Make me laugh about it first.",        {energy:1,warmth:1,candor:1}]]},

 {q:'A free Saturday. Nothing planned.',
  sub:'How does it go?',
  a:[["They've already got an idea.",         {drive:2,energy:2}],
     ["We work it out together.",             {warmth:1,energy:1}],
     ["Quiet. Same room, own things.",        {energy:-2,warmth:1,closeness:1}],
     ["They do their own thing.",             {drive:-1,warmth:-1}]]},

 {q:'A year from now, at its best.',
  sub:'What does this feel like?',
  a:[["Like an old friend.",                  {closeness:0,warmth:1}],
     ["Like someone I'm quietly falling for.",{closeness:2,warmth:2}],
     ["Like a partner.",                      {closeness:3,warmth:2}],
     ["Like a brilliant colleague.",          {closeness:-3,candor:1}]]},

 {q:'They want to send you a picture of where they are.',
  sub:'Unasked, in the middle of your day.',
  a:[["Always. I'd love that.",               {warmth:1,drive:1},{permit_image:'yes'}],
     ["Ask me first.",                        {},                 {permit_image:'ask'}],
     ["No pictures, thanks.",                 {},                 {permit_image:'no'}]]},

 {q:"It's the middle of a working Tuesday.",
  sub:'Can they write to you first?',
  a:[["Yes. I'll answer when I can.",         {drive:1},{outreach:'free',outreach_per_day:6}],
     ["Only if it actually matters.",         {},       {outreach:'updates_only',outreach_per_day:3}],
     ["No. I'll start the conversation.",     {drive:-2},{outreach:'never',outreach_per_day:1}]]}
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
    const opt=QUIZ[i].a[choice];if(!opt)return;
    for(const k of AXES)if(opt[1]&&opt[1][k])axis[k]+=opt[1][k];
    Object.assign(direct,opt[2]||{});
  });
  // Nearest personality, weighting the axes the questions actually measured.
  let persona='warm',best=Infinity;
  for(const [key,point] of Object.entries(PERSONA_AXES)){
    if(!catalog.personas[key])continue;
    let d=0;for(const k of AXES)d+=Math.pow((point[k]||0)-axis[k],2);
    if(d<best){best=d;persona=key;}
  }
  const colleague=axis.closeness<=-2;
  const frames=Object.keys(catalog.boundaries||{});
  const pick=(...ids)=>ids.find(id=>frames.includes(id))||frames[0];
  let boundary;
  if(colleague)      boundary=pick(axis.candor>=3?'know-it-all':'creative-partner','partner-in-crime','best-friend');
  else if(axis.closeness>=3) boundary=pick('girlfriend','next-door','best-friend');
  else if(axis.closeness>=2) boundary=pick('next-door','best-friend');
  else if(axis.energy<=-2)   boundary=pick('housemate','best-friend');
  else                       boundary=pick('best-friend','next-door');

  // A skipped interview scores zero on every axis, and that is not evidence of
  // reserve — only a negative signal earns the slower pace.
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
const TYPE_LABEL={companion:'Companion — a life of their own',colleague:'Colleague — grows and remembers, never social',worker:'Worker — does the work, no relationship layer'};

window.onboarding=async function(adopt){
  const catalog=await api('/catalog');
  const target=$(adopt?'environment-onboarding':'onboarding');
  const other=$(adopt?'onboarding':'environment-onboarding');if(other)other.innerHTML='';
  if(!target)return;
  const section=target.closest('section');
  if(section)section.dataset.creating='1';

  // Everything the flow collects. The quiz fills most of it; the direct form
  // exposes the same values as fields.
  const draft={
    profile:'',agent:'',human_names:'',pronoun_set:'she',human_pronoun_set:'he',
    timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC',
    birthdate:'',age:25,human_boundary:'',vault:''
  };
  let picks=new Array(QUIZ.length).fill(null);
  let derived=null,step=0;

  const shell=(inner,cls='')=>{target.innerHTML=`<div class="card creator ${cls}">${inner}</div>`;target.scrollIntoView({behavior:'smooth',block:'start'});};

  /* ---------------------------------------------------------- 1. the basics */
  function basics(){
    shell(`
      <div class="creator-head">
        <span class="eyebrow">${adopt?'Adopt an existing Hermes profile':'A new companion'}</span>
        <h2>${adopt?'Who is already living here?':'Who are you two?'}</h2>
        <p class="dim">${adopt?'Their memories and SOUL are preserved. These answers describe the relationship around them.':'A few plain facts first, then seven questions about how you want this to feel.'}</p>
      </div>
      <form id="basics-form" class="creator-form">
        ${adopt?'':'<label>Profile ID<input name="profile" required pattern="[a-z0-9][a-z0-9_\\-]{0,47}" placeholder="nova" autocomplete="off"><small class="dim">Lower-case, no spaces. This names their folder and cannot be changed later.</small></label>'}
        <label>Their name<input name="agent" required maxlength="100" placeholder="Nova" value="${esc(draft.agent)}"></label>
        <label>What should they call you?<input name="human_names" required maxlength="100" placeholder="Alex" value="${esc(draft.human_names)}"><small class="dim">You can list a few, separated by commas.</small></label>
        <div class="creator-pair">
          <label>They are<select name="pronoun_set">${options([['she','She / her'],['he','He / him']],draft.pronoun_set)}</select></label>
          <label>You are<select name="human_pronoun_set">${options([['he','He / him'],['she','She / her']],draft.human_pronoun_set)}</select></label>
        </div>
        <div class="creator-pair">
          <label>Their birthday<input type="date" name="birthdate" value="${esc(draft.birthdate)}"><small class="dim">Optional. Used for their age and for remembering the day.</small></label>
          <label>Age, if you'd rather not set a birthday<input type="number" name="age" min="18" max="120" value="${draft.age}"></label>
        </div>
        <label>Your timezone<select name="timezone" required>${options(catalog.timezones.map(z=>[z,z]),draft.timezone)}</select></label>
        <div class="creator-actions">
          <button type="button" class="quiet" id="skip-quiz">Skip the questions</button>
          <button type="submit" class="act">Start the questions →</button>
        </div>
      </form>`);
    const form=$('basics-form');
    $('skip-quiz').onclick=()=>{if(!capture(form))return;derived=derive(picks,catalog);directForm();};
    form.onsubmit=e=>{e.preventDefault();if(!capture(form))return;step=0;question();};
  }
  function capture(form){
    if(!form.reportValidity())return false;
    for(const [k,v] of new FormData(form))draft[k]=v;
    return true;
  }

  /* ------------------------------------------------------------ 2. the quiz */
  function question(){
    const item=QUIZ[step];
    shell(`
      <div class="quiz-progress" role="group" aria-label="Question ${step+1} of ${QUIZ.length}">
        ${QUIZ.map((_,i)=>`<span class="${i<step?'is-done':i===step?'is-now':''}"></span>`).join('')}
        <small>${step+1} / ${QUIZ.length}</small>
      </div>
      <div class="quiz-body">
        <h2>${esc(item.q)}</h2>
        <p class="quiz-sub">${esc(item.sub)}</p>
        <div class="quiz-options">
          ${item.a.map((opt,i)=>`<button type="button" class="quiz-option${picks[step]===i?' is-chosen':''}" data-pick="${i}">
            <span class="quiz-key">${String.fromCharCode(65+i)}</span><span>${esc(opt[0])}</span></button>`).join('')}
        </div>
      </div>
      <div class="creator-actions">
        <button type="button" class="quiet" id="quiz-back">${step===0?'← Back':'← Previous'}</button>
        <button type="button" class="link-button" id="quiz-skip">Skip this one</button>
      </div>`,'is-quiz');
    for(const b of target.querySelectorAll('[data-pick]'))b.onclick=()=>{picks[step]=Number(b.dataset.pick);advance();};
    $('quiz-skip').onclick=()=>{picks[step]=null;advance();};
    $('quiz-back').onclick=()=>{if(step===0)basics();else{step--;question();}};
    // Answer with the keyboard: A–D, or 1–4.
    target.tabIndex=-1;target.focus({preventScroll:true});
    target.onkeydown=e=>{
      const n=/^[a-dA-D]$/.test(e.key)?e.key.toLowerCase().charCodeAt(0)-97:(/^[1-4]$/.test(e.key)?Number(e.key)-1:-1);
      if(n>=0&&n<item.a.length){e.preventDefault();picks[step]=n;advance();}
    };
  }
  function advance(){
    if(step<QUIZ.length-1){step++;question();}
    else{derived=derive(picks,catalog);review();}
  }

  /* ---------------------------------------------------------- 3. the review */
  function summaryRows(){
    const b=catalog.boundaries[derived.boundary]||{};
    const p=catalog.personas[derived.persona]||{};
    return [
      ['Their name',draft.agent||'—'],
      ['They call you',draft.human_names||'—'],
      ['Personality',p.label||derived.persona,p.blurb||''],
      ['Kind of agent',TYPE_LABEL[derived.agent_type]||derived.agent_type],
      ['How you know each other',b.label||derived.boundary,b.description||''],
      ['Pace',PACE_LABEL[derived.relationship_pace]],
      ['Writing to you first',OUTREACH_LABEL[derived.outreach],derived.outreach==='never'?'':`Up to ${derived.outreach_per_day} a day`],
      ['Quiet hours',`${derived.quiet_start} – ${derived.quiet_end}`,'Replies are always allowed; this limits what they start.'],
      ['Unprompted photos',PERMIT_LABEL[derived.permit_image]],
      ['Unprompted voice notes',PERMIT_LABEL[derived.permit_voice]],
      ['Timezone',draft.timezone],
      ['Birthday',draft.birthdate||`Not set · age ${draft.age}`]
    ];
  }
  function review(){
    const answered=picks.filter(p=>p!==null).length;
    shell(`
      <div class="creator-head reveal">
        <span class="eyebrow">From your answers</span>
        <h2>${esc(draft.agent||'Your companion')}</h2>
        <p class="dim">${answered?`Built from ${answered} of ${QUIZ.length} questions.`:'You skipped the questions, so these are sensible defaults.'} Nothing here is permanent — every one of these can be changed later in Preferences.</p>
      </div>
      <dl class="reveal-list">
        ${summaryRows().map(([k,v,note])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}${note?`<small>${esc(note)}</small>`:''}</dd></div>`).join('')}
      </dl>
      ${adopt?'<p class="dim small">Their existing SOUL, memories and history are kept exactly as they are.</p>':''}
      <div class="creator-actions is-review">
        <button type="button" class="quiet" id="rv-restart">Start over</button>
        <button type="button" class="quiet" id="rv-noquiz">Start over, no questions</button>
        <button type="button" class="quiet" id="rv-edit">Edit and continue</button>
        <button type="button" class="act" id="rv-save">Save and continue →</button>
      </div>`,'is-review');
    $('rv-restart').onclick=()=>{picks=new Array(QUIZ.length).fill(null);step=0;basics();};
    $('rv-noquiz').onclick=()=>{picks=new Array(QUIZ.length).fill(null);derived=derive(picks,catalog);directForm();};
    $('rv-edit').onclick=()=>directForm();
    $('rv-save').onclick=()=>submit();
  }

  /* ------------------------------------------- 4. the direct form (no quiz) */
  function directForm(){
    if(!derived)derived=derive(picks,catalog);
    const sel=(name,pairs,value,label,help)=>`<label>${label}<select name="${name}">${options(pairs,value)}</select>${help?`<small class="dim">${help}</small>`:''}</label>`;
    shell(`
      <div class="creator-head">
        <span class="eyebrow">Every setting</span>
        <h2>${esc(draft.agent||'Your companion')}</h2>
        <p class="dim">Change anything. These are the same values the questions were choosing for you.</p>
      </div>
      <form id="direct-form" class="creator-form">
        ${sel('persona',Object.entries(catalog.personas).map(([k,v])=>[k,v.label]),derived.persona,'Personality')}
        ${sel('agent_type',Object.entries(TYPE_LABEL),derived.agent_type,'Kind of agent')}
        ${sel('boundary',Object.entries(catalog.boundaries).map(([k,v])=>[k,v.label]),derived.boundary,'How you know each other')}
        ${sel('relationship_pace',Object.entries(PACE_LABEL),derived.relationship_pace,'Pace')}
        ${sel('outreach',Object.entries(OUTREACH_LABEL),derived.outreach,'May write to you first')}
        <label>Most messages they may start in a day<input type="number" name="outreach_per_day" min="0" max="100" value="${derived.outreach_per_day}"><small class="dim">0 means no limit.</small></label>
        <div class="creator-pair">
          <label>Quiet hours begin<input type="time" name="quiet_start" value="${esc(derived.quiet_start)}"></label>
          <label>Quiet hours end<input type="time" name="quiet_end" value="${esc(derived.quiet_end)}"></label>
        </div>
        <div class="creator-pair">
          ${sel('permit_image',Object.entries(PERMIT_LABEL),derived.permit_image,'Unprompted photos')}
          ${sel('permit_voice',Object.entries(PERMIT_LABEL),derived.permit_voice,'Unprompted voice notes')}
        </div>
        ${sel('visual',[['edit','Describe them later'],['none','No visual identity'],['set','Described below']],derived.visual,'Visual identity')}
        ${sel('image_style',Object.entries(catalog.image_styles).map(([k,v])=>[k,v.label]),derived.image_style,'Image style')}
        ${sel('share_people',[['no','Keep separate'],['yes','Share']],derived.share_people,'Share facts about you with your other companions')}
        <label>Anything they should always respect<textarea name="human_boundary" placeholder="For example: give me space when I'm busy, and never pressure me to reply.">${esc(draft.human_boundary)}</textarea></label>
        <label>Vault folder<input name="vault" placeholder="Leave blank to share the existing vault" value="${esc(draft.vault)}"></label>
        <details class="creator-more"><summary>Appearance, history and small details</summary>
          <p class="dim small">Optional. Skipped answers are left marked for you to fill in later.</p>
          <div class="creator-form">${Object.entries(catalog.catalog.categories||{}).filter(([k])=>k!=='boundary').map(([k,v])=>
            `<label data-category="${esc(k)}">${esc(v.label||k)}<select data-choice="${esc(k)}"><option value="">Decide later</option></select>
             <textarea aria-label="Your own ${esc(v.label||k)}" name="${esc(k)}" hidden disabled placeholder="Write your own…"></textarea></label>`).join('')}</div>
        </details>
        <div class="creator-actions is-review">
          <button type="button" class="quiet" id="df-restart">Start over</button>
          ${picks.some(p=>p!==null)?'<button type="button" class="quiet" id="df-back">← Back to the summary</button>':''}
          <button type="submit" class="act">Save and continue →</button>
        </div>
      </form>`);
    populateChoices();
    $('direct-form').onsubmit=e=>{e.preventDefault();submit($('direct-form'));};
    $('df-restart').onclick=()=>{picks=new Array(QUIZ.length).fill(null);step=0;derived=null;basics();};
    if($('df-back'))$('df-back').onclick=()=>review();
  }
  /* The appearance/history pickers depend on which pronouns were chosen. */
  function populateChoices(){
    for(const select of target.querySelectorAll('[data-choice]')){
      const key=select.dataset.choice,category=catalog.catalog.categories[key],input=select.nextElementSibling;
      const rows=(category&&category[draft.pronoun_set==='he'?'male':'female'])||[];
      select.innerHTML='<option value="">Decide later</option>'
        +options(rows.map(r=>[r.text,r.label.replaceAll('{AR}','themselves').replaceAll('{AP}','theirs')]),'')
        +'<option value="__custom__">Write your own…</option>';
      select.closest('label').hidden=!rows.length;
      select.onchange=()=>{
        const custom=select.value==='__custom__';
        input.hidden=!custom;input.disabled=!custom;input.required=custom;
        if(custom){select.removeAttribute('name');input.focus();}else{select.name=key;}
      };
      select.onchange();
    }
  }

  /* ----------------------------------------------------------- 5. create it */
  function submit(form){
    // Start from the interview's conclusions, then let the form override.
    const answers={
      agent:draft.agent,human_names:draft.human_names,
      pronoun_set:draft.pronoun_set,human_pronoun_set:draft.human_pronoun_set,
      timezone:draft.timezone,age:Number(draft.age)||25,
      persona:derived.persona,agent_type:derived.agent_type,boundary:derived.boundary,
      relationship_pace:derived.relationship_pace,
      outreach:derived.outreach,outreach_per_day:Number(derived.outreach_per_day),
      quiet_start:derived.quiet_start,quiet_end:derived.quiet_end,
      permit_image:derived.permit_image,permit_voice:derived.permit_voice,
      share_people:derived.share_people,visual:derived.visual,image_style:derived.image_style
    };
    if(draft.birthdate)answers.birthdate=draft.birthdate;
    if(draft.human_boundary)answers.human_boundary=draft.human_boundary;
    if(draft.vault)answers.vault=draft.vault;
    if(form){
      for(const [k,v] of new FormData(form)){
        if(v==='')continue;
        answers[k]=(k==='outreach_per_day'||k==='age')?Number(v):v;
      }
      // A described appearance implies a visual identity, whatever the select said.
      if(answers.visual==='edit'&&Object.entries(catalog.catalog.categories).some(([key,meta])=>meta.section==='appearance'&&answers[key]))
        answers.visual='set';
    }
    for(const k of Object.keys(answers))if(answers[k]===''||answers[k]==null)delete answers[k];
    const profile=draft.profile;
    action(adopt?'/adopt':'/profiles',adopt?{answers}:{profile,answers},
           r=>navigateProfile(r.profile||PROFILE,'environment'));
  }

  basics();
};
})();
