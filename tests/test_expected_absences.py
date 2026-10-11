"""Explained dated time away remains explained without becoming an observation."""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import companion_config as cc
import companion_feelings as feelings
from tests.chat_fixtures import HermesStore
from tests.support import WorkspaceFixture
from tests.test_chat_dock import run_browser_contract

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.save()
    feelings.save_settings(
        c,
        {**feelings.DEFAULTS, "learn_rhythm": False},
        feelings.settings(c)["revision"],
    )
    return c


def save(c, now=NOW, **overrides):
    payload = {
        "action": "create",
        "id": "trip",
        "label": "Conference",
        "start": NOW.isoformat(),
        "end": (NOW + dt.timedelta(days=3)).isoformat(),
        "evidence": "I will be at a conference for three days.",
        "source": "conversation:test/message:42",
        "revision": feelings.expected_absences(c, now)["revision"],
        **overrides,
    }
    return feelings.record_absence(c, payload, now)


def saved_before_the_limit(c, start, end, ident="trip"):
    """A plan written before one plan was limited to 14 days: it is still read."""
    row = {
        "action": "create",
        "id": ident,
        "label": "Long trip",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "evidence": "I will be away for a while.",
        "source": "conversation:test/message:7",
        "event_id": ident + "-created",
        "recorded_at": NOW.isoformat(),
    }
    with (c.life / "expected-absences.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")


def gap(c, since, now, windows=None):
    return feelings.absence(
        c, since.isoformat(), now, {"absence_windows": windows or []}
    )


def test_future_plan_subtracts_only_elapsed_time_and_remains_expected(companion):
    save(companion, start=(NOW + dt.timedelta(days=1)).isoformat())
    early = gap(companion, NOW, NOW + dt.timedelta(hours=6))
    assert early["unexplained_hours"] == 6
    assert early["expected_hours"] == 0
    assert early["current"] == []
    inside = gap(companion, NOW, NOW + dt.timedelta(days=2))
    assert inside["unexplained_hours"] == 24
    assert inside["expected_hours"] == 24
    assert inside["current"] == ["Conference"]


def test_ended_plan_keeps_its_historical_explanation(companion):
    save(companion)
    later = NOW + dt.timedelta(days=5)
    result = gap(companion, NOW, later)
    assert result["expected_hours"] == 72
    assert result["unexplained_hours"] == 48
    assert result["current"] == []
    assert (
        feelings.expected_absences(companion, later)["absences"][0]["status"] == "ended"
    )


@pytest.mark.parametrize(
    "day, start, finish, hours",
    [
        ("2026-03-08", "-05:00", "-04:00", 23),
        ("2026-11-01", "-04:00", "-05:00", 25),
    ],
)
def test_dated_windows_use_actual_dst_elapsed_time(
    companion, day, start, finish, hours
):
    companion.timezone = "America/New_York"
    begin = dt.datetime.fromisoformat(day + "T00:00:00" + start)
    following = begin.date() + dt.timedelta(days=1)
    end = dt.datetime.fromisoformat(following.isoformat() + "T00:00:00" + finish)
    save(companion, now=begin, start=begin.isoformat(), end=end.isoformat())
    result = gap(companion, begin, end)
    assert result["hours"] == hours
    assert result["expected_hours"] == hours
    assert result["unexplained_hours"] == 0


def test_weekly_and_dated_overlap_is_unioned_across_dst(companion):
    companion.timezone = "America/New_York"
    start = dt.datetime.fromisoformat("2026-03-08T00:00:00-05:00")
    now = dt.datetime.fromisoformat("2026-03-08T11:00:00-04:00")
    save(
        companion,
        now=start,
        start="2026-03-08T01:30:00-05:00",
        end="2026-03-08T10:00:00-04:00",
    )
    save(
        companion,
        now=start,
        id="overlap",
        start="2026-03-08T04:00:00-04:00",
        end="2026-03-08T09:00:00-04:00",
    )
    weekly = [{"label": "Sunday rest", "days": [6], "start": "00:00", "end": "08:00"}]
    result = gap(companion, start, now, weekly)
    assert result["hours"] == 10
    assert result["expected_hours"] == 9
    assert result["unexplained_hours"] == 1


