"""Presence, wardrobe tokens, settings, portable host probes, and launchers."""

import ctypes
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import companion_config as cc
import companion_context as context
import companion_platform as platform
import companion_portrait as portrait
import companion_presence as presence
from fastapi.testclient import TestClient

import launch
import update_release
from kit.app import local_models
from kit.app.server import build
from kit.app.terminal import Console
from kit.app.wardrobe import (
    filter_wardrobe_items,
    is_blacklisted_undergarment,
    is_intimate_garment,
)
from tests.support import AppFixture, WorkspaceFixture

ROOT = Path(__file__).resolve().parents[1]


class PresenceTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(hermes_root=root / "home", vault=root / "vault")
        self.now = dt.datetime(2026, 9, 9, 23, 45, tzinfo=dt.timezone.utc)
        presence.update_wardrobe(
            self.c,
            [
                {"id": "pajamas", "description": "blue pajamas", "use": "sleep"},
                {
                    "id": "gym",
                    "description": "running shorts and tee",
                    "use": "exercise",
                },
            ],
        )

    def data(self, **updates):
        data = {
            "previous_id": None,
            "outfit": ["pajamas"],
            "location": "home",
            "activity": "reading",
            "mood": "relaxed",
            "care": [],
            "transition": "",
            "text": "Reading before bed.",
        }
        data.update(updates)
        return data

    def test_state_survives_midnight_and_retries_do_not_duplicate(self):
        first = presence.update(self.c, self.data(), self.now)
        repeat = presence.update(self.c, self.data(), self.now)
        self.assertFalse(repeat["written"])
        second = presence.update(
            self.c,
            self.data(previous_id=first["episode"]["id"]),
            self.now + dt.timedelta(minutes=15),
        )
        self.assertEqual(
            second["episode"]["state"]["outfit"], first["episode"]["state"]["outfit"]
        )
        self.assertEqual(len(list(presence.events(self.c))), 2)
        self.assertEqual(presence.current(self.c)["id"], second["episode"]["id"])

    def test_outfit_location_and_activity_changes_need_a_transition(self):
        first = presence.update(self.c, self.data(), self.now)["episode"]
        for change in (
            {"outfit": ["gym"]},
            {"location": "gym"},
            {"activity": "sleeping"},
        ):
            with self.assertRaisesRegex(ValueError, "transition"):
                presence.update(
                    self.c,
                    self.data(previous_id=first["id"], **change),
                    self.now + dt.timedelta(minutes=15),
                )
        second = presence.update(
            self.c,
            self.data(
                previous_id=first["id"],
                activity="sleeping",
                transition="Put my book down and went to bed.",
                care=["brushed teeth"],
            ),
            self.now + dt.timedelta(minutes=15),
        )
        self.assertEqual(second["episode"]["state"]["care"], ["brushed teeth"])

    def test_stale_update_cannot_overwrite_newer_chat_transition(self):
        first = presence.update(self.c, self.data(), self.now)["episode"]
        presence.update(
            self.c,
            self.data(
                previous_id=first["id"],
                id="bedtime",
                activity="sleeping",
                transition="Went to bed.",
            ),
            self.now + dt.timedelta(minutes=1),
        )
        with self.assertRaisesRegex(ValueError, "State changed"):
            presence.update(
                self.c,
                self.data(previous_id=first["id"]),
                self.now + dt.timedelta(minutes=15),
            )
        self.assertEqual(presence.current(self.c)["id"], "bedtime")

    def test_wardrobe_edits_do_not_change_historical_outfits(self):
        presence.update(self.c, self.data(), self.now)
        presence.update_wardrobe(
            self.c,
            [
                {
                    "id": "pajamas",
                    "description": "repaired blue pajamas",
                    "use": "sleep",
                    "condition": "laundry",
                }
            ],
        )
        self.assertEqual(
            presence.current(self.c)["state"]["outfit"][0]["description"],
            "blue pajamas",
        )
        self.assertEqual(
            presence.show(self.c)["wardrobe"]["items"][0]["last_worn"],
            self.now.isoformat(),
        )

    def test_unknown_outfits_are_rejected_and_current_state_is_in_context(self):
        with self.assertRaisesRegex(ValueError, "wardrobe"):
            presence.update(self.c, self.data(outfit=["made-up"]), self.now)
        presence.update(self.c, self.data(), self.now)
        out = context.build(self.c, now=self.now)
        self.assertIn("blue pajamas", out)
        self.assertIn("home", out)


