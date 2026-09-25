/* Persistent Chat: one renderer for the conversation store (build plan Phase 2.3-2.5).

   NOT ACTIVATED; loaded only with the keyed client (see chat-store.js for the load order).

   A view is a message log plus a composer bound to the shared draft. The full Chat page
   and the dock are the same View with different containers; exactly one is mounted at a
   time, so there is one active composer. Rendering is keyed and incremental: an element
   is created once per item and afterwards only the parts that changed are replaced, so
   incoming text never rebuilds the log, never touches anything outside it, never moves
   focus and never scrolls someone away from older reading. A growing reply is one
   element from its first snapshot to its settled text. */
(function(){
'use strict';
if(!window.ChatStore)return;
const S=window.ChatStore;
const GROUP_WINDOW=5*60;

function items(s,{limit=0}={}){
  const out=[];
  const linkOf=r=>r._key.startsWith('h:')?s.links.get(r._key.slice(2)):null;
  const presented=new Set();
  for(const r of s.rows){const l=linkOf(r);if(l)presented.add(l.sendId+':'+l.part);}
  const rows=limit&&s.rows.length>limit?s.rows.slice(-limit):s.rows;
  const dayOf=m=>new Date((m.timestamp||0)*1000).toLocaleDateString();
  const sameRun=(a,b)=>a&&b&&a.role===b.role&&String(a.source||'')===String(b.source||'')
    &&Math.abs((b.timestamp||0)-(a.timestamp||0))<=GROUP_WINDOW&&dayOf(a)===dayOf(b);
  rows.forEach((m,i)=>{
    const prev=rows[i-1],next=rows[i+1],day=dayOf(m);
    if(!prev||dayOf(prev)!==day)out.push({key:'d:'+m._key,kind:'day',day});
    const link=linkOf(m),it=link?s.intents.get(link.key):null;
    out.push({key:m._key,kind:'row',row:m,starts:!sameRun(prev,m),ends:!sameRun(m,next),link,
      overlay:link&&link.part==='owner'&&it&&it.status&&!it.status.sent?it:null});
  });
  if(!s.rows.length&&!s.intents.size&&s.history==='ready')out.push({key:'welcome',kind:'welcome'});
  let streaming=false;
  for(const it of s.intents.values()){
    if(!(it.sendId&&presented.has(it.sendId+':owner')))
      out.push({key:'k:'+it.key+':owner',kind:it.request?'request':'owner',it});
    if(it.replies){
      it.replies.forEach((r,n)=>{
        if(presented.has(it.sendId+':reply:'+n))return;
        const {text,extractedMedia}=extractMediaFromContent(r.content);
        const media=[...(r.attachments||[]),...extractedMedia];
        if(text||media.length)out.push({key:'k:'+it.key+':reply:'+n,kind:'reply',it,n,text,media});
      });
    }else if(it.stream&&!presented.has(it.sendId+':reply:0')){
      streaming=true;
      out.push({key:'k:'+it.key+':reply:0',kind:'stream',it});
    }
  }
  if(s.typing&&!streaming)out.push({key:'typing',kind:'typing'});
  return out;
}

const time=d=>d.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});

function statusSmall(it){
  const st=it.status||{text:''};
  return `<small><span class="bubble-status">${st.bad?`<span class="bad">${esc(st.text)}</span>`:esc(st.text)}</span>`+
    (st.actions||[]).map((a,i)=>` <button type="button" class="quiet small" data-keyed-action="${i}">${esc(a.label)}</button>`).join('')+
    (it.confirm?`<span class="keyed-confirm"> ${esc(it.confirm.text)}
      <button type="button" class="quiet small" data-confirm="yes">Send anyway</button>
      <button type="button" class="quiet small" data-confirm="no">Cancel</button></span>`:'')+`</small>`;
}
const stateClass=it=>it.status?.bad?' send-error':it.status?.sent?'':' sending';

