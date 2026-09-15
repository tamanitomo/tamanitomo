/* The same derived state is displayed here and carried into model context. */
function feelingsSummary(state){
  const labels={warmth:'Warmth',trust:'Trust',hurt:'Hurt',irritation:'Irritation',longing:'Missing you'};
  const colors={warmth:'linear-gradient(90deg,#f43f5e,#fb923c)',trust:'linear-gradient(90deg,#0ea5e9,#2dd4bf)',hurt:'linear-gradient(90deg,#ef4444,#f87171)',irritation:'linear-gradient(90deg,#eab308,#facc15)',longing:'linear-gradient(90deg,#8b5cf6,#c084fc)'};
  const icons={warmth:'🔥',trust:'🛡️',hurt:'🩹',irritation:'⚡',longing:'⏳'};
  const away=state.recent_return||state.absence;
  return `<div class="card connection-signals" style="margin-bottom:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px">
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:20px">🌊</span>
        <h2 style="margin:0">Emotional Atmosphere</h2>
        <span class="pill">${esc(state.personality)} temperament</span>
      </div>
      <div class="mood-aura-pill" style="background:rgba(255,255,255,0.05);padding:4px 12px;border-radius:20px;border:1px solid rgba(255,255,255,0.1);font-size:12px">
        <span>✨ <strong>${state.mood?esc(state.mood):'Calm'}</strong></span>
        ${state.mood_at?`<span class="dim small">· ${esc(ago(state.mood_at))}</span>`:''}
      </div>
    </div>
    <div class="feelings-meters-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:14px">
      ${Object.entries(state.meters).map(([key,value])=>{
        const pct=value==null?null:Math.round(value*100);
        return `<div class="feeling-meter-card" style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:12.5px;font-weight:600;display:flex;align-items:center;gap:6px"><span>${icons[key]||'•'}</span> ${labels[key]}</span>
            <strong style="font-size:13px;color:${key==='hurt'&&pct>20?'#f87171':'var(--text,#d8e2ee)'}">${pct==null?'—':pct+'%'}</strong>
          </div>
          <div style="height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:${pct||0}%;background:${colors[key]||'var(--accent)'};border-radius:3px;transition:width .3s"></div>
          </div>
        </div>`;
      }).join('')}
    </div>
    <div style="padding:10px 14px;background:rgba(255,255,255,0.02);border-radius:8px;border:1px solid rgba(255,255,255,0.05);margin-bottom:12px">
      <p class="dim small" style="margin:0;line-height:1.4">
        ${state.absence.current.length?`<strong style="color:#7ee787">Active Expected Routine:</strong> ${esc(state.absence.current.join(', '))}. `:''}
        ${away.hours==null?'Natural messaging rhythm active.':`<strong>${state.recent_return?'Recent Return':'Time Apart'}:</strong> ${Math.round(away.hours)}h elapsed (${Math.round(away.expected_hours)}h in routine windows).`}
      </p>
    </div>
    <details style="margin-top:8px"><summary class="dim small" style="cursor:pointer">What shapes these feelings?</summary>
      <div style="margin-top:8px;font-size:12px;color:rgba(255,255,255,0.7);line-height:1.5">
        <p class="dim small">${esc(state.basis)} Routines describe expectations, not live observations.</p>
        ${state.private_stance?`<p style="font-style:italic">“${esc(state.private_stance)}”</p>`:''}
        ${state.reasons.map(r=>`<p style="margin:4px 0">• ${esc(r.text)} <span class="dim">(${r.occurrence}x${r.repair?' · repaired':''})</span></p>`).join('')||'<p class="dim small">No ruptures recorded. Starting values reflect the selected emotional temperament.</p>'}
      </div>
    </details>
  </div>`;
}
let feelingsGeneration=0;
async function mountFeelings(){
  const generation=++feelingsGeneration,targetHost=$('feelings-controls');
  const [data,first]=await Promise.all([api('/feelings'),api('/feelings/experiences')]);
  if(current!=='relationship'||!targetHost||$('feelings-controls')!==targetHost||generation!==feelingsGeneration)return;
  let history=first.experiences,cursor=first.next_cursor;
  const host=$('feelings-controls');
  host.innerHTML=`<div class="card" style="margin-top:20px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div>
        <h2 style="margin:0">Emotional Experiences Ledger (${data.state.history_count||history.length})</h2>
        <p class="dim small" style="margin:2px 0 0">Authentic moments of warmth, trust, ruptures, and repairs recorded through conversation.</p>
      </div>
      <span class="dim small" id="feelings-history-count" role="status"></span>
    </div>
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
