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


def test_same_file_in_two_sources_is_stored_once_but_counted_by_both() -> None:
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/a.mp3")
    db.replace_source_tracks(folder, [shared])
    db.replace_source_tracks(xml, [shared])

    assert len(db.all_tracks()) == 1
    counts = {source.kind: source.track_count for source in db.list_sources()}
    assert counts == {"folder": 1, "xml": 1}


def test_shared_track_survives_removing_one_of_its_sources() -> None:
    """A file in both a folder scan and an XML import must not vanish when
    either one is removed — only when the last claim on it goes away."""
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/shared.mp3")
    folder_only = track("b" * 12, "/music/folder-only.mp3")
    db.replace_source_tracks(folder, [shared, folder_only])
    db.replace_source_tracks(xml, [shared])

    db.delete_source(folder)
    assert [t.path for t in db.all_tracks()] == ["/music/shared.mp3"]

    db.delete_source(xml)
    assert db.all_tracks() == []


def test_rescanning_a_folder_does_not_steal_tracks_from_another_source() -> None:
    folder = db.upsert_source("folder", "/music")
    xml = db.upsert_source("xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/shared.mp3")
    db.replace_source_tracks(xml, [shared])
    db.replace_source_tracks(folder, [shared])
    db.replace_source_tracks(folder, [shared])  # rescan

    counts = {source.kind: source.track_count for source in db.list_sources()}
    assert counts == {"folder": 1, "xml": 1}
    assert len(db.all_tracks()) == 1


def test_a_folder_rescan_keeps_bpm_and_key_it_cannot_see() -> None:
    """Only rekordbox knows BPM/key; a folder scan must not blank them."""
    xml = db.upsert_source("xml", "rekordbox.xml")
    folder = db.upsert_source("folder", "/music")
    path = "/music/shared.mp3"
    db.replace_source_tracks(
        xml,
        [track("a" * 12, path, bpm=124.0, musical_key="Am", tag_source="rekordbox")],
    )
    db.replace_source_tracks(
        folder, [track("a" * 12, path, artist="Tagged Artist", tag_source="tags")]
    )

    stored = db.all_tracks()[0]
    assert stored.bpm == 124.0
    assert stored.musical_key == "Am"
    assert stored.artist == "Tagged Artist"  # observable fields do update


def test_dropping_a_track_from_a_source_removes_it_when_unclaimed() -> None:
    folder = db.upsert_source("folder", "/music")
    db.replace_source_tracks(
        folder, [track("a" * 12, "/music/a.mp3"), track("b" * 12, "/music/b.mp3")]
    )
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    assert [t.path for t in db.all_tracks()] == ["/music/a.mp3"]


def test_migrates_a_v1_database_without_losing_tracks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1 kept a single source_id column on tracks; upgrading must not force
    a rescan or drop the rekordbox import."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v1.db")  # untouched by init()
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                label TEXT NOT NULL, added_at TEXT NOT NULL, UNIQUE (kind, label)
            );
            CREATE TABLE tracks (
                id TEXT PRIMARY KEY, source_id INTEGER NOT NULL, path TEXT NOT NULL,
                filename TEXT NOT NULL, ext TEXT NOT NULL, artist TEXT, title TEXT NOT NULL,
                album TEXT, duration_sec REAL, bitrate_kbps INTEGER, bpm REAL,
                musical_key TEXT, tag_source TEXT NOT NULL, size_bytes INTEGER NOT NULL,
                mtime_ms INTEGER NOT NULL
            );
            INSERT INTO sources (id, kind, label, added_at)
                VALUES (1, 'folder', '/music', '2026-01-01T00:00:00Z'),
                       (2, 'xml', 'rekordbox.xml', '2026-01-01T00:00:00Z');
            INSERT INTO tracks (id, source_id, path, filename, ext, artist, title,
                                album, duration_sec, bitrate_kbps, bpm, musical_key,
                                tag_source, size_bytes, mtime_ms)
                VALUES ('aaaaaaaaaaaa', 1, '/music/a.mp3', 'a', 'mp3', 'A', 'Song A',
                        NULL, 200.0, 320, NULL, NULL, 'tags', 10, 1),
                       ('bbbbbbbbbbbb', 2, '/x/b.mp3', 'b', 'mp3', 'B', 'Song B',
                        NULL, 300.0, 320, 128.0, 'Am', 'rekordbox', 20, 0);
            """
        )

    db.init()  # migrate

    tracks = {t.path: t for t in db.all_tracks()}
    assert set(tracks) == {"/music/a.mp3", "/x/b.mp3"}
    assert tracks["/x/b.mp3"].bpm == 128.0
    counts = {source.label: source.track_count for source in db.list_sources()}
    assert counts == {"/music": 1, "rekordbox.xml": 1}

    db.init()  # idempotent
    assert len(db.all_tracks()) == 2


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
