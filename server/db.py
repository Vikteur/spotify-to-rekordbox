"""SQLite-backed library store.

Music lives in named **libraries** — normally one per device ("MacBook",
"Studio PC", "USB drive"). Each library is built from one or more **sources**
(a scanned folder, an imported rekordbox XML), and you match a playlist
against one library at a time.

Track rows are global and keyed by file path, joined to sources through
`track_sources`, so a file shared by several sources is stored once and lives
exactly as long as some source still claims it.

Remembered version choices are scoped per library: the same song resolves to
a different file on each device, so a global preference would have the
devices overwriting each other's choices.

Deliberately stdlib `sqlite3`: no ORM, no migration framework, one file on
disk. A connection is opened per call because scans run on a background
thread and sqlite3 connections are not shareable across threads.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from server.models import LibraryInfo, LibraryTrack, Preference, Source

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "library.db"

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS libraries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,          -- 'folder' | 'xml'
    label      TEXT NOT NULL,          -- folder path, or XML filename
    added_at   TEXT NOT NULL,
    UNIQUE (library_id, kind, label)
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
-- Remembered version choices, per library. Not foreign-keyed to tracks:
-- removing a source must not erase a decision, and track ids derive from file
-- paths, so a choice reapplies unchanged if the file comes back.
CREATE TABLE IF NOT EXISTS preferences (
    library_id INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    id         TEXT NOT NULL,          -- signature_id of the Spotify song
    signature  TEXT NOT NULL,
    artist     TEXT NOT NULL,
    title      TEXT NOT NULL,
    track_id   TEXT NOT NULL,
    chosen_at  TEXT NOT NULL,
    PRIMARY KEY (library_id, id)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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

ACTIVE_LIBRARY = "active_library_id"


class DuplicateLibraryName(Exception):
    pass


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        _migrate(conn)
        conn.executescript(SCHEMA)
        _finish_migration(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _migrate(conn: sqlite3.Connection) -> None:
    """Rename any outdated tables aside; SCHEMA then recreates them."""
    # v1: tracks carried a single source_id instead of a join table.
    if _has_column(conn, "tracks", "source_id"):
        conn.execute("ALTER TABLE tracks RENAME TO tracks_v1")
    # v3: sources and preferences had no library.
    if _table_exists(conn, "sources") and not _has_column(conn, "sources", "library_id"):
        conn.execute("ALTER TABLE sources RENAME TO sources_v3")
    if _table_exists(conn, "preferences") and not _has_column(
        conn, "preferences", "library_id"
    ):
        conn.execute("ALTER TABLE preferences RENAME TO preferences_v3")


def _finish_migration(conn: sqlite3.Connection) -> None:
    # Sources must be restored before track_sources rows can reference them.
    if _table_exists(conn, "sources_v3") or _table_exists(conn, "preferences_v3"):
        # Everything that existed before libraries becomes one default library.
        conn.execute(
            "INSERT OR IGNORE INTO libraries (id, name, created_at) VALUES (1, ?, ?)",
            ("My library", datetime.now(timezone.utc).isoformat()),
        )
        if _table_exists(conn, "sources_v3"):
            conn.executescript(
                """
                INSERT OR IGNORE INTO sources (id, library_id, kind, label, added_at)
                     SELECT id, 1, kind, label, added_at FROM sources_v3;
                DROP TABLE sources_v3;
                """
            )
        if _table_exists(conn, "preferences_v3"):
            conn.executescript(
                """
                INSERT OR IGNORE INTO preferences
                       (library_id, id, signature, artist, title, track_id, chosen_at)
                     SELECT 1, id, signature, artist, title, track_id, chosen_at
                       FROM preferences_v3;
                DROP TABLE preferences_v3;
                """
            )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, '1')",
            (ACTIVE_LIBRARY,),
        )

    if _table_exists(conn, "tracks_v1"):
        conn.executescript(
            f"""
            INSERT OR IGNORE INTO tracks ({", ".join(_COLUMNS)})
                 SELECT {", ".join(_COLUMNS)} FROM tracks_v1;
            INSERT OR IGNORE INTO track_sources (track_id, source_id)
                 SELECT id, source_id FROM tracks_v1;
            DROP TABLE tracks_v1;
            """
        )


# --- libraries -------------------------------------------------------------

def create_library(name: str) -> int:
    name = name.strip()
    with connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO libraries (name, created_at) VALUES (?, ?)",
                (name, datetime.now(timezone.utc).isoformat()),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateLibraryName(f"A library named {name!r} already exists.") from exc
        return int(cursor.lastrowid)


def rename_library(library_id: int, name: str) -> bool:
    name = name.strip()
    with connect() as conn:
        try:
            cursor = conn.execute(
                "UPDATE libraries SET name = ? WHERE id = ?", (name, library_id)
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateLibraryName(f"A library named {name!r} already exists.") from exc
        return cursor.rowcount > 0


def delete_library(library_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
        if cursor.rowcount == 0:
            return False
        conn.execute(_DELETE_ORPHANS)  # cascade removed its sources already
        return True


def list_libraries() -> list[LibraryInfo]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT l.id, l.name, l.created_at, "
            "       COUNT(DISTINCT s.id) AS source_count, "
            "       COUNT(DISTINCT ts.track_id) AS track_count "
            "FROM libraries l "
            "LEFT JOIN sources s ON s.library_id = l.id "
            "LEFT JOIN track_sources ts ON ts.source_id = s.id "
            "GROUP BY l.id ORDER BY l.name"
        ).fetchall()
    return [LibraryInfo(**dict(row)) for row in rows]


def library_exists(library_id: int) -> bool:
    with connect() as conn:
        return (
            conn.execute(
                "SELECT 1 FROM libraries WHERE id = ?", (library_id,)
            ).fetchone()
            is not None
        )


def active_library_id() -> int | None:
    """The selected library, falling back to the only/first one that exists."""
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (ACTIVE_LIBRARY,)
        ).fetchone()
        if row:
            library_id = int(row["value"])
            if conn.execute(
                "SELECT 1 FROM libraries WHERE id = ?", (library_id,)
            ).fetchone():
                return library_id
        fallback = conn.execute("SELECT id FROM libraries ORDER BY id LIMIT 1").fetchone()
        return int(fallback["id"]) if fallback else None


def set_active_library_id(library_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (ACTIVE_LIBRARY, str(library_id)),
        )


# --- sources and tracks ----------------------------------------------------

def upsert_source(library_id: int, kind: str, label: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE library_id = ? AND kind = ? AND label = ?",
            (library_id, kind, label),
        ).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO sources (library_id, kind, label, added_at) VALUES (?, ?, ?, ?)",
            (library_id, kind, label, datetime.now(timezone.utc).isoformat()),
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
    """Every stored file across all libraries (one row per unique path)."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tracks ORDER BY path").fetchall()
    return [_to_track(row) for row in rows]