function html(item,ids){
  const id=v=>ids&&v?` id="${esc(v)}"`:'';
  const it=item.it;
  switch(item.kind){
    case 'day':return `<div class="chat-day">${esc(item.day)}</div>`;
    case 'welcome':return `<div class="chat-welcome">${faceHtml(chatName())}<h2>The beginning</h2>
      <p>Whatever you say here, and on any channel ${esc(chatName())} is reachable on, collects in this one place.</p></div>`;
    case 'typing':return `<div class="bubble typing"${id('chat-typing-indicator')} aria-label="${esc(chatName())} is typing"><span class="typing-dots"><i></i><i></i><i></i></span></div>`;
    case 'owner':return `<div class="bubble user${stateClass(it)}" data-channel="desktop" data-client-key="${esc(it.key)}"${id(it.sendId?it.sendId+':owner':'pending-'+it.key+':owner')}>
      <div class="message-body">${richText(it.message)}</div>${statusSmall(it)}</div>`;
    case 'request':return `<div class="keyed-request${stateClass(it)}" role="status" data-client-key="${esc(it.key)}"${id(it.sendId?it.sendId+':owner':'pending-'+it.key+':owner')}>
      <span class="keyed-request-label dim small">${esc(KeyedChat.words.requestLabel)}</span>
      <div class="message-body">${richText(it.message)}</div>${statusSmall(it)}</div>`;
    case 'stream':return `<div class="bubble" aria-label="Incoming reply"${id(it.sendId+':stream')}><div class="message-body">${esc(it.stream)}</div></div>`;
    case 'reply':return `<div class="bubble${it.partial?' partial':''}" data-channel="desktop"${id(it.sendId+':reply:'+item.n)}>
      <div class="message-body">${richText(item.text)}</div>${item.media.map(inlineMedia).join('')}
      <small>${it.partial?'<span class="dim">Partial reply</span> ':''}${esc(time(it.at||new Date()))}</small></div>`;
    case 'row':return rowHtml(item,ids);
  }
  return '';
}

/* One recorded message, as the Chat page has always drawn it (workspace.js chatMessagesHtml). */
function rowHtml(item,ids){
  const m=item.row,channel=channelOf(m.source),at=new Date((m.timestamp||0)*1000);
  const {text,extractedMedia}=extractMediaFromContent(m.content);
  const attachments=[...(m.attachments||[]),...extractedMedia];
  const badge=channel.key==='desktop'||channel.key==='web'?''
    :`<span class="bubble-channel">${channel.mark?channel.mark+' ':''}${esc(channel.label)}</span>`;
  const meta=item.overlay?statusSmall(item.overlay):item.ends?`<small>${badge}<span>${esc(time(at))}</span></small>`:'';
  const shape=[item.starts?'starts-run':'',item.ends?'ends-run':''].filter(Boolean).join(' ');
  const face=m.role!=='user'&&item.ends?faceHtml(chatName(),'bubble-face'):'';
  const l=item.link;
  const linked=l?`${ids?` id="${esc(l.sendId+':'+l.part)}"`:''}${l.part==='owner'?` data-client-key="${esc(l.key)}"`:''}`:'';
  const source=m.source_message!=null?` data-source-session="${esc(m.session)}" data-source-message="${esc(m.source_message)}"`:'';
  return `<div class="bubble ${m.role==='user'?'user':''} ${shape}" data-channel="${esc(channel.key)}"${source}${linked}>
      ${face}<div class="message-body">${richText(text)}</div>${attachments.map(inlineMedia).join('')}${meta}</div>`;
}

function build(markup){const t=document.createElement('template');t.innerHTML=markup.trim();return t.content.firstElementChild;}
const same=(a,b)=>a.nodeType===b.nodeType&&(a.nodeType===1?a.outerHTML===b.outerHTML:a.textContent===b.textContent);
/* Update an element in place: attributes, then only the children that differ. A selection
   inside an unchanged part (the owner's text while its status changes) stays. */
function morph(el,fresh){
  for(const a of [...el.attributes])if(!fresh.hasAttribute(a.name))el.removeAttribute(a.name);
  for(const a of [...fresh.attributes])if(el.getAttribute(a.name)!==a.value)el.setAttribute(a.name,a.value);
  const old=[...el.childNodes],neu=[...fresh.childNodes];
  if(old.length===neu.length){old.forEach((o,i)=>{if(!same(o,neu[i]))o.replaceWith(neu[i]);});return;}
  el.replaceChildren(...neu);
}

