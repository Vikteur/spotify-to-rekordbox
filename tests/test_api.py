import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.library import LIBRARY
from server.scanner.scan import Scanner
from server.spotify.fetch import SpotifyFetchError
from tests.helpers import make_audio_tree, write_mp3
from tests.test_rekordbox_import import collection_xml


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    with TestClient(main.app) as client:  # runs the startup hook (db.init + load)
        client.post("/api/libraries", json={"name": "MacBook"})
        yield client


@pytest.fixture()
def bare_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A client with no libraries at all (fresh install)."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "bare.db")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def library(tmp_path: Path) -> Path:
    root = tmp_path / "music"
    make_audio_tree(root)
    return root


def scan_and_wait(client: TestClient, folder: Path) -> dict:
    response = client.post("/api/scan", json={"folder": str(folder)})
    assert response.status_code == 202
    deadline = time.time() + 10
    while time.time() < deadline:
        status = client.get("/api/scan/status").json()
        if status["state"] in {"done", "error"}:
            return status
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")


def test_full_flow_scan_match_export(client: TestClient, library: Path) -> None:
    status = scan_and_wait(client, library)
    assert status["state"] == "done"
    assert status["library"]["track_count"] == 6
    assert status["scanned"]["skipped_drm"] == 1

    tracks = [
        {"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"},
        {"index": 1, "artist": "Missing Artist", "title": "Not In The Library"},
    ]
    response = client.post("/api/match", json={"tracks": tracks})
    assert response.status_code == 200
    payload = response.json()
    assert payload["library_size"] == 6
    first, second = payload["results"]
    assert first["bucket"] == "auto"
    assert first["candidates"][0]["track"]["title"] == "Am I Wrong"
    assert second["bucket"] == "unmatched"

    matched_id = first["auto_selected_id"]
    response = client.post(
        "/api/export",
        json={"name": "Friday Warmup", "format": "m3u8", "track_ids": [matched_id]},
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="Friday Warmup.m3u8"'
    assert response.text.startswith("#EXTM3U\n")
    assert "am-i-wrong.mp3" in response.text

    response = client.post(
        "/api/export",
        json={"name": "Friday Warmup", "format": "xml", "track_ids": [matched_id]},
    )
    assert response.status_code == 200
    assert "<DJ_PLAYLISTS" in response.text
    assert 'Name="Friday Warmup"' in response.text


def test_library_persists_across_restart(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)

    # A brand new client over the same database file — no rescan.
    with TestClient(main.app) as restarted:
        summary = restarted.get("/api/library").json()
        assert summary["track_count"] == 6
        assert summary["sources"][0]["kind"] == "folder"
        response = restarted.post(
            "/api/match",
            json={"tracks": [{"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"}]},
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["bucket"] == "auto"


def test_import_rekordbox_xml(client: TestClient) -> None:
    xml = collection_xml(
        'Name="Am I Wrong" Artist="Étienne de Crécy" TotalTime="371" AverageBpm="124.00" '
        'Tonality="Am" Location="file://localhost/music/am-i-wrong.mp3"',
        'Name="Substitution" Artist="Purple Disco Machine" Mix="Extended Mix" '
        'TotalTime="213" Location="file://localhost/music/sub.mp3"',
    )
    response = client.post("/api/library/xml?name=collection.xml", content=xml)
    assert response.status_code == 200
    payload = response.json()
    assert payload["imported"] == 2
    assert payload["missing_files"] == 2  # those paths don't exist on this machine
    assert payload["library"]["track_count"] == 2
    assert payload["library"]["sources"][0]["label"] == "collection.xml"

    # The XML library is immediately matchable, files present or not.
    response = client.post(
        "/api/match",
        json={"tracks": [{"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong",
                          "duration_sec": 371}]},
    )
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["bucket"] == "auto"
    assert result["candidates"][0]["track"]["bpm"] == 124.0
    assert result["candidates"][0]["track"]["musical_key"] == "Am"


def test_folder_and_xml_sources_merge(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    xml = collection_xml(
        'Name="Only In Rekordbox" Artist="Some DJ" TotalTime="300" '
        'Location="file://localhost/external-drive/only-here.mp3"'
    )
    response = client.post("/api/library/xml?name=collection.xml", content=xml)
    assert response.status_code == 200

    summary = response.json()["library"]
    assert summary["track_count"] == 7  # 6 scanned + 1 from the XML
    assert {source["kind"] for source in summary["sources"]} == {"folder", "xml"}

    # Both sources are searchable in one match run.
    response = client.post(
        "/api/match",
        json={
            "tracks": [
                {"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"},
                {"index": 1, "artist": "Some DJ", "title": "Only In Rekordbox"},
            ]
        },
    )
    results = response.json()["results"]
    assert results[0]["bucket"] == "auto"
    assert results[1]["bucket"] == "auto"
    assert results[1]["candidates"][0]["track"]["path"] == "/external-drive/only-here.mp3"


def test_remove_source(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    client.post("/api/library/xml?name=collection.xml",
                content=collection_xml('Name="X" Artist="Y" Location="file://localhost/m/x.mp3"'))

    sources = client.get("/api/library").json()["sources"]
    xml_source = next(source for source in sources if source["kind"] == "xml")
    response = client.delete(f"/api/library/sources/{xml_source['id']}")
    assert response.status_code == 200
    assert response.json()["track_count"] == 6
    assert [source["kind"] for source in response.json()["sources"]] == ["folder"]

    assert client.delete("/api/library/sources/9999").status_code == 404


def test_import_rejects_bad_xml(client: TestClient) -> None:
    response = client.post("/api/library/xml", content=b"<not-rekordbox/>")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BAD_XML"

    assert client.post("/api/library/xml", content=b"").status_code == 400


def test_remembered_version_applies_to_the_next_playlist(
    client: TestClient, library: Path
) -> None:
    scan_and_wait(client, library)
    spotify_track = {"index": 0, "artist": "Purple Disco Machine", "title": "Substitution"}

    first = client.post("/api/match", json={"tracks": [spotify_track]}).json()["results"][0]
    assert first["from_preference"] is False
    chosen = first["candidates"][0]["track"]["id"]

    # Picking a version in the UI posts it as the default for this song.
    response = client.post(
        "/api/preferences",
        json={"artist": "Purple Disco Machine", "title": "Substitution", "track_id": chosen},
    )
    assert response.status_code == 200
    assert len(response.json()["preferences"]) == 1

    # A later playlist containing the same song comes back pre-selected.
    again = client.post("/api/match", json={"tracks": [spotify_track]}).json()["results"][0]
    assert again["from_preference"] is True
    assert again["auto_selected_id"] == chosen
    assert again["candidates"][0]["track"]["id"] == chosen
    # Other versions are still offered, so the choice can be changed.
    assert len(again["candidates"]) >= 1


def test_preference_survives_a_restart(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    matched = client.post(
        "/api/match",
        json={"tracks": [{"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"}]},
    ).json()["results"][0]
    client.post(
        "/api/preferences",
        json={
            "artist": "Étienne de Crécy",
            "title": "Am I Wrong",
            "track_id": matched["auto_selected_id"],
        },
    )

    with TestClient(main.app) as restarted:
        again = restarted.post(
            "/api/match",
            json={"tracks": [{"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"}]},
        ).json()["results"][0]
        assert again["from_preference"] is True


def test_preference_endpoints_validate_and_forget(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    assert client.get("/api/preferences").json()["preferences"] == []

    bad = client.post(
        "/api/preferences", json={"artist": "A", "title": "B", "track_id": "deadbeef0000"}
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "UNKNOWN_TRACK"

    track_id = client.post(
        "/api/match", json={"tracks": [{"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"}]}
    ).json()["results"][0]["auto_selected_id"]
    client.post(
        "/api/preferences",
        json={"artist": "Étienne de Crécy", "title": "Am I Wrong", "track_id": track_id},
    )
    preference_id = client.get("/api/preferences").json()["preferences"][0]["id"]

    assert client.delete(f"/api/preferences/{preference_id}").json()["preferences"] == []
    assert client.delete(f"/api/preferences/{preference_id}").status_code == 404

    client.post(
        "/api/preferences",
        json={"artist": "Étienne de Crécy", "title": "Am I Wrong", "track_id": track_id},
    )
    assert client.delete("/api/preferences").json()["preferences"] == []


# --- imported rekordbox playlists ------------------------------------------

def m3u8_of(*paths: Path) -> bytes:
    """A playlist file the way rekordbox exports one, using real paths."""
    lines = ["#EXTM3U"]
    for path in paths:
        lines.append(f"#EXTINF:-1,{path.stem}")
        lines.append(str(path))
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_import_playlist_and_use_it_for_ranking(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    data = m3u8_of(library / "House" / "substitution-ext.mp3")

    response = client.post("/api/library/playlists?name=Most played 2026.m3u8", content=data)
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Most played 2026"
    assert payload["resolved"] == 1
    assert payload["missing"] == 0
    assert payload["playlists"][0]["track_count"] == 1

    result = client.post(
        "/api/match",
        json={"tracks": [{"index": 0, "artist": "Purple Disco Machine", "title": "Substitution"}]},
    ).json()["results"][0]
    top = result["candidates"][0]
    assert top["track"]["filename"] == "substitution-ext"
    assert top["playlists"] == ["Most played 2026"]


def test_playlist_filter_narrows_matching(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    data = m3u8_of(library / "House" / "substitution-ext.mp3")
    playlist_id = client.post(
        "/api/library/playlists?name=Most played 2026.m3u8", content=data
    ).json()["playlist_id"]

    tracks = [
        {"index": 0, "artist": "Purple Disco Machine", "title": "Substitution"},
        {"index": 1, "artist": "Étienne de Crécy", "title": "Am I Wrong"},
    ]
    whole = client.post("/api/match", json={"tracks": tracks}).json()
    assert whole["library_size"] == 6
    assert whole["results"][1]["bucket"] == "auto"

    narrowed = client.post(
        "/api/match", json={"tracks": tracks, "playlist_id": playlist_id}
    ).json()
    assert narrowed["library_size"] == 1
    assert narrowed["results"][0]["candidates"], "the playlist track still matches"
    assert narrowed["results"][1]["bucket"] == "unmatched"  # outside the playlist


def test_playlist_contents_can_be_opened(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    playlist_id = client.post(
        "/api/library/playlists?name=Most played 2026.m3u8",
        content=m3u8_of(
            library / "House" / "substitution-ext.mp3",
            library / "House" / "am-i-wrong.mp3",
        ),
    ).json()["playlist_id"]

    tracks = client.get(f"/api/library/playlists/{playlist_id}/tracks").json()["tracks"]
    # Exported order is preserved, not re-sorted.
    assert [track["filename"] for track in tracks] == ["substitution-ext", "am-i-wrong"]
    assert tracks[1]["artist"] == "Étienne de Crécy"

    assert client.get("/api/library/playlists/9999/tracks").status_code == 404


def test_playlist_contents_are_scoped_to_their_library(
    client: TestClient, library: Path
) -> None:
    scan_and_wait(client, library)
    playlist_id = client.post(
        "/api/library/playlists?name=Mine.m3u8",
        content=m3u8_of(library / "House" / "am-i-wrong.mp3"),
    ).json()["playlist_id"]

    client.post("/api/libraries", json={"name": "Studio PC"})
    assert client.get(f"/api/library/playlists/{playlist_id}/tracks").status_code == 404


def test_playlists_are_listed_and_removable(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    data = m3u8_of(library / "House" / "substitution-ext.mp3")
    client.post("/api/library/playlists?name=All time.m3u8", content=data)

    listed = client.get("/api/library/playlists").json()["playlists"]
    assert [p["name"] for p in listed] == ["All time"]

    assert client.delete(f"/api/library/playlists/{listed[0]['id']}").json()["playlists"] == []
    assert client.delete(f"/api/library/playlists/{listed[0]['id']}").status_code == 404


def test_playlists_are_scoped_to_their_library(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    client.post("/api/library/playlists?name=All time.m3u8",
                content=m3u8_of(library / "House" / "substitution-ext.mp3"))
    client.post("/api/libraries", json={"name": "Studio PC"})
    assert client.get("/api/library/playlists").json()["playlists"] == []


def test_playlist_import_rejects_unusable_input(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    bad = client.post("/api/library/playlists?name=x.m3u8", content=b"#EXTM3U\n")
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "BAD_PLAYLIST"

    foreign = client.post(
        "/api/library/playlists?name=other.m3u8",
        content=b"#EXTM3U\n/some/other/device/track.mp3\n",
    )
    assert foreign.status_code == 400
    assert foreign.json()["detail"]["code"] == "NOTHING_RESOLVED"


def test_scan_missing_folder_404(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scan", json={"folder": str(tmp_path / "nope")})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FOLDER_NOT_FOUND"


def test_scan_trims_pasted_quotes(client: TestClient, library: Path) -> None:
    response = client.post("/api/scan", json={"folder": f'"{library}"'})
    assert response.status_code == 202
    main.SCANNER.wait()


def test_match_with_an_empty_library_409(client: TestClient) -> None:
    response = client.post(
        "/api/match", json={"tracks": [{"index": 0, "artist": "A", "title": "B"}]}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_LIBRARY"


# --- named libraries -------------------------------------------------------

def test_fresh_install_requires_naming_a_library_first(
    bare_client: TestClient, tmp_path: Path
) -> None:
    summary = bare_client.get("/api/library").json()
    assert summary["libraries"] == []
    assert summary["active_library_id"] is None

    blocked = bare_client.post("/api/scan", json={"folder": str(tmp_path)})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "NO_LIBRARY_SELECTED"

    created = bare_client.post("/api/libraries", json={"name": "Studio PC"})
    assert created.status_code == 201
    assert created.json()["active_library_name"] == "Studio PC"
    assert bare_client.post("/api/libraries", json={"name": "  "}).status_code == 400


def test_library_names_must_be_unique(client: TestClient) -> None:
    duplicate = client.post("/api/libraries", json={"name": "MacBook"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "DUPLICATE_NAME"


def test_switching_library_changes_what_a_playlist_matches_against(
    client: TestClient, library: Path, tmp_path: Path
) -> None:
    scan_and_wait(client, library)
    macbook = client.get("/api/library").json()["active_library_id"]

    # A second device whose folder holds a different track.
    other_root = tmp_path / "studio"
    (other_root / "House").mkdir(parents=True)
    write_mp3(other_root / "House" / "studio-only.mp3",
              artist="Studio Artist", title="Studio Only")
    studio = client.post("/api/libraries", json={"name": "Studio PC"}).json()[
        "active_library_id"
    ]
    scan_and_wait(client, other_root)

    tracks = [
        {"index": 0, "artist": "Étienne de Crécy", "title": "Am I Wrong"},
        {"index": 1, "artist": "Studio Artist", "title": "Studio Only"},
    ]
    def filenames(result: dict) -> set[str]:
        return {c["track"]["filename"] for c in result["candidates"]}

    on_studio = client.post("/api/match", json={"tracks": tracks}).json()
    assert on_studio["library_name"] == "Studio PC"
    assert on_studio["results"][1]["bucket"] == "auto"
    assert "studio-only" in filenames(on_studio["results"][1])
    # The MacBook file is not reachable from this library at all.
    assert "am-i-wrong" not in filenames(on_studio["results"][0])

    client.post(f"/api/libraries/{macbook}/select")
    on_macbook = client.post("/api/match", json={"tracks": tracks}).json()
    assert on_macbook["library_name"] == "MacBook"
    assert on_macbook["results"][0]["bucket"] == "auto"
    assert "am-i-wrong" in filenames(on_macbook["results"][0])
    assert "studio-only" not in filenames(on_macbook["results"][1])
    assert client.post("/api/libraries/9999/select").status_code == 404


def test_remembered_versions_do_not_leak_between_libraries(
    client: TestClient, library: Path
) -> None:
    """Each device resolves a song to its own file, so the choices must not
    overwrite one another."""
    scan_and_wait(client, library)
    macbook = client.get("/api/library").json()["active_library_id"]
    song = {"index": 0, "artist": "Purple Disco Machine", "title": "Substitution"}
    chosen = client.post("/api/match", json={"tracks": [song]}).json()["results"][0][
        "candidates"
    ][0]["track"]["id"]
    client.post(
        "/api/preferences",
        json={"artist": song["artist"], "title": song["title"], "track_id": chosen},
    )
    assert len(client.get("/api/preferences").json()["preferences"]) == 1

    studio = client.post("/api/libraries", json={"name": "Studio PC"}).json()[
        "active_library_id"
    ]
    assert client.get("/api/preferences").json()["preferences"] == []  # its own slate

    client.post(f"/api/libraries/{macbook}/select")
    assert len(client.get("/api/preferences").json()["preferences"]) == 1
    assert (
        client.post("/api/match", json={"tracks": [song]}).json()["results"][0][
            "from_preference"
        ]
        is True
    )
    assert studio != macbook


def test_rename_and_delete_library(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    macbook = client.get("/api/library").json()["active_library_id"]

    renamed = client.patch(f"/api/libraries/{macbook}", json={"name": "MacBook Pro"})
    assert renamed.status_code == 200
    assert renamed.json()["active_library_name"] == "MacBook Pro"
    assert renamed.json()["track_count"] == 6  # rename does not disturb contents

    client.post("/api/libraries", json={"name": "Spare"})
    deleted = client.delete(f"/api/libraries/{macbook}")
    assert deleted.status_code == 200
    assert [lib["name"] for lib in deleted.json()["libraries"]] == ["Spare"]
    assert deleted.json()["active_library_name"] == "Spare"  # falls back
    assert client.delete(f"/api/libraries/{macbook}").status_code == 404


def test_spotify_route_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetcher(playlist_id: str) -> dict:
        assert playlist_id == "37i9dQZF1DXcBWIGoYBM5M"
        return {
            "playlist_id": playlist_id,
            "name": "Fixture List",
            "owner_name": "viktor",
            "total": None,
            "truncated": False,
            "tracks": [{"index": 0, "artist": "A", "title": "B", "duration_sec": 200}],
        }

    monkeypatch.setattr(main, "playlist_fetcher", fake_fetcher)
    response = client.post(
        "/api/spotify/playlist",
        json={"url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Fixture List"


def test_spotify_route_bad_url(client: TestClient) -> None:
    response = client.post(
        "/api/spotify/playlist",
        json={"url": "https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BAD_URL"


def test_spotify_route_fetch_failure_hints_paste(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_fetcher(playlist_id: str) -> dict:
        raise SpotifyFetchError("blocked")

    monkeypatch.setattr(main, "playlist_fetcher", failing_fetcher)
    response = client.post(
        "/api/spotify/playlist",
        json={"url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "SPOTIFY_FETCH_FAILED"
    assert "paste" in detail["message"].lower()


def test_export_skipped_files_txt(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    response = client.get("/api/export/skipped")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="skipped files.txt"'
    )
    body = response.text
    assert "old-purchase.m4p" in body          # the DRM one, named
    assert "corrupt.mp3" in body               # the unreadable one, named
    assert "can't sync to MPEG frame" in body  # with its reason


def test_export_skipped_when_nothing_was_skipped(
    client: TestClient, tmp_path: Path
) -> None:
    clean = tmp_path / "clean"
    (clean / "House").mkdir(parents=True)
    write_mp3(clean / "House" / "fine.mp3", artist="A", title="Fine")
    scan_and_wait(client, clean)
    response = client.get("/api/export/skipped")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "NOTHING_SKIPPED"


def test_export_missing_tracks_txt(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    response = client.post(
        "/api/export/missing",
        json={
            "name": "Friday Warmup",
            "tracks": [
                {"artist": "Ghost Artist", "title": "Not In My Library"},
                {"artist": "Some DJ", "title": "Passed On", "had_candidates": True},
            ],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="Friday Warmup - missing.txt"'
    )
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "Ghost Artist - Not In My Library" in body
    assert "MacBook" in body  # named the library it is missing from
    assert "# Skipped" in body

    empty = client.post("/api/export/missing", json={"name": "x", "tracks": []})
    assert empty.status_code == 400


def test_export_unknown_id_400(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    response = client.post(
        "/api/export", json={"name": "x", "format": "m3u8", "track_ids": ["deadbeef0000"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNKNOWN_TRACK"
