import hashlib
from pathlib import Path

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.easymp4 import EasyMP4Tags

from server.models import LibraryTrack
from server.scanner.filename_parse import parse_filename

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".aiff", ".aif"}
DRM_EXTS = {".m4p"}
_EXT_CANONICAL = {"aif": "aiff"}


def _register_dj_tags() -> None:
    """Teach mutagen's "easy" interface the BPM/key fields DJ tools write.

    `bpm` is already known for ID3 (TBPM) and MP4 (tmpo), but musical key is
    not exposed at all: rekordbox and Serato write ID3 TKEY, Mixed In Key
    writes TXXX:INITIALKEY, and MP4 uses an iTunes freeform atom.
    """
    EasyID3.RegisterTextKey("initialkey", "TKEY")
    EasyID3.RegisterTXXXKey("initialkey_txxx", "INITIALKEY")
    try:
        EasyMP4Tags.RegisterFreeformKey("initialkey", "initialkey")
    except Exception:  # older mutagen without freeform registration
        pass


_register_dj_tags()

# Vorbis/FLAC comments are free-form, so the same names work there directly.
_BPM_TAGS = ("bpm", "tempo")
_KEY_TAGS = ("initialkey", "initialkey_txxx", "key")


def track_id(path: str) -> str:
    """A stable per-path id (48 bits of sha1(path)).

    Not assumed globally unique: `path` carries its own UNIQUE constraint, so a
    (astronomically unlikely) id collision between two distinct paths surfaces
    as an IntegrityError on insert rather than silently overwriting a row.
    """
    return hashlib.sha1(path.encode("utf-8")).hexdigest()[:12]


def _first(value: object) -> str | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _lookup(tags: object, names: tuple[str, ...]) -> str | None:
    for name in names:
        try:
            value = _first(tags.get(name))
        except Exception:  # some tag containers raise on unknown keys
            continue
        if value:
            return value
    return None


def _read_bpm(tags: object) -> float | None:
    raw = _lookup(tags, _BPM_TAGS)
    if raw is None:
        return None
    try:
        bpm = float(raw.replace(",", "."))
    except ValueError:
        return None
    # 0 is how taggers spell "not analysed"; absurd values are junk.
    return round(bpm, 2) if 20 <= bpm <= 300 else None


def _read_key(tags: object) -> str | None:
    key = _lookup(tags, _KEY_TAGS)
    return key[:16] if key else None


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
    bpm = None
    musical_key = None
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
            bpm = _read_bpm(tags)
            musical_key = _read_key(tags)

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
            bpm=bpm,
            musical_key=musical_key,
            tag_source=tag_source,
            size_bytes=stat.st_size,
            mtime_ms=int(stat.st_mtime * 1000),
        ),
        error,
    )
