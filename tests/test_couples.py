"""The wedding intake: couple records, magic-link scopes, autosave semantics,
the Spotify search proxy, and never-list exclusion on export."""

import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.scanner.scan import Scanner
from server.spotify import search as spotify_search
from tests.helpers import make_audio_tree

FUTURE = (date.today() + timedelta(days=90)).isoformat()
PAST = (date.today() - timedelta(days=2)).isoformat()

TRACK = {
    "spotify_id": "4uLU6hMCjMI75M1A2tKUQC",
    "isrc": "GBAYE0601498",
    "title": "Someone Like You",
    "artist": "Adele",
    "duration_ms": 285000,
    "art_url": "https://i.scdn.co/image/small",
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    # Auth ships switched off right now (couples_api.auth_disabled). The link
    # tests below cover the real gate, so pin it on here; the bypass itself is
    # covered by test_auth_disabled_bypasses_every_link_check.
    monkeypatch.setenv("AUTH_DISABLED", "0")
    spotify_search.reset()
    with TestClient(main.app) as client:
        yield client
    spotify_search.reset()


def make_couple(client: TestClient, wedding_date: str = FUTURE) -> dict:
    response = client.post(
        "/api/couples", json={"names": "Sofie & Jan", "wedding_date": wedding_date}
    )
    assert response.status_code == 201
    return response.json()


def put_entry(client, token, uid, kind, *, title=None, position=None, **extra):
    body = {"kind": kind, **TRACK, **extra}
    if title is not None:
        body["title"] = title
    if position is not None:
        body["position"] = position
    return client.put(f"/api/guest/{token}/entries/{uid}", json=body)


# --- couple records and tokens ---------------------------------------------

def test_create_couple_and_summary(client: TestClient) -> None:
    detail = make_couple(client)
    assert detail["names"] == "Sofie & Jan"
    assert set(detail["lists"]) == {
        "opening_dance", "second_third", "couple_top20",
        "friends_top20", "must_plays", "playlist_links",
    }
    assert detail["links"]["couple"]["token"] != detail["links"]["friends"]["token"]
    assert not detail["links"]["couple"]["revoked"]

    summary = client.get("/api/couples").json()["couples"]
    assert len(summary) == 1
    assert summary[0]["counts"]["never"] == 0
    assert summary[0]["song_count"] == 0


def test_create_couple_rejects_bad_input(client: TestClient) -> None:
    bad_name = client.post("/api/couples", json={"names": " ", "wedding_date": FUTURE})
    assert bad_name.status_code == 400
    bad_date = client.post(
        "/api/couples", json={"names": "A & B", "wedding_date": "next summer"}
    )
    assert bad_date.status_code == 400
    assert bad_date.json()["detail"]["code"] == "BAD_DATE"


def test_token_scopes_in_guest_state(client: TestClient) -> None:
    detail = make_couple(client)
    couple_token = detail["links"]["couple"]["token"]
    friends_token = detail["links"]["friends"]["token"]

    couple_view = client.get(f"/api/guest/{couple_token}").json()
    assert couple_view["scope"] == "couple"
    assert couple_view["friends_link"] == f"/g/{friends_token}"
    assert "blocklist" in couple_view

    friends_view = client.get(f"/api/guest/{friends_token}").json()
    assert friends_view["scope"] == "friends"
    assert set(friends_view["entries"]) == {"friends_top20"}
    assert "briefing_text" not in friends_view
    assert "blocklist" not in friends_view
    assert "friends_link" not in friends_view


def test_bad_revoked_rotated_and_expired_links(client: TestClient) -> None:
    detail = make_couple(client)
    cid = detail["id"]
    friends_token = detail["links"]["friends"]["token"]

    assert client.get("/api/guest/not-a-real-token").status_code == 404

    client.post(f"/api/couples/{cid}/tokens/friends/revoke", json={"revoked": True})
    assert client.get(f"/api/guest/{friends_token}").status_code == 403

    rotated = client.post(f"/api/couples/{cid}/tokens/friends/rotate").json()
    new_token = rotated["links"]["friends"]["token"]
    assert new_token != friends_token
    assert client.get(f"/api/guest/{friends_token}").status_code == 404  # old link dead
    assert client.get(f"/api/guest/{new_token}").status_code == 200      # fresh + unrevoked

    expired = make_couple(client, wedding_date=PAST)
    gone = client.get(f"/api/guest/{expired['links']['couple']['token']}")
    assert gone.status_code == 410
    assert gone.json()["detail"]["code"] == "LINK_EXPIRED"


def test_auth_disabled_bypasses_every_link_check(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temporary AUTH_DISABLED switch. Delete this with the switch."""
    monkeypatch.setenv("AUTH_DISABLED", "1")

    detail = make_couple(client)
    cid = detail["id"]
    friends_token = detail["links"]["friends"]["token"]

    # A friends link now opens the couple's whole record, not the guest slice.
    assert client.get(f"/api/guest/{friends_token}").json()["scope"] == "couple"

    # Revoked and expired links keep working.
    client.post(f"/api/couples/{cid}/tokens/friends/revoke", json={"revoked": True})
    assert client.get(f"/api/guest/{friends_token}").status_code == 200

    expired = make_couple(client, wedding_date=PAST)
    assert client.get(f"/api/guest/{expired['links']['couple']['token']}").status_code == 200

    # An unknown token still 404s: it names the record, not just the caller.
    assert client.get("/api/guest/not-a-real-token").status_code == 404


# --- entries: idempotency, slots, caps --------------------------------------

def test_put_entry_is_idempotent(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    first = put_entry(client, token, "uid-1", "opening_dance", start_pref="chorus")
    again = put_entry(client, token, "uid-1", "opening_dance", start_pref="chorus")
    assert first.status_code == 200 and again.status_code == 200
    entries = again.json()["entries"]["opening_dance"]
    assert len(entries) == 1
    assert entries[0]["start_pref"] == "chorus"
    assert entries[0]["source_token_kind"] == "couple"


def test_update_keeps_position_and_created_at(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    put_entry(client, token, "uid-a", "couple_top20", position=7)
    updated = put_entry(
        client, token, "uid-a", "couple_top20", title="Rolling in the Deep", position=3
    ).json()["entry"]
    assert updated["title"] == "Rolling in the Deep"
    assert updated["position"] == 7  # moves go through the order endpoint


def test_slot_race_lands_on_next_free_row(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    put_entry(client, token, "uid-a", "couple_top20", position=0)
    second = put_entry(client, token, "uid-b", "couple_top20", position=0).json()["entry"]
    assert second["position"] == 1


def test_list_caps(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    for i in range(5):
        assert put_entry(client, token, f"mp-{i}", "must_plays").status_code == 200
    overflow = put_entry(client, token, "mp-5", "must_plays")
    assert overflow.status_code == 409
    assert overflow.json()["detail"]["code"] == "LIST_FULL"


def test_empty_title_needs_free_text(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    response = client.put(
        f"/api/guest/{token}/entries/ft-1",
        json={"kind": "never_wrong", "title": ""},
    )
    assert response.status_code == 400  # unknown kind

    response = client.put(
        f"/api/guest/{token}/entries/ft-1",
        json={"kind": "couple_top20", "title": "", "free_text": ""},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "EMPTY_TITLE"

    response = client.put(
        f"/api/guest/{token}/entries/ft-1",
        json={"kind": "couple_top20", "title": "", "free_text": "Opa's polka-medley"},
    )
    assert response.status_code == 200
    entry = response.json()["entry"]
    assert entry["title"] == "Opa's polka-medley"
    assert entry["spotify_id"] is None  # unmatched free-text fallback


# --- friend scope rules -----------------------------------------------------

def test_friend_can_only_append_to_friends_list(client: TestClient) -> None:
    detail = make_couple(client)
    couple_token = detail["links"]["couple"]["token"]
    friends_token = detail["links"]["friends"]["token"]

    ok = put_entry(client, friends_token, "fr-1", "friends_top20")
    assert ok.status_code == 200
    assert ok.json()["entry"]["source_token_kind"] == "friend"

    wrong_list = put_entry(client, friends_token, "fr-2", "couple_top20")
    assert wrong_list.status_code == 403

    # A friend may re-save their own row (autosave retry) …
    assert put_entry(client, friends_token, "fr-1", "friends_top20").status_code == 200

    # … but not touch a row the couple added.
    put_entry(client, couple_token, "cp-1", "friends_top20")
    stolen = put_entry(client, friends_token, "cp-1", "friends_top20")
    assert stolen.status_code == 403

    # No deleting, no reordering ("no dragging people to other chairs").
    assert client.delete(f"/api/guest/{friends_token}/entries/fr-1").status_code == 403
    reorder = client.put(
        f"/api/guest/{friends_token}/order/friends_top20",
        json={"positions": [{"uid": "fr-1", "position": 5}]},
    )
    assert reorder.status_code == 403
    block = client.put(f"/api/guest/{friends_token}/blocklist/b1", json=TRACK)
    assert block.status_code == 403


def test_couple_can_reorder_and_delete(client: TestClient) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    put_entry(client, token, "t-0", "couple_top20", position=0, title="First")
    put_entry(client, token, "t-1", "couple_top20", position=1, title="Second")

    swapped = client.put(
        f"/api/guest/{token}/order/couple_top20",
        json={"positions": [{"uid": "t-0", "position": 1}, {"uid": "t-1", "position": 0}]},
    )
    assert swapped.status_code == 200
    entries = swapped.json()["entries"]["couple_top20"]
    assert [entry["title"] for entry in entries] == ["Second", "First"]

    duplicate = client.put(
        f"/api/guest/{token}/order/couple_top20",
        json={"positions": [{"uid": "t-0", "position": 0}, {"uid": "t-1", "position": 0}]},
    )
    assert duplicate.status_code == 400

    removed = client.delete(f"/api/guest/{token}/entries/t-0")
    assert removed.status_code == 200
    assert len(removed.json()["entries"]["couple_top20"]) == 1
    # Deleting again is a no-op, not an error (idempotent autosave retries).
    assert client.delete(f"/api/guest/{token}/entries/t-0").status_code == 200


def test_couple_details_patch_scope(client: TestClient) -> None:
    detail = make_couple(client)
    couple_token = detail["links"]["couple"]["token"]
    friends_token = detail["links"]["friends"]["token"]

    updated = client.patch(
        f"/api/guest/{couple_token}/couple",
        json={"briefing_text": "Open bar, 90s hip-hop, no slow songs before midnight."},
    )
    assert updated.status_code == 200
    assert "no slow songs" in updated.json()["briefing_text"]

    forbidden = client.patch(
        f"/api/guest/{friends_token}/couple", json={"briefing_text": "hijacked"}
    )
    assert forbidden.status_code == 403


# --- never list -------------------------------------------------------------

def test_blocklist_add_update_remove(client: TestClient) -> None:
    detail = make_couple(client)
    token = detail["links"]["couple"]["token"]
    added = client.put(f"/api/guest/{token}/blocklist/nb-1", json=TRACK)
    assert added.status_code == 200
    assert added.json()["entry"]["position"] == 0

    again = client.put(f"/api/guest/{token}/blocklist/nb-1", json=TRACK)
    assert len(again.json()["blocklist"]) == 1  # idempotent

    dj_view = client.get(f"/api/couples/{detail['id']}").json()
    assert len(dj_view["blocklist"]) == 1

    gone = client.delete(f"/api/guest/{token}/blocklist/nb-1")
    assert gone.json()["blocklist"] == []


# --- change log -------------------------------------------------------------

def test_change_log_attributes_token_kinds(client: TestClient) -> None:
    detail = make_couple(client)
    couple_token = detail["links"]["couple"]["token"]
    friends_token = detail["links"]["friends"]["token"]
    put_entry(client, couple_token, "c1", "opening_dance")
    put_entry(client, friends_token, "f1", "friends_top20", title="Mr. Brightside")

    changes = client.get(f"/api/couples/{detail['id']}/changes").json()["changes"]
    kinds = {change["token_kind"] for change in changes}
    assert kinds == {"couple", "friend"}
    friend_change = next(c for c in changes if c["token_kind"] == "friend")
    assert "Mr. Brightside" in friend_change["summary"]
    assert friend_change["kind"] == "friends_top20"


# --- search proxy -----------------------------------------------------------

def test_search_caches_and_rate_limits(client: TestClient, monkeypatch) -> None:
    token = make_couple(client)["links"]["couple"]["token"]
    calls: list[str] = []

    def fake_upstream(q: str) -> list[dict]:
        calls.append(q)
        return [dict(TRACK, uri="spotify:track:x", album="21")]

    monkeypatch.setattr(spotify_search, "_upstream_search", fake_upstream)

    first = client.get(f"/api/guest/{token}/search", params={"q": "Adele someone"})
    assert first.status_code == 200
    assert first.json()["results"][0]["title"] == "Someone Like You"
    # Identical query (modulo case/whitespace) is a cache hit, not a Spotify call.
    client.get(f"/api/guest/{token}/search", params={"q": "  adele   SOMEONE "})
    assert calls == ["adele someone"]

    monkeypatch.setattr(spotify_search, "RATE_MAX_MISSES", 3)
    spotify_search.reset()
    for i in range(3):
        assert client.get(f"/api/guest/{token}/search", params={"q": f"q{i}"}).status_code == 200
    limited = client.get(f"/api/guest/{token}/search", params={"q": "q3"})
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "RATE_LIMITED"


def test_search_requires_live_token_and_reports_unconfigured(
    client: TestClient, monkeypatch
) -> None:
    assert client.get("/api/guest/nope/search", params={"q": "x"}).status_code == 404

    token = make_couple(client)["links"]["couple"]["token"]
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(spotify_search, "CREDENTIALS_FILE", Path("does/not/exist.json"))
    response = client.get(f"/api/guest/{token}/search", params={"q": "adele hello"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SEARCH_UNAVAILABLE"

    state = client.get(f"/api/guest/{token}").json()
    assert state["search_available"] is False


# --- never list excluded from exports ---------------------------------------

def scan_and_wait(client: TestClient, folder: Path) -> None:
    client.post("/api/libraries", json={"name": "MacBook"})
    assert client.post("/api/scan", json={"folder": str(folder)}).status_code == 202
    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get("/api/scan/status").json()["state"] in {"done", "error"}:
            return
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")


def test_export_excludes_blocked_songs_any_version(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "music"
    make_audio_tree(root)
    scan_and_wait(client, root)

    detail = make_couple(client)
    token = detail["links"]["couple"]["token"]
    # Block the plain song; the library holds "Substitution (Extended Mix)".
    client.put(
        f"/api/guest/{token}/blocklist/nb-sub",
        json={"title": "Substitution", "artist": "Purple Disco Machine"},
    )

    matched = client.post(
        "/api/match",
        json={"tracks": [
            {"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"},
            {"index": 1, "artist": "Purple Disco Machine", "title": "Substitution"},
        ]},
    ).json()["results"]
    # The extended mix is a version mismatch, so it may need a manual pick —
    # take the top candidate, exactly like the DJ would.
    track_ids = [
        result["auto_selected_id"] or result["candidates"][0]["track"]["id"]
        for result in matched
    ]
    assert all(track_ids)

    plain = client.post(
        "/api/export", json={"name": "Wedding", "format": "m3u8", "track_ids": track_ids}
    )
    assert "Substitution" in plain.text

    scoped = client.post(
        "/api/export",
        json={
            "name": "Wedding", "format": "m3u8", "track_ids": track_ids,
            "couple_id": detail["id"],
        },
    )
    assert scoped.status_code == 200
    assert "Am I Wrong" in scoped.text
    assert "Substitution" not in scoped.text  # blocked in every version

    all_blocked = client.post(
        "/api/export",
        json={
            "name": "Wedding", "format": "m3u8", "track_ids": [track_ids[1]],
            "couple_id": detail["id"],
        },
    )
    assert all_blocked.status_code == 400

    missing = client.post(
        "/api/export/missing",
        json={
            "name": "Wedding", "couple_id": detail["id"],
            "tracks": [
                {"artist": "Purple Disco Machine", "title": "Substitution", "had_candidates": True},
                {"artist": "Somebody", "title": "Elsewhere", "had_candidates": False},
            ],
        },
    )
    assert missing.status_code == 200
    assert "Substitution" not in missing.text
    assert "Elsewhere" in missing.text


def test_delete_couple_cascades(client: TestClient) -> None:
    detail = make_couple(client)
    token = detail["links"]["couple"]["token"]
    put_entry(client, token, "e1", "couple_top20")
    client.put(f"/api/guest/{token}/blocklist/b1", json=TRACK)

    assert client.delete(f"/api/couples/{detail['id']}").status_code == 200
    assert client.get(f"/api/guest/{token}").status_code == 404
    assert client.get("/api/couples").json()["couples"] == []