@pytest.mark.parametrize("wall", ["2026-03-08T02:30", "2026-11-01T01:30"])
def test_local_dst_gap_or_fold_requires_an_explicit_offset(companion, wall):
    with pytest.raises(ValueError, match="ambiguous or does not exist"):
        save(companion, start=wall, end="2026-11-02T12:00", timezone="America/New_York")
    assert feelings.expected_absences(companion)["history"] == []


def test_local_times_use_requested_timezone_not_machine_timezone(companion):
    row = save(
        companion,
        start="2026-10-01T09:00",
        end="2026-10-01T17:00",
        timezone="Asia/Tokyo",
    )["event"]
    assert row["start"] == "2026-10-01T00:00:00+00:00"
    assert row["end"] == "2026-10-01T08:00:00+00:00"


def test_cancel_preserves_elapsed_explained_time_and_original_evidence(companion):
    original = save(companion)
    path = companion.life / "expected-absences.jsonl"
    prefix = path.read_bytes()
    cancelled = save(
        companion,
        now=NOW + dt.timedelta(hours=4),
        action="cancel",
        evidence="I am back early.",
    )
    assert path.read_bytes().startswith(prefix)
    assert cancelled["absences"][0]["status"] == "cancelled"
    assert cancelled["history"][0] == original["event"]
    result = gap(companion, NOW, NOW + dt.timedelta(hours=10))
    assert result["expected_hours"] == 4
    assert result["unexplained_hours"] == 6


def test_edit_preserves_past_and_changes_only_remaining_plan(companion):
    save(companion)
    save(
        companion,
        now=NOW + dt.timedelta(hours=4),
        action="edit",
        start=(NOW + dt.timedelta(hours=6)).isoformat(),
        end=(NOW + dt.timedelta(hours=8)).isoformat(),
        evidence="Plans changed: I am only busy from six until eight.",
    )
    result = gap(companion, NOW, NOW + dt.timedelta(hours=10))
    assert result["expected_hours"] == 6  # Original 00–04 plus revised 06–08.
    assert result["unexplained_hours"] == 4


def test_edit_before_departure_does_not_count_superseded_future(companion):
    save(companion, start=(NOW + dt.timedelta(hours=5)).isoformat())
    save(
        companion,
        now=NOW + dt.timedelta(hours=2),
        action="edit",
        start=(NOW + dt.timedelta(hours=8)).isoformat(),
        end=(NOW + dt.timedelta(hours=12)).isoformat(),
    )
    assert gap(companion, NOW, NOW + dt.timedelta(hours=10))["expected_hours"] == 2


def test_idempotent_retries_and_revision_conflicts(companion):
    revision = feelings.expected_absences(companion, NOW)["revision"]
    first = save(companion, revision=revision, event_id="request-1")
    retry = save(
        companion,
        now=NOW + dt.timedelta(minutes=1),
        revision=revision,
        event_id="request-1",
    )
    assert retry["written"] is False
    assert retry["event"] == first["event"]
    assert len(retry["history"]) == 1
    with pytest.raises(FileExistsError, match="different content"):
        save(companion, event_id="request-1", label="Different")
    with pytest.raises(FileExistsError, match="Reload"):
        save(companion, id="another", revision=revision)
    with pytest.raises(FileExistsError, match="already exists"):
        save(companion)


def test_default_retry_ids_allow_a_later_return_to_an_earlier_plan(companion):
    save(companion)
    early = NOW + dt.timedelta(hours=1)
    payload = {"action": "edit", "label": "Work trip", "now": early}
    save(companion, **payload)
    save(
        companion, action="edit", label="Long trip", now=early + dt.timedelta(minutes=1)
    )
    result = save(companion, **{**payload, "now": early + dt.timedelta(minutes=2)})
    assert result["written"] is True
    assert result["absences"][0]["label"] == "Work trip"


@pytest.mark.parametrize(
    "change",
    [
        {"evidence": ""},
        {"source": ""},
        {"start": "2026-10-01T12:00"},
        {"end": "2026-09-30T12:00:00+00:00"},
        {"action": "observe"},
    ],
)
def test_invalid_or_unsupported_expectations_do_not_write(companion, change):
    with pytest.raises(ValueError):
        save(companion, **change)
    assert feelings.expected_absences(companion)["history"] == []


