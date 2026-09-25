/* Execute the submitted Vault controller and its real bundled CodeMirror state classes.
   A minimal DOM bypasses presentation; this is NOT a browser/server journey. */
const fs=require('fs'), vm=require('vm'), path=require('path');
const root=path.resolve(process.argv[2]||process.cwd());
function make(){
 const storage=()=>{const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}};
 const timers=new Map();let i=0;
 const ctx={console,setTimeout:fn=>{timers.set(++i,fn);return i},clearTimeout:id=>timers.delete(id),
  navigator:{userAgent:'',platform:'',vendor:''}, document:{documentElement:{style:{}},addEventListener(){}},window:{addEventListener(){}},
  INSTALLATION:'fixture',PROFILE:'nova',current:'chat',localStorage:storage(),sessionStorage:storage(),vaultExpanded:new Set(),vaultTreeData:new Map(),
  $:()=>null,renderVaultTree:()=>{},listVault:async()=>{},openNote:null,notice:()=>{},esc:s=>s,api:async()=>{throw Error('api not installed')},
  askToDiscard:async()=>true,requestAnimationFrame:fn=>fn()};
 vm.createContext(ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'kit/app/static/vault-editor.bundle.js'),'utf8'),ctx);
 let script=fs.readFileSync(path.join(root,'kit/app/static/vault-editor.js'),'utf8');
 const marker='window.VaultEditor=Object.freeze(';
 if(!script.includes(marker))throw Error('test seam marker missing');
 script=script.replace(marker,'window.__Review={model,load,adopt,edited,keep,dirty,keepMineAsCopy,save,drafts,open,close,switchTo};\n'+marker);
 vm.runInContext(script,ctx);
 const r=ctx.window.__Review;
 return {ctx,r,timers,edit(m,s){m.state=m.state.update({changes:{from:0,to:m.state.doc.length,insert:s}}).state;r.edited(m);r.keep(m)},text:m=>m.state.sliceDoc()};
}
const data=(text,revision,p='notes/a.md')=>({path:p,text,revision,editable:true,protected:false,deletable:true});
(async()=>{
 const results={};
 {
  const f=make(),m=f.r.model('notes/a.md');
  f.r.drafts.put(m.path,'recovered owner draft','rev0');
  f.ctx.api=async()=>{throw Error('offline')};await f.r.load(m);
  f.edit(m,'recovered owner draft plus newer typing');
  results.offline_edit={buffer:f.text(m),dirty:f.r.dirty(m),status:m.status,kept:f.r.drafts.get(m.path)};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.drafts.put(m.path,'recovered owner draft','rev0');
  f.ctx.api=async()=>{throw Error('offline')};await f.r.load(m);
  f.ctx.api=async()=>data('external editor text','rev1');await f.r.load(m);
  results.offline_external_read={buffer:f.text(m),status:m.status,conflict:m.conflict,kept:f.r.drafts.get(m.path)};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('old disk','rev0'));
  f.edit(m,'copy request text');f.r.adopt(m,data('external disk','rev1'));
  let release,request;f.ctx.api=async(p,o)=>{request=JSON.parse(o.body);return new Promise(resolve=>release=()=>resolve(data(request.text,'copy-rev',request.path)))};
  f.r.switchTo(m.path);const task=f.r.keepMineAsCopy(m);
  f.edit(m,'copy request text PLUS NEWER TYPING');release();await task;
  results.delayed_copy={buffer:f.text(m),status:m.status,kept:f.r.drafts.get(m.path),savedCopy:request.text,active:f.ctx.window.VaultEditor.active()};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('old disk','rev0'));f.edit(m,'copy request text');f.r.adopt(m,data('external disk','rev1'));
  let release,request;f.ctx.api=async(p,o)=>{if(o){request=JSON.parse(o.body);return new Promise(resolve=>release=()=>resolve(data(request.text,'copy-rev',request.path)))}return data('other note','b-rev','notes/b.md')};
  f.r.switchTo(m.path);const task=f.r.keepMineAsCopy(m);await f.r.open('notes/b.md');release();await task;
  results.delayed_copy_navigation={active:f.ctx.window.VaultEditor.active(),expected:'notes/b.md'};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('old disk','rev0'));f.edit(m,'discarded edit');
  f.ctx.api=async()=>{throw Error('offline')};await f.r.save(m);const retry=m.timer;
  await f.r.close(m.path);
  const writes=[];f.ctx.api=async(p,o)=>{if(o){const b=JSON.parse(o.body);writes.push(b.text);return data(b.text,'saved')}return data('old disk','rev0')};
  if(f.timers.has(retry))await f.timers.get(retry)();
  results.closed_offline_retry={writes,kept:f.r.drafts.get(m.path),active:f.ctx.window.VaultEditor.active()};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('old disk','rev0'));f.edit(m,'submitted edit');
  let reject;f.ctx.api=async()=>new Promise((_,bad)=>reject=bad);const pending=f.r.save(m);
  await f.r.close(m.path);reject(Error('lost before server'));await pending;
  const writes=[];f.ctx.api=async(p,o)=>{const b=JSON.parse(o.body);writes.push(b.text);return data(b.text,'saved')};
  if(f.timers.has(m.timer))await f.timers.get(m.timer)();
  results.closed_inflight_failure={writes,kept:f.r.drafts.get(m.path),known:f.ctx.window.VaultEditor.status(m.path)};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('original','rev0'));f.edit(m,'first submitted');
  let release;const writes=[];
  f.ctx.api=async(p,o)=>{const b=JSON.parse(o.body);writes.push(b);return new Promise(resolve=>release=()=>resolve(data(b.text,'rev1')))};
  const pending=f.r.save(m);f.edit(m,'newer queued edit');release();await pending;
  const afterAck=f.text(m);
  f.ctx.api=async(p,o)=>{const b=JSON.parse(o.body);writes.push(b);return data(b.text,'rev2')};await f.r.save(m);
  results.normal_serial_save={afterAck,buffer:f.text(m),status:m.status,bodies:writes.map(x=>x.text),bases:writes.map(x=>x.revision)};
 }
 {
  const f=make(),m=f.r.model('notes/a.md');f.r.adopt(m,data('old disk','rev0'));f.edit(m,'saved copy text');f.r.adopt(m,data('external disk','rev1'));
  f.r.switchTo(m.path);let copy;
  f.ctx.api=async(p,o)=>{if(o){const b=JSON.parse(o.body);copy=data(b.text,'copy-rev',b.path);return copy;}return copy};
  await f.r.keepMineAsCopy(m);
  results.normal_copy={original:f.text(m),status:m.status,savedCopy:copy.text,activeIsCopy:f.ctx.window.VaultEditor.active()===copy.path,kept:f.r.drafts.get(m.path)};
 }
 console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1});
