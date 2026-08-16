"""Per-couple export: one rekordbox folder, one playlist per chapter.

The DJ's real question is "did I get all their special requests on the stick",
so these cover both halves of that: what he has (the folder XML) and what he
still needs to find (the missing list).
"""

import time
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.export.rekordbox_xml import build_rekordbox_folder_xml
from server.models import LibraryTrack
from server.scanner.scan import Scanner
from tests.helpers import make_audio_tree

FUTURE = (date.today() + timedelta(days=90)).isoformat()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    with TestClient(main.app) as client:
        yield client


def _track(track_id: str, title: str) -> LibraryTrack:
    return LibraryTrack(
        id=track_id, path=rf"D:\muziek\{title}.mp3", filename=title, ext="mp3",
        artist="A", title=title, album=None, duration_sec=180.0,
        bitrate_kbps=320, tag_source="tags", size_bytes=1, mtime_ms=1,
    )


def _scan(client: TestClient, folder: Path) -> None:
    client.post("/api/libraries", json={"name": "MacBook"})
    assert client.post("/api/scan", json={"folder": str(folder)}).status_code == 202
    deadline = time.time() + 10
    while time.time() < deadline:
        if client.get("/api/scan/status").json()["state"] in {"done", "error"}:
            return
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")


def _couple(client: TestClient) -> dict:
    return client.post(
        "/api/couples", json={"names": "Sofie & Jan", "wedding_date": FUTURE}
    ).json()


def _add(client: TestClient, token: str, uid: str, kind: str, title: str,
         artist: str = "", position: int = 0) -> None:
    response = client.put(
        f"/api/guest/{token}/entries/{uid}",
        json={"kind": kind, "title": title, "artist": artist, "position": position},
    )
    assert response.status_code == 200, response.text


# --- the XML builder itself -------------------------------------------------

def test_folder_xml_nests_one_playlist_per_chapter() -> None:
    one, two = _track("aaa", "One"), _track("bbb", "Two")
    xml = build_rekordbox_folder_xml(
        "Sofie & Jan 2026-09-12",
        [("01 Opening dance", [one]), ("02 Their top 20", [one, two])],
    )
    # Type 0 is a folder, Type 1 a playlist — the folder holds both chapters.
    assert '<NODE Type="0" Name="Sofie &amp; Jan 2026-09-12" Count="2">' in xml
    assert '<NODE Name="01 Opening dance" Type="1" KeyType="0" Entries="1">' in xml
    assert '<NODE Name="02 Their top 20" Type="1" KeyType="0" Entries="2">' in xml


def test_folder_xml_writes_a_shared_track_to_the_collection_once() -> None:
    one, two = _track("aaa", "One"), _track("bbb", "Two")
    xml = build_rekordbox_folder_xml(
        "Couple", [("01 A", [one]), ("02 B", [one, two])]
    )
    # Two distinct files, referenced three times across the playlists.
    assert 'Entries="2"' in xml.split("<PLAYLISTS>")[0]
    assert xml.count('<TRACK TrackID=') == 2
    assert xml.count('<TRACK Key="1"/>') == 2


# --- the route --------------------------------------------------------------

def test_export_builds_a_folder_of_matched_chapters(
    client: TestClient, tmp_path: Path
) -> None:
    make_audio_tree(tmp_path / "music")
    _scan(client, tmp_path / "music")
    detail = _couple(client)
    token = detail["links"]["couple"]["token"]
    _add(client, token, "e1", "opening_dance", "Am I Wrong", "Étienne de Crécy")
    _add(client, token, "e2", "couple_top20", "Am I Wrong", "Étienne de Crécy")

    summary = client.get(f"/api/couples/{detail['id']}/export/summary").json()
    assert summary["folder"] == f"Sofie & Jan {FUTURE}"
    assert [p["name"] for p in summary["playlists"]] == [
        "01 Opening dance", "02 Their top 20",
    ]

    export = client.get(f"/api/couples/{detail['id']}/export/rekordbox.xml")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]
    assert f'Name="Sofie &amp; Jan {FUTURE}" Count="2"' in export.text
    # The opening number stays alone in its own list — the DJ's safety net.
    assert '<NODE Name="01 Opening dance" Type="1" KeyType="0" Entries="1">' in export.text


def test_empty_chapters_are_left_out_entirely(
    client: TestClient, tmp_path: Path
) -> None:
    make_audio_tree(tmp_path / "music")
    _scan(client, tmp_path / "music")
    detail = _couple(client)
    token = detail["links"]["couple"]["token"]
    _add(client, token, "e1", "couple_top20", "Am I Wrong", "Étienne de Crécy")

    summary = client.get(f"/api/couples/{detail['id']}/export/summary").json()
    # Numbering restarts from 01 for whatever chapters actually have songs, so
    # an untouched "opening dance" doesn't leave a gap or an empty playlist.
    assert [p["name"] for p in summary["playlists"]] == ["01 Their top 20"]


def test_never_list_songs_never_reach_the_export(
    client: TestClient, tmp_path: Path
) -> None:
    make_audio_tree(tmp_path / "music")
    _scan(client, tmp_path / "music")
    detail = _couple(client)
    token = detail["links"]["couple"]["token"]
    _add(client, token, "e1", "couple_top20", "Am I Wrong", "Étienne de Crécy")
    client.put(
        f"/api/guest/{token}/blocklist/nb1",
        json={"title": "Am I Wrong", "artist": "Étienne de Crécy"},
    )

    summary = client.get(f"/api/couples/{detail['id']}/export/summary").json()
    assert summary["blocked"] == 1
    assert summary["playlists"] == []
    # Nothing left to hand the decks, and the block must not masquerade as a
    # song the DJ should go and buy.
    assert summary["missing"] == 0


def test_missing_list_collects_what_the_library_lacks(
    client: TestClient, tmp_path: Path
) -> None:
    make_audio_tree(tmp_path / "music")
    _scan(client, tmp_path / "music")
    detail = _couple(client)
    token = detail["links"]["couple"]["token"]
    _add(client, token, "e1", "couple_top20", "A Song Nobody Owns", "Ghost Act")
    # The same song in a second chapter must not double the shopping list.
    _add(client, token, "e2", "friends_top20", "A Song Nobody Owns", "Ghost Act")

    summary = client.get(f"/api/couples/{detail['id']}/export/summary").json()
    assert summary["missing"] == 1

    missing = client.get(f"/api/couples/{detail['id']}/export/missing.txt")
    assert missing.status_code == 200
    assert missing.text.count("Ghost Act - A Song Nobody Owns") == 1


def test_export_without_a_library_explains_itself(client: TestClient) -> None:
    detail = _couple(client)
    response = client.get(f"/api/couples/{detail['id']}/export/rekordbox.xml")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_LIBRARY"


def test_unknown_couple_is_a_404(client: TestClient, tmp_path: Path) -> None:
    make_audio_tree(tmp_path / "music")
    _scan(client, tmp_path / "music")
    assert client.get("/api/couples/999/export/summary").status_code == 404
