// Exercise in-app update UI components and reconnection helper.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const root=path.join(__dirname,'../kit/app/static');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');

const index=read('index.html'),workspace=read('workspace.js');
let reloaded=false,appendedElement=null;

const loc = {origin:'http://localhost',reload:()=>{reloaded=true;}};
const sandbox={
  URL,console,
  setTimeout:(fn,delay)=>fn(),
  setInterval:(fn,delay)=>{fn();return 123;},
  clearInterval:id=>{},
  location:loc,
  window:{location:loc},
  document:{
    getElementById:id=>null,
    body:{
      appendChild:el=>{appendedElement=el;return el;}
    },
    createElement:tag=>{
      return {tagName:tag,style:{},innerHTML:'',id:''};
    }
  },
  esc:s=>String(s),
  scoped:p=>p,
  fetch:async(url)=>{
    return {ok:true};
  }
};

vm.createContext(sandbox);
vm.runInContext("const INSTALLATION='existing',PROFILE='sam';",sandbox);
vm.runInContext(workspace.slice(workspace.indexOf('window.waitForRestart'),workspace.indexOf('async function boot')),sandbox);

(async()=>{
  assert.equal(typeof sandbox.window.waitForRestart,'function','waitForRestart must be exposed on window');
  sandbox.window.waitForRestart('2.3.0');
  assert.ok(appendedElement,'waitForRestart must attach overlay backdrop');
  assert.equal(appendedElement.id,'update-reconnect-backdrop');
  assert.match(appendedElement.innerHTML,/Restarting Workspace/);
  assert.match(appendedElement.innerHTML,/v2\.3\.0/);
  await new Promise(resolve => setTimeout(resolve, 50));
  assert.equal(reloaded,true,'successful ping must reload workspace');
  console.log('In-app update UI reconnection tests passed.');
})();
