// Exercise the actual photo helpers without a browser or running backend.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/product.js'),'utf8');
const sandbox={};vm.createContext(sandbox);
for(const name of ['mergePhotos','photoInCollection','photoForCollection'])vm.runInContext(source.match(new RegExp('^function '+name+'.*$','m'))[0],sandbox);
const image={kind:'image',path:'creations/a.png',source:'creation',at:'2026-09-12T00:00:00Z',copies:[{source:'creation',path:'creations/a.png'},{source:'photo session',path:'image-timeline/images/cap.png'},{source:'album',path:'albums/Favorites/a.png'}]};
const rows=sandbox.mergePhotos({items:[image]},{captures:[{image:'/media/timeline/cap.png',id:'cap',activity:'Reading',at:'2026-09-12T00:00:00Z'}]});
assert.equal(rows.length,1);assert.equal(rows[0].capture,'cap');assert.equal(rows[0].title,'Reading');
for(const collection of ['all','creation','photo session','album:Favorites'])assert.equal(sandbox.photoInCollection(image,collection),true);
assert.equal(sandbox.photoInCollection(image,'album:Other'),false);
assert.equal(sandbox.photoInCollection({source:'creation',path:'old.png'},'creation'),true);
assert.equal(sandbox.photoForCollection(image,'album:Favorites').path,'albums/Favorites/a.png');
assert.equal(sandbox.photoForCollection(image,'all').path,'creations/a.png');
console.log('Photo metadata and collection filters passed');
// Date sections retain the original index used by lightbox previous/next.
sandbox.dayKey=value=>value?value.slice(0,10):'';
vm.runInContext(source.match(/^function photoDays.*$/m)[0],sandbox);
const groups=sandbox.photoDays([{at:'2026-09-12T12:00:00Z'},{at:'2026-09-11T12:00:00Z'},{at:'2026-09-12T15:00:00Z'},{at:null}]);
assert.equal(groups.length,3);
assert.equal(groups[0].items[1].index,2);
assert.equal(groups[2].day,'unknown');
// Chat now uses the shared renderer: literal HTML and unsafe links stay inert.
sandbox.esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
vm.runInContext(source.slice(source.indexOf('function richText('),source.indexOf('\nworkspaceHandlers.now=')),sandbox);
const formatted=sandbox.richText('**Hello**\n\n<script>alert(1)</script>\n\n[click](javascript:alert(1))');
assert.ok(formatted.includes('<strong>Hello</strong>'));
assert.ok(!formatted.includes('<script>'));
assert.ok(!formatted.includes('href="javascript:'));
console.log('Date groups and formatted-message safety passed');
(async()=>{
  const workspace=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/workspace.js'),'utf8');
  const pending={},box={innerHTML:'',scrollTop:0,scrollHeight:120};
  const chat={current:'chat',chatSession:'first',api:path=>new Promise(resolve=>pending[path]=resolve),$:()=>box,esc:sandbox.esc,richText:sandbox.richText,chatName:()=> 'Nova',inlineMedia:()=>''};
  vm.createContext(chat);
  vm.runInContext(workspace.slice(workspace.indexOf('let chatLoadGeneration='),workspace.indexOf('\nfunction inlineMedia')),chat);
  const first=chat.loadChat();chat.chatSession='second';const second=chat.loadChat();
  pending['/sessions/second']({messages:[{role:'assistant',timestamp:1,content:'Second conversation'}]});await second;
  pending['/sessions/first']({messages:[{role:'assistant',timestamp:1,content:'Old conversation'}]});await first;
  assert.ok(box.innerHTML.includes('Second conversation'));
  assert.ok(!box.innerHTML.includes('Old conversation'));
  console.log('Out-of-order chat history stays in its selected conversation');
})().catch(error=>{console.error(error);process.exitCode=1;});
