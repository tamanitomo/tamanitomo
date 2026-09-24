/* The same derived state is displayed here and carried into model context. */
/* The five meters, as markup any surface can drop in. The same derived state is
   displayed here and carried into model context, so one renderer keeps the page
   and the prompt telling the same story. */
const FEELING_METERS=[
  ['warmth','Warmth','🔥','Affection toward you right now.'],
  ['trust','Trust','🛡️','How safe it feels to be open with you.'],
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
/* One experience per row, evidence folded away. Used by the emotional history
   on the Us page; the story feed there tells the same events in plainer words. */
function feelingHistoryRows(rows){
  return rows.map(x=>`<article class="moment-row"><div><span class="pill ${x.kind==='connection'?'good':x.kind==='rupture'?'bad':''}">${esc(x.kind)}</span><small>${esc(when(x.at))}</small></div><div><p style="margin:0;font-size:13.5px;line-height:1.4">${esc(x.text)}</p><details style="margin-top:4px"><summary class="dim small" style="cursor:pointer">Context & evidence</summary><p class="dim small" style="margin:4px 0">${esc(x.evidence)}</p></details></div></article>`).join('')||'<p class="dim small" style="padding:14px;text-align:center">No emotional experiences recorded yet. Meaningful connections or ruptures will be noted naturally during conversation.</p>';
}
/* The full, paged history, drawn into whatever host asks for it. A page that
   arrives after the host has gone (the dialog closed, another opened) is dropped. */
async function mountFeelingHistory(host){
  if(!host)return;
  const first=await api('/feelings/experiences');
  if(!host.isConnected)return;
  const history=[...first.experiences];let cursor=first.next_cursor,total=first.total;
  host.innerHTML=`<p class="dim">Warmth, trust, ruptures and repairs, as they happened in conversation — this is what the feelings are made of.</p>
    <div class="feelings-history"></div>
    <div class="actions"><span class="dim small" role="status"></span><button type="button" class="quiet" hidden>Load older experiences</button></div>`;
  const list=host.querySelector('.feelings-history'),count=host.querySelector('[role=status]'),older=host.querySelector('button');
  const draw=()=>{list.innerHTML=feelingHistoryRows(history);count.textContent=`${history.length} of ${total} experiences`;older.hidden=!cursor;};
  older.onclick=async()=>{
    older.disabled=true;
    try{
      const page=await api('/feelings/experiences?'+new URLSearchParams({before:cursor}));
      if(!host.isConnected)return;
      history.push(...page.experiences.filter(row=>!history.some(x=>x.id===row.id)));cursor=page.next_cursor;total=page.total;
      draw();
    }catch(error){if(host.isConnected)count.textContent=error.message;}
    finally{older.disabled=false;}
  };
  draw();
}