def library_tracks(library_id: int) -> list[LibraryTrack]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT t.* FROM tracks t "
            "JOIN track_sources ts ON ts.track_id = t.id "
            "JOIN sources s ON s.id = ts.source_id "
            "WHERE s.library_id = ? ORDER BY t.path",
            (library_id,),
        ).fetchall()
    return [_to_track(row) for row in rows]


def list_sources(library_id: int) -> list[Source]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.library_id, s.kind, s.label, s.added_at, "
            "       COUNT(ts.track_id) AS track_count "
            "FROM sources s LEFT JOIN track_sources ts ON ts.source_id = s.id "
            "WHERE s.library_id = ? GROUP BY s.id ORDER BY s.id",
            (library_id,),
        ).fetchall()
    return [Source(**dict(row)) for row in rows]


def source_library_id(source_id: int) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT library_id FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    return int(row["library_id"]) if row else None


def delete_source(source_id: int) -> bool:
    """Remove a source; its tracks stay if another source still claims them."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        if cursor.rowcount == 0:
            return False
        conn.execute(_DELETE_ORPHANS)  # cascade cleared track_sources already
        return True


# --- remembered version choices (per library) ------------------------------

def save_preference(
    library_id: int,
    preference_id: str,
    signature: str,
    artist: str,
    title: str,
    track_id: str,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO preferences "
            "       (library_id, id, signature, artist, title, track_id, chosen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(library_id, id) DO UPDATE SET track_id = excluded.track_id, "
            "    artist = excluded.artist, title = excluded.title, "
            "    chosen_at = excluded.chosen_at",
            (
                library_id,
                preference_id,
                signature,
                artist,
                title,
                track_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def preference_map(library_id: int) -> dict[str, str]:
    """{signature_id: track_id} for this library — what matching applies."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, track_id FROM preferences WHERE library_id = ?", (library_id,)
        ).fetchall()
    return {row["id"]: row["track_id"] for row in rows}


def list_preferences(library_id: int) -> list[Preference]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.id, p.artist, p.title, p.track_id, p.chosen_at, "
            "       t.filename, t.ext "
            "FROM preferences p LEFT JOIN tracks t ON t.id = p.track_id "
            "WHERE p.library_id = ? ORDER BY p.artist, p.title",
            (library_id,),
        ).fetchall()
    return [
        Preference(
            id=row["id"],
            artist=row["artist"],
            title=row["title"],
            track_id=row["track_id"],
            chosen_at=row["chosen_at"],
            file_label=(f"{row['filename']}.{row['ext']}" if row["filename"] else None),
        )
        for row in rows
    ]


def delete_preference(library_id: int, preference_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "DELETE FROM preferences WHERE library_id = ? AND id = ?",
            (library_id, preference_id),
        )
        return cursor.rowcount > 0


def clear_preferences(library_id: int) -> int:
    with connect() as conn:
        return conn.execute(
            "DELETE FROM preferences WHERE library_id = ?", (library_id,)
        ).rowcount


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        is not None
    )


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _to_track(row: sqlite3.Row) -> LibraryTrack:
    return LibraryTrack(**{column: row[column] for column in _COLUMNS})