def test_explained_gap_has_same_meters_as_no_gap(companion):
    save(companion)
    now = NOW + dt.timedelta(days=2)
    with (
        patch(
            "companion_thread.read", return_value={"last_from_human": NOW.isoformat()}
        ),
        patch.object(feelings, "passive", return_value=None),
    ):
        explained = feelings.compute(companion, now)
    with (
        patch(
            "companion_thread.read", return_value={"last_from_human": now.isoformat()}
        ),
        patch.object(feelings, "passive", return_value=None),
    ):
        baseline = feelings.compute(companion, now)
    assert explained["meters"] == baseline["meters"]
    assert explained["absence"]["unexplained_hours"] == 0


def test_explanation_saved_during_return_applies_to_the_preceding_gap(companion):
    now = NOW + dt.timedelta(days=2)
    # The write follows the returning message by a second, as in an actual turn.
    save(companion, now=now + dt.timedelta(seconds=1))
    with patch(
        "companion_thread.read",
        return_value={
            "last_from_human": now.isoformat(),
            "previous_from_human": NOW.isoformat(),
        },
    ):
        state = feelings.compute(companion, now + dt.timedelta(seconds=2))
    assert state["recent_return"]["unexplained_hours"] == 0
    assert state["meters"]["longing"] == 0
    rendered = feelings.render(companion, state)
    assert "not an observation" in rendered
    assert "conference for three days" in rendered
    assert "conversation:test/message:42" in rendered
    assert "absences" in rendered and "event_id" in rendered


def test_quiet_hours_do_not_explain_absence(companion):
    companion.sleep_time = "00:00"
    companion.wake_time = "23:59"
    result = gap(companion, NOW, NOW + dt.timedelta(hours=12))
    assert result["expected_hours"] == 0


def test_explained_trip_does_not_create_silence_or_cadence_decay(companion):
    import companion_intimacy as intimacy

    # Established connection days keep the score above its friendship floor,
    # so an erroneous silence/cadence penalty would be observable.
    rows = [
        {
            "id": str(day),
            "kind": "connection",
            "topic": "talk",
            "text": "We talked.",
            "evidence": "Synthetic conversation",
            "strength": 0,
            "related": None,
            "at": (NOW - dt.timedelta(days=day)).isoformat(),
        }
        for day in range(1, 61)
    ]
    later = NOW + dt.timedelta(days=3)
    with (
        patch.object(feelings, "experiences", return_value=rows),
        patch(
            "companion_thread.read",
            return_value={"last_from_human": NOW.isoformat(), "hours_since_human": 72},
        ),
    ):
        unexplained = intimacy.compute(companion, later)
        saved_before_the_limit(
            companion, NOW - dt.timedelta(days=20), NOW + dt.timedelta(days=5)
        )
        explained_before = intimacy.compute(companion, NOW)
        explained_after = intimacy.compute(companion, later)
    assert explained_after["score"] == explained_before["score"]
    assert explained_after["score"] > unexplained["score"]
    assert explained_after["cadence"] == explained_before["cadence"]


def test_explained_trip_does_not_expire_prior_contact_credit(companion):
    import companion_intimacy as intimacy

    # Contact concentrated in the older part of the fortnight used to expire
    # during a trip even though no unexplained time had passed.
    store = HermesStore(companion.home)
    store.session("owner", "cli", profile="")
    for day in range(8, 49):
        for turn in range(8):
            store.say(
                "owner",
                "user",
                str(turn) + " Synthetic owner conversation detail." * 7,
                (NOW - dt.timedelta(days=day) + dt.timedelta(hours=turn)).timestamp(),
            )
    store.say("owner", "user", "hello", NOW.timestamp())
    save(companion)

    def fixed_meters(c, now, record=False):
        # Isolate contact decay; ordinary warmth still ages with actual time.
        return {
            "meters": {"trust": 0.7, "warmth": 0.65, "hurt": 0, "irritation": 0},
            "personality": "steady",
            "absence": gap(c, NOW, now),
        }

    with patch.object(feelings, "compute", side_effect=fixed_meters):
        before = intimacy.compute(companion, NOW)
        after = intimacy.compute(companion, NOW + dt.timedelta(days=3))
    assert before["score"] > 25
    assert after["score"] == before["score"]
    assert after["cadence"] == before["cadence"]


