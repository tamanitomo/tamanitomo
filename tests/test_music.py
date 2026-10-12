"""Read-only Spotify discovery and evidence-backed suggestions in isolated profiles."""

import datetime as dt
import io
import json
import urllib.error
import urllib.parse
from unittest.mock import patch

import pytest

import companion_config as cc
import companion_music as music
import companion_notes as notes
import companion_outbox as outbox

NOW = dt.datetime(2026, 10, 12, 15, tzinfo=dt.timezone.utc)
ARTIST_ID = "a" * 22
ALBUM_ID = "b" * 22
ARTIST = {"id": ARTIST_ID, "name": "Example Artist"}
ALBUM = {
    "id": ALBUM_ID,
    "name": "An Example Album",
    "artists": [ARTIST],
    "release_date": "2024-03",
    "release_date_precision": "month",
    "album_type": "album",
}


@pytest.fixture
def companion(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Alex",
        hermes_root=tmp_path / "home",
        vault=tmp_path / "vault",
        timezone="UTC",
        sensors=["music"],
    )
    c.life.mkdir(parents=True)
    return c


@pytest.fixture
def connected():
    with (
        patch.object(
            music.sensors, "_spotify_state", return_value={"client_id": "test"}
        ),
        patch.object(music.sensors, "_spotify_token", return_value="secret-test-token"),
        patch.object(music.urllib.request, "urlopen") as get,
    ):
        yield get


def responds(get, data):
    get.return_value.__enter__.return_value.read.return_value = json.dumps(
        data
    ).encode()


def http_error(code, headers=None):
    return urllib.error.HTTPError(
        "https://api.spotify.com/test", code, "test", headers or {}, io.BytesIO()
    )


def request(get):
    return get.call_args.args[0]


def suggestion(c, get, **overrides):
    responds(get, ALBUM)
    return music.suggest(
        c,
        {
            "album_id": ALBUM_ID,
            "note": "For the rainy evening we were planning.",
            "evidence": "Alex said: let's have a quiet evening on Friday.",
            "source": "session:test message:42",
            **overrides,
        },
        NOW,
    )


def test_top_uses_affinity_scope_time_range_and_link_not_claimed_favorites(
    companion, connected
):
    responds(connected, {"items": [ARTIST], "next": "another-page"})
    result = music.top(companion, 3, "short_term", NOW)
    req = request(connected)
    assert req.method == "GET"
    assert urllib.parse.urlsplit(req.full_url).path == "/v1/me/top/artists"
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query) == {
        "limit": ["3"],
        "time_range": ["short_term"],
    }
    assert result["items"][0]["url"] == f"https://open.spotify.com/artist/{ARTIST_ID}"
    assert result["basis"] == "spotify_calculated_affinity_not_stated_favorite"
    assert result["has_more"]
    assert result["provenance"]["retrieved_at"] == NOW.isoformat()
    assert "secret-test-token" not in json.dumps(result)


def test_missing_connection_does_not_make_network_calls(companion):
    with (
        patch.object(music.sensors, "_spotify_state", return_value=None),
        patch.object(music.urllib.request, "urlopen") as get,
    ):
        result = music.top(companion, now=NOW)
    assert result["status"] == "not_connected"
    get.assert_not_called()


def test_missing_top_scope_is_explained_without_inventing_empty_tastes(
    companion, connected
):
    connected.side_effect = http_error(403)
    result = music.top(companion, now=NOW)
    assert not result["ok"]
    assert result["status"] == "forbidden"
    assert result["required_scope"] == "user-top-read"
    assert "items" not in result


@pytest.mark.parametrize(
    "code,status",
    [(401, "authorization_expired"), (429, "rate_limited"), (500, "unavailable")],
)
def test_api_failure_does_not_retry_or_expose_credentials(
    companion, connected, code, status
):
    connected.side_effect = http_error(code, {"Retry-After": "120"})
    result = music.top(companion, now=NOW)
    assert result["status"] == status
    if code == 429:
        assert result["retry_after_seconds"] == 120
    assert connected.call_count == 1
    assert "secret-test-token" not in json.dumps(result)


def test_recent_keeps_play_timestamp_and_does_not_infer_favorite(companion, connected):
    responds(
        connected,
        {
            "items": [
                {"played_at": "2026-10-12T12:00:00Z", "track": {"artists": [ARTIST]}},
                {"played_at": "2026-10-11T12:00:00Z", "track": {"artists": [ARTIST]}},
            ]
        },
    )
    result = music.recent(companion, now=NOW)
    assert len(result["items"]) == 1
    assert result["items"][0]["played_at"] == "2026-10-12T12:00:00Z"
    assert result["basis"] == "recent_listening_not_stated_favorite"


