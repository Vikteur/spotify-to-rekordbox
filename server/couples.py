"""Wedding-couple intake: couples, their song lists, and guest access.

A **couple** is created by the DJ. The couple answers the intake flow (opening
dance, second/third song, their top 20, friends' top 20, never list, finale)
through a magic link; their friends get a second link scoped to the friends
list only. Nothing here touches audio — every entry is Spotify *metadata*
(or free text), later matched against the DJ's local library.

Access model
    Two bearer tokens per couple, carried in the URL path (`/g/<token>`):
    - couple token: read/write everything on this couple record
    - friends token: append to the friends' top 20 and read only that list
    Tokens are long random secrets (256-bit, `secrets.token_urlsafe`), expire
    once the wedding date has passed, can be revoked, and can be rotated
    (rotation issues a fresh link and un-revokes).

Write model
    Entries are keyed by a **client-generated uid**, so every save is an
    idempotent upsert: autosave can fire the same PUT twice (retry, tab
    close, flaky phone network) without duplicating a song. Slotted lists
    (top 20s, must-plays…) address rows by `position`; when two friends race
    for the same empty row the second lands on the next free one.

Every write is recorded in `couple_changes` with the token kind that made it,
so the DJ can see where a song came from.
"""

import secrets
import sqlite3
from datetime import date, datetime, timezone

from server.db import connect
from server.matcher.normalize import normalize
from server.matcher.versions import extract_version

SCHEMA = """
CREATE TABLE IF NOT EXISTS couples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    names           TEXT NOT NULL,           -- "Sofie & Jan"
    wedding_date    TEXT NOT NULL,           -- ISO date; tokens die after it
    briefing_text   TEXT NOT NULL DEFAULT '',-- "how we party", shown to the DJ
    couple_token    TEXT NOT NULL UNIQUE,
    friends_token   TEXT NOT NULL UNIQUE,
    couple_revoked  INTEGER NOT NULL DEFAULT 0,
    friends_revoked INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS couple_entries (
    uid          TEXT PRIMARY KEY,           -- client-generated: upserts are idempotent
    couple_id    INTEGER NOT NULL REFERENCES couples(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,              -- opening_dance | second_third | ...
    position     INTEGER NOT NULL,           -- slot/row in the list
    spotify_id   TEXT,                       -- NULL = free-text fallback (unmatched)
    isrc         TEXT,
    title        TEXT NOT NULL,
    artist       TEXT NOT NULL DEFAULT '',
    duration_ms  INTEGER,
    art_url      TEXT,
    free_text    TEXT,                       -- what they typed when not on Spotify
    note         TEXT,                       -- per-entry note to the DJ
    start_pref   TEXT,                       -- opening dance: top | chorus | fade
    source_token_kind TEXT NOT NULL,         -- couple | friend | dj
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS couple_entries_list ON couple_entries(couple_id, kind, position);
-- The never list is a blocklist, not a playlist: it never loads as tracks and
-- its songs are excluded from every export for this couple.
CREATE TABLE IF NOT EXISTS couple_blocklist (
    uid          TEXT PRIMARY KEY,
    couple_id    INTEGER NOT NULL REFERENCES couples(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    spotify_id   TEXT,
    isrc         TEXT,
    title        TEXT NOT NULL,
    artist       TEXT NOT NULL DEFAULT '',
    duration_ms  INTEGER,
    art_url      TEXT,
    free_text    TEXT,
    source_token_kind TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS couple_blocklist_couple ON couple_blocklist(couple_id, position);
CREATE TABLE IF NOT EXISTS couple_changes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    couple_id  INTEGER NOT NULL REFERENCES couples(id) ON DELETE CASCADE,
    token_kind TEXT NOT NULL,                -- couple | friend | dj
    action     TEXT NOT NULL,                -- added | updated | removed | reordered | details
    kind       TEXT,                         -- list kind (NULL for couple-record edits)
    uid        TEXT,
    summary    TEXT NOT NULL,                -- human line for the DJ's log
    at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS couple_changes_couple ON couple_changes(couple_id, id);
"""

