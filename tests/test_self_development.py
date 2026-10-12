"""End-to-end deterministic guarantees for self-authored development.

These tests use only disposable synthetic profiles.  They establish storage,
lineage, selection and integration guarantees; they do not claim that a mocked
planner proves natural frontier-model behavior.
"""

import datetime as dt
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_active as active  # noqa: E402
import companion_arcs as arcs  # noqa: E402
import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402
import companion_local_reflection as reflection  # noqa: E402
import companion_perspectives as views  # noqa: E402
import companion_preread as preread  # noqa: E402
import companion_render as render  # noqa: E402
import companion_self as slf  # noqa: E402
from tests.test_chat_dock import run_browser_contract  # noqa: E402

UTC = dt.timezone.utc
DAY = dt.datetime(2026, 10, 12, 10, tzinfo=UTC)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        profile="nova",
        hermes_root=tmp_path / "hermes",
        vault=tmp_path / "vault",
        timezone="UTC",
        soul_in_vault=False,
        context_mode="fixed",
        context_tokens=32768,
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.soul.write_text(
        render.render_template("SOUL.md.tmpl", render.mapping_for(c, "warm", "none")),
        encoding="utf-8",
    )
    c.save()
    return c


def encounter(c, suffix="film", source_type="human_words", observed_as="actual_words"):
    return views.record_encounter(
        c,
        source_type,
        f"chat:one:{suffix}",
        DAY,
        f"session:one message:{suffix}",
        "We can forgive someone without inviting them back into our life.",
        observed_as,
        operation_id=f"encounter-{suffix}",
        now=DAY,
    )["entry"]


def authored_view(c, suffix="film", subject="forgiveness"):
    source = encounter(c, suffix)
    interpretation = views.record_interpretation(
        c,
        [source["id"]],
        "That distinction made forgiveness feel less like surrender.",
        interested="The boundary between release and reconciliation.",
        unresolved_question="Can forgiveness remain private?",
        operation_id=f"interpret-{suffix}",
        now=DAY,
    )["entry"]
    perspective = views.record_perspective(
        c,
        subject,
        "Forgiveness need not require restored access.",
        ["Release and reconciliation answer different needs."],
        "provisional",
        interpretation_ids=[interpretation["id"]],
        source_ids=[source["id"]],
        operation_id=f"perspective-{suffix}",
        now=DAY,
    )["entry"]
    return source, interpretation, perspective


def empty_plan(text="I kept thinking about the conversation."):
    return {
        "reflection": text,
        "preferences": [],
        "interpretations": [],
        "perspectives": [],
        "investigations": [],
        "questions": [],
        "facts": [],
        "standing": [],
        "moments": [],
        "answers": [],
        "open_loops": [],
        "soul_append": "",
    }


UI_SETUP = r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
global.workspaceHandlers={};
global.esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
vm.runInThisContext(fs.readFileSync('kit/app/static/us.js','utf8'));
"""


def test_growth_ui_keeps_current_history_legacy_empty_and_prose_safe():
    run_browser_contract(UI_SETUP + r"""
const current={perspective_id:'view-1',subject:'Trust <script>x</script>',text:'Access & forgiveness',uncertainty:'mixed',valence:'mixed'};
const history={'view-1':[
  {recorded_at:'2026-10-01',change:'new',position:'Old <img src=x>',revision_reason:''},
  {recorded_at:'2026-10-02',change:'nuance',position:'Access & forgiveness',revision_reason:'Artifact <b>changed it</b>'}
]};
let html=usDiscoveriesHTML([current],8,'Mira','',history);
assert.ok(html.includes('2 revisions')&&html.includes('Current view · mixed'));
assert.ok(html.includes('&lt;script&gt;')&&html.includes('&lt;img src=x&gt;')&&html.includes('&lt;b&gt;changed it&lt;/b&gt;'));
assert.ok(!html.includes('<script>')&&!html.includes('<img src=x>'));
html=usDiscoveriesHTML([{...current,legacy:true}],8,'Mira','',{});
assert.ok(html.includes('source links are unknown'));
assert.ok(usDiscoveriesHTML([],8,'Mira').includes('has not recorded'));
html=usIndependentGrowthHTML(
  [{question:'Why <script>?',status:'blocked',mode:'independent',obstacle:'Outage & no result'}],
  [{title:'Two endings',next_action:'Reread tomorrow',beats:[],ended:null},{title:'Done',beats:[],ended:{outcome:'resolved'}}]
);
assert.ok(html.includes('Why &lt;script&gt;?')&&html.includes('Outage &amp; no result'));
assert.ok(html.includes('Two endings')&&!html.includes('>Done<'));
assert.ok(usIndependentGrowthHTML([],[]).includes('No independent investigation'));
""")


def test_growth_page_drops_stale_profile_load_without_touching_a_draft():
    run_browser_contract(UI_SETUP + r"""
