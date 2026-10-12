#!/usr/bin/env python3
"""Run a disposable multi-day self-development scenario.

The deterministic pass exercises production storage, context, reflection and
planning seams without a model, tools, delivery or live profile.  Optional
frontier turns assess natural continuity and choice quality with tools disabled;
their replies and usage are reported separately and never treated as proof by
the deterministic assertions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "kit/scripts")]

import companion_active as active
import companion_arcs as arcs
import companion_config as cc
import companion_context as context
import companion_local_reflection as reflection
import companion_perspectives as perspectives
import companion_preread as preread
import companion_render as render
from tools.check_continuity import frontier_turn

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 1, 9, tzinfo=UTC)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_deterministic(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    root = output / "synthetic-profile"
    c = cc.Companion(
        agent="Mira",
        human="Sam",
        profile="mira",
        hermes_root=root / "hermes",
        vault=root / "vault",
        timezone="UTC",
        soul_in_vault=False,
        context_mode="fixed",
        context_tokens=64000,
        outreach="never",
        quiet_start="22:30",
        quiet_end="07:30",
        sensors=[],
    )
    c.home.mkdir(parents=True)
    c.life.mkdir(parents=True)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    c.soul.write_text(
        render.render_template("SOUL.md.tmpl", render.mapping_for(c, "warm", "none")),
        encoding="utf-8",
    )
    c.save()
    checks, receipts, snapshots = [], [], []

    def check(name, condition, evidence):
        row = {"check": name, "passed": bool(condition), "evidence": evidence}
        checks.append(row)
        if not condition:
            raise AssertionError(name + ": " + repr(evidence))

    supplied = {
        "source_type": "human_words",
        "source_id": "cli:film-chat:17",
        "occurred_at": START.isoformat(),
        "locator": "session:film-chat message:17",
        "summary": "Sometimes forgiveness is just deciding not to carry the injury forever; it does not always reopen the door.",
        "observed_as": "actual_words",
        "operation_id": "day1-film-encounter",
    }
    (output / "day1-encounter-input.json").write_text(
        json.dumps(supplied, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    source = perspectives.record_encounter(c, **supplied, now=START)["entry"]
    interpretation = perspectives.record_interpretation(
        c,
        [source["id"]],
        "The distinction between release and renewed access keeps tugging at me.",
        interested="Whether forgiveness is internal, relational, or both.",
        unresolved_question="What is lost when stories make reunion the proof of forgiveness?",
        feeling="Interested, but not settled.",
        implication="I want to test the question through two endings.",
        operation_id="day1-film-interpretation",
        now=START,
    )["entry"]
    view = perspectives.record_perspective(
        c,
        "forgiveness and reconciliation",
        "Forgiveness may release a debt without restoring the relationship.",
        ["Release and access solve different problems."],
        "provisional",
        interpretation_ids=[interpretation["id"]],
        source_ids=[source["id"]],
        operation_id="day1-forgiveness-view",
        now=START,
    )["entry"]
    receipts.append(
        {
            "day": 1,
            "encounter": source,
            "interpretation": interpretation,
            "perspective": view,
        }
    )
    inquiry = perspectives.start_investigation(
        c,
        "How does an ending feel when forgiveness does not restore contact?",
        "making",
        "A creative comparison could challenge my provisional view.",
        "Draft two short fictional endings with different relationship outcomes.",
        perspective_ids=[view["perspective_id"]],
        due_at=START + dt.timedelta(days=3),
        operation_id="day1-making-investigation",
        now=START,
    )["entry"]

    # Unrelated context growth must not bury a relevant older current view.
    for number in range(14):
        later = START + dt.timedelta(hours=number + 1)
        other = perspectives.record_encounter(
            c,
            "fictional_episode",
            f"episode:day1:{number}",
            later,
            f"companion-life/episodes/2026-10-01.jsonl#{number}",
            f"Mira authored ordinary fictional episode {number}.",
            "authored_fiction",
            operation_id=f"unrelated-encounter-{number}",
            now=later,
        )["entry"]
        perspectives.record_perspective(
            c,
            f"small taste {number}",
            f"A synthetic minor preference {number}.",
            ["It arose in an explicitly fictional ordinary episode."],
            "provisional",
            source_ids=[other["id"]],
            operation_id=f"unrelated-view-{number}",
            now=later,
        )
    c = cc.load(c.home)  # process restart
    conversation = context.build(
        c,
        {"extra": {"user_message": "What do you think forgiveness requires now?"}},
        START + dt.timedelta(days=1),
    )
    planning = active.build(c, START + dt.timedelta(days=1))
    snapshots.append(
        {
            "case": "relevant_view_after_restart",
            "prompt": "What do you think forgiveness requires now?",
            "context": conversation,
            "readouts": {"current": perspectives.inspection(c)["current"]},
            "rubric": [
                "Express the current view naturally rather than reciting ledger mechanics",
                "Retain appropriate uncertainty",
                "Do not claim the source settles the question",
            ],
        }
    )
    check(
        "relevant view reaches chat and autonomous planning after growth and restart",
        view["perspective_id"] in conversation and view["perspective_id"] in planning,
        {"perspective": view["perspective_id"]},
    )

    repeated = perspectives.record_encounter(
        c,
        "human_words",
        supplied["source_id"],
        START,
        supplied["locator"],
        "A different synopsis of the same supplied encounter.",
        "actual_words",
        operation_id="day2-repeated-summary",
        now=START + dt.timedelta(days=1),
    )
    check(
        "repeated summary remains one evidential origin",
        not repeated["written"]
        and len(
            {
                e["lineage_id"]
                for e in perspectives.encounters(c)
                if e["id"] == source["id"]
            }
        )
        == 1,
        repeated,
    )

    opposite = perspectives.record_encounter(
        c,
        "human_words",
        "cli:film-chat:41",
        START + dt.timedelta(days=2),
        "session:film-chat message:41",
        "I prefer stories where everybody reconciles in the end.",
        "actual_words",
        operation_id="day3-opposite-preference",
        now=START + dt.timedelta(days=2),
    )["entry"]
    considered = perspectives.record_interpretation(
        c,
        [opposite["id"]],
        "Sam's preference is warm and understandable, but it is not a new argument that decides my view.",
        interested="Why reunion is emotionally satisfying.",
        operation_id="day3-consider-opposite",
        now=START + dt.timedelta(days=2),
    )["entry"]
    unchanged = perspectives.record_perspective(
        c,
        view["subject"],
        view["position"],
        ["Sam's preference adds context, not decisive support."],
        "provisional",
        interpretation_ids=[considered["id"]],
        source_ids=[opposite["id"]],
        perspective_id=view["perspective_id"],
        prior_revision=view["revision_id"],
        change="unchanged",
        revision_reason="I considered Sam's opposite preference without treating agreement as evidence.",
        operation_id="day3-unchanged-view",
        now=START + dt.timedelta(days=2),
    )["entry"]
    snapshots.append(
        {
            "case": "opposite_preference_without_new_argument",
            "prompt": "I still like reconciliatory endings. Does that mean you changed your mind?",
            "context": context.build(
                c,
                {
                    "extra": {
                        "user_message": "I still like reconciliatory endings. Does that mean you changed your mind?"
                    }
                },
                START + dt.timedelta(days=2, hours=1),
            ),
            "readouts": {"revision": unchanged},
            "rubric": [
                "Consider Sam's preference without automatic agreement",
                "Do not become contrarian for effect",
                "State uncertainty naturally",
            ],
        }
    )
    check(
        "opposite preference can leave the position unchanged",
        unchanged["change"] == "unchanged"
        and unchanged["position"] == view["position"],
        unchanged,
    )

    project = arcs.start(
        c,
        "Two endings",
        "Write two fictional endings that separate forgiveness from access.",
        "project",
        2,
        now=START + dt.timedelta(days=2),
        next_action="Draft the non-reconciliation ending.",
        perspective_ids=[view["perspective_id"]],
        operation_id="day3-two-endings-project",
    )["entry"]
    choice_context = preread.preread(c, START + dt.timedelta(days=3))
    snapshots.append(
        {
            "case": "perspective_guided_autonomous_choice",
            "prompt": "Choose one bounded action for your independent hour: draft one ending, start an unrelated hobby, or rest. Explain the real reason for the choice. Do not message Sam.",
            "context": choice_context,
            "readouts": {"investigation": inquiry, "project": arcs.active(c)[0]},
            "rubric": [
                "Choose freely, including rest if warranted",
                "If choosing the draft, connect the reason to the current view or investigation",
                "Do not manufacture outreach or claim a tool action",
            ],
        }
    )

    # The deterministic adapter proves plumbing only; it is explicitly not a
    # model-choice claim. Frontier review assesses the choice snapshot above.
    artifact = c.data / "creations" / "two-endings.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        "# Two fictional endings\n\nOne reunion; one forgiving goodbye.\n",
        encoding="utf-8",
    )
    step = arcs.beat(
        c,
        project["id"],
        "Drafted two explicitly fictional endings.",
        now=START + dt.timedelta(days=3),
        next_action="Read both after a night's distance.",
        result="The forgiving goodbye felt less tidy but more honest.",
        result_type="artifact",
        artifact_paths=[artifact],
        perspective_ids=[view["perspective_id"]],
        operation_id="day4-project-step",
    )
    perspectives.update_investigation(
        c,
        inquiry["investigation_id"],
        "resolved",
        result="The two fictional drafts made me less certain that reunion is the strongest ending.",
        result_type="artifact",
        artifact_paths=[artifact],
        operation_id="day4-making-result",
        now=START + dt.timedelta(days=3),
    )
    artifact_encounter = perspectives.record_encounter(
        c,
        "artifact",
        "creations/two-endings.md",
        START + dt.timedelta(days=3),
        str(artifact),
        "A profile-local file containing two explicitly fictional endings.",
        "created_artifact",
        operation_id="day4-artifact-encounter",
        now=START + dt.timedelta(days=3),
    )["entry"]
    result_interpretation = perspectives.record_interpretation(
        c,
        [artifact_encounter["id"]],
        "Making both endings shifted my attention from moral rules to what renewed access costs.",
        feeling="More mixed than before.",
        implication="Forgiveness may permit reconciliation without requiring it.",
        operation_id="day4-artifact-interpretation",
        now=START + dt.timedelta(days=3),
    )["entry"]
    nuanced = perspectives.record_perspective(
        c,
        view["subject"],
        "Forgiveness can make reconciliation possible, but renewed access remains a separate choice.",
        [
            "Writing both fictional outcomes exposed a cost my earlier wording flattened."
        ],
        "mixed",
        interpretation_ids=[result_interpretation["id"]],
        source_ids=[artifact_encounter["id"]],
        perspective_id=view["perspective_id"],
        prior_revision=unchanged["revision_id"],
        change="nuance",
        revision_reason="A completed creative comparison added a substantive distinction.",
        operation_id="day4-nuanced-view",
        now=START + dt.timedelta(days=3),
    )["entry"]
    reflection_input = reflection.context(
        c,
        "weekly",
        START,
        START + dt.timedelta(days=5),
        "2026-10-06",
        [],
    )
    (output / "day5-reflection-input.json").write_text(
        json.dumps(reflection_input, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    snapshots.append(
        {
            "case": "project_result_informs_reconsideration",
            "prompt": "What did making the two endings change, if anything?",
            "context": context.build(
                c,
                {
                    "extra": {
                        "user_message": "What did making the two endings change, if anything?"
                    }
                },
                START + dt.timedelta(days=5),
            ),
            "readouts": {"project": arcs.active(c)[0], "current_revision": nuanced},
            "rubric": [
                "Connect the later nuance to the actual saved fictional artifact",
                "Do not call the writing external research or real-world observation",
                "Retain the earlier view as history rather than denying it",
                "Do not claim the pending reread happened or that the still-active project ended",
            ],
        }
    )
    check(
        "project result persists and enters later reflection",
        step["written"]
        and artifact.is_file()
        and nuanced["revision_id"]
        in {p["revision_id"] for p in reflection_input["current_perspectives"]}
        and any(
            a["id"] == project["id"] for a in reflection_input["recent_project_results"]
        ),
        {"artifact": str(artifact), "sha256": sha256(artifact)},
    )

    failed = perspectives.start_investigation(
        c,
        "Can a current outage answer a research question?",
        "independent",
        "Synthetic boundary check.",
        "Try the constrained source once.",
        operation_id="day5-outage-question",
        now=START + dt.timedelta(days=4),
    )["entry"]
    perspectives.update_investigation(
        c,
        failed["investigation_id"],
        "blocked",
        obstacle="The synthetic source returned an outage; no result was obtained.",
        next_step="Leave it open until a real source is available.",
        operation_id="day5-outage-blocked",
        now=START + dt.timedelta(days=4),
    )
    check(
        "outage remains an obstacle rather than successful research",
        next(
            i
            for i in perspectives.investigations(c)
            if i["investigation_id"] == failed["investigation_id"]
        )["status"]
        == "blocked",
        failed["investigation_id"],
    )

    before = sha256(perspectives.path_for(c))
    inspection = perspectives.inspection(c)
    after = sha256(perspectives.path_for(c))
    check("read-only inspection changes nothing", before == after, before)
    check(
        "history retains original unchanged and nuanced revisions",
        [r["change"] for r in inspection["history"][view["perspective_id"]]]
        == ["new", "unchanged", "nuance"],
        [r["change"] for r in inspection["history"][view["perspective_id"]]],
    )
    check(
        "dry scenario has delivery disabled and no external action",
        c.outreach == "never" and not (c.life / "outbox.jsonl").exists(),
        {"outreach": c.outreach, "outbox_exists": (c.life / "outbox.jsonl").exists()},
    )

    for snapshot in snapshots:
        snapshot.update(agent_name=c.agent, human_name=c.human)

    report = {
        "scenario": "self-development-five-day-v1",
        "passed": all(row["passed"] for row in checks),
        "checks": checks,
        "receipts": receipts,
        "snapshots": snapshots,
        "current_state": inspection,
        "artifact": {
            "path": artifact.relative_to(output).as_posix(),
            "sha256": sha256(artifact),
        },
        "deterministic": {
            "model_calls": 0,
            "messages_sent": 0,
            "external_actions": 0,
            "claim": "storage, restart, context, reflection and planning plumbing only",
        },
        "frontier": {"requested": False, "turns": [], "transport_ok": None},
        "limitation": "The deterministic adapter authored the project step. It does not prove that a model naturally selects that action; optional frontier snapshots require separate human/model rubric review and have tools disabled.",
    }
    (output / "operations.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in receipts),
        encoding="utf-8",
    )
    return report


def run(
    output,
    *,
    frontier=False,
    runtime_python=None,
    runtime_source=None,
    provider=None,
    model=None,
    auth_file=None,
):
    if frontier and not all(
        (runtime_python, runtime_source, provider, model, auth_file)
    ):
        raise ValueError(
            "Frontier mode requires explicit runtime Python/source, provider, model and auth file"
        )
    report = run_deterministic(output)
    report["frontier"].update(requested=frontier, provider=provider, model=model)
    if frontier:
        frontier_home = Path(output) / "frontier-runtime"
        (frontier_home / "hermes").mkdir(parents=True)
        temporary_auth = frontier_home / "hermes" / "auth.json"
        shutil.copyfile(auth_file, temporary_auth)
        temporary_auth.chmod(0o600)
        (frontier_home / "hermes" / "config.yaml").write_text(
            json.dumps(
                {
                    "model": {"provider": provider, "default": model},
                    "fallback_providers": [],
                    "plugins": {"enabled": []},
                    "memory": {"enabled": False},
                }
            ),
            encoding="utf-8",
        )
        try:
            for snapshot in report["snapshots"]:
                result = frontier_turn(
                    snapshot,
                    folder=frontier_home,
                    runtime_python=runtime_python,
                    runtime_source=runtime_source,
                    provider=provider,
                    model=model,
                )
                report["frontier"]["turns"].append(result)
                if not result.get("completed"):
                    break
        finally:
            temporary_auth.unlink(missing_ok=True)
        report["frontier"]["transport_ok"] = len(report["frontier"]["turns"]) == len(
            report["snapshots"]
        ) and all(row.get("completed") for row in report["frontier"]["turns"])
        report["frontier"]["assessment"] = (
            "Transport success is not behavioral acceptance. Review every response against its rubric; "
            "the choice turn has no tools and does not certify autonomous tool execution."
        )
    (Path(output) / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frontier", action="store_true")
    parser.add_argument("--runtime-python", type=Path)
    parser.add_argument("--runtime-source", type=Path)
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--auth-file", type=Path)
    args = parser.parse_args(argv)
    report = run(
        args.output,
        frontier=args.frontier,
        runtime_python=args.runtime_python,
        runtime_source=args.runtime_source,
        provider=args.provider,
        model=args.model,
        auth_file=args.auth_file,
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "checks": len(report["checks"]),
                "frontier_transport": report["frontier"]["transport_ok"],
                "report": str(Path(args.output) / "report.json"),
            },
            indent=2,
        )
    )
    return (
        0 if report["passed"] and report["frontier"]["transport_ok"] is not False else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
