"""Evidence-backed facts, caps, isolation, deduplication, and durable corrections."""

import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import companion_config as cc
import companion_context as ctx
import companion_life as life
import companion_local_reflection as reflection
import companion_memory as mem
import companion_recall as rec
import companion_self as slf

ROOT = Path(__file__).resolve().parents[1]
BUDGET_WINDOWS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 200192, 272000, 900000]


class BudgetTests(unittest.TestCase):

    def test_allocation_never_exceeds_the_cap(self):
        for ctx in BUDGET_WINDOWS:
            b = cc.Companion(context_tokens=ctx).budgets()
            used = sum((v for k, v in b.items() if k != "total"))
            self.assertLessEqual(used, b["total"], f"overspent at {ctx}")

    def test_rules_and_tail_are_always_reserved(self):
        for ctx in BUDGET_WINDOWS:
            b = cc.Companion(context_tokens=ctx).budgets()
            self.assertGreater(b["rules"], 0)
            self.assertGreater(b["tail"], 0)

    def test_priority_is_respected_when_sections_compete(self):
        for ctx in BUDGET_WINDOWS:
            b = cc.Companion(context_tokens=ctx).budgets()
            present = [k for k in cc._PRIORITY if b[k]]
            vals = [b[k] for k in present]
            self.assertEqual(
                vals, sorted(vals, reverse=True), f"inverted at {ctx}: {b}"
            )

    def test_small_windows_drop_sections_rather_than_starve_them(self):
        tiny = cc.Companion(context_tokens=4096).budgets()
        kept = [k for k in cc._PRIORITY if tiny[k]]
        self.assertLess(len(kept), len(cc._PRIORITY))
        self.assertIn("loops", kept)
        for k in kept:
            self.assertGreaterEqual(tiny[k], cc._MIN_USEFUL)

    def test_big_windows_keep_every_section(self):
        big = cc.Companion(context_tokens=272000).budgets()
        for k in cc._PRIORITY:
            self.assertGreater(big[k], 0)

    def test_soul_cap_matches_the_hermes_rule_including_its_floor(self):
        self.assertEqual(cc.soul_cap(8192), 20000)
        self.assertEqual(cc.soul_cap(131072), 31457)
        self.assertEqual(cc.soul_cap(272000), 65280)
        self.assertEqual(cc.soul_cap(10000000), 500000)
        self.assertLess(
            cc.Companion(context_tokens=131072).soul_warn, cc.soul_cap(131072)
        )

    def test_injection_is_clamped_both_ends(self):
        self.assertEqual(cc.injection_cap(1000), cc.INJECTION_MIN)
        self.assertEqual(cc.injection_cap(9000000), cc.INJECTION_MAX)

    def test_tiers(self):
        self.assertEqual(cc.tier(8192), "tiny")
        self.assertEqual(cc.tier(32768), "small")
        self.assertEqual(cc.tier(131072), "medium")
        self.assertEqual(cc.tier(272000), "large")
        self.assertTrue(cc.Companion(context_tokens=8192).compact)
        self.assertFalse(cc.Companion(context_tokens=272000).compact)


TZ = ZoneInfo("America/New_York")
WINDOWS = [4096, 8192, 16384, 32768, 65536, 131072, 272000]


def make(tmp, **kw):
    base = dict(
        agent="Nova",
        human="Alex",
        pronoun_set="she",
        timezone="America/New_York",
        hermes_root=tmp / ".hermes",
        vault=tmp / "vault",
    )
    base.update(kw)
    c = cc.Companion(**base)
    c.soul_dir.mkdir(parents=True, exist_ok=True)
    (c.soul_dir / "ActiveContext.md").write_text(
        "## Right now\nAt the desk.\n\n## Active open loops\n### Porch light\n- waiting on the switch\n### Dentist\n- open since Tuesday\n\n## Ignore me\nnot injected\n",
        encoding="utf-8",
    )
    return c


def seed(c, facts=25):
    now = dt.datetime.now(TZ)
    life.record(
        c.life,
        "Stayed too long in the bookstore.",
        "bookstore",
        "completed",
        now,
        agent=c.agent,
        human=c.human,
    )
    for i in range(facts):
        slf.record_fact(
            c.human_dir,
            f"Alex detail {i} recorded at some length",
            f"said it {i}",
            now,
            category="likes",
        )
    slf.record_pref(
        c.life, "The quiet before he wakes.", now, valence="like", agent=c.agent
    )
    slf.ask(c.life, "Has Alex ever lived abroad?", now)


class InjectionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = make(self.tmp)
        seed(self.c)

    def test_fits_its_budget_at_every_window(self):
        for w in WINDOWS:
            c = make(self.tmp, context_tokens=w)
            out = ctx.build(c, {"extra": {"user_message": "hi"}})
            self.assertLessEqual(len(out), c.budgets()["total"], f"over budget at {w}")

    def test_lookup_tail_survives_at_every_window(self):
        for w in WINDOWS:
            c = make(self.tmp, context_tokens=w)
            out = ctx.build(c, {"extra": {"user_message": "hi"}})
            self.assertIn("proof of never", out, f"tail lost at {w}")

    def test_open_loops_with_nested_subheadings_are_not_lost(self):
        """The live regression: '## Active open loops' whose body is all '###'."""
        out = ctx.build(self.c, {"extra": {"user_message": "hi"}})
        self.assertIn("Porch light", out)
        self.assertIn("Dentist", out)
        self.assertNotIn("not injected", out)

    def test_overflow_is_disclosed_not_hidden(self):
        """25 recorded facts must never just fail to appear. On a roomy window
        they are trimmed with a count; on a window too small to carry them at all
        the section is named in the omissions line."""
        for w in (4096, 8192, 32768):
            c = make(self.tmp, context_tokens=w)
            seed(c)
            out = ctx.build(c, {"extra": {"user_message": "hi"}})
            trimmed = "more facts not shown" in out or "no room in this context" in out
            omitted = (
                "Omitted this turn" in out
                and "facts" in out.split("Omitted this turn")[1]
            )
            self.assertTrue(trimmed or omitted, f"silent loss at {w}")

    def test_counts_are_always_truthful(self):
        out = ctx.build(self.c, {"extra": {"user_message": "hi"}})
        self.assertIn("25 recorded facts", out)

    def test_recall_only_fires_on_a_history_question(self):
        plain = ctx.build(self.c, {"extra": {"user_message": "what is the weather"}})
        asked = ctx.build(
            self.c, {"extra": {"user_message": "do you remember when I traveled?"}}
        )
        self.assertNotIn("Personal-history retrieval", plain)
        self.assertIn("Personal-history retrieval", asked)

    def test_build_writes_nothing(self):
        before = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.tmp.rglob("*")
            if p.is_file()
        }
        ctx.build(self.c, {"extra": {"user_message": "do you remember paris?"}})
        after = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.tmp.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_malformed_payload_does_not_crash(self):
        for bad in (
            None,
            {},
            {"extra": None},
            {"extra": {"user_message": None}},
            "nonsense",
            [1, 2],
        ):
            self.assertTrue(ctx.build(self.c, bad))

    def test_missing_data_degrades_to_a_usable_injection(self):
        bare = make(pathlib.Path(tempfile.mkdtemp()))
        out = ctx.build(bare, {"extra": {"user_message": "hi"}})
        self.assertIn("Nova", out)
        self.assertIn("No episodes recorded today", out)

    def test_agent_and_human_names_are_not_hardcoded(self):
        c = make(
            pathlib.Path(tempfile.mkdtemp()),
            agent="Kit",
            human="Rowan",
            pronoun_set="he",
        )
        out = ctx.build(c, {"extra": {"user_message": "hi"}})
        self.assertIn("Kit", out)
        self.assertIn("Rowan", out)
        self.assertNotIn("Nova", out)
        self.assertNotIn("Alex", out)
        for banned in ("ExampleAgent", "Alex"):
            self.assertNotIn(banned, out)