(async()=>{
  global.INSTALLATION='one';global.PROFILE='mira';global.current='relationship';
  let draft='unsent text',renders=0;const waits={};
  global.api=path=>new Promise(resolve=>{waits[path]=resolve;});
  global.$=()=>{renders++;throw Error('stale profile rendered');};
  const pending=workspaceHandlers.relationship();
  PROFILE='rowan';
  waits['/overview']({loops:[]});
  waits['/relationship']({moments:[],bars:{}});
  waits['/ledgers']({facts:[],standing:[],relationship:[],questions:[],preferences:[],perspectives:{history:{}},investigations:[],projects:[]});
  waits['/feelings/experiences']({experiences:[]});
  waits['/facts/held']({held:[]});
  await pending;
  assert.equal(renders,0);assert.equal(draft,'unsent text');
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_encounter_lineage_deduplicates_summaries_and_survives_restart(companion):
    first, interpretation, perspective = authored_view(companion)
    repeated = views.record_encounter(
        companion,
        "human_words",
        "chat:one:film",
        DAY,
        "session:one message:film",
        "A later summary of the same words.",
        "actual_words",
        operation_id="different-summary-operation",
        now=DAY + dt.timedelta(days=1),
    )
    assert not repeated["written"]
    assert repeated["entry"]["id"] == first["id"]
    assert len(views.encounters(companion)) == 1
    assert interpretation["lineage_ids"] == [first["lineage_id"]]

    restarted = cc.load(companion.home)
    current = views.current_perspectives(restarted)
    assert [(p["perspective_id"], p["position"]) for p in current] == [
        (perspective["perspective_id"], "Forgiveness need not require restored access.")
    ]


def test_explicit_revisions_keep_history_reject_stale_targets_and_retry(companion):
    _source, _interpretation, original = authored_view(companion)
    revised = views.record_perspective(
        companion,
        "forgiveness",
        "Forgiveness and reconciliation can overlap, but neither guarantees the other.",
        ["A later example made the boundary feel less absolute."],
        "mixed",
        perspective_id=original["perspective_id"],
        prior_revision=original["revision_id"],
        change="nuance",
        revision_reason="A substantive counterexample added nuance.",
        operation_id="revise-forgiveness",
        now=DAY + dt.timedelta(days=3),
    )
    retry = views.record_perspective(
        companion,
        "forgiveness",
        "Forgiveness and reconciliation can overlap, but neither guarantees the other.",
        ["A later example made the boundary feel less absolute."],
        "mixed",
        perspective_id=original["perspective_id"],
        prior_revision=original["revision_id"],
        change="nuance",
        revision_reason="A substantive counterexample added nuance.",
        operation_id="revise-forgiveness",
        now=DAY + dt.timedelta(days=3),
    )
    assert revised["written"] and not retry["written"] and retry["resumed"]
    assert len(views.perspective_history(companion, original["perspective_id"])) == 2
    assert (
        views.current_perspectives(companion)[0]["revision_id"]
        == revised["entry"]["revision_id"]
    )
    with pytest.raises(ValueError, match="stale prior_revision"):
        views.record_perspective(
            companion,
            "forgiveness",
            "An attempted stale overwrite.",
            ["It raced a newer decision."],
            "uncertain",
            perspective_id=original["perspective_id"],
            prior_revision=original["revision_id"],
            change="supersede",
            revision_reason="This should lose the race.",
            operation_id="stale-revision",
            now=DAY + dt.timedelta(days=4),
        )


def test_concurrent_revisions_allow_one_current_success(companion):
    _source, _interpretation, original = authored_view(companion)

    def revise(number):
        try:
            return views.record_perspective(
                companion,
                "forgiveness",
                f"Concurrent position {number}.",
                [f"Concurrent reason {number}."],
                "uncertain",
                perspective_id=original["perspective_id"],
                prior_revision=original["revision_id"],
                change="nuance",
                revision_reason="Concurrent synthetic reconsideration.",
                operation_id=f"concurrent-{number}",
                now=DAY + dt.timedelta(days=1),
            )
        except ValueError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, (1, 2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum("stale prior_revision" in str(result) for result in results) == 1
    assert len(views.perspective_history(companion, original["perspective_id"])) == 2


def test_relevance_outweighs_recency_in_normal_and_compact_context(companion):
    _source, _interpretation, important = authored_view(companion)
    for number in range(12):
        source = encounter(companion, f"unrelated-{number}")
        views.record_perspective(
            companion,
            f"unrelated subject {number}",
            f"A newer unrelated position {number}.",
            ["Synthetic unrelated reason."],
            "provisional",
            source_ids=[source["id"]],
            operation_id=f"unrelated-view-{number}",
            now=DAY + dt.timedelta(hours=number + 1),
        )
    selected = views.snapshot(
        companion, "Do you still think forgiveness needs reconciliation?", 420, DAY
    )
    assert important["perspective_id"] in {
        item["perspective_id"] for item in selected["current"]
    }

    # 16k is still the compact/tiny rules tier, but retains the minimum useful
    # perspective section. At 8k the whole low-priority section is disclosed as
    # omitted by design rather than injected as an unusable fragment.
    companion.context_tokens = 16000
    compact = slf.summary(
        companion,
        companion.budgets(),
        query="What do you think forgiveness requires?",
    )["preferences"]
    assert important["perspective_id"] in compact
    companion.context_tokens = 64000
    conversation = context.build(
        companion,
        {"extra": {"user_message": "What do you think forgiveness requires?"}},
        DAY + dt.timedelta(days=2),
    )
    assert important["perspective_id"] in conversation
    assert "revision=" + important["revision_id"] in conversation


def test_corrected_unavailable_fiction_and_metadata_keep_their_boundaries(companion):
    human = encounter(companion)
    views.update_support(
        companion,
        human["id"],
        "corrected",
        "The speaker corrected the quoted claim.",
        now=DAY + dt.timedelta(days=1),
    )
    fiction = encounter(companion, "fiction", "fictional_episode", "authored_fiction")
    metadata = encounter(companion, "album", "media_metadata", "catalog_only")
    assert {e["id"]: e for e in views.encounters(companion)}[human["id"]][
        "support_status"
    ] == "corrected"
    assert fiction["observed_as"] == "authored_fiction"
    assert metadata["observed_as"] == "catalog_only"
    assert fiction["lineage_id"] != metadata["lineage_id"]


def test_legacy_rows_load_and_malformed_state_is_not_empty(companion):
    slf.record_pref(
        companion.life, "I like sharp citrus.", DAY, "like", "citrus", "Nova"
    )
    legacy = views.inspection(companion)
    assert legacy["current"][0]["legacy"]
    assert legacy["current"][0]["source_ids"] == []

    with views.path_for(companion).open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    broken = views.inspection(companion)
    assert broken["status"] == "malformed"
    assert broken["current"] == []
    rendered = active.developing_views(companion, DAY)
    assert "unavailable" in rendered


def test_cross_profile_and_operation_conflicts_are_refused(companion):
    source, interpretation, original = authored_view(companion)
    other = cc.Companion(
        agent="Rowan",
        human="Alex",
        profile="rowan",
        hermes_root=companion.hermes_root,
        vault=companion.vault,
        timezone="UTC",
    )
    other.life.mkdir(parents=True)
    with pytest.raises(ValueError, match="cross-profile encounter"):
        views.record_interpretation(
            other, [source["id"]], "This must not cross profiles."
        )
    with pytest.raises(ValueError, match="cross-profile perspective"):
        views.start_investigation(
            other,
            "Can I borrow this view?",
            "independent",
            "Synthetic isolation test.",
            "Try to read it.",
            perspective_ids=[original["perspective_id"]],
        )
    with pytest.raises(ValueError, match="different content"):
        views.record_interpretation(
            companion,
            [source["id"]],
            "Different content under the same operation.",
            operation_id=interpretation["operation_id"],
        )


def test_investigation_results_require_real_support_and_artifacts(companion, tmp_path):
    _source, _interpretation, perspective = authored_view(companion)
    started = views.start_investigation(
        companion,
        "How does a story change when reconciliation is withheld?",
        "making",
        "It tests a question in my current view.",
        "Draft one scene with two different endings.",
        perspective_ids=[perspective["perspective_id"]],
        due_at=DAY + dt.timedelta(hours=2),
        operation_id="start-making",
        now=DAY,
    )["entry"]
    with pytest.raises(ValueError, match="tool_evidence"):
        views.update_investigation(
            companion,
            started["investigation_id"],
            "resolved",
            result="A search supposedly succeeded.",
            result_type="tool_evidence",
            operation_id="false-tool-success",
            now=DAY + dt.timedelta(hours=1),
        )
    outside = tmp_path / "outside.txt"
    outside.write_text("outside this profile", encoding="utf-8")
    with pytest.raises(ValueError, match="workspace"):
        views.update_investigation(
            companion,
            started["investigation_id"],
            "resolved",
            result="Made a file elsewhere.",
            result_type="artifact",
            artifact_paths=[outside],
            operation_id="outside-artifact",
            now=DAY + dt.timedelta(hours=1),
        )
    linked = companion.life / "linked-outside.txt"
    linked.symlink_to(outside)
    with pytest.raises(ValueError, match="workspace"):
        views.artifact_reference(companion, linked)

    artifact = companion.life / "creations" / "two-endings.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("Two invented endings.", encoding="utf-8")
    done = views.update_investigation(
        companion,
        started["investigation_id"],
        "resolved",
        result="I drafted two fictional endings and preferred the unresolved one.",
        result_type="artifact",
        artifact_paths=[artifact],
        operation_id="real-artifact",
        now=DAY + dt.timedelta(hours=2),
    )
    reference = done["entry"]["artifact_refs"][0]
    assert views.resolve_artifact(companion, reference)["available"]
    artifact.unlink()
    assert not views.resolve_artifact(companion, reference)["available"]


def test_projects_retain_choice_reason_next_step_obstacle_and_artifact(companion):
    _source, _interpretation, perspective = authored_view(companion)
    project = arcs.start(
        companion,
        "Two endings",
        "Write parallel endings around forgiveness.",
        "project",
        3,
        now=DAY,
        next_action="Draft the estranged ending.",
        perspective_ids=[perspective["perspective_id"]],
        operation_id="project-start",
    )["entry"]
    before = preread.fingerprint(companion, DAY)
    artifact = companion.data / "drafts" / "ending.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("An invented ending.", encoding="utf-8")
    step = arcs.beat(
        companion,
        project["id"],
        "Drafted the first ending.",
        now=DAY + dt.timedelta(days=1),
        next_action="Compare it with a reconciled ending.",
        obstacle="The second voice still sounds too neat.",
        result="A fictional draft now exists.",
        result_type="artifact",
        artifact_paths=[artifact],
        perspective_ids=[perspective["perspective_id"]],
        operation_id="project-step-one",
    )
    retry = arcs.beat(
        companion,
        project["id"],
        "Drafted the first ending.",
        now=DAY + dt.timedelta(days=1),
        next_action="Compare it with a reconciled ending.",
        obstacle="The second voice still sounds too neat.",
        result="A fictional draft now exists.",
        result_type="artifact",
        artifact_paths=[artifact],
        perspective_ids=[perspective["perspective_id"]],
        operation_id="project-step-one",
    )
    assert step["written"] and not retry["written"]
    folded = arcs.active(companion)[0]
    assert folded["next_action"].startswith("Compare")
    assert folded["obstacle"].startswith("The second")
    assert folded["beats"][-1]["result_type"] == "artifact"
    after = preread.fingerprint(companion, DAY + dt.timedelta(days=1))
    assert before != after
    assert after == preread.fingerprint(
        companion, DAY + dt.timedelta(days=1, minutes=1)
    )


def test_structured_reflection_applies_complete_chain_and_replays_safely(companion):
    source = {
        "7:0": {
            "id": "7",
            "role": "user",
            "content": "I think forgiveness always requires reconciliation.",
            "timestamp": DAY.timestamp(),
            "session_id": "chat-seven",
            "channel": "cli",
        }
    }
    plan = empty_plan()
    plan["interpretations"] = [
        {
            "local_id": "i1",
            "quote_id": "7:0",
            "text": "I understand the appeal, but I am not persuaded yet.",
            "interested": "The claim's moral certainty.",
            "inference": "Alex treats restored contact as part of forgiveness.",
            "unresolved_question": "What about unsafe reconciliation?",
            "feeling": "Curious and resistant.",
            "implication": "I should test edge cases before settling.",
        }
    ]
    plan["perspectives"] = [
        {
            "local_id": "p1",
            "subject": "forgiveness",
            "position": "I am not convinced forgiveness always restores contact.",
            "reasons": ["Safety and release can pull apart."],
            "uncertainty": "provisional",
            "interpretation_ids": ["i1"],
            "source_quote_ids": ["7:0"],
            "change": "new",
            "target_perspective_id": "",
            "target_revision_id": "",
            "revision_reason": "",
        }
    ]
    plan["investigations"] = [
        {
            "question": "How do stories portray forgiveness without reunion?",
            "mode": "independent",
            "reason": "It could challenge or refine my provisional view.",
            "next_step": "Compare two stories I already know, without claiming new research.",
            "perspective_ids": ["p1"],
        }
    ]
    reflection.validate(plan, "daily", source, [], "Alex")
    first = reflection.apply_plan(companion, "daily", "2026-10-12", plan, source, DAY)
    second = reflection.apply_plan(companion, "daily", "2026-10-12", plan, source, DAY)
    assert {row["kind"] for row in first} >= {
        "interpretation",
        "perspective",
        "investigation",
        "journal",
    }
    assert len(views.encounters(companion)) == 1
    assert len(views.interpretations(companion)) == 1
    assert len(views.current_perspectives(companion)) == 1
    assert len(views.investigations(companion, "open")) == 1
    assert any(row.get("resumed") for row in second if row["kind"] != "journal")
    reflected = reflection.context(
        companion,
        "weekly",
        DAY,
        DAY + dt.timedelta(days=3),
        "2026-10-15",
        [],
    )
    assert reflected["current_perspectives"][0]["subject"] == "forgiveness"
    assert reflected["open_investigations"][0]["mode"] == "independent"


def test_api_exposes_current_separately_from_history(companion):
    from fastapi.testclient import TestClient
    from kit.app.server import build

    _source, _interpretation, original = authored_view(companion)
    revision = views.record_perspective(
        companion,
        "forgiveness",
        "My view now holds two possibilities in tension.",
        ["The later example did not settle the conflict."],
        "mixed",
        perspective_id=original["perspective_id"],
        prior_revision=original["revision_id"],
        change="tension",
        revision_reason="Conflicting support remains unresolved.",
        operation_id="api-revision",
        now=DAY + dt.timedelta(days=2),
    )["entry"]
    app = build(home=companion.home)
    with TestClient(app) as client:
        payload = client.get("/api/ledgers").json()
    app.state.operations.pool.shutdown(wait=True)
    app.state.dashboards.close()
    assert [p["revision_id"] for p in payload["perspectives"]["current"]] == [
        revision["revision_id"]
    ]
    assert len(payload["perspectives"]["history"][original["perspective_id"]]) == 2
    assert payload["preferences"][0]["text"] == revision["position"]
