// The Journal archive's route and date helpers, run from the shipped file without a browser.
// Run under a daylight-saving TZ (the Python wrapper sets America/New_York) so local-midnight
// arithmetic would show up here as a skipped or repeated day.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../kit/app/static/journal.js'),'utf8');
const listeners=[];
const sandbox={workspaceHandlers:{},window:{addEventListener:(name,fn)=>listeners.push(name)}};
vm.createContext(sandbox);
vm.runInContext(source+'\n;this.api={journalValidDay,journalRouteParse,journalRouteHash,journalAddDays,journalNeighbours};',sandbox);
const j=sandbox.api;
assert.equal(typeof sandbox.workspaceHandlers.journals,'function');
assert.deepEqual(listeners,['popstate']);

// routes: existing bare links still parse; a shared link carries date and view
assert.deepEqual({...j.journalRouteParse('#journals')},{day:null,view:null});
assert.deepEqual({...j.journalRouteParse('#journals/2026-09-20/reflection')},{day:'2026-09-20',view:'reflection'});
assert.deepEqual({...j.journalRouteParse('#journals/2026-09-20')},{day:'2026-09-20',view:null});
assert.deepEqual({...j.journalRouteParse('#journals/2026-02-30/day')},{day:null,view:'day'});
assert.deepEqual({...j.journalRouteParse('#journals/../../x/<script>')},{day:null,view:null});
assert.equal(j.journalRouteParse('#timeline'),null);
assert.equal(j.journalRouteParse('#photos/2026-09-20/day'),null);
assert.equal(j.journalRouteHash('2026-09-20','day'),'#journals/2026-09-20/day');

// dates stay dates
for(const bad of ['2026-9-1','2026-13-01','2025-02-29','','2026-09-20T00:00',null,undefined,20260920])
  assert.equal(j.journalValidDay(bad),false,String(bad));
assert.equal(j.journalValidDay('2024-02-29'),true);

// stepping days across both 2026 US transitions and a year end
assert.equal(j.journalAddDays('2026-03-07',1),'2026-03-08');
assert.equal(j.journalAddDays('2026-03-08',1),'2026-03-09');
assert.equal(j.journalAddDays('2026-11-01',1),'2026-11-02');
assert.equal(j.journalAddDays('2026-11-02',-1),'2026-11-01');
assert.equal(j.journalAddDays('2026-12-31',1),'2027-01-01');
let d='2026-01-01';for(let i=0;i<365;i++)d=j.journalAddDays(d,1);
assert.equal(d,'2027-01-01');

// neighbours are the nearest dates on record, whatever order they arrive in
assert.deepEqual({...j.journalNeighbours(['2026-09-22','2026-09-18','2026-09-20','2026-09-20'],'2026-09-20')},
  {older:'2026-09-18',newer:'2026-09-22'});
assert.deepEqual({...j.journalNeighbours(['2026-09-18'],'2026-09-19')},{older:'2026-09-18',newer:null});
assert.deepEqual({...j.journalNeighbours([],'2026-09-19')},{older:null,newer:null});
console.log('Journal archive route and date helpers passed ('+Intl.DateTimeFormat().resolvedOptions().timeZone+')');
