// The three outcomes of an import, checked without a browser: their graph
// rebuilt into a kit lane, their graph as detected, and their original file.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/studios.js'),'utf8');
const region=source.slice(source.indexOf(' let importSource=null;'),
                          source.indexOf(' async function runImport('));
assert.ok(region.includes('showImportResult'),'could not slice the import reporter out');

function run(result,{withFile=true}={}){
  const report={innerHTML:'',querySelectorAll:()=>[]};
  const status={textContent:'',innerHTML:''};
  const made=[],elements={};             // presets adopted, and live buttons
  const notices=[];
  const sandbox={
    esc:s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),
    // An element exists only if the markup actually rendered that id, which is
    // how this checks which buttons were offered.
    // Elements are cached, so a handler wired inside the reporter is still
    // there to be fired afterwards.
    $:id=>id==='workflow-import-report'?report
        :id==='workflow-import-status'?status
        :report.innerHTML.includes(`id="${id}"`)
          ?(elements[id]=elements[id]||{onclick:null,textContent:'',innerHTML:''})
        :id==='workflow-import-file'?{value:''}:null,
    readPreset(){},presetSuffix:()=>'abc',drawPreset(){},setWorkflowMode(){},
    notice:m=>notices.push(m),
    settings:{presets:{push:p=>made.push(p)}},
    presetIndex:0,token:'',scoped:p=>p,post:async()=>({}),api:async()=>({}),fetch:async()=>({}),
    URL:{createObjectURL:()=>'blob:',revokeObjectURL(){}},document:{createElement:()=>({click(){}})},
    setTimeout(){},
  };
  vm.createContext(sandbox);
  vm.runInContext(region,sandbox);
  if(withFile)vm.runInContext('importSource={name:"x.png"};',sandbox);
  vm.runInContext('showImportResult('+JSON.stringify(result)+')',sandbox);
  return {html:report.innerHTML,made,notices,sandbox,elements};
}

const base={found:{source:'ComfyUI graph',nodes:5},notes:[],preset:{incomplete:true,workflow:{}}};

// 1. A graph we could rebuild offers all three, and leads with the rebuilt one.
let r=run({...base,adapted:{incomplete:false,workflow:{}},adapted_error:''});
assert.ok(r.html.includes('id="keep-adapted"'),'rebuilt lane not offered');
assert.ok(r.html.includes('id="keep-imported"'),'as-detected not offered');
assert.ok(r.html.includes('id="download-original"'),'original download not offered');
assert.ok(r.html.includes('class="act" id="keep-adapted"'),'rebuilt lane should be the primary action');
assert.ok(r.html.includes('Add the rebuilt lane'));

// 2. A rebuilt lane still missing its weights is offered as a draft, not hidden.
r=run({...base,adapted:{incomplete:true,workflow:{}},adapted_error:''});
assert.ok(r.html.includes('Save rebuilt lane as a draft'));

// 3. When it cannot be rebuilt, say why, and as-detected becomes the main action.
r=run({...base,adapted:null,adapted_error:'This graph does not say which architecture it is for.'});
assert.ok(!r.html.includes('id="keep-adapted"'),'must not offer a lane that was not built');
assert.ok(r.html.includes('Cannot rebuild this into a kit lane'));
assert.ok(r.html.includes('does not say which architecture'));
assert.ok(r.html.includes('class="act" id="keep-imported"'),'as-detected should be primary instead');

// 4. A URL import has no local file, so no original to hand back.
r=run({...base,adapted:null,adapted_error:''},{withFile:false});
assert.ok(!r.html.includes('id="download-original"'),'nothing to download from a page import');

// 5. Each button saves ITS OWN graph -- the whole point of offering both.
r=run({...base,preset:{incomplete:true,workflow:{theirs:1}},
       adapted:{incomplete:false,workflow:{ours:1}},adapted_error:''});
r.elements['keep-adapted'].onclick();
assert.equal(r.made.length,1);
// Compared as text: the object was built inside the vm realm, so its
// prototype is not the host's and a strict deep-equal would fail on that alone.
assert.equal(JSON.stringify(r.made[0].workflow),'{"ours":1}','rebuilt button must save the rebuilt graph');
assert.ok(r.made[0].id.startsWith('import-'));
assert.ok(/Rebuilt into a kit lane/.test(r.notices[0]),r.notices[0]);

r=run({...base,preset:{incomplete:true,workflow:{theirs:1}},
       adapted:{incomplete:false,workflow:{ours:1}},adapted_error:''});
r.elements['keep-imported'].onclick();
assert.equal(JSON.stringify(r.made[0].workflow),'{"theirs":1}','as-detected button must save their graph');
console.log('Import offers rebuilt lane, as-detected and the original, and explains a refusal');
