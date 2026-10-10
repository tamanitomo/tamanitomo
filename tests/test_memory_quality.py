"""One fact said twice is one fact, one day's news does not stay a fact, and an old
ledger can be tidied after a person has read the plan.

The cases are invented, shaped like pairs from two companions' real ledgers
(2026-10-10) that got past the earlier word-overlap check."""

import datetime as dt
import json
import pathlib
import tempfile
import unittest
from zoneinfo import ZoneInfo

import companion_config as cc
import companion_self as slf

TZ = ZoneInfo("America/New_York")
NOW = dt.datetime(2026, 10, 7, 9, 31, tzinfo=TZ)
EVIDENCE = "2026-10-07T09:30:00-04:00: I said so"


class SameFactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "robin"

    def fact(self, statement, evidence=EVIDENCE, now=NOW, root=None, **kw):
        return slf.record_fact(
            root or self.root,
            statement,
            evidence,
            now,
            kw.pop("category", "work"),
            "stated",
            "session:a message:1",
            human="Robin",
            **kw,
        )

    def test_a_reworded_repeat_becomes_evidence_for_the_first(self):
        first = self.fact(
            "If the garden project takes off, Robin would consider opening a nursery."
        )
        again = self.fact(
            "Robin is considering opening a nursery if the garden project takes off.",
            evidence="2026-10-07T10:10:00-04:00: if it works out I'd open one",
        )
        self.assertFalse(again["written"])
        self.assertEqual(again["merged_into"], first["entry"]["id"])
        self.assertTrue(again["evidence_added"])
        self.assertIn("supersedes", again["next"])
        [fact] = slf.facts(self.root, now=NOW)
        self.assertEqual(
            fact["more_evidence"],
            ["2026-10-07T10:10:00-04:00: if it works out I'd open one"],
        )

    def test_a_detail_only_one_side_capitalises_is_not_a_different_name(self):
        first = self.fact(
            "Robin is handling a computer-rollout task involving transporting and setting "
            "up a projector, screen, and extension cord, and showing Priya how to use them."
        )
        again = self.fact(
            "Robin is handling a finite IT-support task for Priya: bringing an extension "
            "cord, projector, and screen, setting them up, and showing her how to use them."
        )
        self.assertFalse(again["written"])
        self.assertEqual(again["similar_to"][0]["id"], first["entry"]["id"])
        self.assertEqual(len(slf.facts(self.root, now=NOW)), 1)

    def test_a_fuller_version_is_offered_as_a_refinement(self):
        first = self.fact("Mara is Robin's wife.", category="people")
        fuller = self.fact(
            "Mara is Robin's wife; they married on June 12, 2015.",
            category="people",
        )
        self.assertFalse(fuller["written"])
        self.assertEqual(fuller["similar_to"][0]["id"], first["entry"]["id"])
        self.assertIn("supersedes", fuller["next"])
        refined = self.fact(
            "Mara is Robin's wife; they married on June 12, 2015.",
            category="people",
            supersedes=first["entry"]["id"],
        )
        self.assertTrue(refined["written"])

    def test_opposites_changed_numbers_qualifiers_and_swapped_names_stay_separate(self):
        pairs = (
            ("Robin likes Fire Emblem.", "Robin dislikes Fire Emblem."),
            (
                "Robin has two cats named after rivers.",
                "Robin has three cats named after rivers.",
            ),
            (
                "Robin's sister Alice lives in Raleigh.",
                "Robin's sister Beth lives in Raleigh.",
            ),
            (
                "Robin's last job was at the county library.",
                "Robin's job is at the county library.",
            ),
        )
        for i, (one, two) in enumerate(pairs):
            with self.subTest(pair=(one, two)):
                root = self.root / str(i)
                self.assertTrue(self.fact(one, root=root)["written"])
                self.assertTrue(self.fact(two, root=root)["written"])

    def test_the_companions_own_day_and_debugging_notes_are_not_facts_about_robin(self):
        own = self.fact(
            "Nova finished reading a novel about a lighthouse.", agent="Nova"
        )
        self.assertFalse(own["written"])
        self.assertIn("about Nova", own["reason"])
        note = self.fact(
            "Robin's pulse error comes from companion_presence.py:101 rejecting the outfit."
        )
        self.assertFalse(note["written"])
        self.assertIn("technical note", note["reason"])
        self.assertTrue(
            self.fact("Robin told Nova he loves her.", agent="Nova")["written"]
        )
        self.assertFalse((self.root / "facts.jsonl").read_text().count("Nova finished"))

    def test_a_batch_says_why_a_fact_was_not_written(self):
        c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=pathlib.Path(self.tmp.name) / "home",
            vault=pathlib.Path(self.tmp.name) / "vault",
            timezone="America/New_York",
        )
        c.human_dir.mkdir(parents=True)
        entries = [
            {
                "kind": "fact",
                "category": "work",
                "statement": "If the garden project takes off, Robin would consider opening a nursery.",
                "evidence": EVIDENCE,
            },
            {
                "kind": "fact",
                "category": "work",
                "statement": "Robin is considering opening a nursery if the garden project takes off.",
                "evidence": "2026-10-07T10:10:00-04:00: I'd open one if it works",
            },
            {
                "kind": "fact",
                "category": "people",
                "statement": "Mara is Robin's wife.",
                "evidence": EVIDENCE,
            },
            {
                "kind": "fact",
                "category": "people",
                "statement": "Mara is Robin's wife; they married on June 12, 2015.",
                "evidence": EVIDENCE,
            },
            {
                "kind": "fact",
                "category": "work",
                "statement": "Robin is setting up a projector for Priya today.",
                "evidence": EVIDENCE,
            },
        ]
        path = pathlib.Path(self.tmp.name) / "batch.json"
        path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        out = slf.ledger_batch(c, path, NOW)
        self.assertIsNone(out["failed_at"])
        merged, refused, short = out["results"][1], out["results"][3], out["results"][4]
        self.assertEqual(merged["merged_into"], out["results"][0]["id"])
        self.assertEqual(refused["similar_to"][0]["id"], out["results"][2]["id"])
        self.assertIn("supersedes", refused["next"])
        self.assertTrue(short["written"])
        self.assertEqual(short["expires_at"], "2026-10-08T23:59:59-04:00")


class ShortLivedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "robin"

    def fact(self, statement, evidence=EVIDENCE, now=NOW, **kw):
        return slf.record_fact(
            self.root,
            statement,
            evidence,
            now,
            kw.pop("category", "work"),
            "stated",
            "session:a message:1",
            human="Robin",
            **kw,
        )

    def test_one_days_news_leaves_the_profile_after_the_next_day(self):
        out = self.fact(
            "Robin is setting up a projector and screen for Priya at work today."
        )
        self.assertTrue(out["written"])
        self.assertEqual(out["expires_at"], "2026-10-08T23:59:59-04:00")
        self.assertIn("short-lived", out["note"])
        late_tomorrow = dt.datetime(2026, 10, 8, 23, 0, tzinfo=TZ)
        self.assertEqual(len(slf.facts(self.root, now=late_tomorrow)), 1)
        after = dt.datetime(2026, 10, 9, 0, 0, 1, tzinfo=TZ)
        self.assertEqual(slf.facts(self.root, now=after), [])
        self.assertEqual(len(slf._read(self.root / "facts.jsonl")), 1, "kept")

    def test_tomorrow_and_this_week_stay_longer_and_lasting_stays(self):
        tomorrow = self.fact(
            "Robin has a dentist appointment tomorrow morning.", category="health"
        )
        self.assertEqual(tomorrow["expires_at"][:10], "2026-10-09")
        week = self.fact("Robin is covering the front desk this week.")
        self.assertEqual(week["expires_at"][:10], "2026-10-14")
        lasting = self.fact(
            "Robin still works at the county library today, as he has since 2019.",
            lasting=True,
        )
        self.assertTrue(lasting["written"])
        self.assertNotIn("expires_at", lasting["entry"])

    def test_a_dated_quote_alone_does_not_make_a_fact_short_lived(self):
        out = self.fact(
            "Robin works at the county library.",
            evidence="2026-10-07T09:30:00-04:00: I was at the library all day today",
        )
        self.assertNotIn("expires_at", out["entry"])

    def test_a_retry_on_another_day_is_the_same_row_not_a_conflict(self):
        statement = "Robin is at the harvest-festival breakfast tonight."
        self.fact(statement)
        again = self.fact(statement, now=NOW + dt.timedelta(days=3))
        self.assertFalse(again["written"])
        self.assertEqual(len(slf._read(self.root / "facts.jsonl")), 1)