SLEEP_AND_WORK = [
    {"label": "Sleep", "days": list(range(7)), "start": "23:00", "end": "07:00"},
    {"label": "Work", "days": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"},
]


def test_daily_routines_do_not_stretch_the_cadence_window(companion):
    import companion_intimacy as intimacy

    feelings.save_settings(
        companion,
        {**feelings.DEFAULTS, "learn_rhythm": False, "absence_windows": SLEEP_AND_WORK},
        feelings.settings(companion)["revision"],
    )
    start, days = intimacy._cadence_window(companion, NOW, None, UTC)
    assert start == NOW - dt.timedelta(days=14)
    assert days == pytest.approx(14, abs=1 / 1440)


def test_routines_leave_contact_cadence_unchanged(companion):
    import companion_intimacy as intimacy

    # Par is per calendar day and already allows for sleep and work. Measuring
    # the window in hours outside them more than doubled cadence for this history.
    store = HermesStore(companion.home)
    store.session("owner", "telegram", profile="")
    for day in range(60):
        store.say(
            "owner",
            "user",
            "Synthetic owner conversation detail. " * 6,
            (NOW - dt.timedelta(days=day, hours=4)).timestamp(),
        )
    plain = intimacy.compute(companion, NOW)
    feelings.save_settings(
        companion,
        {**feelings.DEFAULTS, "learn_rhythm": False, "absence_windows": SLEEP_AND_WORK},
        feelings.settings(companion)["revision"],
    )
    routine = intimacy.compute(companion, NOW)
    assert 0 < plain["cadence"] < 1
    assert routine["cadence"] == plain["cadence"]
    assert routine["score"] == plain["score"]


def test_available_cadence_lookback_is_bounded_and_respects_relationship_start(
    companion,
):
    import companion_intimacy as intimacy

    saved_before_the_limit(
        companion, NOW - dt.timedelta(days=800), NOW + dt.timedelta(days=1)
    )
    with patch.object(feelings, "absence", wraps=feelings.absence) as read:
        start, days = intimacy._cadence_window(companion, NOW, None, UTC)
    assert start == NOW - dt.timedelta(days=366)
    assert days == 0
    assert read.call_count <= 6
    relationship_start = (NOW - dt.timedelta(days=2)).date()
    start, days = intimacy._cadence_window(companion, NOW, relationship_start, UTC)
    assert start.date() == relationship_start
    assert days == 0


def test_routine_hours_never_count_as_silence(companion):
    import companion_intimacy as intimacy

    # The owner's rule (2026-10-10): time inside routines is not silence. Only the
    # silence penalty changes; the contact cadence stays a calendar fortnight.
    store = HermesStore(companion.home)
    store.session("owner", "telegram", profile="")
    for day in range(3, 40):
        for turn in range(8):
            store.say(
                "owner",
                "user",
                str(turn) + " Synthetic owner conversation detail." * 7,
                (NOW - dt.timedelta(days=day) + dt.timedelta(hours=turn)).timestamp(),
            )
    plain = intimacy.compute(companion, NOW)
    whole_day = [
        {"label": "Morning", "days": list(range(7)), "start": "00:00", "end": "12:00"},
        {"label": "Evening", "days": list(range(7)), "start": "12:00", "end": "00:00"},
    ]
    feelings.save_settings(
        companion,
        {**feelings.DEFAULTS, "learn_rhythm": False, "absence_windows": whole_day},
        feelings.settings(companion)["revision"],
    )
    routine = intimacy.compute(companion, NOW)
    assert plain["cadence"] >= 1.0
    assert routine["cadence"] == plain["cadence"]
    assert routine["score"] > plain["score"]


def test_routines_covering_every_hour_do_not_cancel_the_contact_deficit(companion):
    import companion_intimacy as intimacy

    config = {
        **feelings.DEFAULTS,
        "learn_rhythm": False,
        "absence_windows": [
            {
                "label": "Morning",
                "days": list(range(7)),
                "start": "00:00",
                "end": "12:00",
            },
            {
                "label": "Evening",
                "days": list(range(7)),
                "start": "12:00",
                "end": "00:00",
            },
        ],
    }
    feelings.save_settings(companion, config, feelings.settings(companion)["revision"])
    with patch(
        "companion_thread.read",
        return_value={"last_from_human": NOW.isoformat(), "hours_since_human": 72},
    ):
        result = intimacy.compute(companion, NOW + dt.timedelta(days=3))
    # Declaring the whole day as routine once reported perfect cadence with no
    # contact at all; the contact target must not be that easy to opt out of.
    assert result["cadence"] == 0.0


def test_cli_reads_and_records_only_the_requested_profile(companion):
    command = [
        sys.executable,
        str(Path(feelings.__file__)),
        "--home",
        str(companion.home),
    ]
    initial = json.loads(
        subprocess.run(
            [*command, "absences"], capture_output=True, text=True, check=True
        ).stdout
    )
    payload = {
        "revision": initial["revision"],
        "label": "Tomorrow",
        "start": "2030-01-01T09:00:00+00:00",
        "end": "2030-01-01T17:00:00+00:00",
        "evidence": "I will be at work.",
        "source": "conversation:test/9",
    }
    result = json.loads(
        subprocess.run(
            [*command, "absence", "--json", json.dumps(payload)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert result["written"] is True
    assert result["absences"][0]["status"] == "upcoming"


class ExpectedAbsenceApiTests(WorkspaceFixture):
    def test_api_create_edit_cancel_and_profile_isolation(self):
        path = "/api/feelings/absences"
        initial = self.get(path).json()
        data = {
            "revision": initial["revision"],
            "id": "holiday",
            "label": "Holiday",
            "start": "2030-01-01T09:00",
            "end": "2030-01-03T17:00",
            "timezone": "Europe/London",
            "evidence": "I am away for a holiday.",
            "source": "owner-app",
        }
        created = self.post(path, data)
        assert created.status_code == 200, created.text
        assert self.get(path, profile="rowan").json()["absences"] == []
        conflict = self.post(path, {**data, "id": "other"})
        assert conflict.status_code == 409
        edited = self.post(
            path,
            {
                **data,
                "action": "edit",
                "revision": created.json()["revision"],
                "label": "Longer holiday",
                "evidence": "The holiday was extended.",
                "end": "2030-01-04T17:00",
            },
        )
        assert edited.status_code == 200, edited.text
        cancelled = self.post(
            path,
            {
                "id": "holiday",
                "action": "cancel",
                "revision": edited.json()["revision"],
                "evidence": "The holiday was cancelled.",
                "source": "owner-app",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        result = self.get(path).json()
        assert result["absences"][0]["status"] == "cancelled"
        assert len(result["history"]) == 3


def test_ui_date_conversion_preserves_companion_timezone_and_escapes_summary():
    run_browser_contract(r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context={Intl,Date,esc:s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;'),when:s=>s};
vm.createContext(context);vm.runInContext(fs.readFileSync('kit/app/static/feelings.js','utf8'),context);
assert.equal(context.absenceLocalTime('2026-10-01T00:00:00Z','Asia/Tokyo'),'2026-10-01T09:00');
assert.equal(context.absenceLocalTime('2026-11-01T06:30:00Z','America/New_York'),'2026-11-01T01:30');
const html=context.expectedAbsencesSummary([{status:'upcoming',label:'<img>',start:'start',end:'end'}]);
assert.ok(html.includes('&lt;img&gt;'));assert.ok(!html.includes('<img>'));assert.ok(html.includes('data-us-action="absences"'));
""")


def test_us_form_submits_create_edit_cancel_and_refuses_changed_profile():
    run_browser_contract(r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let store={revision:'r0',timezone:'Asia/Tokyo',absences:[],history:[]},requests=[],form;
const node=()=>({textContent:'',disabled:false,onclick:null});
const status=node(),newButton=node(),reloadButton=node(),back=node(),submit=node(),error=node();
const box={
  set innerHTML(html){
    const row=store.absences[0];
    const field=value=>({value:value||'',type:'datetime-local',checked:false,focus(){}});
    form={isConnected:true,elements:{label:field(row?.label),start:field(row?.start),end:field(row?.end),evidence:field(''),explicit:field('')},reportValidity:()=>true,
      querySelector:selector=>selector==='[type=submit]'?submit:error};
  },
  querySelector:selector=>selector==='form'?form:back,
};
let rowButtons=[];
const host={isConnected:true,
  set innerHTML(html){rowButtons=store.absences.filter(r=>r.status!=='cancelled').flatMap(r=>[
    {dataset:{absenceEdit:r.id}},{dataset:{absenceCancel:r.id}}
  ]);},
  querySelector:selector=>({'[data-absence-editor]':box,'[data-absence-new]':newButton,'[data-absence-reload]':reloadButton,'[data-absence-status]':status}[selector]),
  querySelectorAll:()=>rowButtons,
};
const context={Intl,Date,INSTALLATION:'test',PROFILE:'nova',current:'relationship',esc:String,when:String,
  confirmEditorLeave:async()=>true,clearEditorDirty(){},$:()=>null,
  api:async(path,options)=>{
    assert.equal(path,'/feelings/absences');
    if(options){
      const payload=JSON.parse(options.body);requests.push(payload);
      const row={...(store.absences[0]||{}),...payload,id:payload.id||'saved-trip',
        start:payload.start?payload.start+'+09:00':store.absences[0]?.start,
        end:payload.end?payload.end+'+09:00':store.absences[0]?.end,
        status:payload.action==='cancel'?'cancelled':'upcoming',recorded_at:'2026-10-01T00:00:00Z'};
      store={...store,revision:'r'+requests.length,absences:[row],history:[...store.history,row]};
    }
    return JSON.parse(JSON.stringify(store));
  },
};
vm.createContext(context);vm.runInContext(fs.readFileSync('kit/app/static/feelings.js','utf8'),context);
(async()=>{
  await context.mountExpectedAbsences(host);
  await newButton.onclick();
  form.elements.label.value='Work trip';form.elements.start.value='2030-10-02T09:00';form.elements.end.value='2030-10-03T17:00';
  form.elements.evidence.value='I will be away for work.';
  await form.onsubmit({preventDefault(){}});
  assert.equal(requests[0].action,'create');assert.equal(requests[0].revision,'r0');
  assert.equal(requests[0].timezone,'Asia/Tokyo');assert.equal(requests[0].source,'owner-app');
  assert.equal(requests[0].start,'2030-10-02T09:00');
  await rowButtons[0].onclick();
  form.elements.start.value='2030-10-02T09:00';form.elements.end.value='2030-10-04T17:00';
  form.elements.evidence.value='I am staying one more night.';
  await form.onsubmit({preventDefault(){}});
  assert.equal(requests[1].action,'edit');assert.equal(requests[1].id,'saved-trip');assert.equal(requests[1].revision,'r1');
  await rowButtons[1].onclick();form.elements.evidence.value='The trip was cancelled.';
  await form.onsubmit({preventDefault(){}});
  assert.equal(requests[2].action,'cancel');assert.equal(requests[2].revision,'r2');
  assert.ok(!('start' in requests[2]));assert.ok(status.textContent.includes('Elapsed time remains explained'));
  await newButton.onclick();context.PROFILE='rowan';
  await form.onsubmit({preventDefault(){}});
  assert.equal(requests.length,3,'an old editor must never write to another profile');
})().catch(error=>{console.error(error);process.exitCode=1;});
""")


def test_a_damaged_line_is_set_aside_not_fatal(companion):
    # One torn line used to stop the whole feelings calculation for the companion.
    save(companion)
    path = companion.life / "expected-absences.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"id": "torn", "action": "cre')
    later = NOW + dt.timedelta(hours=1)
    state = feelings.expected_absences(companion, later)
    assert [row["id"] for row in state["absences"]] == ["trip"]
    assert state["skipped_lines"] == 1
    assert feelings.compute(companion, later)["expected_absences"]
    save(
        companion,
        now=later,
        id="course",
        label="Course",
        start=(NOW + dt.timedelta(days=5)).isoformat(),
        end=(NOW + dt.timedelta(days=6)).isoformat(),
    )
    state = feelings.expected_absences(companion, later)
    assert sorted(row["id"] for row in state["absences"]) == ["course", "trip"]
    assert state["skipped_lines"] == 1
