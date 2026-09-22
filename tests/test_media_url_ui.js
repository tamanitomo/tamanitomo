// A URL escaped for an HTML attribute must never be assigned to a property.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../kit/app/static/index.html'),'utf8');
const product=fs.readFileSync(path.join(__dirname,'../kit/app/static/product.js'),'utf8');

// The two builders, lifted out of the page.
const sandbox={location:{origin:'https://example.test'},URL,token:'tok3n',
  INSTALLATION:'existing',PROFILE:'sam',
  esc:s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))};
vm.createContext(sandbox);
for(const name of ['scoped','rawMediaUrl','mediaUrl'])
  vm.runInContext(html.match(new RegExp('^function '+name+'.*$','m'))[0],sandbox);

const raw=sandbox.rawMediaUrl('/api/content/file?path=a/b.png');
const escaped=sandbox.mediaUrl('/api/content/file?path=a/b.png');

// rawMediaUrl is the real thing: every parameter survives.
const params=new URL(raw,'https://example.test').searchParams;
assert.equal(params.get('profile'),'sam','profile must reach the server');
assert.equal(params.get('installation'),'existing');
assert.equal(params.get('token'),'tok3n','the access token must survive too');

// mediaUrl is for interpolation, and is NOT safe to assign to a property:
// the entities stay literal and the parameters come out renamed.
assert.ok(escaped.includes('&amp;'),'mediaUrl is expected to escape');
const broken=new URL(escaped,'https://example.test').searchParams;
assert.equal(broken.get('profile'),null);
assert.ok([...broken.keys()].includes('amp;profile'),
  'this is the failure being guarded against: profile arrives as amp;profile');

// So no source file may assign mediaUrl() straight onto .src or .href. That
// silently served every companion the default one's pictures.
const offenders=[];
for(const file of fs.readdirSync(path.join(__dirname,'../kit/app/static')).filter(f=>f.endsWith('.js'))){
  const text=fs.readFileSync(path.join(__dirname,'../kit/app/static',file),'utf8');
  text.split('\n').forEach((line,i)=>{
    if(/\.(src|href)\s*=\s*mediaUrl\(/.test(line)||/setAttribute\(\s*['"](?:src|href)['"]\s*,\s*mediaUrl\(/.test(line))
      offenders.push(`${file}:${i+1}`);
  });
}
assert.deepEqual(offenders,[],'assign rawMediaUrl to a property; mediaUrl is for HTML');
console.log('Media URLs keep their profile and token, and none are assigned escaped');
