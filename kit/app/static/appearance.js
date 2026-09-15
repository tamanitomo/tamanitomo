/* Workspace appearance: theme, accent, and the destinations pinned to the
   mobile bar. State lives with the companion's profile on the server, so a
   companion looks the same on the phone and the desktop, with a localStorage
   mirror so the first paint never flashes the wrong palette. */
(function(){
const THEME_NAMES={
  midnight:'Midnight',nord:'Nordic Frost',ocean:'Deep Ocean',emerald:'Emerald Pine',
  amethyst:'Amethyst',synthwave:'Synthwave',ember:'Ember',sakura:'Sakura',carbon:'Carbon',
  daylight:'Daylight',parchment:'Parchment',mist:'Morning Mist'
};
const DARK=['midnight','nord','ocean','emerald','amethyst','synthwave','ember','sakura','carbon'];
const LIGHT=['daylight','parchment','mist'];
const DEFAULTS={theme:'midnight',accent:'',follow_system:false,
  dark_theme:'midnight',light_theme:'daylight',nav_pins:['chat','now','photos','journals']};
const KEY='companion-appearance';
const dark=matchMedia('(prefers-color-scheme: dark)');

let state=Object.assign({},DEFAULTS);
try{const raw=localStorage.getItem(KEY);if(raw)state=Object.assign(state,JSON.parse(raw));}catch(e){}

/* Which theme is actually showing, once "match system" is taken into account. */
function effective(){
  if(state.follow_system)return dark.matches?state.dark_theme:state.light_theme;
  return state.theme;
}
/* Text that sits on top of a filled accent. A custom accent can be any
   lightness, so pick the readable side rather than trusting the theme's. */
function onAccent(hex){
  const m=/^#([0-9a-f]{6})$/i.exec(hex||'');
  if(!m)return null;
  const n=parseInt(m[1],16),r=(n>>16)&255,g=(n>>8)&255,b=n&255;
  const lin=c=>{c/=255;return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4);};
  return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b)>0.42?'#0b0d12':'#ffffff';
}
function apply(){
  const root=document.documentElement;
  root.dataset.theme=effective();
  if(state.accent){
    root.style.setProperty('--accent',state.accent);
    const on=onAccent(state.accent);
    if(on)root.style.setProperty('--on-accent',on);
  }else{
    root.style.removeProperty('--accent');
    root.style.removeProperty('--on-accent');
  }
  try{localStorage.setItem(KEY,JSON.stringify(state));}catch(e){}
  window.dispatchEvent(new CustomEvent('appearance-change',{detail:Object.assign({},state)}));
}
/* Read a theme's real token values so swatches can never drift from the CSS. */
function swatch(id){
  const root=document.documentElement,was=root.dataset.theme,had=root.style.getPropertyValue('--accent');
  root.dataset.theme=id;root.style.removeProperty('--accent');
  const s=getComputedStyle(root);
  const out={bg:s.getPropertyValue('--bg').trim(),panel:s.getPropertyValue('--panel').trim(),
             accent:s.getPropertyValue('--accent').trim(),ink:s.getPropertyValue('--ink').trim(),
             edge:s.getPropertyValue('--edge').trim()};
  root.dataset.theme=was;if(had)root.style.setProperty('--accent',had);
  return out;
}
dark.addEventListener('change',()=>{if(state.follow_system)apply();});

window.Appearance={
  THEME_NAMES,DARK,LIGHT,
  get state(){return Object.assign({},state);},
  effective,apply,swatch,
  name:id=>THEME_NAMES[id]||id,
  isDark:id=>DARK.includes(id),
  /* Merge a change, paint it at once, then persist to the profile. */
  async set(patch){
    state=Object.assign(state,patch);apply();
    try{await api('/appearance',{method:'POST',body:JSON.stringify(patch)});}
    catch(e){/* Local preference still applies if the profile cannot be written. */}
  },
  /* Pull the profile's saved appearance and adopt it. */
  async load(){
    try{
      const d=await api('/appearance');
      if(d&&d.appearance){state=Object.assign({},DEFAULTS,d.appearance);apply();}
      return d;
    }catch(e){apply();return null;}
  },
  reset(){state=Object.assign({},DEFAULTS);apply();}
};
apply();
})();
