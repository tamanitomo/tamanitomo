/* Execute the submitted Journal module with a minimal DOM and deferred API.
   Boundary: Node VM/state + emitted HTML, not a browser/HTTP end-to-end test. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements=new Map();
function element(id){
  if(!elements.has(id))elements.set(id,{id,innerHTML:'',textContent:'',value:'',hidden:true,disabled:false,
    setAttribute(){},addEventListener(){},querySelectorAll(){return [];},querySelector(){return null;},
    focus(){},scrollIntoView(){}});
  return elements.get(id);
}
let releaseIndex;const indexPromise=new Promise(r=>releaseIndex=r);
let heldList;const listPromise=new Promise(r=>heldList=r);
const deferred=process.env.DEFER_LIST==='1';
const listeners={};let ctx;const requests=[];
const list={timezone:'UTC',entries:[],warnings:[]};
const index={today:'2026-09-25',days:{'2026-09-18':{scenes:true},'2026-09-20':{scenes:true}}};
const sandbox={console,setTimeout,clearTimeout,URLSearchParams,Intl,Date,Map,Set,String,Number,CSS:{escape:x=>x},
  INSTALLATION:'existing',PROFILE:'nova',current:'journals',selectedJournal:null,profileTimezone:'UTC',
  location:{pathname:'/',search:'',hash:'#journals/2026-09-18/day'},
  history:{pushState:(_,__,url)=>sandbox.location.hash=url.slice(url.indexOf('#')),replaceState:(_,__,url)=>sandbox.location.hash=url.slice(url.indexOf('#'))},
  workspaceHandlers:{},TAB_ALIASES:{},TABS:[['journals'],['photos']],showTab(){},
  document:{removeEventListener(){},addEventListener(){}},window:{addEventListener:(name,fn)=>listeners[name]=fn},
  $:element,esc:x=>String(x??''),icon:()=>'',companionToday:()=>index.today,stamp:x=>x,
  sentenceCase:x=>x,excerpt:x=>x,spanLabel:x=>String(x),jump:()=>'',wireRoutes(){},
  empty:(_,title,text)=>`${title}: ${text}`,richText:x=>x,mediaPrivacy:()=>'',mediaUrl:x=>x,openPhotoViewer(){},
  api:async path=>{
    requests.push(path);
    if(path==='/journals?limit=1000')return deferred?listPromise:list;
    if(path==='/journal/archive')return deferred?index:indexPromise;
    if(path.startsWith('/journal/archive/'))return {day:path.split('/').pop(),today:index.today,timezone:'UTC',agent:'Nova',
      scenes:[],unplaced_photos:[],sources:{scenes:'none',photos:'available'},plan:{state:'none',items:[]},reflection:{state:'none',entries:[]},together:{state:'none',moments:[]}};
    throw new Error('Unexpected API '+path);
  }
};
ctx=vm.createContext(sandbox);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const opening=vm.runInContext('workspaceHandlers.journals()',ctx);
 await flush();
 const navigate=process.env.NAVIGATE!=='0';
 if(navigate){
   sandbox.location.hash='#journals/2026-09-20/day';listeners.popstate();await flush();
 }
 const before=vm.runInContext('({...journalState})',ctx);
 if(deferred)heldList(list);else releaseIndex(index);
 await opening;await flush();
 const result={boundary:'actual journal.js in Node VM; minimal DOM and deferred API',delayed:deferred?'journal list':'archive index',
    navigated:navigate,before,after:vm.runInContext('({...journalState})',ctx),hash:sandbox.location.hash,requests,
    html:element('journal-page').innerHTML};
 console.log(JSON.stringify(result,null,2));
 if(process.env.ASSERT_LATEST==='1')assert.equal(result.after.day,navigate?'2026-09-20':'2026-09-18', 'late initial load must not replace the selected date');
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
