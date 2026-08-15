import os
import time
from pathlib import Path

import pytest

from server import db
from server.library import LIBRARY
from server.scanner.scan import Scanner
from tests.helpers import make_audio_tree


@pytest.fixture()
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()
    LIBRARY.reload()
    root = tmp_path / "music"
    make_audio_tree(root)
    return root


def scan(root: Path, force: bool = False) -> Scanner:
    scanner = Scanner()
    scanner.start_scan(str(root), force=force)
    scanner.wait()
    return scanner


def test_first_scan_finds_everything(library: Path) -> None:
    scanner = scan(library)
    status = scanner.status()
    assert status["state"] == "done"
    # 6 audio files (hidden dir skipped, notes.txt ignored), 1 DRM m4p counted.
    assert status["scanned"]["track_count"] == 6
    assert status["scanned"]["skipped_drm"] == 1
    assert status["library"]["by_ext"] == {"mp3": 5, "wav": 1}
    assert status["parsed"] == 6
    assert status["from_cache"] == 0
    # The corrupt file is reported but still present as a track.
    assert any("corrupt" in error["message"] for error in status["errors"])
    assert any(track.title == "corrupt" for track in LIBRARY.tracks)
    assert len(LIBRARY.by_id) == 6


def test_second_scan_is_all_cache(library: Path) -> None:
    scan(library)
    scanner = scan(library)
    status = scanner.status()
    assert status["parsed"] == 0
    assert status["from_cache"] == 6
    assert status["scanned"]["track_count"] == 6


def test_touched_file_is_reparsed_alone(library: Path) -> None:
    scan(library)
    target = library / "House" / "am-i-wrong.mp3"
    future = time.time() + 10
    os.utime(target, (future, future))
    scanner = scan(library)
    status = scanner.status()
    assert status["parsed"] == 1
    assert status["from_cache"] == 5


def test_force_ignores_cache(library: Path) -> None:
    scan(library)
    scanner = scan(library, force=True)
    assert scanner.status()["parsed"] == 6


def test_deleted_file_leaves_library(library: Path) -> None:
    scan(library)
    (library / "Untagged" / "random_name.mp3").unlink()
    scanner = scan(library)
    assert scanner.status()["scanned"]["track_count"] == 5
    assert all("random_name" not in track.path for track in LIBRARY.tracks)


def test_library_survives_a_restart(library: Path) -> None:
    """The whole point of the database: a fresh process needs no rescan."""
    scan(library)

    from server.library import Library

    restarted = Library()
    restarted.reload()
    assert len(restarted.tracks) == 6
    assert restarted.is_loaded() is True
    assert restarted.summary()["sources"][0]["kind"] == "folder"


def test_rescanning_a_folder_does_not_duplicate_tracks(library: Path) -> None:
    scan(library)
    scan(library)
    scan(library, force=True)
    assert len(LIBRARY.tracks) == 6
    assert len(db.list_sources()) == 1


def test_missing_folder_errors_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()
    scanner = Scanner()
    scanner.start_scan(str(tmp_path / "nope"))
    scanner.wait()
    status = scanner.status()
    assert status["state"] == "done"
    assert status["scanned"]["track_count"] == 0
