import hashlib
from pathlib import Path

import mutagen

from server.models import LibraryTrack
from server.scanner.filename_parse import parse_filename

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif"}
DRM_EXTS = {".m4p"}
_EXT_CANONICAL = {"aif": "aiff"}


def track_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def _first(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_track(path: Path) -> tuple[LibraryTrack, str | None]:
    """Read one audio file into a LibraryTrack.

    Files mutagen cannot parse still become tracks via the filename (rekordbox
    may still play them); the returned error string reports the parse problem.
    """
    stat = path.stat()
    error: str | None = None
    audio = None
    try:
        audio = mutagen.File(path, easy=True)
    except Exception as exc:  # mutagen raises assorted format errors
        error = f"{path.name}: {exc}"
    if audio is None and error is None:
        error = f"{path.name}: unrecognized or corrupt audio file"

    artist = title = album = None
    duration_sec = None
    bitrate_kbps = None
    if audio is not None:
        info = getattr(audio, "info", None)
        length = float(getattr(info, "length", 0) or 0)
        duration_sec = round(length, 1) if length > 0 else None
        bitrate = getattr(info, "bitrate", 0) or 0
        bitrate_kbps = round(bitrate / 1000) if bitrate else None
        tags = audio.tags
        if tags:
            artist = _first(tags.get("artist"))
            title = _first(tags.get("title"))
            album = _first(tags.get("album"))

    if title:
        tag_source = "tags"
    else:
        tag_source = "filename"
        artist, title = parse_filename(path.stem)

    ext = path.suffix.lower().lstrip(".")
    return (
        LibraryTrack(
            id=track_id(str(path)),
            path=str(path),
            filename=path.stem,
            ext=_EXT_CANONICAL.get(ext, ext),
            artist=artist,
            title=title,
            album=album,
            duration_sec=duration_sec,
            bitrate_kbps=bitrate_kbps,
            tag_source=tag_source,
            size_bytes=stat.st_size,
            mtime_ms=int(stat.st_mtime * 1000),
        ),
        error,
    )