# Chapter lists and their row counts. None = unbounded (append-only order).
LIST_KINDS: dict[str, int | None] = {
    "opening_dance": 1,
    "second_third": 2,
    "couple_top20": 20,
    "friends_top20": 20,
    "must_plays": 5,
    "playlist_links": None,
}

LIST_LABELS = {
    "opening_dance": "Opening dance",
    "second_third": "Second & third song",
    "couple_top20": "Their top 20",
    "friends_top20": "Friends' top 20",
    "must_plays": "Must-plays",
    "playlist_links": "Playlist links",
    "never": "Never list",
}

START_PREFS = ("top", "chorus", "fade")

ENTRY_COLUMNS = (
    "uid", "couple_id", "kind", "position", "spotify_id", "isrc", "title",
    "artist", "duration_ms", "art_url", "free_text", "note", "start_pref",
    "source_token_kind", "created_at", "updated_at",
)

BLOCK_COLUMNS = (
    "uid", "couple_id", "position", "spotify_id", "isrc", "title", "artist",
    "duration_ms", "art_url", "free_text", "source_token_kind", "created_at",
)


class CoupleError(Exception):
    """A domain rule was broken; `code` maps onto an HTTP error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise CoupleError("BAD_DATE", "Wedding date must be YYYY-MM-DD.") from exc


# --- couples ----------------------------------------------------------------

def create_couple(names: str, wedding_date: str) -> int:
    names = names.strip()
    if not names:
        raise CoupleError("EMPTY_NAMES", "Give the couple a name, e.g. “Sofie & Jan”.")
    _parse_date(wedding_date)
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO couples (names, wedding_date, couple_token, friends_token,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (names, wedding_date.strip(), _new_token(), _new_token(), _now()),
        )
        return int(cursor.lastrowid)


def get_couple(couple_id: int) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM couples WHERE id = ?", (couple_id,)
        ).fetchone()


def update_couple(
    couple_id: int,
    *,
    names: str | None = None,
    wedding_date: str | None = None,
    briefing_text: str | None = None,
) -> bool:
    sets, values = [], []
    if names is not None:
        if not names.strip():
            raise CoupleError("EMPTY_NAMES", "Names can't be empty.")
        sets.append("names = ?")
        values.append(names.strip())
    if wedding_date is not None:
        _parse_date(wedding_date)
        sets.append("wedding_date = ?")
        values.append(wedding_date.strip())
    if briefing_text is not None:
        sets.append("briefing_text = ?")
        values.append(briefing_text)
    if not sets:
        return True
    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE couples SET {', '.join(sets)} WHERE id = ?",
            (*values, couple_id),
        )
        return cursor.rowcount > 0


def delete_couple(couple_id: int) -> bool:
    with connect() as conn:
        return conn.execute(
            "DELETE FROM couples WHERE id = ?", (couple_id,)
        ).rowcount > 0


def list_couples() -> list[dict]:
    """Every couple with per-chapter song counts, newest wedding first."""
    with connect() as conn:
        couples = conn.execute(
            "SELECT * FROM couples ORDER BY wedding_date DESC, id DESC"
        ).fetchall()
        entry_counts = conn.execute(
            "SELECT couple_id, kind, COUNT(*) AS n FROM couple_entries"
            " GROUP BY couple_id, kind"
        ).fetchall()
        block_counts = conn.execute(
            "SELECT couple_id, COUNT(*) AS n FROM couple_blocklist GROUP BY couple_id"
        ).fetchall()
        last_changes = conn.execute(
            "SELECT couple_id, MAX(at) AS at FROM couple_changes GROUP BY couple_id"
        ).fetchall()
    by_couple: dict[int, dict[str, int]] = {}
    for row in entry_counts:
        by_couple.setdefault(row["couple_id"], {})[row["kind"]] = row["n"]
    blocks = {row["couple_id"]: row["n"] for row in block_counts}
    changed = {row["couple_id"]: row["at"] for row in last_changes}
    return [
        {
            "id": row["id"],
            "names": row["names"],
            "wedding_date": row["wedding_date"],
            "created_at": row["created_at"],
            "counts": {
                **{kind: by_couple.get(row["id"], {}).get(kind, 0) for kind in LIST_KINDS},
                "never": blocks.get(row["id"], 0),
            },
            "song_count": sum(by_couple.get(row["id"], {}).values()),
            "last_change_at": changed.get(row["id"]),
        }
        for row in couples
    ]


# --- tokens -----------------------------------------------------------------

def _token_column(token_kind: str) -> tuple[str, str]:
    if token_kind == "couple":
        return "couple_token", "couple_revoked"
    if token_kind == "friends":
        return "friends_token", "friends_revoked"
    raise CoupleError("BAD_TOKEN_KIND", "Token kind must be 'couple' or 'friends'.")


def rotate_token(couple_id: int, token_kind: str) -> bool:
    """Issue a fresh link. The old token dies; a revoked link comes back alive."""
    token_col, revoked_col = _token_column(token_kind)
    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE couples SET {token_col} = ?, {revoked_col} = 0 WHERE id = ?",
            (_new_token(), couple_id),
        )
        return cursor.rowcount > 0


def set_revoked(couple_id: int, token_kind: str, revoked: bool) -> bool:
    token_col, revoked_col = _token_column(token_kind)
    del token_col
    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE couples SET {revoked_col} = ? WHERE id = ?",
            (1 if revoked else 0, couple_id),
        )
        return cursor.rowcount > 0


def token_expired(couple: sqlite3.Row, today: date | None = None) -> bool:
    """Links stop working the day after the wedding (the day itself still counts)."""
    return (today or date.today()) > _parse_date(couple["wedding_date"])


def find_by_token(token: str) -> tuple[sqlite3.Row, str] | None:
    """(couple row, 'couple'|'friends') for a live token — else None."""
    if not token:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM couples WHERE couple_token = ? OR friends_token = ?",
            (token, token),
        ).fetchone()
    if row is None:
        return None
    kind = "couple" if secrets.compare_digest(row["couple_token"], token) else "friends"
    return row, kind


# --- entries ----------------------------------------------------------------

def _entry_dict(row: sqlite3.Row) -> dict:
    entry = {column: row[column] for column in ENTRY_COLUMNS if column != "couple_id"}
    return entry


def _block_dict(row: sqlite3.Row) -> dict:
    return {column: row[column] for column in BLOCK_COLUMNS if column != "couple_id"}


def list_entries(couple_id: int, kind: str | None = None) -> dict[str, list[dict]]:
    """Entries grouped by kind ({kind: [...]}, ordered by position)."""
    with connect() as conn:
        if kind is None:
            rows = conn.execute(
                "SELECT * FROM couple_entries WHERE couple_id = ?"
                " ORDER BY kind, position, created_at",
                (couple_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM couple_entries WHERE couple_id = ? AND kind = ?"
                " ORDER BY position, created_at",
                (couple_id, kind),
            ).fetchall()
    grouped: dict[str, list[dict]] = {k: [] for k in ([kind] if kind else LIST_KINDS)}
    for row in rows:
        grouped.setdefault(row["kind"], []).append(_entry_dict(row))
    return grouped


def upsert_entry(couple_id: int, uid: str, fields: dict, token_kind: str) -> dict:
    """Idempotently create or update one entry; returns the stored entry.

    New entries take the requested position when that slot is free, otherwise
    the first free slot (two friends typing into the same row must not clobber
    each other). Updates keep their position — moving rows is `reorder()`.
    """
    kind = fields.get("kind")
    if kind not in LIST_KINDS:
        raise CoupleError("BAD_KIND", f"Unknown list kind {kind!r}.")
    cap = LIST_KINDS[kind]
    title = (fields.get("title") or "").strip()
    free_text = (fields.get("free_text") or "").strip() or None
    if not title and free_text:
        title = free_text
    if not title:
        raise CoupleError("EMPTY_TITLE", "Pick a song or type one in first.")
    start_pref = fields.get("start_pref")
    if start_pref is not None and start_pref not in START_PREFS:
        raise CoupleError("BAD_START_PREF", "Start preference must be top, chorus or fade.")

    now = _now()
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM couple_entries WHERE uid = ?", (uid,)
        ).fetchone()
        if existing is not None and (
            existing["couple_id"] != couple_id or existing["kind"] != kind
        ):
            raise CoupleError("UID_CONFLICT", "That entry belongs to another list.")

        if existing is None:
            position = _free_position(conn, couple_id, kind, cap, fields.get("position"))
            conn.execute(
                "INSERT INTO couple_entries (uid, couple_id, kind, position,"
                " spotify_id, isrc, title, artist, duration_ms, art_url, free_text,"
                " note, start_pref, source_token_kind, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid, couple_id, kind, position,
                    fields.get("spotify_id"), fields.get("isrc"), title,
                    (fields.get("artist") or "").strip(), fields.get("duration_ms"),
                    fields.get("art_url"), free_text, fields.get("note"),
                    start_pref, token_kind, now, now,
                ),
            )
        else:
            conn.execute(
                "UPDATE couple_entries SET spotify_id = ?, isrc = ?, title = ?,"
                " artist = ?, duration_ms = ?, art_url = ?, free_text = ?, note = ?,"
                " start_pref = ?, updated_at = ? WHERE uid = ?",
                (
                    fields.get("spotify_id"), fields.get("isrc"), title,
                    (fields.get("artist") or "").strip(), fields.get("duration_ms"),
                    fields.get("art_url"), free_text, fields.get("note"),
                    start_pref, now, uid,
                ),
            )
        row = conn.execute(
            "SELECT * FROM couple_entries WHERE uid = ?", (uid,)
        ).fetchone()
    return _entry_dict(row)


def _free_position(
    conn: sqlite3.Connection,
    couple_id: int,
    kind: str,
    cap: int | None,
    requested: int | None,
) -> int:
    taken = {
        row["position"]
        for row in conn.execute(
            "SELECT position FROM couple_entries WHERE couple_id = ? AND kind = ?",
            (couple_id, kind),
        ).fetchall()
    }
    if cap is None:  # append-only list
        return max(taken, default=-1) + 1
    if requested is not None and 0 <= requested < cap and requested not in taken:
        return requested
    for slot in range(cap):
        if slot not in taken:
            return slot
    label = LIST_LABELS.get(kind, kind)
    raise CoupleError("LIST_FULL", f"{label} is full — all {cap} spots are taken.")


def entry_owner(uid: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM couple_entries WHERE uid = ?", (uid,)
        ).fetchone()


def delete_entry(couple_id: int, uid: str) -> dict | None:
    """Remove one entry; returns what was removed (for the change log)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM couple_entries WHERE uid = ? AND couple_id = ?",
            (uid, couple_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM couple_entries WHERE uid = ?", (uid,))
    return _entry_dict(row)


def reorder(couple_id: int, kind: str, positions: list[dict]) -> None:
    """Apply an explicit {uid: position} mapping for one list (couple/DJ only)."""
    if kind not in LIST_KINDS:
        raise CoupleError("BAD_KIND", f"Unknown list kind {kind!r}.")
    cap = LIST_KINDS[kind]
    seen_positions: set[int] = set()
    for item in positions:
        position = item.get("position")
        if not isinstance(position, int) or position < 0:
            raise CoupleError("BAD_POSITION", "Positions must be non-negative integers.")
        if cap is not None and position >= cap:
            raise CoupleError("BAD_POSITION", f"Position {position} is past the last row.")
        if position in seen_positions:
            raise CoupleError("BAD_POSITION", "Two songs can't share one row.")
        seen_positions.add(position)
    with connect() as conn:
        owned = {
            row["uid"]
            for row in conn.execute(
                "SELECT uid FROM couple_entries WHERE couple_id = ? AND kind = ?",
                (couple_id, kind),
            ).fetchall()
        }
        for item in positions:
            if item["uid"] not in owned:
                raise CoupleError("UNKNOWN_ENTRY", "That song isn't in this list.")
        now = _now()
        conn.executemany(
            "UPDATE couple_entries SET position = ?, updated_at = ? WHERE uid = ?",
            [(item["position"], now, item["uid"]) for item in positions],
        )


# --- never list (blocklist) -------------------------------------------------

def list_blocklist(couple_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM couple_blocklist WHERE couple_id = ?"
            " ORDER BY position, created_at",
            (couple_id,),
        ).fetchall()
    return [_block_dict(row) for row in rows]


def upsert_block(couple_id: int, uid: str, fields: dict, token_kind: str) -> dict:
    title = (fields.get("title") or "").strip()
    free_text = (fields.get("free_text") or "").strip() or None
    if not title and free_text:
        title = free_text
    if not title:
        raise CoupleError("EMPTY_TITLE", "Pick a song or type one in first.")
    now = _now()
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM couple_blocklist WHERE uid = ?", (uid,)
        ).fetchone()
        if existing is not None and existing["couple_id"] != couple_id:
            raise CoupleError("UID_CONFLICT", "That entry belongs to another couple.")
        if existing is None:
            position = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM couple_blocklist"
                " WHERE couple_id = ?",
                (couple_id,),
            ).fetchone()["next"]
            conn.execute(
                "INSERT INTO couple_blocklist (uid, couple_id, position, spotify_id,"
                " isrc, title, artist, duration_ms, art_url, free_text,"
                " source_token_kind, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid, couple_id, position, fields.get("spotify_id"),
                    fields.get("isrc"), title, (fields.get("artist") or "").strip(),
                    fields.get("duration_ms"), fields.get("art_url"), free_text,
                    token_kind, now,
                ),
            )
        else:
            conn.execute(
                "UPDATE couple_blocklist SET spotify_id = ?, isrc = ?, title = ?,"
                " artist = ?, duration_ms = ?, art_url = ?, free_text = ? WHERE uid = ?",
                (
                    fields.get("spotify_id"), fields.get("isrc"), title,
                    (fields.get("artist") or "").strip(), fields.get("duration_ms"),
                    fields.get("art_url"), free_text, uid,
                ),
            )
        row = conn.execute(
            "SELECT * FROM couple_blocklist WHERE uid = ?", (uid,)
        ).fetchone()
    return _block_dict(row)


