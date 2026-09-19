// Reconnection waits for the new version AND a new server process.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const workspace=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/workspace.js'),'utf8');
const settings=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/settings.js'),'utf8');
const product=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/product.js'),'utf8');
assert.match(settings,/What’s new in v\$\{esc\(d\.latest_version\)\}/,'updates panel shows patch notes before installation');
assert.ok(settings.indexOf('update-release-notes-body') < settings.indexOf('btn-inapp-update'),'patch notes appear before the Update button');
assert.match(settings,/esc\(d\.release_notes/,'release notes are escaped before entering HTML');
assert.doesNotMatch(product,/id="banner-apply-update"/,'home banner must open review instead of updating immediately');
assert.match(product,/See what’s new &amp; update/);
let reloaded=false,element=null,tick,status={version:'2.2.1',instance_id:'old'};
const loc={reload:()=>{reloaded=true;}};
const sandbox={console,
  setTimeout:fn=>fn(),setInterval:fn=>{tick=fn;return 123;},clearInterval:()=>{},
  window:{location:loc},document:{getElementById:()=>null,
    body:{appendChild:el=>{element=el;}},createElement:()=>({style:{}})},
  esc:String,scoped:p=>p,fetch:async()=>({ok:true,json:async()=>status})};
vm.createContext(sandbox);
vm.runInContext(workspace.slice(workspace.indexOf('window.waitForRestart'),workspace.indexOf('async function boot')),sandbox);
(async()=>{
  sandbox.window.waitForRestart('2.3.0','old');
  assert.equal(element.id,'update-reconnect-backdrop');
  assert.match(element.innerHTML,/v2\.3\.0/);
  await tick();assert.equal(reloaded,false,'old version cannot finish reconnect');
  status={version:'2.3.0',instance_id:'old'};
  await tick();assert.equal(reloaded,false,'old process with newly written VERSION cannot finish reconnect');
  status={version:'2.3.0',instance_id:'new'};
  await tick();assert.equal(reloaded,true,'updated process completes reconnect');
  console.log('In-app update UI reconnection tests passed.');
})();
