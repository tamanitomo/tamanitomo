"""Shared time is scoped to a companion and never invents playback or memories."""

from unittest.mock import patch

import companion_context as context
import companion_notes as notes
import companion_preread as preread
import companion_viewing as viewing

from tests.support import WorkspaceFixture
from tests.test_chat_dock import run_browser_contract


class SharedSessionsApi(WorkspaceFixture):
    def test_manual_session_reaches_chat_without_sensors_and_keeps_its_meaning(self):
        before = preread.fingerprint(self.c)
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
            started = self.post(
                "/api/viewing/sessions", {"title": "The detective", "comments": "quiet"}
            )
            self.assertEqual(started.status_code, 200, started.text)
            session = started.json()["sessions"][0]
            self.assertEqual(session["mode"], "manual")
            self.assertNotEqual(before, preread.fingerprint(self.c))
            prefix = "/api/viewing/sessions/" + session["id"]
            paused = self.post(prefix + "/pause").json()["sessions"][0]
            self.assertEqual(paused["state"], "paused")
            self.assertEqual(self.post(prefix + "/resume").status_code, 200)
            progress = self.post(
                prefix + "/report",
                {"text": "We just met the detective.", "position_min": 12},
            )
            self.assertEqual(progress.status_code, 200, progress.text)
            built = context.build(
                self.c, {"extra": {"user_message": "What do you think?"}}
            )
            self.assertIn("The detective", built)
            self.assertIn("Quiet company", built)
            self.assertIn("We just met the detective", built)
            kept = self.post(
                prefix + "/moment",
                {"text": "We both guessed the toaster was the culprit."},
            )
            self.assertEqual(kept.status_code, 200, kept.text)
            records = notes.moments(self.c)
            self.assertEqual(len(records), 1)
            self.assertIn("toaster", records[0]["text"])
            self.assertIn("Shared session", records[0]["evidence"])
            self.assertEqual(self.post(prefix + "/stop").json()["sessions"], [])
            self.assertIn("does not mean", viewing.session_context(self.c, limit=2000))
            self.assertEqual(
                self.get("/api/viewing/sessions", profile="rowan").json()["moments"], []
            )
            self.assertEqual(
                self.get("/api/music/suggestions").json(),
                {"suggestions": [], "enabled": "music" in (self.c.sensors or [])},
            )

    def test_invalid_or_other_profile_session_cannot_be_changed(self):
        data = self.post("/api/viewing/sessions", {"title": "Our film"}).json()
        ident = data["sessions"][0]["id"]
        self.assertGreaterEqual(
            self.post(
                f"/api/viewing/sessions/{ident}/pause", profile="rowan"
            ).status_code,
            400,
        )
        self.assertGreaterEqual(
            self.post(
                "/api/viewing/sessions", {"title": "Film", "hours": True}
            ).status_code,
            400,
        )
        self.assertGreaterEqual(
            self.post(
                f"/api/viewing/sessions/{ident}/moment", {"text": ""}
            ).status_code,
            400,
        )
        self.assertEqual(viewing.moments(self.c), [])


def test_shared_time_and_album_cards_escape_content_and_only_link_spotify():
    run_browser_contract(r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
global.esc=x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
vm.runInThisContext(fs.readFileSync('kit/app/static/together.js','utf8'));
let html=sharedTimeHtml({sessions:[{id:'a',title:'<img onerror=x>',state:'paused',mode:'manual',comments:'quiet'}]});
assert.ok(html.includes('Resume together'));assert.ok(html.includes('Quiet company'));
assert.ok(!html.includes('<img'));assert.ok(html.includes('data-shared-form="moment"'));
html=musicSuggestionsHtml([{note:'<script>x</script>',album:{name:'Album',url:'javascript:alert(1)',artists:[]}}]);
assert.ok(!html.includes('javascript:'));assert.ok(!html.includes('<script>'));
html=musicSuggestionsHtml([{note:'Our evening',album:{name:'Album',url:'https://open.spotify.com/album/1234567890123456789012',artists:[{name:'Artist'}]}}]);
assert.ok(html.includes('noopener noreferrer'));assert.ok(html.includes('Our evening'));
html=musicSuggestionsHtml([],false);
assert.ok(html.includes('Music is switched off'));assert.ok(!html.includes('Albums chosen for you'));
html=musicSuggestionsHtml([{note:'Kept',album:{name:'Album',artists:[]}}],false);
assert.ok(html.includes('Music is switched off'));assert.ok(html.includes('Kept'));
""")
