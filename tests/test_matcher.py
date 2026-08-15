import time

import pytest

from server.matcher.index import LibraryIndex
from server.matcher.match import match_one, match_playlist
from server.matcher.score import version_score
from server.matcher.versions import extract_version
from server.models import LibraryTrack, PlaylistTrackInput


def track(id_: str, artist: str | None, title: str, duration: float | None,
          tag_source: str = "tags") -> LibraryTrack:
    return LibraryTrack(
        id=id_, path=f"/music/{id_}.mp3", filename=id_, ext="mp3",
        artist=artist, title=title, album=None, duration_sec=duration,
        bitrate_kbps=320, tag_source=tag_source, size_bytes=1, mtime_ms=1,
    )


# A small realistic library: a 4-version family, accents, a typo'd tag,
# a filename-only file, and distractors.
LIBRARY = [
    track("anthem-orig", "Artist One", "Anthem", 240),
    track("anthem-rmx2", "Artist One", "Anthem (Artist Two Remix)", 250),
    track("anthem-ext", "Artist One", "Anthem (Extended Mix)", 330),
    track("anthem-club", "Artist One", "Anthem (Club Mix)", 260),
    track("amiwrong", "Étienne de Crécy", "Am I Wrong", 371),
    track("umbrella", "Rihana", "Umbrela", 263),          # typo'd tags
    track("sunset", None, "sunset lover petit biscuit", 238, "filename"),
    track("gecko-radio", "DJ Four", "Gecko (Radio Edit)", 172),
    track("gecko-ext", "DJ Four", "Gecko (Extended Mix)", 325),
    track("d1", "Someone Else", "Completely Different", 200),
    track("d2", "Another Act", "Nothing Alike", 210),
    track("d3", "Third Band", "Unrelated Song", 190),
    track("d4", "Artist One", "Other Anthem Of Ours", 230),
]


@pytest.fixture(scope="module")
def index() -> LibraryIndex:
    return LibraryIndex(LIBRARY)


def query(title: str, artist: str = "", duration: float | None = None) -> PlaylistTrackInput:
    return PlaylistTrackInput(index=0, artist=artist, title=title, duration_sec=duration)


def test_exact_match_is_auto(index: LibraryIndex) -> None:
    result = match_one(query("Am I Wrong", "Étienne de Crécy", 371), index)
    assert result.bucket == "auto"
    assert result.auto_selected_id == "amiwrong"
    assert result.candidates[0].score > 0.95


def test_original_wins_over_remix_family(index: LibraryIndex) -> None:
    result = match_one(query("Anthem", "Artist One", 240), index)
    assert result.bucket == "auto"
    assert result.auto_selected_id == "anthem-orig"
    listed = {c.track.id for c in result.candidates}
    assert {"anthem-rmx2", "anthem-club"} <= listed  # alternatives still shown


def test_specific_remix_wins_over_original(index: LibraryIndex) -> None:
    result = match_one(query("Anthem (Artist Two Remix)", "Artist One", 250), index)
    assert result.bucket == "auto"
    assert result.auto_selected_id == "anthem-rmx2"


def test_unowned_remix_is_ambiguous_not_auto(index: LibraryIndex) -> None:
    # We have the original + other versions, but not THIS remix: never auto-pick.
    result = match_one(query("Anthem (Artist Three Remix)", "Artist One", 245), index)
    assert result.bucket == "ambiguous"
    assert result.auto_selected_id is None
    assert len(result.candidates) >= 3


def test_radio_vs_extended_needs_the_user(index: LibraryIndex) -> None:
    # Query duration matches the radio edit, but version intent is unclear.
    result = match_one(query("Gecko", "DJ Four", 172), index)
    assert result.bucket == "ambiguous"
    assert result.candidates[0].track.id == "gecko-radio"
    assert {c.track.id for c in result.candidates[:2]} == {"gecko-radio", "gecko-ext"}


def test_typo_tags_found_via_fallback(index: LibraryIndex) -> None:
    result = match_one(query("Umbrella", "Rihanna", 263), index)
    assert result.candidates, "typo'd track should be found by the fuzzy fallback"
    assert result.candidates[0].track.id == "umbrella"
    assert result.bucket == "auto"


def test_filename_only_file_matches_via_combined_facet(index: LibraryIndex) -> None:
    result = match_one(query("Sunset Lover", "Petit Biscuit", 238), index)
    assert result.candidates[0].track.id == "sunset"
    assert result.bucket == "auto"
    assert "combined" in result.candidates[0].parts


def test_missing_track_is_unmatched(index: LibraryIndex) -> None:
    result = match_one(query("Not In Library", "Missing Artist", 200), index)
    assert result.bucket == "unmatched"
    assert result.auto_selected_id is None


def test_pasted_line_without_artist_or_duration(index: LibraryIndex) -> None:
    result = match_one(query("Anthem"), index)
    assert result.candidates[0].track.id == "anthem-orig"
    assert result.bucket in {"auto", "ambiguous"}


def test_match_playlist_preserves_order(index: LibraryIndex) -> None:
    tracks = [
        PlaylistTrackInput(index=0, artist="Artist One", title="Anthem", duration_sec=240),
        PlaylistTrackInput(index=1, artist="Missing", title="Nope", duration_sec=100),
    ]
    results = match_playlist(tracks, index)
    assert [r.input.index for r in results] == [0, 1]
    assert [r.bucket for r in results] == ["auto", "unmatched"]


def test_version_score_table() -> None:
    original = extract_version("Song")
    extended = extract_version("Song (Extended Mix)")
    remix_a = extract_version("Song (A Remix)")
    remix_b = extract_version("Song (B Remix)")
    remaster = extract_version("Song (Remastered 2011)")
    assert version_score(original, original) == 1.0
    assert version_score(remix_a, remix_a) == 1.0
    assert version_score(original, extended) == 0.60
    assert version_score(original, remix_a) == 0.25
    assert version_score(remix_a, remix_b) == 0.20
    assert version_score(original, remaster) == pytest.approx(0.90)
    assert version_score(extended, remix_a) == 0.20


def test_duration_deltas_are_reported(index: LibraryIndex) -> None:
    result = match_one(query("Anthem", "Artist One", 240), index)
    by_id = {c.track.id: c for c in result.candidates}
    assert by_id["anthem-orig"].duration_delta_sec == 0
    assert by_id["anthem-ext"].duration_delta_sec == 90


def test_performance_20k_library_100_queries() -> None:
    big = [
        track(f"t{i}", f"Artist {i % 997}", f"Song Number {i} ({'Remix' if i % 7 == 0 else 'Original Mix'})", 180 + i % 200)
        for i in range(20_000)
    ]
    started = time.monotonic()
    big_index = LibraryIndex(big)
    queries = [
        PlaylistTrackInput(index=i, artist=f"Artist {i % 997}", title=f"Song Number {i * 13 % 20000}", duration_sec=200)
        for i in range(100)
    ]
    match_playlist(queries, big_index)
    elapsed = time.monotonic() - started
    assert elapsed < 8, f"index+match took {elapsed:.1f}s — something is quadratic"
