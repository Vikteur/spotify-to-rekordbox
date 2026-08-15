import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.export.m3u8 import build_m3u8
from server.export.rekordbox_xml import build_rekordbox_xml
from server.matcher.index import LibraryIndex
from server.matcher.match import match_playlist
from server.models import PlaylistTrackInput
from server.scanner.scan import SCANNER, ScanInProgress
from server.spotify.fetch import SpotifyFetchError, fetch_playlist
from server.spotify.parse_embed import (
    BadPlaylistUrl,
    EmbedParseError,
    parse_playlist_url,
)

app = FastAPI(title="spotify-to-rekordbox")

# Module-level so tests can swap in a fixture-backed fake.
playlist_fetcher = fetch_playlist

_PASTE_HINT = "Use the paste-text fallback: one 'Artist - Title' per line."


class ScanRequest(BaseModel):
    folder: str
    force: bool = False


class PlaylistRequest(BaseModel):
    url: str


class MatchRequest(BaseModel):
    tracks: list[PlaylistTrackInput]


class ExportRequest(BaseModel):
    name: str
    format: str  # "m3u8" | "xml"
    track_ids: list[str]


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


_index_cache: tuple[int, LibraryIndex] | None = None


def _get_index() -> LibraryIndex:
    global _index_cache
    generation = SCANNER.generation
    if _index_cache is None or _index_cache[0] != generation:
        _index_cache = (generation, LibraryIndex(SCANNER.tracks))
    return _index_cache[1]


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/scan", status_code=202)
def start_scan(request: ScanRequest) -> dict:
    folder = request.folder.strip().strip("\"'")
    if not folder:
        raise _error(400, "EMPTY_FOLDER", "Enter a folder path to scan.")
    path = Path(folder).expanduser()
    if not path.is_dir():
        raise _error(
            404, "FOLDER_NOT_FOUND", f"Not a folder (or not readable): {path}"
        )
    try:
        SCANNER.start_scan(str(path), force=request.force)
    except ScanInProgress:
        raise _error(409, "SCAN_IN_PROGRESS", "A scan is already running.")
    return {"started": True}


@app.get("/api/scan/status")
def scan_status() -> dict:
    return SCANNER.status()


@app.post("/api/spotify/playlist")
def spotify_playlist(request: PlaylistRequest) -> dict:
    try:
        playlist_id = parse_playlist_url(request.url)
    except BadPlaylistUrl as exc:
        raise _error(400, "BAD_URL", str(exc))
    try:
        return playlist_fetcher(playlist_id)
    except SpotifyFetchError as exc:
        raise _error(502, "SPOTIFY_FETCH_FAILED", f"{exc} {_PASTE_HINT}")
    except EmbedParseError as exc:
        raise _error(502, "SPOTIFY_PARSE_FAILED", f"{exc} {_PASTE_HINT}")


@app.post("/api/match")
def match(request: MatchRequest) -> dict:
    status = SCANNER.status()
    if status["state"] == "scanning":
        raise _error(409, "SCAN_IN_PROGRESS", "Wait for the scan to finish.")
    if not SCANNER.has_library():
        raise _error(409, "NO_LIBRARY", "Scan a music folder first.")
    if not request.tracks:
        raise _error(400, "NO_TRACKS", "The playlist has no tracks.")
    results = match_playlist(request.tracks, _get_index())
    return {
        "results": [result.model_dump() for result in results],
        "library_size": len(SCANNER.tracks),
    }


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w \-]", "", name, flags=re.ASCII).strip()
    return cleaned or "playlist"


@app.post("/api/export")
def export(request: ExportRequest) -> Response:
    if not SCANNER.has_library():
        raise _error(409, "NO_LIBRARY", "Scan a music folder first.")
    tracks = []
    for track_id in request.track_ids:
        track = SCANNER.by_id.get(track_id)
        if track is None:
            raise _error(400, "UNKNOWN_TRACK", f"Unknown track id {track_id!r}.")
        tracks.append(track)
    if not tracks:
        raise _error(400, "NO_TRACKS", "Nothing selected to export.")

    stem = _safe_filename(request.name)
    if request.format == "m3u8":
        content = build_m3u8(tracks)
        media_type = "audio/x-mpegurl; charset=utf-8"
        filename = f"{stem}.m3u8"
    elif request.format == "xml":
        content = build_rekordbox_xml(request.name, tracks)
        media_type = "application/xml; charset=utf-8"
        filename = f"{stem}.rekordbox.xml"
    else:
        raise _error(400, "BAD_FORMAT", "format must be 'm3u8' or 'xml'.")
    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# When the client has been built (npm run build), serve it so the whole app
# runs from uvicorn alone. Mounted last so /api routes take precedence.
DIST = Path(__file__).resolve().parent.parent / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
