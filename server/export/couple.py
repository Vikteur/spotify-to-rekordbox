"""Per-couple export: one rekordbox folder holding one playlist per chapter.

The DJ's routine per wedding is a handful of separate rekordbox playlists —
the opening number alone in its own list (so it can never be confused with
anything else on the night), then the first tracks, their top 20, the friends'
top 20. The couple already fills in exactly those buckets, so this turns them
into one importable file instead of an export-and-rename per chapter.

Numbering the playlists keeps rekordbox's alphabetical sort in running order.
"""

from server.couples import LIST_LABELS
from server.models import PlaylistTrackInput

# Export order = the order of the night. `never` is deliberately absent: it is
# a filter applied to every other chapter, not a playlist to hand the decks.
CHAPTER_ORDER = (
    "opening_dance",
    "second_third",
    "couple_top20",
    "friends_top20",
    "must_plays",
    "playlist_links",
)


def chapter_name(position: int, kind: str) -> str:
    """'01 Opening dance' — the prefix keeps rekordbox's A-Z sort in set order."""
    return f"{position:02d} {LIST_LABELS.get(kind, kind)}"


def folder_label(names: str, wedding_date: str) -> str:
    """'Sofie & Jan 2026-09-12' — one folder per wedding, sorted by couple."""
    return f"{names.strip() or 'Couple'} {wedding_date}".strip()


def entry_inputs(entries: list[dict]) -> list[PlaylistTrackInput]:
    """Chapter entries as matcher input, in their stored order.

    A guest may type a song instead of picking one from Spotify, so `free_text`
    stands in when there is no `title`. Entries with neither are dropped: an
    empty row is a slot the couple never filled, not a missing song.
    """
    inputs: list[PlaylistTrackInput] = []
    for index, entry in enumerate(entries):
        title = (entry.get("title") or entry.get("free_text") or "").strip()
        if not title:
            continue
        duration_ms = entry.get("duration_ms")
        inputs.append(
            PlaylistTrackInput(
                index=index,
                artist=(entry.get("artist") or "").strip(),
                title=title,
                duration_sec=duration_ms / 1000 if duration_ms else None,
            )
        )
    return inputs
