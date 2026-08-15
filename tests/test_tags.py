from pathlib import Path

import pytest

from server.scanner.filename_parse import parse_filename
from server.scanner.tags import read_track
from tests.helpers import make_audio_tree


@pytest.fixture(scope="module")
def tree(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return make_audio_tree(tmp_path_factory.mktemp("library"))


def test_tagged_mp3_with_accents(tree: dict[str, Path]) -> None:
    track, error = read_track(tree["tagged_accents"])
    assert error is None
    assert track.artist == "Étienne de Crécy"
    assert track.title == "Am I Wrong"
    assert track.album == "Super Discount"
    assert track.tag_source == "tags"
    assert track.ext == "mp3"
    assert track.duration_sec is not None and 0.5 < track.duration_sec < 2.0
    assert track.bitrate_kbps == 32
    assert track.id and len(track.id) == 12


def test_untagged_mp3_falls_back_to_filename(tree: dict[str, Path]) -> None:
    track, error = read_track(tree["untagged_numbered"])
    assert error is None
    assert track.tag_source == "filename"
    assert track.artist == "Artist X"
    assert track.title == "Some Song"


def test_untagged_without_separator_is_title_only(tree: dict[str, Path]) -> None:
    track, _ = read_track(tree["untagged_plain"])
    assert track.artist is None
    assert track.title == "random name"


def test_wav_duration_is_exact(tree: dict[str, Path]) -> None:
    track, error = read_track(tree["wav_exact"])
    assert error is None
    assert track.ext == "wav"
    assert track.duration_sec == 2.5
    assert track.artist == "Test Tone"
    assert track.title == "Exact"


def test_corrupt_file_reports_error_but_keeps_track(tree: dict[str, Path]) -> None:
    track, error = read_track(tree["corrupt"])
    assert error is not None
    assert track.title == "corrupt"
    assert track.duration_sec is None
    assert track.tag_source == "filename"


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("01. Artist X - Some Song", ("Artist X", "Some Song")),
        ("Artist_-_Title", ("Artist", "Title")),
        ("12) Someone – En Dash Title", ("Someone", "En Dash Title")),
        ("Someone — Em Dash", ("Someone", "Em Dash")),
        ("no separator here", (None, "no separator here")),
        ("05 - Real Artist - Real Title", ("Real Artist", "Real Title")),
    ],
)
def test_parse_filename(stem: str, expected: tuple[str | None, str]) -> None:
    assert parse_filename(stem) == expected
