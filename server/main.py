import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import db
from server.export.m3u8 import build_m3u8
from server.export.rekordbox_xml import build_rekordbox_xml
from server.library import LIBRARY
from server.matcher.index import LibraryIndex
from server.matcher.match import match_playlist
from server.matcher.signature import signature_id, signature_of
from server.models import PlaylistTrackInput
from server.rekordbox_import import RekordboxXmlError, parse_collection
from server.scanner.scan import SCANNER, ScanInProgress
from server.spotify.fetch import SpotifyFetchError, fetch_playlist
from server.spotify.parse_embed import (
    BadPlaylistUrl,
    EmbedParseError,
    parse_playlist_url,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Restore the library from disk so a restart needs no rescan.
    db.init()
    LIBRARY.reload()
    yield


app = FastAPI(title="spotify-to-rekordbox", lifespan=lifespan)

# Module-level so tests can swap in a fixture-backed fake.
playlist_fetcher = fetch_playlist

_PASTE_HINT = "Use the paste-text fallback: one 'Artist - Title' per line."
MAX_XML_BYTES = 256 * 1024 * 1024


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


class PreferenceRequest(BaseModel):
    artist: str = ""
    title: str
    track_id: str


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _count_missing_files(tracks: list) -> int:
    """How many imported paths aren't on this machine (drive not connected?).

    Checks each directory once first: when a whole drive is absent — the common
    case — that answers for every file under it without a stat per track.
    """
    directory_exists: dict[str, bool] = {}
    missing = 0
    for track in tracks:
        parent = os.path.dirname(track.path)
        present = directory_exists.get(parent)
        if present is None:
            present = os.path.isdir(parent)
            directory_exists[parent] = present
        if not present or not os.path.exists(track.path):
            missing += 1
    return missing


_index_cache: tuple[int, LibraryIndex] | None = None


def _get_index() -> LibraryIndex:
    global _index_cache
    generation = LIBRARY.generation
    if _index_cache is None or _index_cache[0] != generation:
        _index_cache = (generation, LibraryIndex(LIBRARY.tracks))
    return _index_cache[1]


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# --- library sources -------------------------------------------------------

@app.get("/api/library")
def library() -> dict:
    return LIBRARY.summary()


@app.delete("/api/library/sources/{source_id}")
def remove_source(source_id: int) -> dict:
    if not db.delete_source(source_id):
        raise _error(404, "NO_SOURCE", f"No library source with id {source_id}.")
    LIBRARY.reload()
    return LIBRARY.summary()


@app.post("/api/library/xml")
async def import_rekordbox_xml(request: Request, name: str = "rekordbox.xml") -> dict:
    """Import a rekordbox collection XML export (raw request body, not multipart)."""
    data = await request.body()
    if not data:
        raise _error(400, "EMPTY_FILE", "No XML content was uploaded.")
    if len(data) > MAX_XML_BYTES:
        raise _error(413, "FILE_TOO_LARGE", "That XML export is unexpectedly large.")
    try:
        tracks, warnings = parse_collection(data)
    except RekordboxXmlError as exc:
        raise _error(400, "BAD_XML", str(exc))

    source_id = db.upsert_source("xml", name)
    db.replace_source_tracks(source_id, tracks)
    LIBRARY.reload()

    missing = _count_missing_files(tracks)
    return {
        "imported": len(tracks),
        "missing_files": missing,
        "warnings": warnings[:20],
        "library": LIBRARY.summary(),
    }


# --- folder scanning -------------------------------------------------------

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


# --- playlist, matching, export --------------------------------------------

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
    if SCANNER.is_scanning():
        raise _error(409, "SCAN_IN_PROGRESS", "Wait for the scan to finish.")
    if not LIBRARY.is_loaded():
        raise _error(
            409,
            "NO_LIBRARY",
            "Add a library first: scan a folder or import a rekordbox XML.",
        )
    if not request.tracks:
        raise _error(400, "NO_TRACKS", "The playlist has no tracks.")
    results = match_playlist(request.tracks, _get_index(), db.preference_map())
    return {
        "results": [result.model_dump() for result in results],
        "library_size": len(LIBRARY.tracks),
    }


# --- remembered version choices --------------------------------------------

@app.get("/api/preferences")
def get_preferences() -> dict:
    return {"preferences": [p.model_dump() for p in db.list_preferences()]}


@app.post("/api/preferences")
def save_preference(request: PreferenceRequest) -> dict:
    """Remember this file as the default for this song from now on."""
    if request.track_id not in LIBRARY.by_id:
        raise _error(400, "UNKNOWN_TRACK", f"Unknown track id {request.track_id!r}.")
    db.save_preference(
        signature_id(request.artist, request.title),
        signature_of(request.artist, request.title),
        request.artist,
        request.title,
        request.track_id,
    )
    return {"preferences": [p.model_dump() for p in db.list_preferences()]}


@app.delete("/api/preferences/{preference_id}")
def forget_preference(preference_id: str) -> dict:
    if not db.delete_preference(preference_id):
        raise _error(404, "NO_PREFERENCE", "No remembered choice with that id.")
    return {"preferences": [p.model_dump() for p in db.list_preferences()]}


@app.delete("/api/preferences")
def forget_all_preferences() -> dict:
    db.clear_preferences()
    return {"preferences": []}


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w \-]", "", name, flags=re.ASCII).strip()
    return cleaned or "playlist"


@app.post("/api/export")
def export(request: ExportRequest) -> Response:
    if not LIBRARY.is_loaded():
        raise _error(409, "NO_LIBRARY", "Add a library first.")
    tracks = []
    for track_id in request.track_ids:
        track = LIBRARY.by_id.get(track_id)
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