class View{
  /* parts: {kind:'page'|'dock', log, form, box, send, status, ids, limit, visible(), onOlder()} */
  constructor(parts){
    Object.assign(this,parts);
    this.scope=S.now();
    this.els=new Map();      // item key -> {el, markup}
    this.hintSeq=-1;
    this.head=document.createElement('div');this.head.className='chat-log-head';
    this.log.replaceChildren(this.head);
  }
  mount(){
    S.mount(this);
    const s=S.state(this.scope);
    this.unsubscribe=S.subscribe(()=>this.render());
    this.wireComposer();
    this.log.addEventListener('click',this.onClick=e=>this.click(e));
    // Where the reader is, kept as they scroll: by the time a view is disposed its log may
    // already be hidden (showTab hides the section first) and could not be measured.
    this.log.addEventListener('scroll',this.onScroll=()=>{
      if(this.nearBottom())this.hideNew();
      if(this.measuring)return;
      this.measuring=requestAnimationFrame(()=>{this.measuring=0;if(this.log.clientHeight)this.saveAnchor();});
    },{passive:true});
    // Pictures resolve their height late; a reader at the foot stays at the foot.
    this.log.addEventListener('load',this.onLoad=()=>{if(this.follow)this.toBottom();},true);
    this.saved=s.scroll[this.kind]||null;
    this.render(true);
    return this;
  }
  saveAnchor(){S.state(this.scope).scroll[this.kind]=this.anchor();}
  unmount(){
    if(!this.unsubscribe)return;
    if(this.log.clientHeight)this.saveAnchor();
    if(this.measuring)cancelAnimationFrame(this.measuring);
    this.hideNew();
    this.unsubscribe();this.unsubscribe=null;
    this.log.removeEventListener('click',this.onClick);
    this.log.removeEventListener('scroll',this.onScroll);
    this.log.removeEventListener('load',this.onLoad,true);
    this.observer?.disconnect();
    S.unmount(this);
  }
  composer(){return this.box&&this.box.isConnected?this.box:null;}

