from pathlib import Path

import pytest

from server import db
from server.matcher.index import LibraryIndex
from server.matcher.match import match_one
from server.playlist_import import (
    PlaylistImportError,
    parse_playlist,
    resolve_entries,
)
from tests.test_matcher import LIBRARY, query


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()


@pytest.fixture()
def lib() -> int:
    return db.create_library("MacBook")


@pytest.fixture(scope="module")
def index() -> LibraryIndex:
    return LibraryIndex(LIBRARY)


@pytest.fixture(scope="module")
def by_id() -> dict:
    return {track.id: track for track in LIBRARY}


# --- parsing the formats rekordbox exports ---------------------------------

def test_parses_m3u8_with_paths() -> None:
    data = (
        "#EXTM3U\n"
        "#EXTINF:240,Artist One - Anthem\n"
        "/music/anthem.mp3\n"
        "#EXTINF:330,Artist One - Anthem (Extended Mix)\n"
        "/music/anthem-ext.mp3\n"
    ).encode("utf-8")
    name, entries = parse_playlist(data, "Most played 2026.m3u8")
    assert name == "Most played 2026"
    assert [entry.path for entry in entries] == ["/music/anthem.mp3", "/music/anthem-ext.mp3"]
    assert entries[0].artist == "Artist One"
    assert entries[0].title == "Anthem"


def test_parses_m3u8_with_file_uris_and_accents() -> None:
    data = (
        "#EXTM3U\n"
        "file://localhost/Users/v/Music/%C3%89tienne%20-%20Am%20I%20Wrong.mp3\n"
    ).encode("utf-8")
    _, entries = parse_playlist(data, "x.m3u8")
    assert entries[0].path == "/Users/v/Music/Étienne - Am I Wrong.mp3"


def test_parses_pls() -> None:
    data = (
        "[playlist]\nNumberOfEntries=2\n"
        "File1=/music/a.mp3\nTitle1=A\n"
        "File2=/music/b.mp3\nTitle2=B\n"
    ).encode("utf-8")
    _, entries = parse_playlist(data, "list.pls")
    assert [entry.path for entry in entries] == ["/music/a.mp3", "/music/b.mp3"]


def test_parses_rekordbox_txt_in_utf16() -> None:
    """rekordbox writes TXT as UTF-16 with a BOM and no file paths."""
    text = (
        "#\tTrack Title\tArtist\tBPM\tKey\n"
        "1\tAnthem\tArtist One\t128.00\t8A\n"
        "2\tGecko\tDJ Four\t124.00\t5A\n"
    )
    _, entries = parse_playlist(text.encode("utf-16"), "Most played.txt")
    assert [(e.artist, e.title) for e in entries] == [
        ("Artist One", "Anthem"),
        ("DJ Four", "Gecko"),
    ]
    assert all(entry.path is None for entry in entries)


def test_parses_playlist_exported_as_xml() -> None:
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<DJ_PLAYLISTS Version="1.0.0"><COLLECTION Entries="1">'
        '<TRACK Name="Anthem" Artist="Artist One" '
        'Location="file://localhost/music/anthem.mp3"/>'
        '</COLLECTION><PLAYLISTS><NODE Type="0" Name="ROOT" Count="1">'
        '<NODE Name="Most played" Type="1" KeyType="0" Entries="1">'
        '<TRACK Key="1"/></NODE></NODE></PLAYLISTS></DJ_PLAYLISTS>'
    ).encode("utf-8")
    _, entries = parse_playlist(data, "export.xml")
    # The PLAYLISTS key reference must not be counted as a second track.
    assert len(entries) == 1
    assert entries[0].path == "/music/anthem.mp3"


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"", "empty"),
        (b"#EXTM3U\n", "No tracks found"),
        (b"#\tBPM\tKey\n1\t128\t8A\n", "Track Title"),
    ],
)
def test_rejects_unusable_files(data: bytes, match: str) -> None:
    with pytest.raises(PlaylistImportError, match=match):
        parse_playlist(data, "x.m3u8")


# --- resolving entries to library tracks -----------------------------------