class TidyTests(unittest.TestCase):
    """A ledger written before these checks, tidied only after the plan is read."""

    NOW = dt.datetime(2026, 10, 10, 9, 0, tzinfo=TZ)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "robin"

    def legacy(self, statement, recorded_at, ident, category="work", evidence=None):
        """A row as an older release wrote it: no duplicate check, no expiry."""
        evidence = evidence or f"{recorded_at}: {statement}"
        slf._append(
            self.root / "facts.jsonl",
            {
                "id": ident,
                "kind": "human_fact",
                "category": category,
                "statement": statement,
                "evidence": evidence,
                "source": "session:a message:1",
                "confidence": "stated",
                "status": "active",
                "supersedes": "",
                "recorded_at": recorded_at,
                "provenance": "Recorded from stated or observed evidence about Robin; not imagined",
            },
        )
        return ident

    def ledger(self):
        self.legacy(
            "Robin has an older 4 GB GTX 1050 Ti available to install in his office tower.",
            "2026-09-20T10:00:00-04:00",
            "fact-gpu-1",
            "logistics",
        )
        self.legacy(
            "Robin has an older 4 GB GTX 1050 Ti available for the office tower.",
            "2026-09-21T10:00:00-04:00",
            "fact-gpu-2",
            "logistics",
        )
        lunch = 'Robin said: "I ended up eating some for lunch today."'
        self.legacy(
            lunch,
            "2026-09-14T14:10:00-04:00",
            "fact-lunch-1",
            evidence="2026-09-14T14:09:00-04:00: I ended up eating some for lunch today.",
        )
        self.legacy(
            lunch,
            "2026-09-15T04:00:00-04:00",
            "fact-lunch-2",
            evidence="2026-09-14T14:09:30-04:00: I ended up eating some for lunch today.",
        )
        self.legacy(
            'Robin said: "I make 48k, and that is after a $3k raise yesterday."',
            "2026-09-17T22:35:00-04:00",
            "fact-pay",
            evidence="2026-09-17T22:34:00-04:00: I make 48k, and that is after a $3k raise yesterday.",
        )
        self.legacy(
            "Robin is at the 7 a.m. harvest-festival breakfast today.",
            "2026-10-08T06:50:00-04:00",
            "fact-gala",
        )
        self.legacy(
            "Mara is Robin's wife.",
            "2026-09-10T10:00:00-04:00",
            "fact-wife",
            "people",
        )
        self.legacy(
            "Mara is Robin's wife; they married on June 12, 2015.",
            "2026-09-11T10:00:00-04:00",
            "fact-wife-2",
            "people",
        )

    def plan(self):
        return slf.tidy_plan(self.root, self.NOW, human="Robin")

    def test_the_plan_lists_each_kind_and_changes_nothing(self):
        self.ledger()
        before = (self.root / "facts.jsonl").read_bytes()
        plan = self.plan()
        self.assertEqual((self.root / "facts.jsonl").read_bytes(), before)
        by = {}
        for item in plan["items"]:
            by.setdefault(item["action"], []).append(item)
        merges = {(i["id"], i["into"]) for i in by["merge"]}
        self.assertEqual(
            merges, {("fact-gpu-2", "fact-gpu-1"), ("fact-lunch-2", "fact-lunch-1")}
        )
        self.assertEqual([i["id"] for i in by["expire"]], ["fact-gala"])
        rewrites = {i["id"]: i for i in by["rewrite"]}
        self.assertEqual(set(rewrites), {"fact-lunch-1", "fact-pay"})
        self.assertTrue(rewrites["fact-pay"]["mentions_a_day"])
        self.assertEqual(
            [set(i["ids"]) for i in by["review"]], [{"fact-wife", "fact-wife-2"}]
        )
        self.assertEqual(plan["counts"]["merge"], 2)

    def test_apply_does_only_what_was_decided_and_keeps_the_history(self):
        self.ledger()
        plan = self.plan()
        for item in plan["items"]:
            if item.get("id") == "fact-pay":
                item["new_statement"] = "Robin makes 48k after a $3k raise."
            if item.get("id") == "fact-lunch-1":
                item["action"] = "retire"
        out = slf.tidy_apply(self.root, plan, self.NOW, human="Robin")
        self.assertEqual(out["skipped"], [])
        active = {f["id"]: f for f in slf.facts(self.root, now=self.NOW)}
        statements = sorted(f["statement"] for f in active.values())
        self.assertEqual(
            statements,
            [
                "Mara is Robin's wife.",
                "Mara is Robin's wife; they married on June 12, 2015.",
                "Robin has an older 4 GB GTX 1050 Ti available to install in his office tower.",
                "Robin makes 48k after a $3k raise.",
            ],
        )
        self.assertEqual(
            active["fact-gpu-1"]["more_evidence"],
            [
                "2026-09-21T10:00:00-04:00: Robin has an older 4 GB GTX 1050 Ti available for the office tower."
            ],
        )
        pay = next(
            f for f in active.values() if f["statement"].startswith("Robin makes")
        )
        self.assertEqual(pay["supersedes"], "fact-pay")
        self.assertEqual(pay["statement_origin"], "model_paraphrase")
        self.assertIn("I make 48k", pay["evidence"])
        history = slf._read(self.root / "facts.jsonl")
        self.assertTrue(any(r.get("id") == "fact-gala" for r in history))

    def test_a_fact_changed_since_the_plan_is_skipped_not_forced(self):
        self.ledger()
        plan = self.plan()
        slf.retract_fact(self.root, "fact-gala", "corrected by hand", self.NOW)
        out = slf.tidy_apply(self.root, plan, self.NOW, human="Robin")
        self.assertIn(
            {
                "id": "fact-gala",
                "action": "expire",
                "why": "no longer active, or changed",
            },
            out["skipped"],
        )

    def test_the_companions_own_name_is_not_a_doubt(self):
        self.ledger()
        plan = self.plan()
        item = next(i for i in plan["items"] if i.get("id") == "fact-pay")
        item["new_statement"] = "Robin told Nova he makes 48k after a $3k raise."
        doubted = slf.tidy_apply(self.root, {"items": [item]}, self.NOW, "Robin")
        self.assertIn("Nova", doubted["skipped"][0]["why"])
        named = slf.tidy_apply(self.root, {"items": [item]}, self.NOW, "Robin", "Nova")
        self.assertEqual(named["applied"], 1)

    def test_a_doubtful_rewrite_waits_until_a_person_marks_it_reviewed(self):
        self.ledger()
        plan = self.plan()
        item = next(i for i in plan["items"] if i.get("id") == "fact-pay")
        item["new_statement"] = "Robin makes 52k after a $3k raise."
        plan = {"items": [item]}
        out = slf.tidy_apply(self.root, plan, self.NOW, human="Robin")
        self.assertEqual(out["applied"], 0)
        self.assertIn("number", out["skipped"][0]["why"])
        item["reviewed"] = True
        self.assertEqual(
            slf.tidy_apply(self.root, plan, self.NOW, "Robin")["applied"], 1
        )


if __name__ == "__main__":
    unittest.main()