class IsolationTests(unittest.TestCase):

    def test_two_agents_cannot_see_each_others_ledgers(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        root = make(tmp)
        nova = make(tmp, profile="nova", agent="Nova2")
        seed(root, facts=3)
        self.assertEqual(len(slf.facts(root.human_dir)), 3)
        self.assertEqual(len(slf.facts(nova.human_dir)), 0)
        out = ctx.build(nova, {"extra": {"user_message": "hi"}})
        self.assertNotIn("Alex detail 0", out)

    def test_recall_scopes_sessions_to_the_owning_profile(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        root = make(tmp)
        sub = make(tmp, profile="nova")
        self.assertTrue(root.is_root)
        self.assertFalse(sub.is_root)
        self.assertEqual(
            rec.search(root, "travel")["status"],
            "no_evidence_found_in_searched_sources",
        )

    def test_native_default_sessions_are_recalled_without_named_profiles(self):
        import sqlite3

        c = make(pathlib.Path(tempfile.mkdtemp()))
        c.home.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(c.home / "state.db") as db:
            db.executescript(
                "CREATE TABLE sessions(id TEXT, profile_name TEXT, source TEXT);\n                CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,\n                content TEXT, timestamp REAL, _compressed_summary INTEGER);\n                CREATE VIRTUAL TABLE messages_fts USING fts5(content);"
            )
            for i, profile in enumerate(("default", "other"), 1):
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?)", (str(i), profile, "cli")
                )
                db.execute(
                    "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                    (i, str(i), "user", "Paris visit " + profile, 1, 0),
                )
                db.execute(
                    "INSERT INTO messages_fts(rowid,content) VALUES (?,?)",
                    (i, "Paris visit " + profile),
                )
        db.close()
        results = rec.search(c, "Paris")["results"]
        self.assertEqual([r["source"] for r in results], ["hermes:message:1"])

    def test_stopwords_include_both_names(self):
        c = make(pathlib.Path(tempfile.mkdtemp()), agent="Nova", human="Alex")
        got = rec.terms("did Nova ask Alex about Japan", rec.stopwords(c))
        self.assertIn("japan", got)
        self.assertNotIn("nova", got)
        self.assertNotIn("alex", got)


class SoulBlockTests(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = make(self.tmp)
        self.c.home.mkdir(parents=True, exist_ok=True)
        self.c.soul.write_text(
            "# SOUL\n\nWritten by the human.\n\n## Essence\nChosen.\n", encoding="utf-8"
        )

    def test_init_appends_without_altering_existing_text(self):
        before = self.c.soul.read_text(encoding="utf-8")
        r = slf.soul_init(self.c)
        self.assertTrue(r["written"])
        self.assertTrue(r["appended"])
        after = self.c.soul.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertIn("Written by the human.", after)

    def test_writes_only_touch_the_block(self):
        slf.soul_init(self.c)
        head, _, tail = slf._split_soul(self.c.soul)
        slf.soul_write(self.c, "- likes thunderstorms", "append")
        slf.soul_write(self.c, "- rewritten", "set")
        h2, b2, t2 = slf._split_soul(self.c.soul)
        self.assertEqual((h2, t2), (head, tail))
        self.assertEqual(b2.strip(), "- rewritten")

    def test_warning_scales_with_the_model_window(self):
        small = make(self.tmp, context_tokens=8192)
        big = make(self.tmp, context_tokens=272000)
        self.assertLess(small.soul_warn, big.soul_warn)
        slf.soul_init(self.c)
        r = slf.soul_write(self.c, "x" * (self.c.soul_warn + 50), "set")
        self.assertIn("truncates", r["warning"])
        self.assertEqual(
            len(slf._split_soul(self.c.soul)[1].strip()), self.c.soul_warn + 50
        )

    def test_every_write_is_backed_up(self):
        slf.soul_init(self.c)
        slf.soul_write(self.c, "- one", "append")
        self.assertTrue(list(self.c.soul_backups.glob("SOUL.md.*")))


class LedgerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = make(self.tmp)
        self.now = dt.datetime.now(TZ)

    def test_evidence_is_mandatory(self):
        with self.assertRaises(ValueError):
            slf.record_fact(self.c.human_dir, "Alex loves Paris", "", self.now)

    def test_compact_history_pages_cover_the_whole_day_and_disclose_shortening(self):
        start = self.now.replace(hour=12, minute=0, second=0, microsecond=0)
        for i in range(19):
            life.record(
                self.c.life,
                str(i) + " " + "x" * 500,
                "reading",
                "in_progress",
                start + dt.timedelta(seconds=i),
                event_id=f"episode-{i}",
            )
        day = self.now.date().isoformat()
        first = life.history_page(self.c.life, day, 0, 8, True)
        second = life.history_page(self.c.life, day, first["next_offset"], 8, True)
        last = life.history_page(self.c.life, day, second["next_offset"], 8, True)
        self.assertEqual(first["total"], 19)
        self.assertEqual(
            [r["id"] for p in (first, second, last) for r in p["episodes"]],
            [f"episode-{i}" for i in range(19)],
        )
        self.assertIsNone(last["next_offset"])
        self.assertTrue(first["episodes"][0]["text_truncated"])
        full = life.history_page(self.c.life, day, 0, 1)
        self.assertEqual(len(full["episodes"][0]["text"]), 502)
        digest = life.history_digest(self.c.life, day)
        self.assertEqual([r["offset"] for r in digest["episodes"]], list(range(19)))
        self.assertIsNone(digest["next_offset"])
        self.assertLess(len(json.dumps(digest)), 22000)
        self.assertIn("shortened excerpts", digest["detail"])

    def test_supersede_retires_without_erasing(self):
        old = slf.record_fact(
            self.c.human_dir, "works nights", "rota", self.now, category="work"
        )["entry"]
        slf.record_fact(
            self.c.human_dir,
            "works days",
            "corrected me",
            self.now,
            category="work",
            supersedes=old["id"],
        )
        self.assertEqual(
            [f["statement"] for f in slf.facts(self.c.human_dir)], ["works days"]
        )
        self.assertIn(
            "works nights",
            (self.c.human_dir / "facts.jsonl").read_text(encoding="utf-8"),
        )

    def test_retract_mistaken_fact_preserves_history_and_is_idempotent(self):
        old = slf.record_fact(
            self.c.human_dir, "Misclassified agent thought", "wrong evidence", self.now
        )["entry"]
        slf.retract_fact(
            self.c.human_dir, old["id"], "This was not about Alex.", self.now
        )
        again = slf.retract_fact(
            self.c.human_dir, old["id"], "This was not about Alex.", self.now
        )
        self.assertFalse(again["written"])
        self.assertEqual(slf.facts(self.c.human_dir), [])
        self.assertIn(
            "Misclassified agent thought",
            (self.c.human_dir / "facts.jsonl").read_text(encoding="utf-8"),
        )
        with self.assertRaises(ValueError):
            slf.retract_fact(self.c.human_dir, "missing", "No such fact.", self.now)

    def test_ledger_cli_reports_partial_failure_to_scheduler(self):
        import contextlib
        import io
        from unittest.mock import patch

        path = self.tmp / "input.json"
        path.write_text(
            json.dumps([{"kind": "pref", "text": "A quiet room"}, {"kind": "episode"}]),
            encoding="utf-8",
        )
        with (
            patch.object(
                sys, "argv", ["companion_self.py", "ledger", "--file", str(path)]
            ),
            patch.object(cc, "load", return_value=self.c),
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as caught,
        ):
            slf.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(len(slf._read(self.c.life / "preferences.jsonl")), 1)

    def test_question_lifecycle(self):
        q = slf.ask(self.c.life, "Has Alex lived abroad?", self.now)["entry"]
        slf.resolve(self.c.life, q["id"], "asked", self.now)
        slf.resolve(self.c.life, q["id"], "answered", self.now, "Two years in Osaka.")
        done = slf.questions(self.c.life, "answered")[0]
        self.assertEqual(done["answer"], "Two years in Osaka.")
        self.assertEqual(slf.questions(self.c.life, "open"), [])

    def test_episode_plan_is_not_completion(self):
        r = life.record(
            self.c.life, "Thinking about the pool.", "swim", "planned", self.now
        )
        self.assertEqual(r["episode"]["status"], "planned")

    def test_episode_retry_is_idempotent(self):
        a = life.record(self.c.life, "same", "walk", "completed", self.now)
        b = life.record(self.c.life, "same", "walk", "completed", self.now)
        self.assertTrue(a["written"])
        self.assertFalse(b["written"])

    def test_a_batch_file_records_prose_no_shell_could_carry(self):
        """The reason the batch exists: apostrophes and newlines reach the ledger
        intact, because they never pass through a shell argument."""
        prose = "Alex's mother — she's called \"Bee\" — lives\nin Osaka."
        path = self.tmp / "reflection.json"
        path.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "kind": "fact",
                            "category": "people",
                            "statement": prose,
                            "evidence": "he said so on 2026-09-09",
                        },
                        {
                            "kind": "pref",
                            "valence": "curious",
                            "subject": "Osaka",
                            "text": "I want to know what it's like there.",
                        },
                        {"kind": "ask", "text": "What was Osaka like?"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        r = slf.ledger_batch(self.c, path, self.now)
        self.assertEqual(r["applied"], 3)
        self.assertIsNone(r["failed_at"])
        self.assertEqual(slf.facts(self.c.human_dir)[0]["statement"], prose)
        self.assertEqual(len(slf.questions(self.c.life, "open")), 1)

    def test_a_bad_entry_stops_the_batch_and_the_file_can_be_rerun(self):
        path = self.tmp / "reflection.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "kind": "fact",
                        "category": "likes",
                        "statement": "likes rain",
                        "evidence": "said so",
                    },
                    {
                        "kind": "fact",
                        "category": "likes",
                        "statement": "likes snow",
                        "evidence": "",
                    },
                ]
            ),
            encoding="utf-8",
        )
        r = slf.ledger_batch(self.c, path, self.now)
        self.assertEqual(r["failed_at"], 1)
        self.assertEqual(r["applied"], 1)
        self.assertFalse(r["results"][1]["ok"])
        path.write_text(
            json.dumps(
                [
                    {
                        "kind": "fact",
                        "category": "likes",
                        "statement": "likes rain",
                        "evidence": "said so",
                    },
                    {
                        "kind": "fact",
                        "category": "likes",
                        "statement": "likes snow",
                        "evidence": "said so too",
                    },
                ]
            ),
            encoding="utf-8",
        )
        r = slf.ledger_batch(self.c, path, self.now)
        self.assertEqual(r["applied"], 2)
        self.assertFalse(r["results"][0]["written"])
        self.assertEqual(len(slf.facts(self.c.human_dir)), 2)

    def test_a_batch_refuses_shapes_it_cannot_read(self):
        path = self.tmp / "reflection.json"
        for body in (
            '{"entries": {}}',
            "[]",
            '[{"kind":"gossip"}]',
            '["not an object"]',
        ):
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(ValueError):
                r = slf.ledger_batch(self.c, path, self.now)
                if r["failed_at"] is not None:
                    raise ValueError(r["results"][-1]["error"])

    def test_corrupt_lines_are_skipped(self):
        slf.record_fact(self.c.human_dir, "likes rain", "said so", self.now)
        with (self.c.human_dir / "facts.jsonl").open("a", encoding="utf-8") as f:
            f.write("{bad\n\n")
        self.assertEqual(len(slf.facts(self.c.human_dir)), 1)