def test_resolves_by_exact_path() -> None:
    """An m3u8 from the same device resolves without any fuzzy matching."""
    from server.models import LibraryTrack
    from server.playlist_import import PlaylistEntry
    from server.scanner.tags import track_id

    path = "/music/Artist One - Anthem.mp3"
    track = LibraryTrack(
        id=track_id(path), path=path, filename="Artist One - Anthem", ext="mp3",
        artist="Artist One", title="Anthem", album=None, duration_sec=240.0,
        bitrate_kbps=320, tag_source="tags", size_bytes=1, mtime_ms=1,
    )
    small_index = LibraryIndex([track])
    resolved, missing = resolve_entries(
        [
            PlaylistEntry(path=path, artist="", title=""),
            PlaylistEntry(path="/nowhere/gone.mp3", artist="", title=""),
        ],
        small_index,
        {track.id: track},
    )
    assert resolved == [track.id]
    assert len(missing) == 1


def test_resolves_by_metadata_when_the_format_has_no_paths(
    index: LibraryIndex, by_id: dict
) -> None:
    """The rekordbox TXT export carries only artist and title."""
    from server.playlist_import import PlaylistEntry

    resolved, missing = resolve_entries(
        [PlaylistEntry(path=None, artist="DJ Four", title="Gecko (Extended Mix)")],
        index,
        by_id,
    )
    assert resolved == ["gecko-ext"]
    assert missing == []


def test_resolution_ignores_weak_metadata_matches(index: LibraryIndex, by_id: dict) -> None:
    from server.playlist_import import PlaylistEntry

    resolved, missing = resolve_entries(
        [PlaylistEntry(path=None, artist="Nobody", title="Not A Real Song")],
        index,
        by_id,
    )
    assert resolved == []
    assert len(missing) == 1


# --- how membership changes matching ---------------------------------------

def test_playlist_membership_breaks_a_genuine_tie(index: LibraryIndex) -> None:
    """A pasted line has no duration, so the radio edit and the extended mix
    score identically — the one you actually play should win."""
    tied = query("Gecko", "DJ Four")
    scores = {c.track.id: c.score for c in match_one(tied, index).candidates}
    assert scores["gecko-ext"] == scores["gecko-radio"], "premise: a real tie"

    result = match_one(tied, index, membership={"gecko-radio": ["Most played 2026"]})
    assert result.candidates[0].track.id == "gecko-radio"
    assert result.candidates[0].playlists == ["Most played 2026"]


def test_membership_can_settle_an_otherwise_too_close_call() -> None:
    """The same track filed twice — a 320 rip and a lossless copy — is a
    coin toss on score alone, but only one of them is the one you play."""
    from server.models import LibraryTrack

    def copy(id_: str, folder: str) -> LibraryTrack:
        return LibraryTrack(
            id=id_, path=f"/{folder}/Artist One - Anthem.mp3",
            filename="Artist One - Anthem", ext="mp3", artist="Artist One",
            title="Anthem", album=None, duration_sec=240.0, bitrate_kbps=320,
            tag_source="tags", size_bytes=1, mtime_ms=1,
        )

    duplicates = LibraryIndex([copy("in-sets", "sets"), copy("in-archive", "archive")])
    asked = query("Anthem", "Artist One", 240)

    plain = match_one(asked, duplicates)
    assert plain.bucket == "ambiguous"  # identical scores, nothing to choose on
    assert plain.candidates[0].score == plain.candidates[1].score

    decided = match_one(asked, duplicates, membership={"in-sets": ["Most played 2026"]})
    assert decided.bucket == "auto"
    assert decided.auto_selected_id == "in-sets"


def test_membership_never_promotes_a_version_spotify_did_not_ask_for(
    index: LibraryIndex,
) -> None:
    """Playing the radio edit constantly still must not let it stand in for
    the plain track: the version gate outranks the nudge."""
    result = match_one(
        query("Gecko", "DJ Four"), index,
        membership={"gecko-radio": ["Most played 2026", "All time"]},
    )
    assert result.bucket == "ambiguous"
    assert result.auto_selected_id is None
    assert result.candidates[0].track.id == "gecko-radio"  # offered first, not forced


