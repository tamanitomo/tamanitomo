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

/* The chip editor and the renderer must agree on where a tag ends. A weight
   like `(white dress, ivory:1.3)` contains commas and is still one tag; if the
   editor splits it into fragments, one ✕ leaves an unbalanced bracket that the
   sampler reads as literal punctuation. Mirrors companion_media.split_terms. */
{
  const studios=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/studios.js'),'utf8');
  const start=studios.indexOf('function tagsFromText(text){');
  const box={};vm.createContext(box);
  vm.runInContext(studios.slice(start,studios.indexOf('\nfunction tagFieldHTML'))+
    '\n;globalThis.__tags=tagsFromText;',box);
  // The helper runs in its own realm, so its arrays fail a strict prototype
  // check; compare the contents rather than the objects.
  const tags=text=>JSON.stringify(box.__tags(text));
  assert.equal(tags('(white dress, ivory:1.3), lowres, (two people:1.3)'),
    JSON.stringify(['(white dress, ivory:1.3)','lowres','(two people:1.3)']),'a weight is one tag');
  assert.equal(tags('a, b, c'),JSON.stringify(['a','b','c']));
  assert.equal(tags(''),'[]');
  assert.equal(tags('[soft], (a, b:1.2)'),JSON.stringify(['[soft]','(a, b:1.2)']));
  // Removing any one tag must leave brackets balanced.
  const all=box.__tags('(white dress, ivory:1.3), lowres, (two people:1.3)');
  for(let i=0;i<all.length;i++){
    const rest=all.filter((_,j)=>j!==i).join(', ');
    let depth=0;
    for(const ch of rest){if(ch==='('||ch==='[')depth++;else if(ch===')'||ch===']')depth--;}
    assert.equal(depth,0,`removing tag ${i} left unbalanced brackets: ${rest}`);
  }
  console.log('Prompt tags keep their weights intact');
}

/* Wardrobe slots are a display concern: the emoji say what part of an outfit a
   garment is, and must never reach an image prompt (prompts are built
   server-side from item.description, which the classifier does not touch). */
{
  const product=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/product.js'),'utf8');
  const box={esc:s=>String(s)};
  vm.createContext(box);
  vm.runInContext(product.slice(product.indexOf('const WARDROBE_SLOTS='),
                                product.indexOf('/* One chip:'))+
    ';globalThis.W={wardrobeSlot,slotLabel,bySlot};',box);
  const {wardrobeSlot,slotLabel,bySlot}=box.W;
  const slot=t=>slotLabel(wardrobeSlot(t));

  // Footwear has to win over "top": "low-top sneakers" is not a shirt.
  assert.equal(slot('clean classic low-top white platform canvas sneakers'),'Shoes');
  assert.equal(slot('warm cream fitted ribbed crop top revealing the midriff'),'Top');
  assert.equal(slot('warm cream soft stretch-cotton bikini panties with lace trim'),'Undies');
  assert.equal(slot('warm cream high-waisted seamless sculpting leggings'),'Bottom');
  assert.equal(slot('warm cream soft cushioned cotton ankle socks'),'Sock');
  assert.equal(slot('grey beanie'),'Hat');
  assert.equal(slot('thin gold necklace'),'Jewelry');
  assert.equal(slot('denim jacket'),'Additional');
  // A sports bra is worn as an athletic top, and the stage filter treats it as
  // one; calling it underwear here would contradict that.
  assert.equal(slot('black sports bra'),'Top');
  assert.equal(slot('something unrecognisable'),'Additional');
  // "cap sleeves" is a tee, "hooded" is a jacket: neither word is a hat on its own.
  assert.equal(slot('sage green fitted scoop-neck baby tee with cap sleeves'),'Top');
  assert.equal(slot('hooded denim jacket'),'Additional');
  assert.equal(slot('black baseball cap'),'Hat');

  // Listed head down, whatever order they arrive in.
  const order=bySlot(['white sneakers','grey beanie','blue jeans','cotton tee',
                      'gold ring','ankle socks','cotton briefs','wool scarf'])
    .map(t=>slotLabel(wardrobeSlot(t)));
  assert.deepEqual(JSON.stringify(order),
    JSON.stringify(['Hat','Jewelry','Top','Undies','Bottom','Sock','Shoes','Additional']));

  // Objects carry a category and an id worth reading, not only a description.
  assert.equal(slot({id:'closet-underwear-1',description:'soft cotton pair'}),'Undies');
  console.log('Wardrobe slots classify and order correctly');
}
