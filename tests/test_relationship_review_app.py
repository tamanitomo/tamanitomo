"""Restriction inspection is read-only; review is explicit, scoped and revision checked."""

import datetime as dt
import json

import companion_feelings as feelings
import companion_intimacy as intimacy

from tests.support import WorkspaceFixture
from tests.test_chat_dock import run_browser_contract


class RelationshipReviewApiTests(WorkspaceFixture):
    def corrected_restriction(self):
        now = dt.datetime.now(dt.timezone.utc)
        rows = []
        for index in range(2):
            rows.append(
                feelings.record(
                    self.c,
                    {
                        "kind": "rupture",
                        "topic": "boundary_violation",
                        "text": f"Synthetic boundary incident {index}",
                        "evidence": f"Synthetic source quotation {index}",
                    },
                    now - dt.timedelta(days=2 - index),
                )["experience"]
            )
        intimacy.compute(self.c, now - dt.timedelta(minutes=10), record=True)
        for row in rows:
            feelings.record(
                self.c,
                {
                    "id": "correction-" + row["id"],
                    "kind": "correction",
                    "topic": row["topic"],
                    "related": row["id"],
                    "text": "This source was recorded incorrectly",
                    "evidence": "The synthetic transcript supports this correction",
                },
                now - dt.timedelta(minutes=5),
            )
        return rows

    def test_opening_report_does_not_write_or_retire_and_other_profiles_stay_separate(
        self,
    ):
        self.corrected_restriction()
        before = {
            p.relative_to(self.c.home): p.read_bytes()
            for p in self.c.home.rglob("*")
            if p.is_file()
        }
        response = self.get("/api/relationship/review")
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertTrue(report["restriction"]["eligible"])
        self.assertTrue(report["restriction"]["effective"])
        self.assertEqual(
            {row["status"] for row in report["restriction"]["incidents"]}, {"corrected"}
        )
        self.assertFalse(report["stance"]["assessed"])
        after = {
            p.relative_to(self.c.home): p.read_bytes()
            for p in self.c.home.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)
        other = self.get("/api/relationship/review", profile="rowan").json()
        self.assertFalse(other["restriction"]["present"])
        self.assertEqual(other["incidents"], [])

    def test_explicit_review_preserves_sources_identity_and_configuration(self):
        self.corrected_restriction()
        protected = [
            self.c.home / ".permanent-friend.json",
            self.c.life / "relationship-feelings.jsonl",
            self.c.soul,
            self.c.home / "companion.json",
        ]
        before = {path: path.read_bytes() for path in protected}
        report = self.get("/api/relationship/review").json()
        response = self.post(
            "/api/relationship/review",
            {
                "revision": report["revision"],
                "reason": "The supporting sources were explicitly corrected.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertTrue(saved["written"])
        self.assertEqual(saved["report"]["restriction"]["status"], "retired")
        self.assertFalse(saved["report"]["restriction"]["effective"])
        self.assertFalse(saved["report"]["restriction"]["eligible"])
        self.assertEqual(before, {path: path.read_bytes() for path in protected})
        self.assertEqual(
            saved["review"]["reason"],
            "The supporting sources were explicitly corrected.",
        )

    def test_stale_and_cross_profile_reviews_cannot_apply(self):
        self.corrected_restriction()
        report = self.get("/api/relationship/review").json()
        cross = self.post(
            "/api/relationship/review",
            {"revision": report["revision"], "reason": "Wrong profile"},
            profile="rowan",
        )
        self.assertEqual(cross.status_code, 409, cross.text)
        feelings.record(
            self.c,
            {
                "kind": "connection",
                "topic": "shared_film",
                "text": "A new synthetic experience",
                "evidence": "A new synthetic quote",
            },
        )
        stale = self.post(
            "/api/relationship/review",
            {"revision": report["revision"], "reason": "Source history changed"},
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.get("/api/relationship/review").json()["reviews"], [])

    def test_missing_provenance_and_bad_json_do_not_offer_a_review(self):
        (self.c.home / ".permanent-friend.json").write_text(
            json.dumps({"permanent_friend": True, "violations": 2})
        )
        report = self.get("/api/relationship/review").json()
        self.assertFalse(report["restriction"]["eligible"])
        self.assertEqual(report["restriction"]["provenance"], "legacy")
        refused = self.post(
            "/api/relationship/review",
            {"revision": report["revision"], "reason": "No verifiable sources"},
        )
        self.assertEqual(refused.status_code, 400, refused.text)
        for body in (
            {"revision": report["revision"], "reason": True},
            {"revision": {}, "reason": "Test"},
            {"revision": report["revision"], "reason": " "},
        ):
            self.assertEqual(
                self.post("/api/relationship/review", body).status_code, 400
            )


UI_SETUP = r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
global.workspaceHandlers={};
global.esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
vm.runInThisContext(fs.readFileSync('kit/app/static/us.js','utf8'));
const report={revision:'v1',configuration:{boundary:'next-door',romantic_progression:true,explicit:false,adult_images:false,nsfw_revoked:false},derived:{stage_name:'Friends',active_violation_count:0,blockers:[]},restriction:{present:true,effective:true,status:'active',provenance:'identified',eligible:true,reason:'Corrected sources',incidents:[{id:'source',status:'corrected',topic:'boundary_violation',text:'<script>source</script>',evidence:'Old quote',corrections:[{id:'correction',text:'Correction kept',evidence:'Quoted correction',at:'2026-10-12'}],repairs:[]}]},incidents:[],reviews:[],warnings:[],stance:{assessed:false,note:'Authored stance is not assessed.'}};
"""


def test_diagnostic_ui_explains_sources_without_promising_intimacy_or_unverified_review():
    run_browser_contract(UI_SETUP + r"""
let html=boundaryReviewHtml(report);
assert.ok(html.includes('Configured boundaries'));
assert.ok(html.includes('Corrected')&&html.includes('Quoted correction'));
assert.ok(!html.includes('<script>'));
assert.ok(html.includes('name="reason"')&&html.includes('Review corrected restriction'));
assert.ok(html.includes('Authored stance is not assessed.'));
assert.ok(html.includes('data-boundary-identity'));
assert.ok(html.includes('does not assess the companion’s present wishes'));
report.restriction.eligible=false;report.restriction.provenance='legacy';
html=boundaryReviewHtml(report);
assert.ok(!html.includes('<form'));
assert.ok(html.includes('source information is incomplete'));
report.restriction={present:false,status:'absent',eligible:false,provenance:'missing',incidents:[]};
html=boundaryReviewHtml(report);
assert.ok(html.includes('No saved restriction'));
assert.ok(html.includes('Authored stance is not assessed.'));
delete report.stance;
assert.ok(boundaryReviewHtml(report).includes('Authored identity, standing instructions, memories and model rules'));
assert.ok(!usStanding({permanent_friend:true},'Nova').includes('This does not reopen'));
""")


def test_boundary_review_drops_cross_profile_read_and_never_writes_on_open():
    run_browser_contract(UI_SETUP + r"""
(async()=>{
  global.INSTALLATION='one';global.PROFILE='nova';
  let resolveRead,calls=[];
  global.api=(path,opts)=>{calls.push({path,opts});return new Promise(resolve=>resolveRead=resolve);};
  let rendered=0;
  const host={isConnected:true,set innerHTML(value){rendered++;},querySelector(){throw Error('stale profile rendered');}};
  const pending=mountBoundaryReview(host);
  PROFILE='rowan';resolveRead(report);await pending;
  assert.equal(rendered,0);assert.equal(calls.length,1);assert.equal(calls[0].opts,undefined);
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_boundary_review_keeps_reason_on_conflict_and_requires_new_revision():
    run_browser_contract(UI_SETUP + r"""
(async()=>{
  global.INSTALLATION='one';global.PROFILE='nova';global.clearEditorDirty=()=>{};
  global.confirmEditorLeave=async()=>true;
  let calls=[],posts=0;
  global.api=async(path,opts)=>{
    calls.push({path,opts});
    if(!opts)return report;
    posts++;let error=new Error('Sources changed');error.status=409;throw error;
  };
  const errorBox={textContent:''},status={textContent:''},button={disabled:false,dataset:{}};
  const form={isConnected:true,elements:{reason:{value:'Keep this exact explanation'}},reportValidity:()=>true,querySelector:s=>s==='[type=submit]'?button:errorBox};
  const controls={};
  const host={isConnected:true,innerHTML:'',querySelector:s=>s==='form'?form:s==='[data-boundary-status]'?status:(controls[s]??={})};
  await mountBoundaryReview(host);
  assert.equal(posts,0);
  await form.onsubmit({preventDefault(){}});
  assert.equal(posts,1);
  assert.deepEqual(JSON.parse(calls[1].opts.body),{revision:'v1',reason:'Keep this exact explanation'});
  assert.equal(form.elements.reason.value,'Keep this exact explanation');
  assert.ok(button.disabled);assert.ok(errorBox.textContent.includes('refresh the report'));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_boundary_review_drops_late_write_result_after_profile_switch():
    run_browser_contract(UI_SETUP + r"""
(async()=>{
  global.INSTALLATION='one';global.PROFILE='nova';
  global.clearEditorDirty=()=>{throw Error('Old profile cleared current draft');};
  let finishWrite,calls=[];
  global.api=async(path,opts)=>{
    calls.push({path,opts});
    if(!opts)return report;
    return new Promise(resolve=>finishWrite=resolve);
  };
  const button={disabled:false,dataset:{}};
  const form={isConnected:true,elements:{reason:{value:'Explicit synthetic review'}},reportValidity:()=>true,querySelector:()=>button};
  let rendered=0;const controls={};
  const host={isConnected:true,set innerHTML(value){rendered++;},querySelector:s=>s==='form'?form:(controls[s]??={})};
  await mountBoundaryReview(host);
  const pending=form.onsubmit({preventDefault(){}});
  PROFILE='rowan';finishWrite({written:true,report});await pending;
  assert.equal(rendered,1);assert.equal(calls.length,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_boundary_review_success_refreshes_only_hero_preserving_other_drafts():
    run_browser_contract(UI_SETUP + r"""
(async()=>{
  global.INSTALLATION='one';global.PROFILE='nova';global.current='relationship';
  let cleared=0;global.clearEditorDirty=()=>cleared++;global.chatName=()=> 'Nova';
  const hero={outerHTML:''},page={querySelector:s=>s==='.us-hero'?hero:null};
  global.$=id=>id==='relationship'?page:null;
  global.relationshipHero=()=>'<section>Updated relationship</section>';
  let calls=[];
  global.api=async(path,opts)=>{
    calls.push({path,opts});
    if(path==='/relationship')return {bars:{feelings:{}}};
    if(!opts)return report;
    return {written:true,report:{...report,restriction:{...report.restriction,eligible:false,status:'retired'}}};
  };
  const status={textContent:''},button={disabled:false,dataset:{}};
  const form={isConnected:true,elements:{reason:{value:'Explicit synthetic review'}},reportValidity:()=>true,querySelector:()=>button};
  let rendered=0;const controls={};
  const host={isConnected:true,set innerHTML(value){rendered++;},querySelector:s=>s==='form'?(rendered===1?form:null):s==='[data-boundary-status]'?status:(controls[s]??={})};
  await mountBoundaryReview(host);await form.onsubmit({preventDefault(){}});
  assert.equal(cleared,1);assert.equal(rendered,2);
  assert.equal(hero.outerHTML,'<section>Updated relationship</section>');
  assert.ok(status.textContent.includes('updated recorded state'));
  assert.equal(calls.filter(row=>row.opts?.method==='POST').length,1);
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
