/* The same derived state is displayed here and carried into model context. */
/* The five meters, as markup any surface can drop in. The same derived state is
   displayed here and carried into model context, so one renderer keeps the page
   and the prompt telling the same story. */
const FEELING_METERS=[
  ['warmth','Warmth','🔥','How affectionate she feels toward you right now.'],
  ['trust','Trust','🛡️','How safe she feels being open with you.'],
  ['hurt','Hurt','🩹','Lingering pain from something that went wrong.'],
  ['irritation','Irritation','⚡','Friction that has not been talked through yet.'],
  ['longing','Missing you','⏳','How much your absence is being felt.'],
];
function feelingMeters(meters){
  return `<div class="meter-grid">${FEELING_METERS.map(([key,label,icon,why])=>{
    const value=meters?meters[key]:null;
    const pct=value==null?null:Math.round(value*100);
    return `<div class="meter-card meter-${key}" title="${esc(why)}">
      <div class="meter-head"><span>${icon} ${label}</span><strong>${pct==null?'—':pct+'%'}</strong></div>
      <div class="meter-track"><div class="meter-fill" style="width:${pct||0}%"></div></div>
      <small class="dim">${esc(why)}</small>
    </div>`;
  }).join('')}</div>`;
}
let feelingsGeneration=0;
async function mountFeelings(){
  const generation=++feelingsGeneration,targetHost=$('feelings-controls');
  const [data,first]=await Promise.all([api('/feelings'),api('/feelings/experiences')]);
  if(current!=='relationship'||!targetHost||$('feelings-controls')!==targetHost||generation!==feelingsGeneration)return;
  let history=first.experiences,cursor=first.next_cursor;
  const host=$('feelings-controls');
  host.innerHTML=`<div class="card">
    <div class="section-heading" style="margin-top:0">
      <h2>What moved the feelings</h2>
      <span class="dim small" id="feelings-history-count" role="status"></span>
    </div>
    <p class="dim">Warmth, trust, ruptures and repairs, as they happened in conversation — this is what the meters above are made of.</p>
    <div id="feelings-history"></div>
    <div style="margin-top:12px">
      <button type="button" class="quiet" id="feelings-older" hidden>Load older experiences</button>
    </div>
  </div>`;
  const historyHTML=rows=>rows.map(x=>`<article class="moment-row"><div><span class="pill ${x.kind==='connection'?'good':x.kind==='rupture'?'bad':''}">${esc(x.kind)}</span><small>${esc(when(x.at))}</small></div><div><p style="margin:0;font-size:13.5px;line-height:1.4">${esc(x.text)}</p><details style="margin-top:4px"><summary class="dim small" style="cursor:pointer">Context & evidence</summary><p class="dim small" style="margin:4px 0">${esc(x.evidence)}</p></details></div></article>`).join('')||'<p class="dim small" style="padding:14px;text-align:center">No emotional experiences recorded yet. Meaningful connections or ruptures will be noted naturally during conversation.</p>';
  const drawHistory=()=>{
    $('feelings-history').innerHTML=historyHTML(history);
    $('feelings-history-count').textContent=`${history.length} of ${first.total} experiences`;
    $('feelings-older').hidden=!cursor;
  };
  $('feelings-older').onclick=async()=>{
    const button=$('feelings-older');button.disabled=true;
    try{
      const page=await api('/feelings/experiences?'+new URLSearchParams({before:cursor}));
      if(current!=='relationship'||generation!==feelingsGeneration||$('feelings-controls')!==host)return;
      history.push(...page.experiences.filter(row=>!history.some(x=>x.id===row.id)));cursor=page.next_cursor;first.total=page.total;
      drawHistory();
    }catch(error){if($('feelings-controls')===host)$('feelings-history-count').textContent=error.message;}
    finally{button.disabled=false;}
  };
  drawHistory();
}
