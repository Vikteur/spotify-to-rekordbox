import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.main as main
import server.scanner.cache as cache_module
from server.scanner.scan import Scanner
from server.spotify.fetch import SpotifyFetchError
from tests.helpers import make_audio_tree


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(cache_module, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(main, "SCANNER", Scanner())
    monkeypatch.setattr(main, "_index_cache", None)
    return TestClient(main.app)


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
    assert status["library"]["skipped_drm"] == 1

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
    body = response.text
    assert body.startswith("#EXTM3U\n")
    assert "am-i-wrong.mp3" in body

    response = client.post(
        "/api/export",
        json={"name": "Friday Warmup", "format": "xml", "track_ids": [matched_id]},
    )
    assert response.status_code == 200
    assert "<DJ_PLAYLISTS" in response.text
    assert 'Name="Friday Warmup"' in response.text


def test_scan_missing_folder_404(client: TestClient, tmp_path: Path) -> None:
    response = client.post("/api/scan", json={"folder": str(tmp_path / "nope")})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "FOLDER_NOT_FOUND"


def test_scan_trims_pasted_quotes(client: TestClient, library: Path) -> None:
    response = client.post("/api/scan", json={"folder": f'"{library}"'})
    assert response.status_code == 202
    main.SCANNER.wait()


def test_match_before_scan_409(client: TestClient) -> None:
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
