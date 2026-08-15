import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import db
from server.library import LIBRARY
from server.scanner.scan import Scanner
from server.spotify.fetch import SpotifyFetchError
from tests.helpers import make_audio_tree
from tests.test_rekordbox_import import collection_xml


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    with TestClient(main.app) as client:  # runs the startup hook (db.init + reload)
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


def test_scan_missing_folder_404(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scan", json={"folder": str(tmp_path / "nope")})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FOLDER_NOT_FOUND"


def test_scan_trims_pasted_quotes(client: TestClient, library: Path) -> None:
    response = client.post("/api/scan", json={"folder": f'"{library}"'})
    assert response.status_code == 202
    main.SCANNER.wait()


def test_match_before_any_library_409(client: TestClient) -> None:
    LIBRARY.reload()  # empty database
    response = client.post(
        "/api/match", json={"tracks": [{"index": 0, "artist": "A", "title": "B"}]}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_LIBRARY"


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


def test_export_unknown_id_400(client: TestClient, library: Path) -> None:
    scan_and_wait(client, library)
    response = client.post(
        "/api/export", json={"name": "x", "format": "m3u8", "track_ids": ["deadbeef0000"]}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNKNOWN_TRACK"
