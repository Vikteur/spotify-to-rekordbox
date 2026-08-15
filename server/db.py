"""SQLite-backed library store.

The library survives restarts: tracks found by scanning a folder, or imported
from a rekordbox XML export, are written here and the in-memory index is
rebuilt from this file at startup — so you scan once, not every launch.

Deliberately stdlib `sqlite3`: no ORM, no migration framework, one file on
disk. A connection is opened per call because scans run on a background
thread and sqlite3 connections are not shareable across threads.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from server.models import LibraryTrack, Source

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "library.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kind     TEXT NOT NULL,            -- 'folder' | 'xml'
    label    TEXT NOT NULL,            -- folder path, or XML filename
    added_at TEXT NOT NULL,
    UNIQUE (kind, label)
);
CREATE TABLE IF NOT EXISTS tracks (
    id           TEXT PRIMARY KEY,     -- sha1(path)[:12] — also dedupes across sources
    source_id    INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,
    filename     TEXT NOT NULL,
    ext          TEXT NOT NULL,
    artist       TEXT,
    title        TEXT NOT NULL,
    album        TEXT,
    duration_sec REAL,
    bitrate_kbps INTEGER,
    bpm          REAL,
    musical_key  TEXT,
    tag_source   TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    mtime_ms     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS tracks_source ON tracks(source_id);
"""

_COLUMNS = (
    "id", "source_id", "path", "filename", "ext", "artist", "title", "album",
    "duration_sec", "bitrate_kbps", "bpm", "musical_key", "tag_source",
    "size_bytes", "mtime_ms",
)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_source(kind: str, label: str) -> int:
    """Return the id of the (kind, label) source, creating it if needed."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE kind = ? AND label = ?", (kind, label)
        ).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO sources (kind, label, added_at) VALUES (?, ?, ?)",
            (kind, label, datetime.now(timezone.utc).isoformat()),
        )
        return int(cursor.lastrowid)


def replace_source_tracks(source_id: int, tracks: list[LibraryTrack]) -> None:
    placeholders = ", ".join("?" * len(_COLUMNS))
    with connect() as conn:
        conn.execute("DELETE FROM tracks WHERE source_id = ?", (source_id,))
        conn.executemany(
            f"INSERT OR REPLACE INTO tracks ({', '.join(_COLUMNS)}) "
            f"VALUES ({placeholders})",
            [
                tuple(
                    source_id if column == "source_id" else getattr(track, column)
                    for column in _COLUMNS
                )
                for track in tracks
            ],
        )


def source_tracks(source_id: int) -> dict[str, LibraryTrack]:
    """Previously stored tracks for a source, keyed by path (incremental scans)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tracks WHERE source_id = ?", (source_id,)
        ).fetchall()
    return {row["path"]: _to_track(row) for row in rows}


def all_tracks() -> list[LibraryTrack]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tracks ORDER BY path").fetchall()
    return [_to_track(row) for row in rows]


def list_sources() -> list[Source]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.kind, s.label, s.added_at, "
            "       COUNT(t.id) AS track_count "
            "FROM sources s LEFT JOIN tracks t ON t.source_id = s.id "
            "GROUP BY s.id ORDER BY s.id"
        ).fetchall()
    return [Source(**dict(row)) for row in rows]


def delete_source(source_id: int) -> bool:
    with connect() as conn:
        conn.execute("DELETE FROM tracks WHERE source_id = ?", (source_id,))
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return cursor.rowcount > 0


def _to_track(row: sqlite3.Row) -> LibraryTrack:
    return LibraryTrack(**{column: row[column] for column in _COLUMNS})