class MemoryPressureTests(unittest.TestCase):
    """Hermes stops accepting memories at its cap. The kit has to see it coming."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Alex",
            hermes_root=root / "h",
            vault=root / "v",
            timezone="UTC",
            context_tokens=8192,
        )
        self.dir = mem.memory_dir(self.c)
        self.dir.mkdir(parents=True)
        (self.c.home / "config.yaml").write_text(
            "memory:\n  memory_char_limit: 2200\n  user_char_limit: 1375\n",
            encoding="utf-8",
        )

    def fill(self, name, n):
        (self.dir / name).write_text(
            mem.ENTRY_DELIMITER.join(
                (
                    f"- Fact number {i} about an ordinary day, recorded plainly."
                    for i in range(n)
                )
            ),
            encoding="utf-8",
        )

    def test_status_reports_the_fraction_and_flags_the_warning_line(self):
        self.fill("MEMORY.md", 20)
        row = [r for r in mem.status(self.c) if r["file"] == "MEMORY.md"][0]
        self.assertFalse(row["over_warn"])
        self.fill("MEMORY.md", 900)
        row = [r for r in mem.status(self.c) if r["file"] == "MEMORY.md"][0]
        self.assertTrue(row["over_warn"])
        self.assertGreater(row["fraction"], 1)

    def test_archiving_moves_the_oldest_and_keeps_every_entry(self):
        self.fill("MEMORY.md", 900)
        before = (self.dir / "MEMORY.md").read_text(encoding="utf-8")
        result = mem.archive(self.c, "MEMORY.md", apply=True)
        after = (self.dir / "MEMORY.md").read_text(encoding="utf-8")
        archived = mem.archive_for(self.c, "MEMORY.md").read_text(encoding="utf-8")
        self.assertEqual(result["moved"] + result["kept"], 900)
        self.assertLess(len(after), len(before))
        self.assertIn("Fact number 899", after)
        self.assertNotIn("Fact number 0 ", after)
        self.assertIn("Fact number 0 ", archived)
        for i in range(900):
            self.assertIn(f"Fact number {i} ", after + archived)

    def test_a_dry_run_changes_nothing_and_a_second_run_is_a_no_op(self):
        self.fill("MEMORY.md", 900)
        before = (self.dir / "MEMORY.md").read_text(encoding="utf-8")
        mem.archive(self.c, "MEMORY.md", apply=False)
        self.assertEqual((self.dir / "MEMORY.md").read_text(encoding="utf-8"), before)
        mem.archive(self.c, "MEMORY.md", apply=True)
        again = mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertEqual(again["moved"], 0)

    def test_archives_stay_reachable_through_recall(self):
        self.dir.joinpath("MEMORY.md").write_text(
            mem.ENTRY_DELIMITER.join(
                ["- Alex mentioned the lighthouse at Montauk."]
                + [f"- Filler {i}." for i in range(900)]
            ),
            encoding="utf-8",
        )
        mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertNotIn(
            "lighthouse", (self.dir / "MEMORY.md").read_text(encoding="utf-8")
        )
        hits = rec.search(self.c, "lighthouse Montauk", limit=3)
        self.assertTrue(any(("lighthouse" in r["excerpt"] for r in hits["results"])))

    def test_native_delimiters_keep_headings_inside_their_entries(self):
        (self.dir / "USER.md").write_text(
            mem.ENTRY_DELIMITER.join(
                (
                    f"## Entry {i}\n\nSomething recorded on an ordinary day, at some length."
                    for i in range(400)
                )
            ),
            encoding="utf-8",
        )
        result = mem.archive(self.c, "USER.md", apply=True)
        self.assertEqual(result["moved"] + result["kept"], 400)
        self.assertTrue(
            mem.archive_for(self.c, "USER.md")
            .read_text(encoding="utf-8")
            .startswith("\n<!-- archived")
        )

    def test_native_entry_with_headings_and_blank_lines_is_not_split(self):
        text = "One entry\n\n## Detail\nparagraph § literal"
        self.assertEqual(mem.entries(text), ("", [text]))
        self.assertEqual(
            mem.entries(text + mem.ENTRY_DELIMITER + "Next")[1], [text, "Next"]
        )

    def test_caps_are_per_file_characters_not_context_budget_or_utf8_bytes(self):
        (self.c.home / "config.yaml").write_text(
            "memory:\n  memory_char_limit: 100\n  user_char_limit: 50\n",
            encoding="utf-8",
        )
        (self.dir / "MEMORY.md").write_text("é" * 80, encoding="utf-8")
        rows = {r["file"]: r for r in mem.status(self.c)}
        self.assertEqual(rows["MEMORY.md"]["chars"], 80)
        self.assertEqual(rows["MEMORY.md"]["bytes"], 160)
        self.assertEqual(rows["USER.md"]["cap"], 50)
        self.assertTrue(rows["MEMORY.md"]["over_warn"])

    def test_interrupted_archive_recovers_without_duplicating_entries(self):
        from unittest.mock import patch

        self.fill("MEMORY.md", 100)
        source = self.dir / "MEMORY.md"
        before = source.read_text(encoding="utf-8")
        original = mem.atomic_write

        def fail_source(path, text):
            if pathlib.Path(path) == source:
                raise OSError("simulated source replacement failure")
            return original(path, text)

        with patch.object(mem, "atomic_write", side_effect=fail_source):
            with self.assertRaises(OSError):
                mem.archive(self.c, "MEMORY.md", apply=True)
        dest = mem.archive_for(self.c, "MEMORY.md")
        once = dest.read_text(encoding="utf-8")
        self.assertEqual(source.read_text(encoding="utf-8"), before)
        mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertEqual(dest.read_text(encoding="utf-8"), once)
        self.assertFalse(dest.with_suffix(".pending.json").exists())
        self.assertEqual(mem.archive(self.c, "MEMORY.md", apply=True)["moved"], 0)

    def test_uncooperative_writer_is_preserved_and_recovery_refuses_conflict(self):
        from unittest.mock import patch

        self.fill("MEMORY.md", 100)
        source = self.dir / "MEMORY.md"
        before = source.read_text(encoding="utf-8")
        dest = mem.archive_for(self.c, "MEMORY.md")
        original = mem.atomic_write

        def concurrent_write(path, text):
            result = original(path, text)
            if pathlib.Path(path) == dest:
                source.write_text(
                    before + mem.ENTRY_DELIMITER + "Concurrent fact", encoding="utf-8"
                )
            return result

        with patch.object(mem, "atomic_write", side_effect=concurrent_write):
            with self.assertRaisesRegex(ValueError, "changed"):
                mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertIn("Concurrent fact", source.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "unfinished"):
            mem.archive(self.c, "MEMORY.md", apply=True)

    def test_archive_uses_the_native_sidecar_lock_and_preserves_original(self):
        self.fill("MEMORY.md", 100)
        p = self.dir / "MEMORY.md"
        before = p.read_bytes()
        mem.archive(self.c, "MEMORY.md", apply=True)
        self.assertTrue(p.with_suffix(".md.lock").exists())
        backups = list((mem.archive_dir(self.c) / "originals").glob("*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)

    def test_invalid_targets_are_rejected_without_changing_data(self):
        self.fill("MEMORY.md", 100)
        for target in (0, -1, True):
            with self.assertRaises(ValueError):
                mem.archive(self.c, "MEMORY.md", keep_chars=target, apply=True)
        with self.assertRaises(ValueError):
            mem.archive(self.c, "../SOUL.md", apply=True)


class RecallScopeTests(unittest.TestCase):
    """A named profile must never surface another companion's messages, whether
    each profile owns its store or they all share one."""

    SCHEMA = "CREATE TABLE sessions(id TEXT, profile_name TEXT, source TEXT);\n        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,\n        content TEXT, timestamp REAL, _compressed_summary INTEGER);\n        CREATE VIRTUAL TABLE messages_fts USING fts5(content);"

    def seed(self, path, rows):
        import sqlite3

        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(self.SCHEMA)
        for i, (profile, text) in enumerate(rows, 1):
            con.execute("INSERT INTO sessions VALUES (?,?,?)", (str(i), profile, "cli"))
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?)",
                (i, str(i), "user", text, 1, 0),
            )
            con.execute(
                "INSERT INTO messages_fts(rowid,content) VALUES (?,?)", (i, text)
            )
        con.commit()
        con.close()

    def test_rewind_rows_stay_hidden_but_compaction_history_is_recalled(self):
        import sqlite3

        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp, profile="nova")
        self.seed(
            c.home / "state.db",
            [
                ("nova", "Paris active"),
                ("nova", "Paris rewound"),
                ("nova", "Paris archived"),
            ],
        )
        with sqlite3.connect(c.home / "state.db") as con:
            con.execute("ALTER TABLE messages ADD COLUMN active INTEGER DEFAULT 1")
            con.execute("ALTER TABLE messages ADD COLUMN compacted INTEGER DEFAULT 0")
            con.execute("UPDATE messages SET active=0 WHERE id IN (2,3)")
            con.execute("UPDATE messages SET compacted=1 WHERE id=3")
        got = [r["excerpt"] for r in rec.search(c, "Paris")["results"]]
        self.assertCountEqual(got, ["Paris active", "Paris archived"])

    def test_its_own_store_treats_unlabelled_sessions_as_its_own(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp, profile="nova")
        self.seed(
            c.home / "state.db",
            [
                ("", "Paris unlabelled"),
                ("nova", "Paris nova"),
                ("rowan", "Paris rowan"),
            ],
        )
        got = [r["excerpt"] for r in rec.search(c, "Paris")["results"]]
        self.assertEqual(len(got), 2)
        self.assertFalse(any(("rowan" in g for g in got)))

    def test_a_shared_store_hides_everything_but_this_profiles_own_name(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp, profile="nova")
        rootdb = pathlib.Path(c.hermes_root) / "state.db"
        self.seed(
            rootdb,
            [
                ("", "Paris unlabelled"),
                ("default", "Paris default"),
                ("nova", "Paris nova"),
                ("rowan", "Paris rowan"),
            ],
        )
        c.home.mkdir(parents=True, exist_ok=True)
        try:
            (c.home / "state.db").symlink_to(rootdb)
        except OSError:
            self.skipTest("symlinks unavailable")
        out = rec.search(c, "Paris")
        got = [r["excerpt"] for r in out["results"]]
        self.assertEqual(got, ["Paris nova"])
        self.assertIn(
            "shared session store: scoped strictly to this profile", out["warnings"]
        )

    def test_the_root_agent_never_reads_a_named_profile(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp)
        self.seed(
            c.home / "state.db", [("", "Paris unlabelled"), ("nova", "Paris nova")]
        )
        got = [r["excerpt"] for r in rec.search(c, "Paris")["results"]]
        self.assertEqual(got, ["Paris unlabelled"])

    def test_a_sibling_shared_store_excludes_unlabelled_messages(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp, profile="nova")
        peer = c.hermes_root / "profiles/other/state.db"
        self.seed(peer, [("", "Paris private peer"), ("nova", "Paris explicit owner")])
        c.home.mkdir(parents=True, exist_ok=True)
        try:
            (c.home / "state.db").symlink_to(peer)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual(
            [r["excerpt"] for r in rec.search(c, "Paris")["results"]],
            ["Paris explicit owner"],
        )

    def test_hard_linked_store_is_also_strict(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp, profile="nova")
        peer = c.hermes_root / "profiles/other/state.db"
        self.seed(
            peer, [("default", "Paris private peer"), ("nova", "Paris explicit owner")]
        )
        c.home.mkdir(parents=True, exist_ok=True)
        try:
            os.link(peer, c.home / "state.db")
        except OSError:
            self.skipTest("hard links unavailable")
        self.assertEqual(
            [r["excerpt"] for r in rec.search(c, "Paris")["results"]],
            ["Paris explicit owner"],
        )

    def test_root_redirected_into_a_profile_does_not_read_its_messages(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = make(tmp)
        peer = c.hermes_root / "profiles/other/state.db"
        self.seed(peer, [("default", "Paris private peer")])
        try:
            (c.home / "state.db").symlink_to(peer)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual(rec.search(c, "Paris")["results"], [])


class AutomaticMemoryTests(unittest.TestCase):

    def test_hook_archives_before_build_and_keeps_archive_searchable(self):
        import json
        import pathlib
        import subprocess
        import sys
        import tempfile

        import companion_config as cc
        import companion_memory as memory
        import companion_recall as recall

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            home = root / "home"
            home.mkdir()
            c = cc.Companion(hermes_root=home, vault=root / "vault")
            c.save()
            (home / "config.yaml").write_text(
                "memory:\n  memory_char_limit: 1000\n", encoding="utf-8"
            )
            (home / "memories").mkdir()
            entries = [
                "oldmap " + "x" * 290,
                "middle " + "y" * 290,
                "recent " + "z" * 290,
            ]
            source = home / "memories/MEMORY.md"
            source.write_text(memory.ENTRY_DELIMITER.join(entries), encoding="utf-8")
            command = [
                sys.executable,
                str(pathlib.Path(memory.__file__).with_name("companion_context.py")),
                "--home",
                str(home),
            ]
            first = subprocess.run(
                command, input="{}", text=True, capture_output=True, check=True
            )
            self.assertTrue(json.loads(first.stdout)["context"])
            self.assertLess(memory.status(c)[1]["fraction"], 0.8)
            archive = memory.archive_for(c, "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn(entries[0], archive)
            self.assertIn(entries[-1], source.read_text(encoding="utf-8"))
            subprocess.run(
                command, input="{}", text=True, capture_output=True, check=True
            )
            self.assertEqual(
                archive, memory.archive_for(c, "MEMORY.md").read_text(encoding="utf-8")
            )
            self.assertIn("oldmap", json.dumps(recall.search(c, "oldmap")))


class MemoryCapTests(unittest.TestCase):
    """Hermes ships a page and a half of memory. That is a fine default for an
    assistant and nothing at all for somebody who is meant to know you next year."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.c = make(self.tmp)
        self.c.home.mkdir(parents=True, exist_ok=True)
        (self.c.home / "config.yaml").write_text(
            "model:\n  default: test\n", encoding="utf-8"
        )
        self.c.soul.parent.mkdir(parents=True, exist_ok=True)
        self.c.soul.write_text("x" * 8000, encoding="utf-8")

    def test_a_bigger_window_earns_a_bigger_memory(self):
        big = mem.recommend_caps(cc.dataclasses.replace(self.c, context_tokens=272000))
        small = mem.recommend_caps(cc.dataclasses.replace(self.c, context_tokens=8192))
        self.assertGreater(big["caps"]["MEMORY.md"], small["caps"]["MEMORY.md"])
        self.assertEqual(big["tier"], "large")
        self.assertEqual(small["tier"], "tiny")

    def test_a_large_soul_raises_the_floor_rather_than_being_squeezed(self):
        self.c.soul.write_text("x" * 40000, encoding="utf-8")
        plan = mem.recommend_caps(cc.dataclasses.replace(self.c, context_tokens=8192))
        self.assertGreaterEqual(plan["caps"]["MEMORY.md"], 40000 * 3)

    def test_the_caps_are_written_where_hermes_reads_them(self):
        plan = mem.recommend_caps(self.c)
        mem.write_caps(self.c, plan["caps"])
        self.assertEqual(mem.caps(self.c), plan["caps"])
        import yaml

        cfg = yaml.safe_load((self.c.home / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["model"]["default"], "test")

    def test_it_explains_itself_in_words_a_person_can_check(self):
        plan = mem.recommend_caps(self.c)
        self.assertIn("tokens", plan["reason"])
        self.assertIn("nothing is lost", plan["note"])


def empty(text="A quiet day of reading, in my own imagined life."):
    return dict(
        reflection=text,
        preferences=[],
        questions=[],
        facts=[],
        standing=[],
        moments=[],
        answers=[],
        open_loops=[],
        soul_append="",
    )


class FactQualityTests(unittest.TestCase):
    """Facts are propositions backed by a verbatim quote; questions are asked to the human."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
        )
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text(
            "A companion.\n" + slf.BEGIN + "\nI like books.\n" + slf.END + "\n",
            encoding="utf-8",
        )
        self.now = dt.datetime(2026, 9, 23, 11, tzinfo=dt.timezone.utc)
        self.source = {
            "7": {
                "id": "7",
                "role": "user",
                "content": "I play Fire Emblem all the time.",
                "timestamp": self.now.timestamp(),
                "session_id": "chat",
            },
            "8": {
                "id": "8",
                "role": "assistant",
                "content": "You love Fire Emblem.",
                "timestamp": self.now.timestamp(),
                "session_id": "chat",
            },
        }

    def plan(self, **facts):
        plan = empty()
        plan["facts"] = [{"quote_id": "7", "category": "likes", **facts}]
        return plan

    def converse(self, *quotes):
        """Yesterday's conversation in state.db, for tests that run reflect().
        Returns the quote IDs, in order."""
        db = sqlite3.connect(self.c.home / "state.db")
        db.executescript(
            "CREATE TABLE IF NOT EXISTS sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE IF NOT EXISTS messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);"
        )
        db.execute("INSERT INTO sessions VALUES (?,?,?)", ("chat", "telegram", "robin"))
        at = (self.now - dt.timedelta(days=1)).timestamp()
        for i, q in enumerate(quotes, 1):
            db.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,1,0,0)",
                (i, "chat", "user", q, at + i),
            )
        db.commit()
        db.close()
        return [f"{i}:0" for i in range(1, len(quotes) + 1)]

    def run_daily(self, plan, **kw):
        return reflection.reflect(
            self.c,
            "daily",
            "http://127.0.0.1:1",
            "m",
            human_id="robin",
            now=self.now,
            planner=kw.pop("planner", lambda *a: (plan, None)),
            **kw,
        )

    def test_schema_requires_a_statement_on_every_fact(self):
        fact = reflection.schema("daily", self.source, [])["properties"]["facts"][
            "items"
        ]
        self.assertEqual(set(fact["required"]), {"quote_id", "category", "statement"})
        with self.assertRaises(ValueError):
            reflection.validate(self.plan(), "daily", self.source, [], "Robin")
        for bad in ("", "   ", "x" * 401):
            with self.assertRaises(ValueError):
                reflection.validate(
                    self.plan(statement=bad), "daily", self.source, [], "Robin"
                )

    def test_the_proposition_is_stored_and_the_quote_is_the_evidence(self):
        plan = self.plan(statement="Robin enjoys playing Fire Emblem.")
        reflection.validate(plan, "daily", self.source, [], "Robin")
        reflection.apply_plan(
            self.c, "daily", "2026-09-22", plan, self.source, self.now
        )
        [fact] = slf.facts(self.c.human_dir)
        self.assertEqual(fact["statement"], "Robin enjoys playing Fire Emblem.")
        self.assertIn("I play Fire Emblem all the time.", fact["evidence"])
        self.assertNotIn("said:", fact["statement"])
        self.assertIn("session:chat message:7", fact["source"])
        self.assertEqual(fact["confidence"], "stated")

    def test_a_statement_still_needs_trusted_human_evidence(self):
        for quote in ("8", "missing"):
            plan = self.plan(statement="Robin enjoys playing Fire Emblem.")
            plan["facts"][0]["quote_id"] = quote
            with self.assertRaises(ValueError):
                reflection.validate(plan, "daily", self.source, [], "Robin")

    WRAPPERS = (
        'Robin said: "I play Fire Emblem all the time."',
        "Robin said that he plays Fire Emblem.",
        "robin mentioned: Fire Emblem",
        "Robin told me he plays Fire Emblem.",
        "The human said: I play Fire Emblem",
        "The user said he plays Fire Emblem.",
    )

    def test_refused_plans_are_retried_a_bounded_number_of_times(self):
        self.converse("I play Fire Emblem all the time.")
        bad = self.plan(statement="Robin plays Fire Emblem.")
        bad["facts"][0]["quote_id"] = "not-a-quote"
        calls = []

        def planner(*a):
            calls.append(1)
            return (bad, None)

        for _ in range(reflection.MAX_ATTEMPTS):
            with self.assertRaises(ValueError):
                self.run_daily(None, planner=planner)
            self.now += dt.timedelta(hours=2)
        held = self.run_daily(None, planner=planner)
        self.assertEqual(held["status"], "held")
        self.assertEqual(
            len(calls), reflection.MAX_ATTEMPTS, "the model is not asked again"
        )
        self.assertEqual(len(held["errors"]), reflection.MAX_ATTEMPTS)
        folder = self.c.life / "local-reflections"
        self.assertEqual(
            len(list(folder.glob(held["id"] + ".rejected-*.json"))),
            reflection.MAX_ATTEMPTS,
            "each refused plan is kept for review",
        )
        self.assertEqual(slf.facts(self.c.human_dir), [])

    def attempts(self, key=None):
        folder = self.c.life / "local-reflections"
        [path] = (
            [folder / f"{key}.attempts.json"]
            if key
            else list(folder.glob("*.attempts.json"))
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_whole_attempt_is_counted_before_the_request(self):
        self.converse("I play Fire Emblem all the time.")
        seen = []

        def planner(*a):
            seen.append(self.attempts()["count"])
            raise OSError("connection refused")

        with self.assertRaises(OSError):
            self.run_daily(None, planner=planner)
        self.assertEqual(seen, [1], "accounted on disk before inference")
        self.assertEqual(self.attempts()["errors"][0]["error"], "connection refused")
        for exc in (
            ValueError("reflection was truncated; nothing recorded"),
            json.JSONDecodeError("bad", "x", 0),
        ):
            self.now += dt.timedelta(hours=2)

            def fail(*a, exc=exc):
                raise exc

            with self.assertRaises(ValueError):
                self.run_daily(None, planner=fail)
        self.now += dt.timedelta(hours=2)
        held = self.run_daily(None, planner=lambda *a: self.fail("budget spent"))
        self.assertEqual((held["status"], held["attempts"]), ("held", 3))

    def test_a_crash_mid_generation_still_spends_the_attempt(self):
        self.converse("I play Fire Emblem all the time.")

        class Killed(BaseException):
            pass

        def planner(*a):
            raise Killed()

        with self.assertRaises(Killed):
            self.run_daily(None, planner=planner)
        self.assertEqual(self.attempts()["count"], 1)


class FactLedgerTests(unittest.TestCase):
    """Write-time duplicates are refused only on an exact canonical match; the rest is report-only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "robin"
        self.now = dt.datetime(2026, 9, 23, 11, tzinfo=dt.timezone.utc)

    def fact(
        self,
        statement,
        evidence="2026-09-23T10:00:00+00:00: I said so",
        category="likes",
        source="session:a message:1",
        **kw,
    ):
        return slf.record_fact(
            self.root,
            statement,
            evidence,
            self.now,
            category,
            "stated",
            source,
            human="Robin",
            **kw,
        )

    def test_the_same_proposition_is_one_fact_whatever_its_category_source_or_evidence(
        self,
    ):
        first = self.fact("Robin enjoys playing Fire Emblem.")
        again = self.fact(
            "  Robin enjoys   playing Fire Emblem.  ",
            evidence="2026-09-24T09:00:00+00:00: Fire Emblem again",
            category="other",
            source="session:b message:9",
        )
        self.assertTrue(first["written"])
        self.assertEqual(
            again,
            {
                "written": False,
                "reason": "fact already recorded",
                "duplicate_of": first["entry"]["id"],
            },
        )
        self.assertEqual(len(slf.facts(self.root)), 1)
        self.assertEqual(
            len(slf._read(self.root / "facts.jsonl")), 1, "nothing appended"
        )

    def test_different_facts_are_kept(self):
        for s in (
            "Robin likes tea.",
            "Robin dislikes tea.",
            "Robin does not like tea.",
            "Robin's sister Alice lives in Raleigh.",
            "Robin's sister Beth lives in Raleigh.",
            "Robin has a GTX 1050 Ti in the first spare PC.",
            "Robin has a GTX 1050 Ti in the second spare PC.",
            "Robin has a 4.5 GB card.",
            "Robin has a 45 GB card.",
        ):
            self.assertTrue(self.fact(s)["written"], s)
        self.assertEqual(len(slf.facts(self.root)), 9)

    def test_only_formatting_is_folded(self):
        cases = json.loads(
            (ROOT / "tests/canonical_statement_cases.json").read_text(encoding="utf-8")
        )
        for a, b in cases["same"]:
            self.assertEqual(
                slf.canonical_statement(a), slf.canonical_statement(b), (a, b)
            )
        for a, b in cases["different"] + cases["revised"]:
            self.assertNotEqual(
                slf.canonical_statement(a), slf.canonical_statement(b), (a, b)
            )
        for i, (a, b) in enumerate(cases["different"] + cases["revised"]):
            root = self.root.parent / f"pair-{i}"
            slf.record_fact(root, a, "2026-09-23: said so", self.now, human="Robin")
            self.assertTrue(
                slf.record_fact(
                    root, b, "2026-09-23: said so", self.now, human="Robin"
                )["written"],
                (a, b),
            )

    def test_corrections_and_retractions_still_work(self):
        original = self.fact("Robin likes tea.")["entry"]
        fixed = self.fact(
            "Robin likes tea.", category="dislikes", supersedes=original["id"]
        )
        self.assertTrue(fixed["written"])
        self.assertEqual(
            [f["id"] for f in slf.facts(self.root)], [fixed["entry"]["id"]]
        )
        slf.retract_fact(self.root, fixed["entry"]["id"], "Never said it", self.now)
        self.assertEqual(slf.facts(self.root), [])
        self.assertEqual(
            len(slf._read(self.root / "facts.jsonl", kind="human_fact")),
            2,
            "history retained",
        )
        self.assertTrue(
            self.fact(
                "Robin likes tea.", evidence="2026-09-25T09:00:00+00:00: I do like tea"
            )["written"]
        )

    def test_a_correction_is_not_cancelled_by_an_equal_fact(self):
        coffee = self.fact("Robin likes coffee.")["entry"]
        tea = self.fact("Robin likes tea.", source="session:b message:2")["entry"]
        fixed = self.fact(
            "Robin likes tea.",
            evidence="2026-09-24T09:00:00+00:00: tea, not coffee",
            supersedes=coffee["id"],
        )
        self.assertTrue(fixed["written"])
        self.assertEqual(fixed["entry"]["supersedes"], coffee["id"])
        self.assertEqual(
            fixed["equal_to"], [tea["id"]], "the overlap is reported, not merged"
        )
        active = {f["id"] for f in slf.facts(self.root)}
        self.assertNotIn(coffee["id"], active, "the corrected fact is no longer active")
        self.assertEqual(active, {tea["id"], fixed["entry"]["id"]})

    def test_retrying_a_correction_is_idempotent(self):
        original = self.fact("Robin likes tea.")["entry"]
        first = self.fact("Robin likes green tea.", supersedes=original["id"])
        again = self.fact("Robin likes green tea.", supersedes=original["id"])
        self.assertTrue(first["written"])
        self.assertFalse(again["written"])
        self.assertEqual(again["entry"]["id"], first["entry"]["id"])

    def test_a_correction_target_is_checked_inside_the_lock(self):
        """The target has to still be active when the row is appended, not just
        when record_fact began: a rival correction may land in between."""
        original = self.fact("Robin likes tea.")["entry"]
        real = slf._append

        def rival_first(path, row, **kw):
            if row.get("statement") == "Robin likes coffee.":
                real(
                    path, {**row, "id": "fact-rival", "statement": "Robin likes cocoa."}
                )
            return real(path, row, **kw)

        slf._append = rival_first
        try:
            with self.assertRaisesRegex(ValueError, "active fact"):
                self.fact("Robin likes coffee.", supersedes=original["id"])
        finally:
            slf._append = real
        self.assertEqual(
            [f["statement"] for f in slf.facts(self.root)], ["Robin likes cocoa."]
        )

    def test_concurrent_corrections_of_one_fact_leave_one_winner(self):
        import threading

        original = self.fact("Robin likes tea.")["entry"]
        gate = threading.Barrier(8)
        results = []

        def correct(i):
            gate.wait()
            try:
                results.append(
                    self.fact(f"Robin likes tea number {i}.", supersedes=original["id"])
                )
            except ValueError as exc:
                results.append(exc)

        threads = [threading.Thread(target=correct, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        written = [r for r in results if isinstance(r, dict) and r["written"]]
        self.assertEqual(len(written), 1)
        self.assertEqual(sum((isinstance(r, ValueError) for r in results)), 7)
        self.assertEqual(
            [f["id"] for f in slf.facts(self.root)], [written[0]["entry"]["id"]]
        )

    def test_a_retry_written_by_a_newer_release_is_the_same_row(self):
        old = self.fact("Robin plays Fire Emblem.")["entry"]
        path = self.root / "facts.jsonl"
        before = path.read_bytes()
        again = slf.record_fact(
            self.root,
            "Robin plays Fire Emblem.",
            "2026-09-23T10:00:00+00:00: I said so",
            self.now,
            "likes",
            "stated",
            "session:a message:1",
            human="Robin",
            statement_origin="model_paraphrase",
        )
        self.assertFalse(again["written"])
        self.assertEqual(again["entry"]["id"], old["id"])
        self.assertEqual(path.read_bytes(), before)

    def test_rerunning_the_same_write_is_still_idempotent(self):
        first = self.fact("Robin enjoys tea.")
        again = self.fact("Robin enjoys tea.")
        self.assertFalse(again["written"])
        self.assertEqual(again["entry"]["id"], first["entry"]["id"])

    def test_duplicate_report_finds_candidates_and_changes_nothing(self):
        self.fact(
            "Robin has an older 4 GB GTX 1050 Ti available to install in his old office tower.",
            category="logistics",
        )
        self.fact(
            "Robin has an older 4 GB GTX 1050 Ti available for the old office tower.",
            category="other",
        )
        self.fact("Robin has a GTX 1050 Ti in the first spare PC.")
        self.fact("Robin has a GTX 1050 Ti in the second spare PC.")
        self.fact("Robin likes Fire Emblem.")
        self.fact("Robin dislikes Fire Emblem.")
        before = (self.root / "facts.jsonl").read_bytes()
        report = slf.duplicate_facts(self.root)
        self.assertEqual(
            (self.root / "facts.jsonl").read_bytes(), before, "report only"
        )
        pairs = {
            tuple(sorted((f["statement"] for f in c["facts"]))): c
            for c in report["candidates"]
        }
        dell = pairs[
            tuple(
                sorted(
                    [
                        "Robin has an older 4 GB GTX 1050 Ti available to install in his old office tower.",
                        "Robin has an older 4 GB GTX 1050 Ti available for the old office tower.",
                    ]
                )
            )
        ]
        self.assertIn("contains every word", dell["reason"])
        self.assertEqual({f["category"] for f in dell["facts"]}, {"logistics", "other"})
        self.assertTrue(all((f["id"] for f in dell["facts"])))
        spare = pairs[
            tuple(
                sorted(
                    [
                        "Robin has a GTX 1050 Ti in the first spare PC.",
                        "Robin has a GTX 1050 Ti in the second spare PC.",
                    ]
                )
            )
        ]
        self.assertIn("probably distinct", spare["reason"])
        self.assertEqual(len(slf.facts(self.root)), 6)


class ParaphraseScreenTests(unittest.TestCase):
    """The statement of a reflected fact is the model's wording of an exact
    quote. paraphrase_concerns() screens for obvious changes; it does not verify
    meaning. Each case is (quote, statement, what the screen should find)."""

    NAMES = ("Robin", "Nova")
    FAITHFUL = [
        ("I play Fire Emblem all the time.", "Robin enjoys playing Fire Emblem."),
        ("My sister is Bee.", "Robin's sister is Bee."),
        ("I don't like olives.", "Robin dislikes olives."),
        ("I can't stand mornings.", "Robin is not a morning person."),
        ("I'm 34.", "Robin is 34."),
        ("I have three cats.", "Robin has 3 cats."),
        ("I came second in the race.", "Robin placed 2nd in the race."),
        ("No, I work as a nurse.", "Robin works as a nurse."),
        ("I might move to Denver next year.", "Robin might move to Denver next year."),
        (
            "I want you to remind me about it.",
            "Robin wants Nova to remind him about it.",
        ),
        ("I have a 4 GB GTX 1050 Ti.", "Robin has a 4 GB GTX 1050 Ti."),
        ("I turned 34.", "Robin is 34."),
        ("It cost $1,200.", "Robin paid $1200 for it."),
    ]
    CAUGHT = [
        ("I have three cats.", "Robin has 4 cats.", "number"),
        ("My card has 4.5 GB.", "Robin has a 45 GB card.", "number"),
        ("It was -5 out.", "Robin measured +5 degrees.", "number"),
        ("I got a raise.", "Robin got a 5% raise.", "number"),
        ("I like olives.", "Robin does not like olives.", "negation"),
        ("I don't drink coffee.", "Robin drinks coffee.", "negation"),
        ("I quit smoking.", "Robin smokes.", "negation"),
        (
            "My sister lives in Raleigh.",
            "Robin's sister Alice lives in Raleigh.",
            "name",
        ),
        ("I work at a bank.", "Robin works at Larkspur Savings.", "name"),
        (
            "I have a dentist appointment.",
            "Robin has a dentist appointment tomorrow.",
            "time",
        ),
        ("I went hiking.", "Robin goes hiking every weekend.", "time"),
        ("I started a new job.", "Robin started a new job in March.", "name"),
        ("I started a new job.", "Robin started a new job on 2026-09-01.", "number"),
        ("I might move to Denver.", "Robin is moving to Denver.", "certain"),
        ("I'm thinking about getting a dog.", "Robin is getting a dog.", "certain"),
        ("Maybe I will learn piano.", "Robin is learning piano.", "certain"),
        ("My sister loves hiking.", "Robin loves hiking.", "someone else"),
        ("She plays the cello.", "Robin plays the cello.", "someone else"),
        ("My friend thinks I should quit.", "Robin wants to quit.", "someone else"),
    ]
    MISSED = [
        ("I love tea.", "Robin loves coffee."),
        ("My sister and I went to Paris.", "Robin went to Paris alone."),
        ("I used to live in Ohio.", "Robin lives in Ohio."),
        (
            "I play Fire Emblem all the time.",
            "Robin is a professional Fire Emblem player.",
        ),
    ]

    def test_faithful_paraphrases_pass(self):
        for quote, statement in self.FAITHFUL:
            self.assertEqual(
                slf.paraphrase_concerns(statement, quote, self.NAMES),
                [],
                (quote, statement),
            )

    def test_obvious_changes_are_found(self):
        for quote, statement, expected in self.CAUGHT:
            found = slf.paraphrase_concerns(statement, quote, self.NAMES)
            self.assertTrue(
                any((expected in f for f in found)), (quote, statement, found)
            )

    def test_known_limitations_are_stated_not_hidden(self):
        for quote, statement in self.MISSED:
            self.assertEqual(
                slf.paraphrase_concerns(statement, quote, self.NAMES),
                [],
                f"now caught -- move to CAUGHT: {quote!r} / {statement!r}",
            )
        self.assertIn("not otherwise verified", slf.PARAPHRASE_CHECK)


class HeldFactTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            hermes_root=root / "home",
            vault=root / "vault",
            timezone="UTC",
        )
        self.c.home.mkdir(parents=True)
        self.c.soul_dir.mkdir(parents=True)
        self.c.soul.write_text(
            "A companion.\n" + slf.BEGIN + "\n" + slf.END + "\n", encoding="utf-8"
        )
        self.now = dt.datetime(2026, 9, 23, 11, tzinfo=dt.timezone.utc)
        self.source = {
            "1": {
                "id": "1",
                "role": "user",
                "content": "I have three cats.",
                "timestamp": self.now.timestamp(),
                "session_id": "chat",
            },
            "2": {
                "id": "2",
                "role": "user",
                "content": "My sister loves hiking.",
                "timestamp": self.now.timestamp(),
                "session_id": "chat",
            },
        }

    def plan(self):
        plan = empty()
        plan["facts"] = [
            {"quote_id": "1", "category": "other", "statement": "Robin has 3 cats."},
            {"quote_id": "2", "category": "likes", "statement": "Robin loves hiking."},
        ]
        return plan

    def test_a_mismatched_statement_is_held_not_remembered(self):
        results = reflection.apply_plan(
            self.c, "daily", "2026-09-22", self.plan(), self.source, self.now
        )
        [fact] = slf.facts(self.c.human_dir)
        self.assertEqual(fact["statement"], "Robin has 3 cats.")
        self.assertEqual(fact["statement_origin"], "model_paraphrase")
        self.assertIn("not otherwise verified", fact["statement_check"])
        self.assertTrue(
            fact["evidence"].endswith("I have three cats."), "the quote stays exact"
        )
        [held] = slf.held_facts(self.c.human_dir)
        self.assertEqual(held["statement"], "Robin loves hiking.")
        self.assertIn("someone else", held["reasons"][0])
        self.assertTrue(any((r.get("held") for r in results)))
        known = slf.fact_statements(self.c.human_dir)["facts"]
        self.assertEqual(
            [(f["statement"], f.get("origin")) for f in known],
            [("Robin has 3 cats.", "model_paraphrase")],
            "a held statement is not offered back as known; a paraphrase says so",
        )

    def test_reapplying_a_plan_does_not_duplicate_held_or_active_rows(self):
        for _ in range(2):
            reflection.apply_plan(
                self.c, "daily", "2026-09-22", self.plan(), self.source, self.now
            )
        self.assertEqual(len(slf._read(self.c.human_dir / "facts-held.jsonl")), 1)
        self.assertEqual(len(slf._read(self.c.human_dir / "facts.jsonl")), 1)

    def test_a_person_accepts_or_dismisses_a_held_statement(self):
        reflection.apply_plan(
            self.c, "daily", "2026-09-22", self.plan(), self.source, self.now
        )
        [held] = slf.held_facts(self.c.human_dir)
        out = slf.decide_held(self.c.human_dir, held["id"], "accept", self.now, "Robin")
        self.assertTrue(out["written"])
        self.assertEqual(slf.held_facts(self.c.human_dir), [])
        self.assertIn(
            "Robin loves hiking.", [f["statement"] for f in slf.facts(self.c.human_dir)]
        )
        with self.assertRaises(slf.HeldDecisionConflict):
            slf.decide_held(self.c.human_dir, held["id"], "dismiss", self.now)


class HeldDecisionProtocolTests(unittest.TestCase):
    """decide_held: one serialized, recoverable decision per held fact."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name) / "robin"
        self.now = dt.datetime(2026, 9, 23, 11, tzinfo=dt.timezone.utc)
        self.held = slf.hold_fact(
            self.root,
            "Robin loves hiking.",
            "2026-09-20: My sister loves hiking.",
            self.now,
            "likes",
            "session:a message:2",
            ["the quote is about someone else"],
        )["entry"]

    def decide(self, decision, **kw):
        return slf.decide_held(
            self.root, self.held["id"], decision, self.now, "Robin", **kw
        )

    def rows(self, kind, name="facts-held.jsonl"):
        return slf._read(self.root / name, kind=kind)

    def active_from_held(self):
        return [
            f
            for f in slf.facts(self.root)
            if f.get("statement") == "Robin loves hiking."
        ]

    def test_accept_keeps_the_held_record_and_marks_an_override(self):
        before = self.held
        out = self.decide("accept")
        [fact] = self.active_from_held()
        self.assertEqual(out["fact_id"], fact["id"])
        self.assertEqual(fact["held_decision"]["held_id"], self.held["id"])
        self.assertIn("not a machine verification", fact["held_decision"]["note"])
        self.assertEqual(fact["statement_origin"], "model_paraphrase")
        [kept] = self.rows("held_fact")
        self.assertEqual(kept, before, "held row, reasons and exact evidence unchanged")
        [decision] = self.rows("held_fact_decision")
        self.assertEqual(
            (decision["decision"], decision["fact_id"], decision["op_id"]),
            ("accept", fact["id"], out["op_id"]),
        )

    def test_the_same_decision_repeated_is_idempotent(self):
        first = self.decide("accept")
        again = self.decide("accept")
        self.assertTrue(again["already_decided"])
        self.assertEqual(again["fact_id"], first["fact_id"])
        self.assertEqual(len(self.active_from_held()), 1)
        self.assertEqual(len(self.rows("held_fact_decision")), 1)
        self.assertEqual(self.decide("accept")["op_id"], first["op_id"])

    def test_an_opposite_later_decision_conflicts_before_any_effect(self):
        self.decide("dismiss")
        before = (self.root / "facts-held.jsonl").read_bytes()
        with self.assertRaises(slf.HeldDecisionConflict):
            self.decide("accept")
        self.assertEqual(self.active_from_held(), [], "dismissed stays dismissed")
        self.assertFalse((self.root / "facts.jsonl").exists())
        self.assertEqual((self.root / "facts-held.jsonl").read_bytes(), before)

    def test_a_retry_after_the_fact_was_retracted_does_not_resurrect_it(self):
        out = self.decide("accept")
        slf.retract_fact(self.root, out["fact_id"], "Not me, my sister", self.now)
        again = self.decide("accept")
        self.assertTrue(again["already_decided"])
        self.assertEqual(self.active_from_held(), [])
        self.assertEqual(
            len(self.rows("human_fact", "facts.jsonl")), 1, "no second row written"
        )

    def test_accepting_when_an_equal_fact_is_active_records_duplicate_of(self):
        equal = slf.record_fact(
            self.root,
            "Robin loves hiking.",
            "2026-09-19: I love hiking",
            self.now,
            "likes",
            human="Robin",
        )["entry"]
        other = slf.record_fact(
            self.root,
            "Robin likes tea.",
            "2026-09-19: tea",
            self.now,
            "likes",
            human="Robin",
        )["entry"]
        out = self.decide("accept")
        self.assertEqual(out["duplicate_of"], equal["id"])
        self.assertNotIn("fact_id", out)
        self.assertEqual(
            {f["id"] for f in slf.facts(self.root)},
            {equal["id"], other["id"]},
            "nothing retracted to compensate",
        )
        self.assertEqual(self.decide("accept")["duplicate_of"], equal["id"])

    def test_every_interruption_boundary_recovers_to_one_outcome(self):
        from unittest import mock

        real_append, real_record = (slf._append, slf.record_fact)

        class Crash(Exception):
            pass

        def crash_on(kind):

            def append(path, row, *a, **k):
                if row.get("kind") == kind:
                    raise Crash(kind)
                return real_append(path, row, *a, **k)

            return mock.patch.object(slf, "_append", append)

        def crash_record(*a, **k):
            raise Crash("fact")

        boundaries = {
            "before intent": crash_on("held_fact_intent"),
            "after intent, before fact": mock.patch.object(
                slf, "record_fact", crash_record
            ),
            "after fact, before decision": crash_on("held_fact_decision"),
        }
        for name, patch in boundaries.items():
            for decision in ("accept", "dismiss"):
                if decision == "dismiss" and name == "after intent, before fact":
                    continue
                with self.subTest(boundary=name, decision=decision):
                    self.tmp.cleanup()
                    self.setUp()
                    with patch, self.assertRaises(Crash):
                        self.decide(decision)
                    pending = slf.held_facts(self.root)
                    self.assertEqual(len(pending), 1, "still undecided after the crash")
                    if name != "before intent":
                        self.assertEqual(pending[0]["pending_decision"], decision)
                        opposite = "dismiss" if decision == "accept" else "accept"
                        with self.assertRaises(slf.HeldDecisionConflict):
                            self.decide(opposite)
                    out = self.decide(decision)
                    self.assertEqual(out["resumed"], name != "before intent")
                    self.assertEqual(slf.held_facts(self.root), [])
                    self.assertEqual(
                        len(self.active_from_held()), 1 if decision == "accept" else 0
                    )
                    self.assertEqual(
                        len(self.rows("human_fact", "facts.jsonl")),
                        1 if decision == "accept" else 0,
                    )
                    self.assertEqual(len(self.rows("held_fact_intent")), 1)
                    [done] = self.rows("held_fact_decision")
                    self.assertEqual(done["op_id"], out["op_id"])

    def test_concurrent_threads_settle_one_decision(self):
        import threading

        barrier = threading.Barrier(8)
        outcomes = []

        def run(decision):
            barrier.wait()
            try:
                outcomes.append(("ok", self.decide(decision)["decision"]))
            except slf.HeldDecisionConflict:
                outcomes.append(("conflict", decision))

        threads = [
            threading.Thread(target=run, args=("accept" if i % 2 else "dismiss",))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        [winner] = {d for kind, d in outcomes if kind == "ok"}
        self.assertEqual(
            sum((1 for kind, d in outcomes if kind == "conflict")),
            4,
            "every opposite decision conflicted",
        )
        self.assertEqual(len(self.rows("held_fact_decision")), 1)
        self.assertEqual(len(self.active_from_held()), 1 if winner == "accept" else 0)

    def test_concurrent_processes_settle_one_decision(self):
        import subprocess

        script = 'import sys,json,datetime as dt;sys.path.insert(0,sys.argv[1]);import companion_self as slf\ntry:print(json.dumps(slf.decide_held(sys.argv[2],sys.argv[3],sys.argv[4],dt.datetime(2026,9,23,11,tzinfo=dt.timezone.utc),"Robin")["decision"]))\nexcept slf.HeldDecisionConflict:print(json.dumps("conflict"))'
        procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(ROOT / "kit/scripts"),
                    str(self.root),
                    self.held["id"],
                    "accept" if i % 2 else "dismiss",
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            for i in range(6)
        ]
        answers = [json.loads(p.communicate(timeout=60)[0]) for p in procs]
        self.assertTrue(all((p.returncode == 0 for p in procs)))
        [winner] = {a for a in answers if a != "conflict"}
        self.assertEqual(answers.count("conflict"), 3)
        self.assertEqual(len(self.rows("held_fact_decision")), 1)
        self.assertEqual(len(self.active_from_held()), 1 if winner == "accept" else 0)


class ReadOnlyTests(unittest.TestCase):
    """Reading and reporting never change a byte of the history they read."""

    def test_reads_and_reports_leave_history_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            c = cc.Companion(
                agent="Nova",
                human="Robin",
                hermes_root=root / "home",
                vault=root / "vault",
                timezone="UTC",
            )
            c.home.mkdir(parents=True)
            c.soul_dir.mkdir(parents=True)
            c.soul.write_text(
                "A companion.\n" + slf.BEGIN + "\n" + slf.END + "\n", encoding="utf-8"
            )
            now = dt.datetime(2026, 9, 23, 11, tzinfo=dt.timezone.utc)
            a = slf.record_fact(
                c.human_dir,
                "Robin likes tea.",
                "2026-09-20: I like tea",
                now,
                "likes",
                human="Robin",
            )["entry"]
            slf.record_fact(
                c.human_dir,
                "Robin likes green tea.",
                "2026-09-20: green tea",
                now,
                "likes",
                supersedes=a["id"],
                human="Robin",
            )
            slf.record_fact(
                c.human_dir,
                "Robin has an older 4 GB card for the spare PC.",
                "2026-09-20: card",
                now,
                "other",
                human="Robin",
            )
            slf.record_fact(
                c.human_dir,
                "Robin has an older 4 GB card to install in a spare PC.",
                "2026-09-21: card",
                now,
                "logistics",
                human="Robin",
            )
            slf.hold_fact(
                c.human_dir,
                "Robin loves hiking.",
                "2026-09-20: My sister loves hiking.",
                now,
                "likes",
                "s",
                ["someone else"],
            )
            db = sqlite3.connect(c.home / "state.db")
            db.executescript(
                "CREATE TABLE sessions(id TEXT, source TEXT,user_id TEXT); CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER,compacted INTEGER,_compressed_summary INTEGER);"
            )
            db.execute("INSERT INTO sessions VALUES ('chat','telegram','robin')")
            db.execute(
                "INSERT INTO messages VALUES (1,'chat','user','hello',?,1,0,0)",
                (now.timestamp() - 3600,),
            )
            db.commit()
            db.close()
            snapshot = lambda: {
                p: p.read_bytes()
                for p in sorted(root.rglob("*"))
                if p.is_file() and (not p.name.endswith(".lock"))
            }
            before = snapshot()
            slf.facts(c.human_dir)
            slf.fact_statements(c.human_dir)
            slf.duplicate_facts(c.human_dir)
            slf.held_facts(c.human_dir)
            rows, *_ = reflection.messages(c, now - dt.timedelta(days=1), now, "robin")
            reflection.context(
                c, "checkin", now - dt.timedelta(days=1), now, "2026-09-23", rows
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(snapshot(), before)


def test_memory_snapshots_preserve_bom_newlines_and_utf8_exactly(tmp_path):
    from types import SimpleNamespace

    companion = SimpleNamespace(soul_dir=tmp_path)
    text = "\ufefffirst\r\n§\r\n茶\n"
    today = dt.date(2026, 9, 25)
    first = mem.snapshot(companion, "MEMORY.md", text, today)
    target = pathlib.Path(first["snapshot"])
    assert first["written"] is True
    assert target.read_bytes() == text.encode("utf-8")
    unchanged_at = target.stat().st_mtime_ns
    second = mem.snapshot(companion, "MEMORY.md", text, today)
    assert second == {"snapshot": str(target), "written": False}
    assert target.stat().st_mtime_ns == unchanged_at
    assert target.read_bytes() == text.encode("utf-8")
