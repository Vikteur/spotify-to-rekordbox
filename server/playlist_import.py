"""Read a playlist exported from rekordbox into a list of entries.

rekordbox offers several export formats and they differ in one way that
matters: M3U8, PLS and XML carry absolute file paths, so entries resolve to
your library exactly. The TXT export carries only columns of metadata — no
paths — so those entries have to be matched by artist and title like a
Spotify track would be.

Encoding is sniffed rather than assumed: rekordbox writes TXT as UTF-16 with
a BOM, while M3U8 is UTF-8.
"""

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from server.rekordbox_import import location_to_path

_PLS_FILE_RE = re.compile(r"^File\d+\s*=\s*(.+)$", re.IGNORECASE)
_EXTINF_RE = re.compile(r"^#EXTINF:[^,]*,(.*)$")
_TITLE_COLUMNS = ("track title", "title", "name", "song")
_ARTIST_COLUMNS = ("artist", "artist name")

# Stricter than a normal match: a wrong resolution here would silently
# promote the wrong version of a song in every future playlist.
RESOLVE_MIN_SCORE = 0.75


class PlaylistImportError(Exception):
    pass


@dataclass(frozen=True)
class PlaylistEntry:
    """One line of a playlist: a path when the format has one, else metadata."""

    path: str | None
    artist: str
    title: str


def decode(data: bytes) -> str:
    for bom, encoding in (
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
        (b"\xef\xbb\xbf", "utf-8-sig"),
    ):
        if data.startswith(bom):
            return data.decode(encoding, errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def parse_playlist(data: bytes, filename: str = "") -> tuple[str, list[PlaylistEntry]]:
    """→ (suggested playlist name, entries). Raises PlaylistImportError."""
    if not data.strip():
        raise PlaylistImportError("That file is empty.")
    text = decode(data)
    stripped = text.lstrip()

    if stripped.startswith("<?xml") or stripped.startswith("<DJ_PLAYLISTS"):
        entries = _parse_xml(text)
    elif stripped.lower().startswith("[playlist]"):
        entries = _parse_pls(text)
    elif "\t" in text.split("\n", 1)[0]:
        entries = _parse_txt(text)
    else:
        entries = _parse_m3u(text)

    if not entries:
        raise PlaylistImportError(
            "No tracks found in that file. Export the playlist from rekordbox "
            "(right-click the playlist > Export) as m3u8, txt, pls or xml."
        )
    return _default_name(filename), entries


def _default_name(filename: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename.strip()) or "Imported playlist"
    return stem


def _split_label(label: str) -> tuple[str, str]:
    for separator in (" - ", " – ", " — "):
        if separator in label:
            artist, title = label.split(separator, 1)
            return artist.strip(), title.strip()
    return "", label.strip()


def _parse_m3u(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            match = _EXTINF_RE.match(line)
            if match:
                pending = match.group(1).strip()
            continue
        artist, title = _split_label(pending) if pending else ("", "")
        path = location_to_path(line) if line.lower().startswith("file://") else line
        entries.append(PlaylistEntry(path=path, artist=artist, title=title))
        pending = ""
    return entries


def _parse_pls(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    for raw in text.splitlines():
        match = _PLS_FILE_RE.match(raw.strip())
        if match:
            value = match.group(1).strip()
            path = location_to_path(value) if value.lower().startswith("file://") else value
            entries.append(PlaylistEntry(path=path, artist="", title=""))
    return entries


def _parse_xml(text: str) -> list[PlaylistEntry]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise PlaylistImportError(f"not valid XML: {exc}") from exc
    entries: list[PlaylistEntry] = []
    for element in root.iter("TRACK"):
        location = element.get("Location")
        if not location:
            continue  # a PLAYLISTS key reference, not a collection entry
        entries.append(
            PlaylistEntry(
                path=location_to_path(location),
                artist=(element.get("Artist") or "").strip(),
                title=(element.get("Name") or "").strip(),
            )
        )
    return entries


def resolve_entries(entries, index, by_id: dict) -> tuple[list[str], list[PlaylistEntry]]:
    """Turn playlist entries into library track ids.

    Paths resolve exactly. Entries without one (the TXT export) fall back to
    the same fuzzy matching a Spotify track gets, at a stricter threshold —
    a wrong assignment here would silently promote the wrong version later.
    """
    from server.matcher.match import match_one
    from server.models import PlaylistTrackInput
    from server.scanner.tags import track_id as id_for_path

    resolved: list[str] = []
    missing: list[PlaylistEntry] = []
    seen: set[str] = set()
    for entry in entries:
        track_id = None
        if entry.path:
            candidate = id_for_path(entry.path)
            if candidate in by_id:
                track_id = candidate
        if track_id is None and (entry.title or entry.artist):
            result = match_one(
                PlaylistTrackInput(index=0, artist=entry.artist, title=entry.title),
                index,
            )
            if result.candidates and result.candidates[0].score >= RESOLVE_MIN_SCORE:
                track_id = result.candidates[0].track.id
        if track_id is None:
            missing.append(entry)
        elif track_id not in seen:
            seen.add(track_id)
            resolved.append(track_id)
    return resolved, missing


def _parse_txt(text: str) -> list[PlaylistEntry]:
    """rekordbox's tab-separated export: a header row, then one row per track."""
    rows = [line for line in text.splitlines() if line.strip()]
    if not rows:
        return []
    header = [cell.strip().lower().lstrip("﻿#").strip() for cell in rows[0].split("\t")]

    def column(names: tuple[str, ...]) -> int | None:
        for index, cell in enumerate(header):
            if cell in names:
                return index
        return None

    title_at = column(_TITLE_COLUMNS)
    artist_at = column(_ARTIST_COLUMNS)
    location_at = column(("location", "file", "path", "folder"))
    if title_at is None:
        raise PlaylistImportError(
            "That looks like a rekordbox TXT export but has no 'Track Title' "
            "column — re-export it with the title and artist columns visible."
        )

    entries: list[PlaylistEntry] = []
    for line in rows[1:]:
        cells = line.split("\t")
        if len(cells) <= title_at:
            continue
        title = cells[title_at].strip()
        if not title:
            continue
        artist = cells[artist_at].strip() if artist_at is not None and len(cells) > artist_at else ""
        path = None
        if location_at is not None and len(cells) > location_at:
            candidate = cells[location_at].strip()
            if candidate:
                path = (
                    location_to_path(candidate)
                    if candidate.lower().startswith("file://")
                    else candidate
                )
        entries.append(PlaylistEntry(path=path, artist=artist, title=title))
    return entries