  wireComposer(){
    const box=this.box;if(!box)return;
    box.dataset.chatComposer=this.kind;
    box.value=S.draft.get(this.scope);
    this.grow=()=>{box.style.height='auto';box.style.height=Math.min(box.scrollHeight,this.kind==='dock'?140:200)+'px';};
    this.grow();
    box.addEventListener('input',()=>{S.draft.set(this.scope,box.value);this.grow();});
    box.addEventListener('keydown',e=>{
      if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!this.send.disabled)this.form.requestSubmit();}
    });
    // The owner's own message is followed to the foot, as the page always did.
    this.form.addEventListener('submit',e=>{e.preventDefault();if(box.value.trim())this.jump=true;return KeyedChat.submit(box,this.grow);});
  }

  click(e){
    const b=e.target.closest('button');if(!b||!this.log.contains(b))return;
    const host=b.closest('[data-item]');const key=host?.dataset.item;
    const it=key&&S.state(this.scope).intents.get(key.split(':')[1]);
    const overlay=!it&&host?.dataset.clientKey?S.state(this.scope).intents.get(host.dataset.clientKey):null;
    const target=it||overlay;if(!target)return;
    if(b.dataset.keyedAction!==undefined)target.status?.actions?.[Number(b.dataset.keyedAction)]?.run(b);
    else if(b.dataset.confirm==='yes')target.confirm?.yes();
    else if(b.dataset.confirm==='no')target.confirm?.no();
  }

  nearBottom(){const l=this.log;return l.scrollHeight-l.scrollTop-l.clientHeight<100;}
  toBottom(){const l=this.log;l.style.scrollBehavior='auto';l.scrollTop=l.scrollHeight;l.style.scrollBehavior='';}
  /* The first message at least partly in view, and how far it sits from the top. Day
     dividers and indicators move when older pages arrive, so they are never the anchor. */
  anchor(){
    if(this.nearBottom())return {bottom:true};
    const top=this.log.getBoundingClientRect().top;
    for(const [key,{el}] of this.els){
      if(key.startsWith('d:')||key==='typing'||key==='welcome')continue;
      const r=el.getBoundingClientRect();
      if(r.bottom>top)return {key,offset:r.top-top};
    }
    return {bottom:true};
  }
  restore(a){
    if(!a||a.bottom){this.toBottom();return;}
    const rec=this.els.get(a.key);
    if(!rec){this.toBottom();return;}
    this.log.scrollTop+=rec.el.getBoundingClientRect().top-this.log.getBoundingClientRect().top-a.offset;
  }
  showNew(){
    if(this.newButton)return;
    this.newButton=build('<button type="button" class="chat-new-messages quiet small">New messages ↓</button>');
    this.newButton.onclick=()=>{this.toBottom();this.hideNew();};
    this.log.parentElement.insertBefore(this.newButton,this.log.nextSibling);
  }
  hideNew(){this.newButton?.remove();this.newButton=null;}

  render(first=false){
    if(!this.unsubscribe||!this.log.isConnected)return;
    const s=S.state(this.scope);
    if(this.visible()&&s.unseen){s.unseen=false;S.changed(this.scope);}
    const before=first?(this.saved||{bottom:true}):this.jump?{bottom:true}:this.anchor();
    this.jump=false;
    const lastBefore=[...this.els.keys()].filter(k=>k!=='typing').at(-1);
    const head=this.headHtml(s);
    if(this.headMarkup!==head){this.head.innerHTML=head;this.headMarkup=head;}
    const list=items(s,{limit:this.limit});
    const keep=new Set();
    let prev=this.head;
    for(const item of list){
      keep.add(item.key);
      const markup=html(item,this.ids);
      let rec=this.els.get(item.key);
      if(!rec){
        const el=build(markup);el.dataset.item=item.key;
        rec={el,markup};this.els.set(item.key,rec);
      }else if(rec.markup!==markup){
        const fresh=build(markup);fresh.dataset.item=item.key;
        if(rec.el.tagName===fresh.tagName)morph(rec.el,fresh);else{rec.el.replaceWith(fresh);rec.el=fresh;}
        rec.markup=markup;
      }
      if(prev.nextSibling!==rec.el)prev.after(rec.el);
      prev=rec.el;
    }
    for(const [key,rec] of this.els)if(!keep.has(key)){rec.el.remove();this.els.delete(key);}
    // Order of the map follows the log, for anchor().
    this.els=new Map(list.map(i=>[i.key,this.els.get(i.key)]));
    if(before?.bottom){this.toBottom();this.follow=true;}
    else{
      this.restore(before);this.follow=false;
      if(!first&&[...this.els.keys()].filter(k=>k!=='typing').at(-1)!==lastBefore)this.showNew();
    }
    if(this.send)this.send.disabled=!s.canSend;
    if(this.status&&this.hintSeq!==(s.hintSeq||0)){this.status.textContent=s.hint;this.hintSeq=s.hintSeq||0;}
    this.after?.(s);
  }
  headHtml(s){
    if(this.kind!=='page')return s.history==='loading'&&!s.rows.length?'<p class="dim small chat-loading" role="status">Reading the conversation…</p>':
      s.history==='error'?'<p class="bad small chat-older">The conversation could not be read. It is kept; try again later.</p>':'';
    const top='<div class="chat-top-sentinel"></div>';
    if(s.history==='loading'&&!s.rows.length)return top+'<p class="dim small chat-loading" role="status">Reading the conversation…</p>';
    if(s.history==='error'&&!s.rows.length)return top+`<p class="bad">${esc(s.historyError||'The conversation could not be read.')}</p>`;
    if(s.older==='loading')return top+'<p class="dim small chat-older" role="status">Reading earlier…</p>';
    if(s.older==='error')return top+'<p class="dim small chat-older"><span class="bad">Earlier messages could not be read.</span></p>';
    if(s.start&&s.rows.length)return top+'<p class="dim small chat-older">The beginning of the conversation.</p>';
    return top;
  }
  /* The page's history paging: a marker at the head of the log (as before). */
  watchTop(onOlder){
    if(typeof IntersectionObserver!=='function')return;
    this.observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))onOlder();},
      {root:this.log,rootMargin:'200px 0px 0px 0px'});
    this.observer.observe(this.head);
  }
}

window.ChatView={View,items};
})();
