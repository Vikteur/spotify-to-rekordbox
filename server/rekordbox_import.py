"""Import a rekordbox collection XML export as a library source.

In rekordbox: File > Export Collection in xml format. The result carries every
track rekordbox knows about — including files on drives that aren't currently
connected — plus rekordbox's own metadata (BPM, key), which is better than
whatever the file tags happen to say.

Parsing is streamed with iterparse: a 20k-track export with beatgrids and cue
points runs to tens of megabytes, and we only need the TRACK attributes.
"""

import io
import re
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import unquote

from server.models import LibraryTrack
from server.scanner.tags import AUDIO_EXTS, track_id

_DRIVE_RE = re.compile(r"^[A-Za-z]:$")
_LOCATION_PREFIXES = ("file://localhost/", "file:///", "file://")


class RekordboxXmlError(Exception):
    pass


def location_to_path(location: str) -> str:
    """'file://localhost/C:/M%C3%BAsica/T%C3%A9%20st.mp3' → 'C:\\Música\\Té st.mp3'.

    The exact inverse of export.rekordbox_xml.path_to_location: percent-decode
    each segment, and rebuild Windows paths with backslashes so the result
    matches what the filesystem (and rekordbox) actually expects.
    """
    rest = location
    for prefix in _LOCATION_PREFIXES:
        if rest.startswith(prefix):
            rest = rest[len(prefix):]
            break
    segments = [unquote(segment) for segment in rest.split("/")]
    if segments and _DRIVE_RE.match(segments[0]):
        return "\\".join(segments)
    return "/" + "/".join(segment for segment in segments if segment)


def _float_or_none(value: str | None) -> float | None:
    try:
        parsed = float(value) if value else 0.0
    except ValueError:
        return None
    return parsed or None


def _int_or_none(value: str | None) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _title_of(element: ET.Element) -> str:
    """rekordbox sometimes splits the version off into a `Mix` attribute."""
    name = (element.get("Name") or "").strip()
    mix = (element.get("Mix") or "").strip()
    if mix and mix.lower() not in name.lower():
        return f"{name} ({mix})"
    return name


def parse_collection(data: bytes) -> tuple[list[LibraryTrack], list[str]]:
    """→ (tracks, warnings). Raises RekordboxXmlError on unusable input."""
    tracks: list[LibraryTrack] = []
    warnings: list[str] = []
    seen_paths: set[str] = set()
    saw_root = False

    try:
        for _, element in ET.iterparse(io.BytesIO(data), events=("end",)):
            if element.tag == "DJ_PLAYLISTS":
                saw_root = True
            if element.tag != "TRACK":
                continue
            # PLAYLISTS nodes also contain <TRACK Key="..."/> entries; only
            # COLLECTION entries carry a Location.
            location = element.get("Location")
            if not location:
                continue

            path = location_to_path(location)
            if path in seen_paths:
                element.clear()
                continue
            seen_paths.add(path)

            pure = PureWindowsPath(path) if _DRIVE_RE.match(path[:2]) else PurePosixPath(path)
            ext = pure.suffix.lower().lstrip(".")
            if f".{ext}" not in AUDIO_EXTS:
                warnings.append(f"skipped non-audio entry: {pure.name}")
                element.clear()
                continue

            title = _title_of(element) or pure.stem
            tracks.append(
                LibraryTrack(
                    id=track_id(path),
                    path=path,
                    filename=pure.stem,
                    ext="aiff" if ext == "aif" else ext,
                    artist=(element.get("Artist") or "").strip() or None,
                    title=title,
                    album=(element.get("Album") or "").strip() or None,
                    duration_sec=_float_or_none(element.get("TotalTime")),
                    bitrate_kbps=_int_or_none(element.get("BitRate")),
                    bpm=_float_or_none(element.get("AverageBpm")),
                    musical_key=(element.get("Tonality") or "").strip() or None,
                    tag_source="rekordbox",
                    size_bytes=_int_or_none(element.get("Size")) or 0,
                    mtime_ms=0,  # not present in the export
                )
            )
            element.clear()
    except ET.ParseError as exc:
        raise RekordboxXmlError(f"not valid XML: {exc}") from exc

    if not saw_root and not tracks:
        raise RekordboxXmlError(
            "no rekordbox collection found — expected a DJ_PLAYLISTS file "
            "exported via File > Export Collection in xml format"
        )
    if not tracks:
        raise RekordboxXmlError("the collection in this XML file is empty")
    return tracks, warnings