class EmotiveViewTests(unittest.TestCase):
    """Emotive.md is rendered from the state, so there is only one place a feeling
    lives and nothing that can disagree with it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.c = cc.Companion(hermes_root=root / "home", vault=root / "vault")
        self.now = dt.datetime(2026, 9, 9, 20, 0, tzinfo=dt.timezone.utc)
        presence.update_wardrobe(
            self.c, [{"id": "pajamas", "description": "blue pajamas", "use": "sleep"}]
        )

    def state(self, **kw):
        data = {
            "previous_id": None,
            "outfit": ["pajamas"],
            "location": "home",
            "activity": "reading",
            "mood": "restless",
            "care": [],
            "transition": "",
            "text": "Reading.",
        }
        data.update(kw)
        return data

    def test_recording_a_state_writes_the_view(self):
        presence.update(
            self.c,
            self.state(
                wants=["an early night"], private_stance="a bit hurt he never answered"
            ),
            self.now,
        )
        text = (self.c.soul_dir / "Emotive.md").read_text(encoding="utf-8")
        self.assertIn("restless", text)
        self.assertIn("an early night", text)
        self.assertIn("a bit hurt he never answered", text)

    def test_an_edit_to_the_view_does_not_survive_the_next_state(self):
        first = presence.update(self.c, self.state(), self.now)["episode"]
        (self.c.soul_dir / "Emotive.md").write_text(
            "I am actually delighted.", encoding="utf-8"
        )
        presence.update(
            self.c,
            self.state(previous_id=first["id"], mood="calmer"),
            self.now + dt.timedelta(minutes=15),
        )
        text = (self.c.soul_dir / "Emotive.md").read_text(encoding="utf-8")
        self.assertNotIn("actually delighted", text)
        self.assertIn("calmer", text)

    def test_wants_and_stance_are_optional_and_bounded(self):
        presence.update(self.c, self.state(), self.now)
        self.assertEqual(presence.current(self.c)["state"]["wants"], [])
        self.assertEqual(presence.current(self.c)["state"]["private_stance"], "")
        with self.assertRaisesRegex(ValueError, "wants"):
            presence.update(self.c, self.state(wants=["a"] * 6), self.now)

    def test_the_view_says_so_when_no_state_exists_yet(self):
        self.assertIn("nothing here to feel", presence.render_emotive(self.c, self.now))


class WardrobeFilterTests(unittest.TestCase):

    def test_blacklisted_undergarment_detection(self):
        self.assertTrue(is_blacklisted_undergarment({"description": "silk panties"}))
        self.assertTrue(
            is_blacklisted_undergarment({"id": "thong_01", "description": "lace"})
        )
        self.assertTrue(
            is_blacklisted_undergarment({"description": "black boxer briefs"})
        )
        self.assertTrue(is_blacklisted_undergarment({"category": "underwear"}))
        self.assertFalse(is_blacklisted_undergarment({"description": "blue jeans"}))
        self.assertFalse(is_blacklisted_undergarment({"description": "green tee"}))
        self.assertFalse(is_blacklisted_undergarment("running shoes"))

    def test_intimate_garment_detection(self):
        self.assertTrue(is_intimate_garment({"description": "lace bralette"}))
        self.assertTrue(is_intimate_garment({"description": "silk underwear"}))
        self.assertTrue(
            is_intimate_garment({"category": "underwear", "description": "cotton"})
        )
        self.assertTrue(
            is_intimate_garment({"intimate": True, "description": "something"})
        )
        self.assertFalse(is_intimate_garment({"description": "supportive sports bra"}))
        self.assertFalse(is_intimate_garment({"description": "sports-bra"}))
        self.assertFalse(is_intimate_garment({"description": "summer sundress"}))

    def test_tiered_wardrobe_visibility_stages(self):
        items = [
            {"id": "dress", "description": "red dress"},
            {"id": "sports_bra", "description": "high-impact sports bra"},
            {"id": "bralette", "description": "lace bralette"},
            {"id": "panties", "description": "silk panties"},
        ]
        stage1 = filter_wardrobe_items(items, stage=1)
        self.assertEqual([i["id"] for i in stage1], ["dress", "sports_bra"])
        stage2 = filter_wardrobe_items(items, stage=2)
        self.assertEqual([i["id"] for i in stage2], ["dress", "sports_bra", "bralette"])
        stage3 = filter_wardrobe_items(items, stage=3)
        self.assertEqual([i["id"] for i in stage3], ["dress", "sports_bra", "bralette"])
        stage4 = filter_wardrobe_items(items, stage=4)
        self.assertEqual(
            [i["id"] for i in stage4], ["dress", "sports_bra", "bralette", "panties"]
        )


UTC = dt.timezone.utc
DRESSED = [
    {"id": "tee", "description": "a green cotton tee"},
    {"id": "jeans", "description": "blue jeans"},
]
TOWEL = [{"id": "towel", "description": "wrapped in a bath towel"}]
NUDE = [{"id": "nude", "description": "undressed"}]


class WardrobeIsReadFromTheRecordTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        self.c = cc.Companion(
            agent="A", human="Z", profile="p", hermes_root=base / "h", vault=base / "v"
        )
        self.c.home.mkdir(parents=True)
        self.c.life.mkdir(parents=True)
        self.c.save()

    def rec(self, activity, location, outfit):
        return {
            "id": "x",
            "recorded_at": "2026-09-21T10:00:00-04:00",
            "state": {
                "activity": activity,
                "location": location,
                "outfit": outfit,
                "mood": "fine",
                "visual": {},
            },
        }

    def test_a_word_in_the_sentence_never_undresses_her(self):
        """Every one of these stripped a fully dressed record."""
        for activity, location in (
            ("brushing teeth", "the bathroom"),
            ("cleaning the bathroom", "home"),
            ("sunbathing on the deck", "the back garden"),
            ("putting on a bathrobe", "the bedroom"),
            ("shopping for a bathing suit", "the mall"),
        ):
            parts = portrait.recorded_parts(
                self.c, self.rec(activity, location, DRESSED)
            )
            with self.subTest(activity=activity):
                self.assertIn("a green cotton tee", parts["wardrobe"])

    def test_the_recorded_tokens_do_undress_her(self):
        for outfit, expected in (
            (NUDE, ""),
            ([], ""),
            (TOWEL, "wrapped in a bath towel"),
        ):
            parts = portrait.prompt_parts(
                self.c, self.rec("showering", "the bathroom", outfit)
            )
            with self.subTest(outfit=outfit):
                self.assertEqual(parts["wardrobe"], expected)

    def test_the_towel_reads_as_a_sentence(self):
        from companion_presence import wardrobe_clause

        parts = portrait.recorded_parts(
            self.c, self.rec("drying off", "the bedroom", TOWEL)
        )
        clause = wardrobe_clause(parts["wardrobe"])
        self.assertEqual(clause, "wrapped in a bath towel")
        self.assertNotIn("wearing wrapped", clause)

    def test_both_prompt_paths_agree_about_how_dressed_she_is(self):
        """Three copies of the rule meant the towel survived one path and not another,
        so which preset you used decided whether she had anything on."""
        for outfit in (DRESSED, TOWEL, NUDE, []):
            record = self.rec("stepping out of the shower", "the bathroom", outfit)
            with self.subTest(outfit=outfit):
                self.assertEqual(
                    portrait.recorded_parts(self.c, record)["wardrobe"],
                    portrait.prompt_parts(self.c, record)["wardrobe"],
                )

    def test_the_scene_is_only_the_scene(self):
        """Camera, light and clothing each have a box; the scene is where she is
        and what she is doing, and nothing else."""
        record = self.rec("drying off", "the bedroom", TOWEL)
        record["state"]["visual"] = {
            "framing": "close from the doorway",
            "lighting": "warm bulb overhead",
            "pose": "towelling her hair",
        }
        scene, _ = portrait.scene_block(self.c, record)
        self.assertIn("drying off", scene)
        self.assertIn("towelling her hair", scene)
        for elsewhere in (
            "wrapped in a bath towel",
            "close from the doorway",
            "warm bulb overhead",
        ):
            self.assertNotIn(elsewhere, scene, elsewhere)


class PublicIsAPlaceNotAWordTests(unittest.TestCase):
    """Public is a field she declares. The words of the location never decide it."""

    def test_the_declaration_decides_whatever_the_words_say(self):
        for location in (
            "the Home Depot",
            "a public bathroom at the mall",
            "my home office",
            "the bedroom",
            "the office",
        ):
            with self.subTest(location=location):
                self.assertTrue(
                    presence.in_public({"location": location, "setting": "public"})
                )
                self.assertFalse(
                    presence.in_public({"location": location, "setting": "private"})
                )
                self.assertFalse(presence.in_public({"location": location}))

    def test_words_only_flag_an_obvious_contradiction(self):
        for location in ("the park", "the mall", "a cafe", "the train"):
            with self.subTest(location=location):
                self.assertTrue(presence.reads_public(location))
        for location in (
            "stuck in the carpool lane",
            "a changing room at the mall",
            "the bedroom",
        ):
            with self.subTest(location=location):
                self.assertFalse(presence.reads_public(location))

    def test_changing_in_private_is_allowed_and_in_public_is_not(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = pathlib.Path(tmp.name)
        c = cc.Companion(
            agent="A", human="Z", profile="p", hermes_root=base / "h", vault=base / "v"
        )
        c.home.mkdir(parents=True)
        c.life.mkdir(parents=True)
        c.save()
        presence.update_wardrobe(
            c,
            [
                {
                    "id": "bra",
                    "description": "plain bra",
                    "use": "underwear",
                    "category": "underwear",
                }
            ],
        )
        now = dt.datetime(2026, 9, 21, 10, tzinfo=UTC)
        base_row = {"previous_id": None, "outfit": ["bra"], "mood": "fine", "text": "x"}
        presence.update(
            c,
            {
                **base_row,
                "location": "the bedroom",
                "activity": "texting friends",
                "setting": "private",
            },
            now,
        )
        previous = presence.current(c)
        self.assertEqual(previous["state"]["setting"], "private")
        moved = {
            **base_row,
            "previous_id": previous["id"],
            "location": "the library",
            "activity": "reading",
            "transition": "Went out.",
        }
        with self.assertRaisesRegex(ValueError, "private setting"):
            presence.update(
                c, {**moved, "setting": "public"}, now + dt.timedelta(minutes=30)
            )
        with self.assertRaisesRegex(ValueError, "say where you are"):
            presence.update(c, moved, now + dt.timedelta(minutes=30))
        with self.assertRaisesRegex(ValueError, "reads as a public place"):
            presence.update(
                c, {**moved, "setting": "private"}, now + dt.timedelta(minutes=30)
            )


BUDGET_WINDOWS = [2048, 4096, 8192, 16384, 32768, 65536, 131072, 200192, 272000, 900000]


class ProfileTests(unittest.TestCase):

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_root_and_profile_homes_resolve_differently(self):
        root = cc.Companion(hermes_root=self.tmp / ".hermes")
        rowan = cc.Companion(profile="rowan", hermes_root=self.tmp / ".hermes")
        self.assertTrue(root.is_root)
        self.assertFalse(rowan.is_root)
        self.assertEqual(root.home, self.tmp / ".hermes")
        self.assertEqual(rowan.home, self.tmp / ".hermes/profiles/rowan")

    def test_profiles_get_isolated_data_subtrees(self):
        v = self.tmp / "vault"
        root = cc.Companion(vault=v)
        rowan = cc.Companion(profile="rowan", vault=v)
        self.assertEqual(root.data, v)
        self.assertEqual(rowan.data, v / "agents/rowan")
        self.assertNotEqual(root.life, rowan.life)
        self.assertFalse(str(rowan.life).startswith(str(root.life) + "/"))

    def test_config_inside_a_profile_dir_pins_that_profile(self):
        home = self.tmp / ".hermes/profiles/nova"
        home.mkdir(parents=True)
        (home / cc.CONFIG_NAME).write_text(json.dumps({"agent": "Nova"}))
        c = cc.load(home)
        self.assertEqual(c.profile, "nova")
        self.assertEqual(c.home, home)

    def test_missing_config_yields_safe_defaults(self):
        c = cc.load(self.tmp / "nothing-here")
        self.assertEqual(c.context_tokens, cc.DEFAULT_CONTEXT_TOKENS)
        self.assertEqual(c.image_mode, "none")

    def test_corrupt_config_fails_instead_of_using_unrelated_defaults(self):
        home = self.tmp / "h"
        home.mkdir()
        (home / cc.CONFIG_NAME).write_text("{not json")
        with self.assertRaisesRegex(ValueError, "Invalid companion configuration"):
            cc.load(home)

    def test_save_load_roundtrip(self):
        home = self.tmp / ".hermes"
        c = cc.Companion(
            agent="Nova",
            human="Alex",
            context_tokens=65536,
            hermes_root=home,
            vault=self.tmp / "vault",
            image_mode="codex",
        )
        c.save()
        back = cc.load(home)
        self.assertEqual(
            (back.agent, back.human, back.context_tokens, back.image_mode),
            ("Nova", "Alex", 65536, "codex"),
        )

    def test_human_dir_is_slugged_safely(self):
        for name, want in (
            ("Alex", "alex"),
            ("Mary Jane", "mary-jane"),
            ("", "human"),
            ("../etc", "etc"),
            ("..", "human"),
            ("/", "human"),
        ):
            c = cc.Companion(human=name, vault=self.tmp)
            self.assertEqual(c.human_dir.name, want)
            self.assertTrue(str(c.human_dir).startswith(str(self.tmp)))

    def test_pronouns(self):
        self.assertEqual(cc.Companion(pronoun_set="he").subj(), "he")
        self.assertEqual(cc.Companion(pronoun_set="she").poss(), "her")
        self.assertEqual(cc.Companion(pronoun_set="they").subj(), "they")
        self.assertEqual(cc.Companion(pronoun_set="they").obj(), "them")
        self.assertEqual(cc.Companion(pronoun_set="they").poss(), "their")
        self.assertEqual(cc.Companion(pronoun_set="they").refl(), "themselves")
        with self.assertRaisesRegex(ValueError, "Invalid pronouns"):
            cc.Companion(pronoun_set="nonsense")
        with self.assertRaisesRegex(ValueError, "Invalid pronouns"):
            cc.Companion(pronoun_set="it")
        self.assertEqual(set(cc.PRONOUNS), {"he", "she", "they"})
        self.assertEqual(cc.Companion().pronoun_set, "she")


class HomeInvariantTests(unittest.TestCase):
    """load(X).home must equal X. Violating this once wrote into a real install."""

    def test_arbitrary_home_is_never_replaced_by_a_default(self):
        for rel in ("sandbox/.hermes", "a/b/c/.hermes", "weird-name", ".hermes"):
            tmp = pathlib.Path(tempfile.mkdtemp()) / rel
            c = cc.load(tmp)
            self.assertEqual(c.home, tmp)
            self.assertEqual(c.hermes_root, tmp)
            self.assertEqual(c.profile, "")
            self.assertNotEqual(c.home, pathlib.Path.home() / ".hermes")

    def test_profile_home_round_trips(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / ".hermes/profiles/nova"
        c = cc.load(home)
        self.assertEqual(c.home, home)
        self.assertEqual(c.profile, "nova")
        self.assertEqual(c.hermes_root, tmp / ".hermes")

    def test_a_stale_stored_root_cannot_redirect_writes(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / ".hermes"
        home.mkdir(parents=True)
        (home / cc.CONFIG_NAME).write_text(
            json.dumps(
                {
                    "agent": "Nova",
                    "hermes_root": "/somewhere/else",
                    "vault": str(tmp / "vault"),
                }
            )
        )
        c = cc.load(home)
        self.assertEqual(c.home, home)
        self.assertEqual(c.agent, "Nova")
        self.assertEqual(c.vault, tmp / "vault")


class PresenceApiTests(WorkspaceFixture):

    def test_hosted_origin_still_requires_token(self):
        with patch.dict(
            os.environ, {"COMPANION_PUBLIC_ORIGIN": "https://companion.example.com"}
        ):
            app = build(
                self.root, token="secret", state_dir=Path(self.tmp.name) / "hosted"
            )
        client = TestClient(app)
        path = "/api/settings?profile=nova"
        self.assertEqual(
            client.post(
                path, headers={"origin": "https://companion.example.com"}, json={}
            ).status_code,
            401,
        )
        headers = {
            "origin": "https://companion.example.com",
            "x-companion-token": "secret",
        }
        self.assertEqual(
            client.post(path, headers=headers, json={"location": "home"}).status_code,
            200,
        )
        headers["origin"] = "https://untrusted.example"
        self.assertEqual(client.post(path, headers=headers, json={}).status_code, 403)

    def test_profile_traversal_and_foreign_installations_refused(self):
        self.assertEqual(self.get("/api/overview", "../../outside").status_code, 400)
        response = self.client.get(
            "/api/profiles?installation=unknown", headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_origin_writes_and_private_media(self):
        response = self.client.post(
            "/api/settings?profile=nova",
            json={"location": "x"},
            headers={**self.headers, "origin": "https://other.test"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get("/media/portrait?profile=nova").status_code, 401
        )
        self.assertEqual(
            self.client.get("/media/timeline/missing.png").status_code, 401
        )
        self.assertEqual(self.get("/api/overview").headers["cache-control"], "no-store")


class PresenceSettingsTests(AppFixture):

    def test_it_refuses_to_change_anything_that_is_not_a_setting(self):
        for payload in (
            {"agent": "Someone Else"},
            {"birthdate": "1990-01-01"},
            {"agent_type": "worker"},
            {"context_tokens": 4096},
        ):
            r = self.client.post("/api/settings", json=payload)
            self.assertEqual(r.status_code, 400, payload)
            self.assertIn("not settable from here", r.json()["detail"])

    def test_a_setting_gets_the_same_validation_the_cli_gets(self):
        r = self.client.post("/api/settings", json={"outreach_per_day": 9999})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(cc.load(self.c.home).outreach_per_day, self.c.outreach_per_day)

    def test_a_valid_setting_lands_on_disk(self):
        r = self.client.post(
            "/api/settings", json={"quiet_start": "22:30", "location": "Lisbon"}
        )
        self.assertEqual(r.status_code, 200)
        again = cc.load(self.c.home)
        self.assertEqual(again.quiet_start, "22:30")
        self.assertEqual(again.location, "Lisbon")

    def test_network_and_pin_auth(self):
        r = self.client.get("/api/network")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("localhost_url", d)
        self.assertIn("lan_urls", d)
        self.assertFalse(d["remote_pin_configured"])
        s_res = self.client.post("/api/settings", json={"remote_pin": "5678"})
        self.assertEqual(s_res.status_code, 200)
        self.assertEqual(cc.load(self.c.home).remote_pin, "5678")
        r2 = self.client.get("/api/network")
        self.assertTrue(r2.json()["remote_pin_configured"])
        bad_auth = self.client.post("/api/auth/pin", json={"pin": "0000"})
        self.assertEqual(bad_auth.status_code, 403)
        good_auth = self.client.post("/api/auth/pin", json={"pin": "5678"})
        self.assertEqual(good_auth.status_code, 200)
        self.assertTrue(good_auth.json()["ok"])
        self.assertIn("companion_pin_session", good_auth.cookies)
        remote_client = TestClient(self.client.app, client=("203.0.113.9", 50000))
        r_remote_locked = remote_client.get("/api/overview")
        self.assertEqual(r_remote_locked.status_code, 401)
        self.assertTrue(r_remote_locked.json().get("pin_required"))
        r_remote_authed = remote_client.get("/api/overview", cookies=good_auth.cookies)
        self.assertEqual(r_remote_authed.status_code, 200)
        clear_res = self.client.post("/api/settings", json={"remote_pin": ""})
        self.assertEqual(clear_res.status_code, 200)
        self.assertEqual(cc.load(self.c.home).remote_pin, "")


def test_process_existence_distinguishes_missing_and_unavailable():
    with (
        patch.object(platform.sys, "platform", "darwin"),
        patch.object(platform.os, "kill") as kill,
    ):
        assert platform.process_exists(123) is True
        kill.assert_called_once_with(123, 0)
        kill.side_effect = ProcessLookupError()
        assert platform.process_exists(123) is False
        kill.side_effect = PermissionError()
        assert platform.process_exists(123) is None
        kill.reset_mock()
        for invalid in (None, "123", -1, 0, True):
            assert platform.process_exists(invalid) is False
        kill.assert_not_called()


def test_windows_process_query_closes_handles_and_never_sends_a_signal():
    kernel = SimpleNamespace(
        OpenProcess=MagicMock(return_value=42),
        GetExitCodeProcess=MagicMock(),
        CloseHandle=MagicMock(),
    )

    def exit_code(handle, result):
        assert handle == 42
        result._obj.value = 259
        return True

    kernel.GetExitCodeProcess.side_effect = exit_code
    with (
        patch.object(platform.sys, "platform", "win32"),
        patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
        patch.object(ctypes, "get_last_error", return_value=87, create=True),
        patch.object(platform.os, "kill") as kill,
    ):
        assert platform.process_exists(123) is True
        kernel.CloseHandle.assert_called_once_with(42)
        kernel.GetExitCodeProcess.side_effect = None
        kernel.GetExitCodeProcess.return_value = False
        assert platform.process_exists(123) is None
        assert kernel.CloseHandle.call_count == 2
        kernel.OpenProcess.return_value = None
        assert platform.process_exists(123) is False
        kill.assert_not_called()


def test_linux_identity_is_optional_and_recycled_pids_are_rejected():
    stat = "123 (a process with spaces) " + " ".join(["S"] + ["0"] * 18 + ["456"])
    with (
        patch.object(platform.sys, "platform", "linux"),
        patch.object(platform, "process_exists", return_value=True),
        patch.object(Path, "read_text", return_value=stat) as read,
    ):
        assert platform.process_matches(123, 456) is True
        assert platform.process_matches(123, 457) is False
        assert platform.process_matches(123, None) is None
        read.return_value = stat.replace(") S", ") Z")
        assert platform.process_matches(123, 456) is False
        read.side_effect = PermissionError()
        assert platform.process_matches(123, 456) is None


def test_non_linux_identity_does_not_read_process_files():
    with (
        patch.object(platform.sys, "platform", "darwin"),
        patch.object(platform, "process_exists", return_value=True) as exists,
        patch.object(Path, "read_text") as read,
    ):
        assert platform.process_matches(123, 456) is None
        exists.return_value = False
        assert platform.process_matches(123, 456) is False
        read.assert_not_called()


def test_unix_memory_uses_standard_system_configuration():
    values = {"SC_PAGE_SIZE": 4096, "SC_PHYS_PAGES": 2097152, "SC_AVPHYS_PAGES": 524288}
    with (
        patch.object(platform.sys, "platform", "linux"),
        patch.object(
            platform.os, "sysconf", side_effect=values.__getitem__, create=True
        ),
        patch.object(Path, "read_text") as read,
    ):
        memory = platform.host_memory()
        assert memory["total_mb"] == 8192
        assert memory["available_mb"] == 2048
        assert memory["total_known"] and memory["available_known"]
        read.assert_not_called()


def test_macos_memory_reads_real_page_counts_instead_of_assuming_half():
    replies = [
        SimpleNamespace(returncode=0, stdout=str(8 * 1024**3)),
        SimpleNamespace(
            returncode=0,
            stdout="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 65536.\nPages inactive: 32768.\nPages speculative: 32768.\n",
        ),
    ]
    with (
        patch.object(platform.sys, "platform", "darwin"),
        patch.object(platform.os, "sysconf", side_effect=ValueError(), create=True),
        patch.object(platform.subprocess, "run", side_effect=replies) as run,
    ):
        memory = platform.host_memory()
        assert memory["total_mb"] == 8192
        assert memory["available_mb"] == 2048
        assert all((call.kwargs["timeout"] == 1 for call in run.call_args_list))


def test_windows_memory_uses_the_native_measurement():

    def fill(result):
        status = result._obj
        assert status.length == 64
        status.total = 16 * 1024**3
        status.available = 3 * 1024**3
        return True

    kernel = SimpleNamespace(GlobalMemoryStatusEx=MagicMock(side_effect=fill))
    with (
        patch.object(platform.sys, "platform", "win32"),
        patch.object(ctypes, "WinDLL", return_value=kernel, create=True),
    ):
        assert platform.host_memory()["total_mb"] == 16384
        assert platform.host_memory()["available_mb"] == 3072


def test_failed_memory_probes_stay_unknown_in_the_model_api():
    with (
        patch.object(platform.sys, "platform", "linux"),
        patch.object(platform.os, "sysconf", side_effect=OSError(), create=True),
        patch.object(local_models, "is_mobile", return_value=False),
    ):
        memory = local_models.get_host_memory()
        assert memory["total_mb"] == memory["available_mb"] == 0
        assert not memory["total_known"] and (not memory["available_known"])


def test_network_probe_closes_its_socket_when_offline():
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.connect.side_effect = OSError("no route")
    with (
        patch.object(platform.socket, "getaddrinfo", side_effect=OSError()),
        patch.object(platform.socket, "socket", return_value=probe),
    ):
        assert platform.lan_addresses() == []
        probe.__exit__.assert_called_once()


def test_network_addresses_are_deduplicated_and_loopback_is_excluded():
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.getsockname.return_value = ("192.168.1.4", 123)
    addresses = [
        (None, None, None, None, (address, 0))
        for address in ("127.0.0.1", "0.0.0.0", "192.168.1.4", "10.0.0.2")
    ]
    with (
        patch.object(platform.socket, "getaddrinfo", return_value=addresses),
        patch.object(platform.socket, "socket", return_value=probe),
    ):
        assert platform.lan_addresses() == ["10.0.0.2", "192.168.1.4"]


def test_console_close_falls_back_when_process_groups_are_unavailable():
    console = Console.__new__(Console)
    console.finished = False
    console.error = ""
    console.process = MagicMock()
    console.process.poll.return_value = None
    with (
        patch.object(os, "name", "posix"),
        patch.object(os, "killpg", side_effect=OSError(), create=True),
    ):
        console.close()
    console.process.terminate.assert_called_once()
    console.process.wait.assert_called_once_with(timeout=1)
    assert console.finished


def test_console_close_forces_stubborn_children_with_bounded_waits():
    console = Console.__new__(Console)
    console.finished = False
    console.error = ""
    console.process = MagicMock()
    console.process.poll.return_value = None
    console.process.wait.side_effect = subprocess.TimeoutExpired("hermes", 1)
    with (
        patch.object(os, "name", "posix"),
        patch.object(os, "killpg", create=True) as group,
        patch("kit.app.terminal.signal.SIGKILL", 9, create=True),
    ):
        console.close()
    assert group.call_count == 2
    assert console.process.wait.call_count == 2
    assert all(
        (call.kwargs == {"timeout": 1} for call in console.process.wait.call_args_list)
    )
    assert console.finished and "did not exit" in console.error
    console.finished = False
    with (
        patch.object(os, "name", "nt"),
        patch.object(os, "killpg", create=True) as group,
    ):
        console.close()
        group.assert_not_called()
    console.process.terminate.assert_called_once_with(force=True)


def test_bootstrap_lock_does_not_grow_on_repeated_launch(tmp_path):
    with patch.object(launch, "ROOT", tmp_path):
        for _ in range(3):
            with launch.setup_lock():
                pass
    assert (tmp_path / ".bootstrap.lock").read_bytes() == b"0"


def test_update_lock_releases_and_does_not_grow(tmp_path):
    for _ in range(3):
        with update_release.runtime_lock(tmp_path):
            pass
    assert (tmp_path / ".runtime.lock").read_bytes() == b"0"


def test_bootstrap_forwards_unicode_and_spaced_arguments(tmp_path):
    import os

    requirements = b"\n"
    (tmp_path / "requirements.txt").write_bytes(requirements)
    python = (
        tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / ".venv/.tamanitomo-requirements").write_text(
        hashlib.sha256(requirements).hexdigest() + "\n"
    )
    arguments = ["app", "--home", str(tmp_path / "My companion 雪")]
    target = "subprocess.call" if os.name == "nt" else "os.execv"
    with (
        patch.object(launch, "ROOT", tmp_path),
        patch("update_release.apply_pending"),
        patch.object(launch.subprocess, "run") as install,
        patch("launch." + target) as run,
    ):
        launch.bootstrap(arguments)
    install.assert_not_called()
    command = run.call_args.args[0] if os.name == "nt" else run.call_args.args[1]
    assert command == [str(python), str(tmp_path / "bin/tamanitomo"), *arguments]


def test_ipv6_launcher_reuses_and_opens_the_ipv6_loopback_url(tmp_path):
    import io
    from kit.cli import app as launcher

    state = tmp_path / "state"
    state.mkdir()
    companion = SimpleNamespace(hermes_root=tmp_path / "hermes", profile="")
    (state / "workspace-server.json").write_text(
        json.dumps({"host": "::", "port": 54321, "root": str(companion.hermes_root)})
    )
    reply = io.BytesIO(
        json.dumps({"app": "tamanitomo", "root": str(companion.hermes_root)}).encode()
    )
    args = SimpleNamespace(host="::", port=8770, no_open=False, token="synthetic")
    with (
        patch.object(launcher, "resolve", return_value=companion),
        patch("kit.app.runtime.app_directory", return_value=state),
        patch.object(launcher.urllib.request, "urlopen", return_value=reply) as request,
        patch.object(launcher.webbrowser, "open") as open_browser,
        patch.object(launcher, "print"),
        patch("kit.app.server.build") as build,
    ):
        assert launcher.cmd_app(args) == 0
    assert request.call_args.args[0].full_url == "http://[::1]:54321/api/instance"
    assert open_browser.call_args.args[0].startswith("http://[::1]:54321/?")
    build.assert_not_called()


import companion_preread as preread
from zoneinfo import ZoneInfo


class AwakeFingerprintProseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.c = cc.Companion(
            hermes_root=folder / "home",
            vault=folder / "vault",
            timezone="America/New_York",
            quiet_start="23:00",
            quiet_end="08:00",
        )
        presence.update_wardrobe(
            self.c, [{"id": "tee", "description": "green tee", "use": "everyday"}]
        )
        self.now = dt.datetime(2026, 9, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        presence.update(
            self.c,
            {
                "previous_id": None,
                "outfit": ["tee"],
                "location": "kitchen",
                "activity": "eating lunch",
                "mood": "content",
                "text": "Lunch.",
                "activity_change": "transition",
            },
            self.now,
        )

    def _reword(
        self,
        minutes,
        activity,
        mood="content",
        activity_change="continue",
        location="kitchen",
    ):
        previous = presence.current(self.c)
        moment = self.now + dt.timedelta(minutes=minutes)
        presence.update(
            self.c,
            {
                "previous_id": previous["id"],
                "outfit": ["tee"],
                "location": location,
                "activity": activity,
                "mood": mood,
                "text": "Still there.",
                "transition": "Still there.",
                "activity_change": activity_change,
            },
            moment,
        )
        return moment

    def test_rewording_the_same_awake_activity_does_not_open_the_gate(self):
        first = preread.fingerprint(self.c, self.now)
        seen = {first}
        for minutes, (phrasing, mood) in enumerate(
            (
                ("finishing the coffee at the kitchen table", "content"),
                ("coffee, plate cleared", "content, a little sleepy"),
                ("lingering over the last of it", "settled"),
            ),
            start=1,
        ):
            moment = self._reword(minutes * 15, phrasing, mood=mood)
            seen.add(preread.fingerprint(self.c, moment))
        self.assertEqual(
            len(seen), 1, "a reworded awake scene opened the pulse/autonomy gate"
        )

    def test_a_declared_transition_still_opens_the_gate(self):
        """The fix must not become a trap the agent can never leave (ISS-04B)."""
        first = preread.fingerprint(self.c, self.now)
        moment = self._reword(
            15,
            "washing up at the sink",
            activity_change="transition",
            location="kitchen",
        )
        self.assertNotEqual(
            preread.fingerprint(self.c, moment),
            first,
            "a genuine transition must still change the fingerprint",
        )

    def test_confirmation_state_still_opens_the_gate(self):
        """`confirmed` is a code-owned flag (carried-forward vs. authored), not prose."""
        first = preread.fingerprint(self.c, self.now)
        later = self.now + dt.timedelta(minutes=25)
        result = presence.advance(
            self.c, now=later
        )  # no model confirmed it in time -> confirmed=False
        self.assertTrue(result.get("written"), result)
        self.assertFalse(presence.current(self.c)["state"].get("confirmed", True))
        self.assertNotEqual(
            preread.fingerprint(self.c, later),
            first,
            "an unconfirmed (carried-forward) scene must be distinguishable from a confirmed one",
        )