def test_catalog_search_handles_quotes_and_current_ten_result_limit(
    companion, connected
):
    responds(connected, {"albums": {"items": [ALBUM]}})
    result = music.search(
        companion, 'artist:"Example Artist" year:2024', "album", 10, NOW
    )
    assert urllib.parse.parse_qs(
        urllib.parse.urlsplit(request(connected).full_url).query
    )["q"] == ['artist:"Example Artist" year:2024']
    assert result["items"][0]["release_date_precision"] == "month"
    with pytest.raises(ValueError, match="between 1 and 10"):
        music.search(companion, "Example", limit=11)


def test_artist_catalog_keeps_albums_and_source_links(companion, connected):
    responds(connected, {"items": [ALBUM], "next": "more"})
    result = music.albums(companion, ARTIST_ID, now=NOW)
    req = request(connected)
    assert f"/artists/{ARTIST_ID}/albums" in req.full_url
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)[
        "include_groups"
    ] == ["album"]
    assert result["items"][0]["url"] == f"https://open.spotify.com/album/{ALBUM_ID}"
    assert result["has_more"]
    with pytest.raises(ValueError, match="between 1 and 10"):
        music.albums(companion, ARTIST_ID, limit=11)


def test_discovery_falls_back_only_with_labeled_listening_evidence(
    companion, connected
):
    def response(req, timeout):
        if "/me/top/" in req.full_url:
            raise http_error(403)
        if "recently-played" in req.full_url:
            data = {
                "items": [
                    {
                        "track": {"artists": [ARTIST]},
                        "played_at": "2026-10-12T12:00:00Z",
                    }
                ]
            }
        else:
            data = {"items": [ALBUM]}
        return io.BytesIO(json.dumps(data).encode())

    connected.side_effect = response
    result = music.discover(companion, now=NOW)
    candidate = result["candidates"][0]
    assert candidate["basis"] == "recent_listening_not_stated_favorite"
    assert candidate["artist_provenance"]["endpoint"] == "/me/player/recently-played"
    assert candidate["album_provenance"]["endpoint"] == f"/artists/{ARTIST_ID}/albums"
    assert result["warnings"][0]["required_scope"] == "user-top-read"
    assert connected.call_count == 3
    assert not outbox.fold(companion)


def test_discovery_rate_limit_does_not_fall_back_and_burn_more_calls(
    companion, connected
):
    connected.side_effect = http_error(429)
    result = music.discover(companion, now=NOW)
    assert result["status"] == "rate_limited"
    assert connected.call_count == 1


def test_malformed_and_oversized_responses_are_not_empty_preferences(
    companion, connected
):
    responds(connected, {"items": {"bad": "shape"}})
    assert music.top(companion, now=NOW)["status"] == "invalid_response"
    connected.return_value.__enter__.return_value.read.return_value = b"x" * (
        music.MAX_BYTES + 1
    )
    assert music.top(companion, now=NOW)["status"] == "invalid_response"


def test_save_requires_evidence_verifies_album_and_never_claims_delivery(
    companion, connected
):
    with pytest.raises(ValueError, match="evidence"):
        suggestion(companion, connected, evidence="")
    connected.assert_not_called()
    saved = suggestion(companion, connected)
    assert saved["written"]
    row = saved["entry"]
    assert row["basis"]["source"] == "session:test message:42"
    assert row["album"]["url"] == f"https://open.spotify.com/album/{ALBUM_ID}"
    assert row["catalog_provenance"]["endpoint"] == f"/albums/{ALBUM_ID}"
    assert music.history(companion)[0]["delivery_status"] == "not_queued"
    assert not outbox.fold(companion)
    assert not suggestion(companion, connected)["written"]
    assert connected.call_count == 1


def test_existing_shared_moment_can_explain_album_without_invented_history(
    companion, connected
):
    moment = notes.add_moment(
        companion,
        {
            "moment": "ritual",
            "text": "Our rainy Friday film evenings",
            "evidence": "session:test message:15",
        },
        NOW,
    )["entry"]
    saved = suggestion(companion, connected, moment_id=moment["id"])
    assert saved["entry"]["basis"]["text"] == moment["text"]
    assert saved["entry"]["basis"]["kind"] == "relationship_moment"
    with pytest.raises(ValueError, match="active relationship moment"):
        suggestion(companion, connected, moment_id="unknown")


def test_failed_catalog_lookup_never_saves_unverified_album(companion, connected):
    connected.side_effect = http_error(404)
    result = suggestion(companion, connected)
    assert not result["ok"]
    assert not music.history(companion)