def test_membership_does_not_overturn_a_clear_win(index: LibraryIndex) -> None:
    """With a duration to go on, the radio edit wins by 0.15 — far more than
    the nudge is worth. The bonus settles ties, it does not campaign."""
    result = match_one(
        query("Gecko", "DJ Four", 172), index,
        membership={"gecko-ext": ["Most played 2026", "All time", "Last month"]},
    )
    assert result.candidates[0].track.id == "gecko-radio"


def test_membership_never_overrides_a_version_mismatch(index: LibraryIndex) -> None:
    """Playing the Extended Mix a lot must not make it stand in for the
    original that the Spotify playlist actually asked for."""
    played_extended = {"anthem-ext": ["Most played 2026", "All time", "Last month"]}
    result = match_one(query("Anthem", "Artist One", 240), index, membership=played_extended)
    assert result.candidates[0].track.id == "anthem-orig"
    assert result.auto_selected_id == "anthem-orig"


def test_being_in_more_playlists_ranks_higher(index: LibraryIndex) -> None:
    result = match_one(
        query("Gecko", "DJ Four"),
        index,
        membership={"gecko-radio": ["2025"], "gecko-ext": ["2026", "All time", "Last month"]},
    )
    assert result.candidates[0].track.id == "gecko-ext"


def test_a_remembered_choice_still_beats_playlist_membership(index: LibraryIndex) -> None:
    from server.matcher.signature import signature_id

    result = match_one(
        query("Gecko", "DJ Four"),
        index,
        preferences={signature_id("DJ Four", "Gecko"): "gecko-radio"},
        membership={"gecko-ext": ["Most played 2026"]},
    )
    assert result.auto_selected_id == "gecko-radio"
    assert result.from_preference is True


def test_matching_is_unchanged_without_playlists(index: LibraryIndex) -> None:
    plain = query("Anthem", "Artist One", 240)
    assert match_one(plain, index, membership={}).auto_selected_id == (
        match_one(plain, index).auto_selected_id
    )


# --- storage ---------------------------------------------------------------

def test_playlists_round_trip_and_replace(lib: int) -> None:
    db.replace_playlist(lib, "Most played 2026", ["a" * 12, "b" * 12], missing_count=3)
    listed = db.list_playlists(lib)
    assert len(listed) == 1
    assert listed[0].name == "Most played 2026"
    assert listed[0].track_count == 2
    assert listed[0].missing_count == 3

    # Re-uploading the same name replaces rather than appending.
    db.replace_playlist(lib, "Most played 2026", ["c" * 12], missing_count=0)
    listed = db.list_playlists(lib)
    assert len(listed) == 1
    assert listed[0].track_count == 1
    assert db.playlist_track_ids(listed[0].id) == {"c" * 12}


def test_membership_map_and_deletion(lib: int) -> None:
    db.replace_playlist(lib, "2026", ["a" * 12], 0)
    db.replace_playlist(lib, "All time", ["a" * 12, "b" * 12], 0)

    membership = db.playlist_membership(lib)
    assert membership["a" * 12] == ["2026", "All time"]
    assert membership["b" * 12] == ["All time"]

    playlist_id = next(p.id for p in db.list_playlists(lib) if p.name == "2026")
    assert db.delete_playlist(lib, playlist_id) is True
    assert db.playlist_membership(lib)["a" * 12] == ["All time"]
    assert db.delete_playlist(lib, 9999) is False


def test_playlists_are_scoped_per_library(lib: int) -> None:
    other = db.create_library("Studio PC")
    db.replace_playlist(lib, "Most played", ["a" * 12], 0)
    db.replace_playlist(other, "Most played", ["b" * 12], 0)

    assert db.playlist_membership(lib) == {"a" * 12: ["Most played"]}
    assert db.playlist_membership(other) == {"b" * 12: ["Most played"]}

    db.delete_library(other)
    assert db.playlist_membership(lib) == {"a" * 12: ["Most played"]}
