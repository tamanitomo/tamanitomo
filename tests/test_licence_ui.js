// The weight downloader must show a model's own terms before fetching it.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../kit/app/static/studios.js'),'utf8');
const slice=source.slice(source.indexOf('const licenceNotice ='),source.indexOf('\n  };',source.indexOf('const licenceNotice ='))+5);
const sandbox={esc:s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))};
vm.createContext(sandbox);
vm.runInContext(slice+'\n;globalThis.__notice=licenceNotice;',sandbox);
const notice=sandbox.__notice;

// Nothing to say when Civitai returned no permissions block.
assert.equal(notice(null),'');

// A permissive model states each permission and is not flagged.
const open=notice({allowCommercialUse:['Image','RentCivit'],allowDerivatives:true,
                   allowNoCredit:true,allowDifferentLicense:true},'https://civitai.com/models/1');
assert.ok(open.includes('Commercial use'));
assert.ok(open.includes('Image, RentCivit'));
assert.ok(!open.includes('is-restricted'),'a fully permissive model must not be flagged');
assert.ok(open.includes('rel="noopener noreferrer"'),'the model-card link must be safe');

// A restrictive model is flagged, and each refusal is marked.
const closed=notice({allowCommercialUse:[],allowDerivatives:false,
                     allowNoCredit:false,allowDifferentLicense:false},'https://civitai.com/models/2');
assert.ok(closed.includes('is-restricted'),'a restricted model must be flagged');
assert.ok(closed.includes('Not allowed'));
assert.ok(closed.includes('None'));

// Missing flags read as unknown rather than as permission.
const unknown=notice({},'');
assert.ok(unknown.includes('Not stated'));
assert.ok(!unknown.includes('Allowed</dd>'),'absent flags must never read as Allowed');

// The page URL is escaped, not interpolated raw.
const nasty=notice({allowDerivatives:true},'https://civitai.com/models/3?a="><script>x()</script>');
assert.ok(!nasty.includes('<script>'),'the model-card URL must be escaped');

console.log('Model licence notice passed');
