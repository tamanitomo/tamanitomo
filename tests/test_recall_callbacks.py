"""Recall obeys owner identity, and implicit callbacks remain current and optional."""

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import companion_config as cc
import companion_context as context
import companion_recall as recall
import companion_self as memory
import companion_transcript as transcript
from chat_fixtures import HermesStore, OWNER_TELEGRAM, standard_sessions
from kit.app import runtime

NOW = dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc)


class RecallCallbacksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.c = cc.Companion(
            agent="Nova",
            human="Robin",
            profile="nova",
            timezone="UTC",
            hermes_root=root / ".hermes",
            vault=root / "vault",
            context_tokens=272000,
        )
        self.c.home.mkdir(parents=True)
        self.binding(telegram=[OWNER_TELEGRAM])
        self.store = HermesStore(self.c.home)
        standard_sessions(self.store)
        runtime.note_workspace_session(self.c, "web")
        with self.store.db() as db:
            db.executescript("""
                CREATE VIRTUAL TABLE messages_fts USING fts5(content);
                CREATE TRIGGER recall_fts AFTER INSERT ON messages BEGIN
                  INSERT INTO messages_fts(rowid,content) VALUES(new.id,new.content);
                END;
            """)

    def binding(self, **values):
        (self.c.home / ".tamanitomo-chat-owner.json").write_text(
            json.dumps(values), encoding="utf-8"
        )

    def say(self, text, session="term", days=1, **columns):
        return self.store.say(
            session,
            "user",
            text,
            (NOW - dt.timedelta(days=days)).timestamp(),
            **columns,
        )

    def search(self, query="The interview's tomorrow.", **kwargs):
        return recall.search(self.c, query, now=NOW, **kwargs)

    def build(self, query):
        return context.build(self.c, {"extra": {"user_message": query}}, now=NOW)

    def test_owner_source_and_message_checks_apply_to_search_and_chat(self):
        self.say("Paris owner direct message", "tg")
        self.say("Paris terminal owner", "term")
        for session in ("stranger", "group", "job", "rowan-tg"):
            self.say("Paris forbidden " + session, session)
        self.store.session("discord", "discord")
        self.say("Paris forbidden discord", "discord")
        self.say("Paris forbidden synthetic telegram", "tg", platform_message_id=None)
        self.say("Paris forbidden hidden display", "tg", display_kind="internal")
        self.say("Paris forbidden summary", "tg", _compressed_summary=1)
        results = self.search("Do you remember Paris?")["results"]
        self.assertCountEqual(
            [row["excerpt"] for row in results],
            ["Paris owner direct message", "Paris terminal owner"],
        )
        output = self.build("Do you remember Paris?")
        self.assertIn("Paris owner direct message", output)
        self.assertNotIn("Paris forbidden", output)

    def test_binding_switches_and_local_gateway_sessions_are_respected(self):
        self.say("Paris workspace", "web")
        self.say("Paris terminal", "term")
        self.say("Paris telegram", "tg")
        self.store.session("false-local", "cli", chat_id="group")
        self.say("Paris local gateway", "false-local")
        self.binding(terminal=False, workspace=True, telegram=[])
        self.assertEqual(
            [row["excerpt"] for row in self.search("Paris")["results"]],
            ["Paris workspace"],
        )
        self.binding(terminal=True, workspace=False, telegram=[])
        self.assertEqual(
            [row["excerpt"] for row in self.search("Paris")["results"]],
            ["Paris terminal"],
        )

    def test_corrupt_binding_fails_closed(self):
        self.say("Paris unknown ownership")
        (self.c.home / ".tamanitomo-chat-owner.json").write_text("[", encoding="utf-8")
        result = self.search("Paris")
        self.assertEqual(result["results"], [])
        self.assertTrue(result["warnings"])

    def test_root_shared_unlabelled_store_fails_closed_for_recall_and_feed(self):
        self.say("Paris private named profile")
        with self.store.db() as database:
            database.execute("ALTER TABLE sessions DROP COLUMN profile_name")
        root = cc.Companion(
            hermes_root=self.c.hermes_root,
            vault=Path(self.tmp.name) / "root-vault",
            timezone="UTC",
        )
        try:
            os.link(self.store.path, root.home / "state.db")
        except OSError:
            self.skipTest("hard links unavailable")
        result = recall.search(root, "Paris", now=NOW)
        self.assertEqual(result["results"], [])
        self.assertTrue(result["warnings"])
        for read in (
            lambda: runtime.feed_page(root),
            lambda: runtime.feed_sync(root),
            lambda: runtime.feed_search(root, "Paris"),
            lambda: runtime.feed_context(root, "1"),
        ):
            with (
                self.subTest(read=read),
                self.assertRaisesRegex(
                    transcript.SourceUnavailable, "Cannot safely scope"
                ),
            ):
                read()

    def test_root_own_unlabelled_store_remains_readable(self):
        root = cc.Companion(
            hermes_root=self.c.hermes_root,
            vault=Path(self.tmp.name) / "root-vault",
            timezone="UTC",
        )
        store = HermesStore(root.home)
        store.session("root", "cli", profile="")
        store.say("root", "user", "Paris root owner", NOW.timestamp())
        with store.db() as database:
            database.execute("ALTER TABLE sessions DROP COLUMN profile_name")
            database.executescript("""
                CREATE VIRTUAL TABLE messages_fts USING fts5(content);
                INSERT INTO messages_fts(rowid,content) SELECT id,content FROM messages;
            """)
        self.assertEqual(
            [
                row["excerpt"]
                for row in recall.search(root, "Paris", now=NOW)["results"]
            ],
            ["Paris root owner"],
        )
        self.assertEqual(
            [row["content"] for row in runtime.feed_page(root)["messages"]],
            ["Paris root owner"],
        )

    def test_original_compacted_history_survives_but_carryover_and_rewind_do_not(self):
        self.store.session("child", "cli", started=NOW.timestamp() - 100)
        with self.store.db() as db:
            db.execute("ALTER TABLE sessions ADD COLUMN parent_session_id TEXT")
            db.execute("ALTER TABLE sessions ADD COLUMN end_reason TEXT")
            db.execute("UPDATE sessions SET end_reason='compression' WHERE id='term'")
            db.execute("UPDATE sessions SET parent_session_id='term' WHERE id='child'")
        self.say("Paris original", active=0, compacted=1)
        self.say("Paris rewind", active=0, compacted=0)
        self.say("Paris carryover", "child")
        self.assertEqual(
            [row["excerpt"] for row in self.search("Paris")["results"]],
            ["Paris original"],
        )

    def test_interview_callback_retrieves_an_implicit_reference_with_its_date(self):
        quote = "I have an interview with Cedar Labs on Monday. I am nervous about the panel."
        self.say(quote, days=4)
        self.say("The interview's tomorrow.", days=0)
        result = self.search(implicit=True)
        self.assertEqual(result["terms"], ["interview"])
        self.assertEqual([r["excerpt"] for r in result["results"]], [quote])
        self.assertEqual(
            result["results"][0]["timestamp"], (NOW - dt.timedelta(days=4)).timestamp()
        )
        output = self.build("The interview’s tomorrow.")
        self.assertIn("Possible topic callback", output)
        self.assertIn("Cedar Labs", output)
        self.assertIn("Relative dates belong to the quoted message", output)

    def test_a_shared_function_word_is_not_a_callback_topic(self):
        self.say("I went to the market with my sister.")
        query = "That was a fun day with the dog."
        self.assertEqual(recall.implicit_terms(self.c, query), ["fun", "dog"])
        self.assertEqual(self.search(query, implicit=True)["results"], [])

    def test_stale_future_and_undated_evidence_are_not_implicit_callbacks(self):
        self.say("The interview was with Ancient Labs", days=91)
        self.say("The interview is with Future Labs", days=-1)
        path = self.c.home / "memories/USER.md"
        path.parent.mkdir()
        path.write_text("Interview planned with Undated Labs", encoding="utf-8")
        self.assertEqual(self.search(implicit=True)["results"], [])
        self.assertNotIn(
            "Possible topic callback", self.build("The interview's tomorrow.")
        )
        explicit = self.search("Do you remember the interview?")
        self.assertIn("Ancient Labs", json.dumps(explicit))
        self.assertIn("Undated Labs", json.dumps(explicit))
        self.assertNotIn("Future Labs", json.dumps(explicit))

    def test_corrected_fact_and_its_original_quote_do_not_return_as_callbacks(self):
        original = "My interview is at Birch Labs, and they use a panel."
        mid = self.say(original)
        old = memory.record_fact(
            self.c.human_dir,
            "Robin's interview is at Birch Labs.",
            original,
            NOW - dt.timedelta(days=1),
            source=f"session:term message:{mid}",
        )["entry"]
        current = memory.record_fact(
            self.c.human_dir,
            "Robin's interview is at Cedar Labs.",
            "I got the company wrong: the interview is at Cedar Labs.",
            NOW,
            supersedes=old["id"],
        )["entry"]
        result = self.search(implicit=True)
        self.assertEqual([row.get("id") for row in result["results"]], [current["id"]])
        self.assertNotIn("Birch Labs", json.dumps(result))
        self.assertIn("Cedar Labs", json.dumps(result))
        historical = self.search("Do you remember Birch Labs?")
        old_quote = next(r for r in historical["results"] if r.get("session") == "term")
        self.assertIn("inactive fact", old_quote["status"])

    def test_retracted_fact_quote_is_not_resurrected_without_a_source_id(self):
        quote = "My interview is for an accounting position."
        self.say(quote)
        fact = memory.record_fact(self.c.human_dir, quote, quote, NOW)["entry"]
        memory.retract_fact(
            self.c.human_dir, fact["id"], "This was a hypothetical.", NOW
        )
        self.assertEqual(self.search(implicit=True)["results"], [])

    def test_generic_weather_and_time_words_do_not_retrieve_unrelated_history(self):
        self.say("The weather forecast was sunny on my interview day.")
        for query in (
            "What is the weather tomorrow?",
            "The weather is sunny today.",
            "Good morning!",
            "See you tomorrow.",
        ):
            with (
                self.subTest(query=query),
                patch.object(context, "search", wraps=recall.search) as search,
            ):
                self.assertNotIn("Possible topic callback", self.build(query))
                search.assert_not_called()

    def test_newest_matches_win_even_after_many_old_messages(self):
        for number in range(55):
            self.say(f"Interview old note {number}", days=30)
        self.say("Interview latest update", days=1)
        result = self.search(implicit=True, limit=1)
        self.assertEqual(result["results"][0]["excerpt"], "Interview latest update")
        self.assertTrue(result["warnings"])

    def test_exhausted_budget_performs_no_transcript_search(self):
        self.say("Interview private context")
        with patch("companion_transcript.owner_evidence") as evidence:
            result = self.search(implicit=True, seconds=0)
        evidence.assert_not_called()
        self.assertEqual(result["results"], [])

    def test_oversized_fact_ledger_does_not_start_automatic_retrieval(self):
        memory.record_fact(
            self.c.human_dir,
            "Robin likes interview practice.",
            "I like interview practice.",
            NOW,
        )
        with (
            patch.object(recall, "CALLBACK_FACT_BYTES", 1),
            patch.object(memory, "facts") as facts,
        ):
            result = self.search(implicit=True)
        facts.assert_not_called()
        self.assertEqual(result["results"], [])
        self.assertTrue(result["warnings"])

    def test_recall_is_read_only(self):
        self.say("Interview with Cedar Labs next week")
        root = Path(self.tmp.name)

        def snapshot():
            return {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*")
                if p.is_file()
            }

        before = snapshot()
        self.assertTrue(self.search(implicit=True)["results"])
        self.assertEqual(before, snapshot())


if __name__ == "__main__":
    unittest.main()
