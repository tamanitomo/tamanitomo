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
/* The feed is one infinite stream, so a slow reply to an abandoned page must
   never repaint a page the reader has since moved on from. */
(async()=>{
  const workspace=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/workspace.js'),'utf8');
  const pending={},box={innerHTML:'',scrollTop:0,scrollHeight:120,
    scrollTo(){},querySelector:()=>null,insertAdjacentHTML(){},classList:{toggle(){}}};
  const chat={current:'chat',chatPageGeneration:1,chatSession:'',chatFeedCursor:null,
    chatFeedLoading:false,chatFeedReady:false,chatLastDay:'',chatTopWatcher:null,
    api:path=>new Promise(resolve=>(pending[path]=pending[path]||[]).push(resolve)),
    $:name=>name==='chat-log'?box:null,esc:sandbox.esc,richText:sandbox.richText,
    chatName:()=>'Nova',inlineMedia:()=>'',faceHtml:()=>'',
    chatKey:k=>k,sessionStorage:{setItem(){},getItem:()=>null},
    chatMessagesHtml:messages=>messages.map(m=>`<div>${m.content}</div>`).join(''),
    watchTopOfLog(){},jumpToNewest(){}};
  vm.createContext(chat);
  vm.runInContext(workspace.slice(workspace.indexOf('async function loadFeed('),
                                  workspace.indexOf('\nasync function loadOlder('))+
                  '\n;globalThis.__loadFeed=loadFeed;',chat);
  const loadFeed=chat.__loadFeed;

  // The reader opens the feed, then something re-renders the page under them.
  const abandoned=loadFeed(1);
  chat.chatPageGeneration=2;
  const current=loadFeed(2);
  // The newer request answers first, then the stale one arrives late.
  const [stale,fresh]=pending['/feed?limit=60'];
  fresh({messages:[{content:'Current page'}],next_cursor:null});
  await current;
  stale({messages:[{content:'Abandoned page'}],next_cursor:null});
  await abandoned;
  assert.ok(box.innerHTML.includes('Current page'));
  assert.ok(!box.innerHTML.includes('Abandoned page'),
    'a reply to an abandoned page must not repaint the feed');
  console.log('Out-of-order feed loads stay on the reader\u2019s current page');
})().catch(error=>{console.error(error);process.exitCode=1;});
