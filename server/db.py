"""SQLite-backed library store.

The library survives restarts: tracks found by scanning a folder, or imported
from a rekordbox XML export, are written here and the in-memory index is
rebuilt from this file at startup — so you scan once, not every launch.

A file can legitimately belong to several sources at once (it sits in your
scanned folder *and* in your rekordbox collection), so tracks and sources are
a many-to-many relation via `track_sources`. A track lives exactly as long as
at least one source still claims it.

Deliberately stdlib `sqlite3`: no ORM, no migration framework, one file on
disk. A connection is opened per call because scans run on a background
thread and sqlite3 connections are not shareable across threads.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from server.models import LibraryTrack, Preference, Source

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "library.db"

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kind     TEXT NOT NULL,            -- 'folder' | 'xml'
    label    TEXT NOT NULL,            -- folder path, or XML filename
    added_at TEXT NOT NULL,
    UNIQUE (kind, label)
);
CREATE TABLE IF NOT EXISTS tracks (
    id           TEXT PRIMARY KEY,     -- sha1(path)[:12] — one row per file
    path         TEXT NOT NULL UNIQUE,
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
CREATE TABLE IF NOT EXISTS track_sources (
    track_id  TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    PRIMARY KEY (track_id, source_id)
);
CREATE INDEX IF NOT EXISTS track_sources_source ON track_sources(source_id);
-- Remembered version choices: which of your files a given Spotify song means.
-- Deliberately not foreign-keyed to tracks: removing a source (or unplugging a
-- drive) must not erase a decision you made, since track ids are derived from
-- the file path and come back unchanged when the file does.
CREATE TABLE IF NOT EXISTS preferences (
    id        TEXT PRIMARY KEY,     -- signature_id of the Spotify song
    signature TEXT NOT NULL,
    artist    TEXT NOT NULL,
    title     TEXT NOT NULL,
    track_id  TEXT NOT NULL,
    chosen_at TEXT NOT NULL
);
"""

_COLUMNS = (
    "id", "path", "filename", "ext", "artist", "title", "album",
    "duration_sec", "bitrate_kbps", "bpm", "musical_key", "tag_source",
    "size_bytes", "mtime_ms",
)

# Fields a source may not be able to observe: a folder scan can read tags but
# never BPM or key, so it must not blank out what a rekordbox import supplied.
_PRESERVED = ("bpm", "musical_key")

_UPSERT = f"""
INSERT INTO tracks ({", ".join(_COLUMNS)})
VALUES ({", ".join("?" * len(_COLUMNS))})
ON CONFLICT(id) DO UPDATE SET
{", ".join(
    f"{column} = COALESCE(excluded.{column}, tracks.{column})"
    if column in _PRESERVED
    else f"{column} = excluded.{column}"
    for column in _COLUMNS if column != "id"
)}
"""

_DELETE_ORPHANS = """
DELETE FROM tracks
 WHERE NOT EXISTS (SELECT 1 FROM track_sources WHERE track_id = tracks.id)
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        # v1 stored a single source_id column on tracks; carry that data over
        # instead of making the user rescan.
        legacy = _has_column(conn, "tracks", "source_id")
        if legacy:
            conn.execute("ALTER TABLE tracks RENAME TO tracks_v1")
        conn.executescript(SCHEMA)
        if legacy:
            conn.executescript(
                f"""
                INSERT OR IGNORE INTO tracks ({", ".join(_COLUMNS)})
                     SELECT {", ".join(_COLUMNS)} FROM tracks_v1;
                INSERT OR IGNORE INTO track_sources (track_id, source_id)
                     SELECT id, source_id FROM tracks_v1;
                DROP TABLE tracks_v1;
                """
            )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


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
    """Make `tracks` exactly what this source contributes, leaving others alone."""
    with connect() as conn:
        conn.execute("DELETE FROM track_sources WHERE source_id = ?", (source_id,))
        conn.executemany(
            _UPSERT,
            [tuple(getattr(track, column) for column in _COLUMNS) for track in tracks],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO track_sources (track_id, source_id) VALUES (?, ?)",
            [(track.id, source_id) for track in tracks],
        )
        conn.execute(_DELETE_ORPHANS)


def source_tracks(source_id: int) -> dict[str, LibraryTrack]:
    """This source's tracks keyed by path (used for incremental rescans)."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT t.* FROM tracks t "
            "JOIN track_sources ts ON ts.track_id = t.id "
            "WHERE ts.source_id = ?",
            (source_id,),
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
            "       COUNT(ts.track_id) AS track_count "
            "FROM sources s LEFT JOIN track_sources ts ON ts.source_id = s.id "
            "GROUP BY s.id ORDER BY s.id"
        ).fetchall()
    return [Source(**dict(row)) for row in rows]


def delete_source(source_id: int) -> bool:
    """Remove a source; its tracks stay if another source still claims them."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        if cursor.rowcount == 0:
            return False
        conn.execute(_DELETE_ORPHANS)  # cascade cleared track_sources already
        return True


def save_preference(
    preference_id: str, signature: str, artist: str, title: str, track_id: str
) -> None:
    """Remember (or update) which file this Spotify song should resolve to."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO preferences (id, signature, artist, title, track_id, chosen_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET track_id = excluded.track_id, "
            "    artist = excluded.artist, title = excluded.title, "
            "    chosen_at = excluded.chosen_at",
            (
                preference_id,
                signature,
                artist,
                title,
                track_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def preference_map() -> dict[str, str]:
    """{signature_id: track_id} — what matching applies."""
    with connect() as conn:
        rows = conn.execute("SELECT id, track_id FROM preferences").fetchall()
    return {row["id"]: row["track_id"] for row in rows}


def list_preferences() -> list[Preference]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.id, p.artist, p.title, p.track_id, p.chosen_at, "
            "       t.filename, t.ext "
            "FROM preferences p LEFT JOIN tracks t ON t.id = p.track_id "
            "ORDER BY p.artist, p.title"
        ).fetchall()
    return [
        Preference(
            id=row["id"],
            artist=row["artist"],
            title=row["title"],
            track_id=row["track_id"],
            chosen_at=row["chosen_at"],
            file_label=(
                f"{row['filename']}.{row['ext']}" if row["filename"] else None
            ),
        )
        for row in rows
    ]


def delete_preference(preference_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM preferences WHERE id = ?", (preference_id,))
        return cursor.rowcount > 0


def clear_preferences() -> int:
    with connect() as conn:
        return conn.execute("DELETE FROM preferences").rowcount


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _to_track(row: sqlite3.Row) -> LibraryTrack:
    return LibraryTrack(**{column: row[column] for column in _COLUMNS})
