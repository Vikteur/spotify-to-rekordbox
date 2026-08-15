from pathlib import Path

import pytest

from server import db
from server.library import Library
from server.models import LibraryTrack


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()


def track(id_: str, path: str, title: str = "Song", **extra) -> LibraryTrack:
    defaults = dict(
        filename=title, ext="mp3", artist="Artist", album=None, duration_sec=200.0,
        bitrate_kbps=320, tag_source="tags", size_bytes=100, mtime_ms=1000,
    )
    defaults.update(extra)
    return LibraryTrack(id=id_, path=path, title=title, **defaults)


def test_init_is_idempotent() -> None:
    db.init()
    db.init()
    assert db.all_tracks() == []


def test_upsert_source_is_stable() -> None:
    first = db.upsert_source("folder", "/music")
    assert db.upsert_source("folder", "/music") == first
    assert db.upsert_source("xml", "/music") != first


def test_tracks_round_trip_with_all_fields() -> None:
    source = db.upsert_source("xml", "rekordbox.xml")
    original = track(
        "a" * 12, "/music/a.mp3", "Am I Wrong", artist="Étienne de Crécy",
        album="Super Discount", bpm=124.0, musical_key="Am", tag_source="rekordbox",
    )
    db.replace_source_tracks(source, [original])

    stored = db.all_tracks()
    assert len(stored) == 1
    assert stored[0].artist == "Étienne de Crécy"
    assert stored[0].bpm == 124.0
    assert stored[0].musical_key == "Am"
    assert stored[0].source_id == source


def test_replace_source_tracks_replaces_not_appends() -> None:
    source = db.upsert_source("folder", "/music")
    db.replace_source_tracks(source, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(source, [track("b" * 12, "/music/b.mp3")])
    assert [t.path for t in db.all_tracks()] == ["/music/b.mp3"]


def test_sources_report_their_counts() -> None:
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(
        xml, [track("b" * 12, "/x/b.mp3"), track("c" * 12, "/x/c.mp3")]
    )

    sources = {source.label: source for source in db.list_sources()}
    assert sources["/music"].track_count == 1
    assert sources["/music"].kind == "folder"
    assert sources["rekordbox.xml"].track_count == 2


def test_source_tracks_keyed_by_path_for_incremental_scans() -> None:
    source = db.upsert_source("folder", "/music")
    db.replace_source_tracks(source, [track("a" * 12, "/music/a.mp3")])
    stored = db.source_tracks(source)
    assert set(stored) == {"/music/a.mp3"}
    assert stored["/music/a.mp3"].mtime_ms == 1000


def test_delete_source_removes_its_tracks() -> None:
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(xml, [track("b" * 12, "/x/b.mp3")])

    assert db.delete_source(folder) is True
    assert [t.path for t in db.all_tracks()] == ["/x/b.mp3"]
    assert [s.label for s in db.list_sources()] == ["rekordbox.xml"]
    assert db.delete_source(9999) is False


def test_same_file_in_two_sources_is_stored_once() -> None:
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/a.mp3")
    db.replace_source_tracks(folder, [shared])
    db.replace_source_tracks(xml, [shared])
    assert len(db.all_tracks()) == 1


def test_library_reloads_from_disk() -> None:
    source = db.upsert_source("folder", "/music")
    db.replace_source_tracks(
        source, [track("a" * 12, "/music/a.mp3"), track("b" * 12, "/music/b.wav", ext="wav")]
    )

    library = Library()
    assert library.is_loaded() is False
    library.reload()

    assert library.is_loaded() is True
    assert len(library.tracks) == 2
    assert library.by_id["a" * 12].path == "/music/a.mp3"
    summary = library.summary()
    assert summary["track_count"] == 2
    assert summary["by_ext"] == {"mp3": 1, "wav": 1}
    assert summary["sources"][0]["label"] == "/music"


def test_library_generation_bumps_so_the_index_rebuilds() -> None:
    library = Library()
    library.reload()
    first = library.generation
    library.reload()
    assert library.generation == first + 1