def delete_block(couple_id: int, uid: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM couple_blocklist WHERE uid = ? AND couple_id = ?",
            (uid, couple_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM couple_blocklist WHERE uid = ?", (uid,))
    return _block_dict(row)


def _block_key(artist: str, title: str) -> tuple[str, str]:
    """Version-agnostic identity: a never-list song blocks *every* version."""
    parts = extract_version(title)
    return normalize(artist or ""), normalize(parts.core_title)


def blocked_keys(couple_id: int) -> set[tuple[str, str]]:
    return {
        _block_key(entry["artist"], entry["title"])
        for entry in list_blocklist(couple_id)
    }


def is_blocked(artist: str | None, title: str, keys: set[tuple[str, str]]) -> bool:
    """True when (artist, any version of title) is on the never list.

    A blocklist entry without an artist blocks by title alone — for a no-go
    list, over-blocking beats letting the song through.
    """
    if not keys:
        return False
    norm_artist, core = _block_key(artist or "", title)
    return (norm_artist, core) in keys or ("", core) in keys


# --- change log -------------------------------------------------------------

def log_change(
    couple_id: int,
    token_kind: str,
    action: str,
    summary: str,
    *,
    kind: str | None = None,
    uid: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO couple_changes (couple_id, token_kind, action, kind, uid,"
            " summary, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (couple_id, token_kind, action, kind, uid, summary, _now()),
        )


def list_changes(couple_id: int, limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT token_kind, action, kind, uid, summary, at FROM couple_changes"
            " WHERE couple_id = ? ORDER BY id DESC LIMIT ?",
            (couple_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]