def test_unusable_album_metadata_is_not_saved_as_verified(companion, connected):
    responds(connected, {**ALBUM, "artists": None})
    result = music.suggest(
        companion,
        {
            "album_id": ALBUM_ID,
            "note": "A possible Friday pick.",
            "evidence": "Friday plan",
            "source": "session:test message:42",
        },
        NOW,
    )
    assert result["status"] == "invalid_response"
    assert not music.history(companion)


def test_saved_suggestions_render_note_link_and_truthful_delivery_status_without_network(
    companion, connected
):
    suggestion(companion, connected)
    connected.reset_mock()
    text = music.render(companion)
    assert "For the rainy evening we were planning." in text
    assert f"https://open.spotify.com/album/{ALBUM_ID}" in text
    assert "not_queued" in text
    assert "not proof of shared listening" in text
    connected.assert_not_called()


def test_share_is_only_queued_and_idempotent_after_actual_delivery(
    companion, connected
):
    saved = suggestion(companion, connected)["entry"]
    queued = music.share(companion, saved["id"], NOW)
    assert queued["status"] == "queued"
    message = outbox.fold(companion)[0]
    assert saved["note"] in message["body"]
    assert saved["album"]["url"] in message["body"]
    assert message["priority"] == "normal"
    assert message["expires_at"] == (NOW + dt.timedelta(hours=8)).isoformat()
    assert music.history(companion)[0]["delivery_status"] == "queued"
    outbox.mark(companion, message["id"], "sent", "mock delivery", NOW)
    again = music.share(companion, saved["id"], NOW + dt.timedelta(days=1))
    assert not again["written"]
    assert again["status"] == "sent"
    assert len(outbox.fold(companion)) == 1
    assert music.history(companion)[0]["delivery_status"] == "sent"


def test_queued_album_still_passes_outreach_and_quiet_hours_gate(companion, connected):
    import companion_outreach

    saved = suggestion(companion, connected)["entry"]
    at_night = NOW.replace(hour=2)
    queued = music.share(companion, saved["id"], at_night)
    assert queued["status"] == "queued"
    assert not companion_outreach.decide(companion, at_night)["allowed"]
    companion.outreach = "never"
    assert not companion_outreach.decide(companion, NOW)["allowed"]
    assert not (companion.data / "outreach.jsonl").exists()


@pytest.mark.parametrize("ident", ["../me", "https://evil.example/album", "", "a" * 23])
def test_catalog_identifier_cannot_change_endpoint(companion, connected, ident):
    with pytest.raises(ValueError, match="Spotify"):
        music.albums(companion, ident)
    connected.assert_not_called()


def test_switched_off_never_opens_the_authorization_or_reads_spotify(
    companion, connected
):
    keep = notes.add_moment(
        companion,
        {"moment": "joke", "text": "The toaster did it", "evidence": "session:test"},
        NOW,
    )["entry"]
    saved = suggestion(companion, connected, moment_id=keep["id"])
    assert saved["ok"]
    connected.reset_mock()
    companion.sensors = []
    with patch.object(music.sensors, "_spotify_state") as state:
        results = [
            music.top(companion, now=NOW),
            music.recent(companion, now=NOW),
            music.search(companion, "Example", now=NOW),
            music.albums(companion, ARTIST_ID, now=NOW),
            music.discover(companion, now=NOW),
            music.suggest(
                companion,
                {"album_id": ALBUM_ID, "note": "Again", "moment_id": keep["id"]},
                NOW,
            ),
            music.share(companion, saved["entry"]["id"], NOW),
            music.Spotify(companion, NOW).get("/me/top/artists"),
        ]
    assert {r["status"] for r in results} == {"switched_off"}
    assert all(not r["ok"] and "Settings" in r["message"] for r in results)
    state.assert_not_called()
    connected.assert_not_called()
    assert outbox.fold(companion) == []
    # Her context no longer carries the picks either; the record itself is kept.
    assert music.render(companion) == ""
    assert len(music.history(companion)) == 1


def test_album_instructions_follow_the_switch(companion):
    import companion_story as story

    companion.soul_dir.mkdir(parents=True, exist_ok=True)
    assert "companion_music.py" in story.instructions(companion)
    assert "companion_music.py" in story.scheduled(companion)
    companion.sensors = []
    assert "companion_music.py" not in story.instructions(companion)
    assert "companion_music.py" not in story.scheduled(companion)
    # Watching together needs no sensor, so it stays offered.
    assert "companion_viewing.py" in story.instructions(companion)
