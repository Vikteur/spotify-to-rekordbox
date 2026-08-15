from pathlib import Path

import pytest

from server import db
from server.matcher.index import LibraryIndex
from server.matcher.match import match_one
from server.matcher.signature import signature_id, signature_of
from server.models import PlaylistTrackInput
from tests.test_matcher import LIBRARY, query


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()


@pytest.fixture(scope="module")
def index() -> LibraryIndex:
    return LibraryIndex(LIBRARY)


# --- what counts as "the same song" ---------------------------------------

def test_same_song_written_differently_shares_a_signature() -> None:
    assert signature_of("Artist One", "Anthem") == signature_of("artist one", "ANTHEM!")
    # Featured artists are excluded: playlists list them inconsistently.
    assert signature_of("Justin Bieber", "Peaches (feat. Daniel Caesar)") == signature_of(
        "Justin Bieber", "Peaches"
    )
    # Accents fold the same way the matcher folds them.
    assert signature_of("Étienne de Crécy", "Am I Wrong") == signature_of(
        "Etienne de Crecy", "Am I Wrong"
    )


def test_different_versions_are_different_songs() -> None:
    original = signature_of("deadmau5", "Strobe")
    radio = signature_of("deadmau5", "Strobe (Radio Edit)")
    remix_a = signature_of("deadmau5", "Strobe (Someone Remix)")
    remix_b = signature_of("deadmau5", "Strobe (Other Remix)")
    assert len({original, radio, remix_a, remix_b}) == 4
    # "(Original Mix)" means "no version", so it is the plain song.
    assert signature_of("deadmau5", "Strobe (Original Mix)") == original


def test_different_artists_are_different_songs() -> None:
    assert signature_of("Artist One", "Anthem") != signature_of("Artist Two", "Anthem")


# --- applying a remembered choice ------------------------------------------

def test_preference_overrides_the_automatic_pick(index: LibraryIndex) -> None:
    plain = query("Anthem", "Artist One", 240)
    assert match_one(plain, index).auto_selected_id == "anthem-orig"

    preferences = {signature_id("Artist One", "Anthem"): "anthem-ext"}
    result = match_one(plain, index, preferences)

    assert result.auto_selected_id == "anthem-ext"
    assert result.from_preference is True
    # The remembered file is offered first, and the alternatives remain.
    assert result.candidates[0].track.id == "anthem-ext"
    assert "anthem-orig" in {candidate.track.id for candidate in result.candidates}


def test_preference_resolves_an_ambiguous_song(index: LibraryIndex) -> None:
    ambiguous = query("Gecko", "DJ Four", 172)
    assert match_one(ambiguous, index).auto_selected_id is None

    preferences = {signature_id("DJ Four", "Gecko"): "gecko-ext"}
    result = match_one(ambiguous, index, preferences)
    assert result.auto_selected_id == "gecko-ext"
    assert result.from_preference is True


def test_preference_only_applies_to_the_song_it_was_set_for(index: LibraryIndex) -> None:
    preferences = {signature_id("Artist One", "Anthem"): "anthem-ext"}
    other = match_one(query("Anthem (Artist Two Remix)", "Artist One", 250), index, preferences)
    assert other.from_preference is False
    assert other.auto_selected_id == "anthem-rmx2"


def test_preference_is_honoured_even_if_scoring_would_not_list_it(index: LibraryIndex) -> None:
    """The song is the one you decided about, so an odd-scoring playlist
    entry must not lose your choice."""
    preferences = {signature_id("Artist One", "Anthem"): "amiwrong"}
    result = match_one(query("Anthem", "Artist One", 240), index, preferences)
    assert result.auto_selected_id == "amiwrong"
    assert result.from_preference is True
    assert result.candidates[0].track.id == "amiwrong"


def test_preference_for_a_track_no_longer_present_is_ignored(index: LibraryIndex) -> None:
    preferences = {signature_id("Artist One", "Anthem"): "deleted-track"}
    result = match_one(query("Anthem", "Artist One", 240), index, preferences)
    assert result.from_preference is False
    assert result.auto_selected_id == "anthem-orig"  # falls back to scoring


def test_no_preferences_leaves_matching_untouched(index: LibraryIndex) -> None:
    plain = query("Anthem", "Artist One", 240)
    assert match_one(plain, index, {}).auto_selected_id == match_one(plain, index).auto_selected_id
    assert match_one(plain, index, {}).from_preference is False


# --- storage ---------------------------------------------------------------

def save(artist: str, title: str, track_id: str) -> None:
    db.save_preference(
        signature_id(artist, title), signature_of(artist, title), artist, title, track_id
    )


def test_preferences_round_trip() -> None:
    save("Artist One", "Anthem", "anthem-ext")
    assert db.preference_map() == {signature_id("Artist One", "Anthem"): "anthem-ext"}

    listed = db.list_preferences()
    assert len(listed) == 1
    assert listed[0].artist == "Artist One"
    assert listed[0].track_id == "anthem-ext"
    assert listed[0].file_label is None  # that track isn't in the database here


def test_choosing_again_overwrites_rather_than_duplicating() -> None:
    save("Artist One", "Anthem", "anthem-ext")
    save("Artist One", "Anthem", "anthem-club")
    assert len(db.list_preferences()) == 1
    assert db.preference_map()[signature_id("Artist One", "Anthem")] == "anthem-club"


def test_forgetting() -> None:
    save("Artist One", "Anthem", "anthem-ext")
    save("DJ Four", "Gecko", "gecko-ext")
    assert db.delete_preference(signature_id("Artist One", "Anthem")) is True
    assert db.delete_preference("nope") is False
    assert len(db.list_preferences()) == 1
    db.clear_preferences()
    assert db.list_preferences() == []


def test_preferences_survive_removing_a_library_source() -> None:
    """Removing a source must not erase decisions — the file may come back."""
    from server.models import LibraryTrack

    source = db.upsert_source("folder", "/music")
    track = LibraryTrack(
        id="anthem-ext", path="/music/anthem-ext.mp3", filename="anthem-ext", ext="mp3",
        artist="Artist One", title="Anthem (Extended Mix)", album=None, duration_sec=330.0,
        bitrate_kbps=320, tag_source="tags", size_bytes=1, mtime_ms=1,
    )
    db.replace_source_tracks(source, [track])
    save("Artist One", "Anthem", "anthem-ext")
    assert db.list_preferences()[0].file_label == "anthem-ext.mp3"

    db.delete_source(source)

    remaining = db.list_preferences()
    assert len(remaining) == 1
    assert remaining[0].track_id == "anthem-ext"
    assert remaining[0].file_label is None  # shown as currently unavailable

    # Re-adding the same file restores the choice, because ids come from paths.
    db.replace_source_tracks(db.upsert_source("folder", "/music"), [track])
    assert db.list_preferences()[0].file_label == "anthem-ext.mp3"


def test_pasted_text_and_spotify_reach_the_same_preference(index: LibraryIndex) -> None:
    """A pasted 'Artist - Title' line has no duration, but it is the same song."""
    save("Artist One", "Anthem", "anthem-ext")
    preferences = db.preference_map()
    from_spotify = match_one(query("Anthem", "Artist One", 240), index, preferences)
    from_paste = match_one(
        PlaylistTrackInput(index=0, artist="Artist One", title="Anthem"), index, preferences
    )
    assert from_spotify.auto_selected_id == from_paste.auto_selected_id == "anthem-ext"
