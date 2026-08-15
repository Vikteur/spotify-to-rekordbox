from pathlib import Path

import pytest

from server import db
from server.library import ActiveLibrary
from server.models import LibraryTrack


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "library.db")
    db.init()


@pytest.fixture()
def lib() -> int:
    return db.create_library("MacBook")


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
    assert db.list_libraries() == []


# --- libraries -------------------------------------------------------------

def test_create_list_and_select_libraries() -> None:
    macbook = db.create_library("MacBook")
    studio = db.create_library("Studio PC")

    libraries = {library.name: library for library in db.list_libraries()}
    assert set(libraries) == {"MacBook", "Studio PC"}
    assert libraries["MacBook"].track_count == 0
    assert libraries["MacBook"].source_count == 0

    # With nothing selected it falls back to the first library.
    assert db.active_library_id() in {macbook, studio}
    db.set_active_library_id(studio)
    assert db.active_library_id() == studio


def test_library_names_are_unique() -> None:
    db.create_library("MacBook")
    with pytest.raises(db.DuplicateLibraryName):
        db.create_library("MacBook")


def test_rename_library() -> None:
    library_id = db.create_library("Laptop")
    db.create_library("Studio PC")
    assert db.rename_library(library_id, "MacBook Pro") is True
    assert [library.name for library in db.list_libraries()] == ["MacBook Pro", "Studio PC"]
    assert db.rename_library(9999, "Nope") is False
    with pytest.raises(db.DuplicateLibraryName):
        db.rename_library(library_id, "Studio PC")


def test_libraries_report_their_own_counts(lib: int) -> None:
    other = db.create_library("Studio PC")
    db.replace_source_tracks(
        db.upsert_source(lib, "folder", "/mac/music"),
        [track("a" * 12, "/mac/a.mp3"), track("b" * 12, "/mac/b.mp3")],
    )
    db.replace_source_tracks(
        db.upsert_source(other, "folder", "/pc/music"), [track("c" * 12, "/pc/c.mp3")]
    )

    counts = {library.name: library.track_count for library in db.list_libraries()}
    assert counts == {"MacBook": 2, "Studio PC": 1}
    assert [t.path for t in db.library_tracks(lib)] == ["/mac/a.mp3", "/mac/b.mp3"]
    assert [t.path for t in db.library_tracks(other)] == ["/pc/c.mp3"]


def test_libraries_are_isolated_from_each_other(lib: int) -> None:
    other = db.create_library("Studio PC")
    same_song_each_device = [
        (lib, "/mac/Anthem.mp3", "a" * 12),
        (other, "/pc/Anthem.mp3", "b" * 12),
    ]
    for library_id, path, track_id in same_song_each_device:
        db.replace_source_tracks(
            db.upsert_source(library_id, "folder", f"{path}-src"),
            [track(track_id, path, "Anthem")],
        )

    assert [t.path for t in db.library_tracks(lib)] == ["/mac/Anthem.mp3"]
    assert [t.path for t in db.library_tracks(other)] == ["/pc/Anthem.mp3"]


def test_deleting_a_library_removes_its_sources_and_tracks(lib: int) -> None:
    other = db.create_library("Studio PC")
    db.replace_source_tracks(
        db.upsert_source(lib, "folder", "/mac/music"), [track("a" * 12, "/mac/a.mp3")]
    )
    db.replace_source_tracks(
        db.upsert_source(other, "folder", "/pc/music"), [track("b" * 12, "/pc/b.mp3")]
    )

    assert db.delete_library(lib) is True
    assert [t.path for t in db.all_tracks()] == ["/pc/b.mp3"]
    assert [library.name for library in db.list_libraries()] == ["Studio PC"]
    assert db.delete_library(9999) is False


def test_active_library_falls_back_when_the_selected_one_is_deleted(lib: int) -> None:
    other = db.create_library("Studio PC")
    db.set_active_library_id(lib)
    db.delete_library(lib)
    assert db.active_library_id() == other


def test_the_same_folder_can_be_scanned_into_two_libraries(lib: int) -> None:
    other = db.create_library("Studio PC")
    first = db.upsert_source(lib, "folder", "/shared/music")
    second = db.upsert_source(other, "folder", "/shared/music")
    assert first != second


# --- sources and tracks ----------------------------------------------------

def test_upsert_source_is_stable(lib: int) -> None:
    first = db.upsert_source(lib, "folder", "/music")
    assert db.upsert_source(lib, "folder", "/music") == first
    assert db.upsert_source(lib, "xml", "/music") != first


def test_tracks_round_trip_with_all_fields(lib: int) -> None:
    source = db.upsert_source(lib, "xml", "rekordbox.xml")
    db.replace_source_tracks(
        source,
        [track("a" * 12, "/music/a.mp3", "Am I Wrong", artist="Étienne de Crécy",
               album="Super Discount", bpm=124.0, musical_key="Am",
               tag_source="rekordbox")],
    )

    stored = db.library_tracks(lib)
    assert len(stored) == 1
    assert stored[0].artist == "Étienne de Crécy"
    assert stored[0].bpm == 124.0
    assert stored[0].musical_key == "Am"


def test_replace_source_tracks_replaces_not_appends(lib: int) -> None:
    source = db.upsert_source(lib, "folder", "/music")
    db.replace_source_tracks(source, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(source, [track("b" * 12, "/music/b.mp3")])
    assert [t.path for t in db.all_tracks()] == ["/music/b.mp3"]


def test_sources_report_their_counts(lib: int) -> None:
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(
        xml, [track("b" * 12, "/x/b.mp3"), track("c" * 12, "/x/c.mp3")]
    )

    sources = {source.label: source for source in db.list_sources(lib)}
    assert sources["/music"].track_count == 1
    assert sources["/music"].kind == "folder"
    assert sources["rekordbox.xml"].track_count == 2
    assert db.source_library_id(folder) == lib


def test_source_tracks_keyed_by_path_for_incremental_scans(lib: int) -> None:
    source = db.upsert_source(lib, "folder", "/music")
    db.replace_source_tracks(source, [track("a" * 12, "/music/a.mp3")])
    stored = db.source_tracks(source)
    assert set(stored) == {"/music/a.mp3"}
    assert stored["/music/a.mp3"].mtime_ms == 1000


def test_delete_source_removes_its_tracks(lib: int) -> None:
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    db.replace_source_tracks(xml, [track("b" * 12, "/x/b.mp3")])

    assert db.delete_source(folder) is True
    assert [t.path for t in db.all_tracks()] == ["/x/b.mp3"]
    assert [s.label for s in db.list_sources(lib)] == ["rekordbox.xml"]
    assert db.delete_source(9999) is False


def test_same_file_in_two_sources_is_stored_once_but_counted_by_both(lib: int) -> None:
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/a.mp3")
    db.replace_source_tracks(folder, [shared])
    db.replace_source_tracks(xml, [shared])

    assert len(db.all_tracks()) == 1
    assert len(db.library_tracks(lib)) == 1  # not double-counted in the library
    counts = {source.kind: source.track_count for source in db.list_sources(lib)}
    assert counts == {"folder": 1, "xml": 1}


def test_shared_track_survives_removing_one_of_its_sources(lib: int) -> None:
    """A file in both a folder scan and an XML import must not vanish when
    either one is removed — only when the last claim on it goes away."""
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/shared.mp3")
    db.replace_source_tracks(folder, [shared, track("b" * 12, "/music/only.mp3")])
    db.replace_source_tracks(xml, [shared])

    db.delete_source(folder)
    assert [t.path for t in db.all_tracks()] == ["/music/shared.mp3"]

    db.delete_source(xml)
    assert db.all_tracks() == []


def test_rescanning_a_folder_does_not_steal_tracks_from_another_source(lib: int) -> None:
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    shared = track("a" * 12, "/music/shared.mp3")
    db.replace_source_tracks(xml, [shared])
    db.replace_source_tracks(folder, [shared])
    db.replace_source_tracks(folder, [shared])  # rescan

    counts = {source.kind: source.track_count for source in db.list_sources(lib)}
    assert counts == {"folder": 1, "xml": 1}
    assert len(db.all_tracks()) == 1


def test_a_folder_rescan_keeps_bpm_and_key_it_cannot_see(lib: int) -> None:
    """A scan of files without analysis tags must not blank rekordbox's values."""
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    folder = db.upsert_source(lib, "folder", "/music")
    path = "/music/shared.mp3"
    db.replace_source_tracks(
        xml, [track("a" * 12, path, bpm=124.0, musical_key="Am", tag_source="rekordbox")]
    )
    db.replace_source_tracks(
        folder, [track("a" * 12, path, artist="Tagged Artist", tag_source="tags")]
    )

    stored = db.all_tracks()[0]
    assert stored.bpm == 124.0
    assert stored.musical_key == "Am"
    assert stored.artist == "Tagged Artist"  # observable fields do update


def test_rekordbox_analysis_outranks_file_tags(lib: int) -> None:
    """Both sources can supply BPM/key; rekordbox analysed it, so it wins."""
    folder = db.upsert_source(lib, "folder", "/music")
    xml = db.upsert_source(lib, "xml", "rekordbox.xml")
    path = "/music/shared.mp3"

    db.replace_source_tracks(
        folder, [track("a" * 12, path, bpm=128.0, musical_key="8A", tag_source="tags")]
    )
    assert db.all_tracks()[0].bpm == 128.0  # tags fill the gap

    db.replace_source_tracks(
        xml, [track("a" * 12, path, bpm=127.98, musical_key="Am", tag_source="rekordbox")]
    )
    stored = db.all_tracks()[0]
    assert stored.bpm == 127.98
    assert stored.musical_key == "Am"

    # ...and a later folder rescan does not take it back.
    db.replace_source_tracks(
        folder, [track("a" * 12, path, bpm=128.0, musical_key="8A", tag_source="tags")]
    )
    assert db.all_tracks()[0].bpm == 127.98


def test_dropping_a_track_from_a_source_removes_it_when_unclaimed(lib: int) -> None:
    folder = db.upsert_source(lib, "folder", "/music")
    db.replace_source_tracks(
        folder, [track("a" * 12, "/music/a.mp3"), track("b" * 12, "/music/b.mp3")]
    )
    db.replace_source_tracks(folder, [track("a" * 12, "/music/a.mp3")])
    assert [t.path for t in db.all_tracks()] == ["/music/a.mp3"]


# --- in-memory active library ----------------------------------------------

def test_active_library_reloads_from_disk(lib: int) -> None:
    db.replace_source_tracks(
        db.upsert_source(lib, "folder", "/music"),
        [track("a" * 12, "/music/a.mp3"), track("b" * 12, "/music/b.wav", ext="wav")],
    )

    library = ActiveLibrary()
    assert library.is_loaded() is False
    library.load(lib)

    assert library.is_loaded() is True
    assert library.id == lib
    assert library.name == "MacBook"
    assert len(library.tracks) == 2
    assert library.by_id["a" * 12].path == "/music/a.mp3"
    summary = library.summary()
    assert summary["track_count"] == 2
    assert summary["by_ext"] == {"mp3": 1, "wav": 1}
    assert summary["active_library_name"] == "MacBook"
    assert summary["sources"][0]["label"] == "/music"


def test_switching_libraries_swaps_the_tracks(lib: int) -> None:
    other = db.create_library("Studio PC")
    db.replace_source_tracks(
        db.upsert_source(lib, "folder", "/mac"), [track("a" * 12, "/mac/a.mp3")]
    )
    db.replace_source_tracks(
        db.upsert_source(other, "folder", "/pc"), [track("b" * 12, "/pc/b.mp3")]
    )

    library = ActiveLibrary()
    library.load(lib)
    assert [t.path for t in library.tracks] == ["/mac/a.mp3"]
    generation = library.generation

    library.load(other)
    assert [t.path for t in library.tracks] == ["/pc/b.mp3"]
    assert library.generation > generation  # forces the matcher index to rebuild
    assert db.active_library_id() == other  # selection is persisted


def test_active_library_with_no_libraries_is_empty() -> None:
    library = ActiveLibrary()
    library.load()
    assert library.id is None
    assert library.is_loaded() is False
    assert library.summary()["libraries"] == []


# --- migrations ------------------------------------------------------------

def test_migrates_a_v1_database_without_losing_tracks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v1 kept a single source_id column on tracks; upgrading must not force
    a rescan or drop the rekordbox import."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v1.db")
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

    db.init()  # migrate v1 -> v4

    tracks = {t.path: t for t in db.all_tracks()}
    assert set(tracks) == {"/music/a.mp3", "/x/b.mp3"}
    assert tracks["/x/b.mp3"].bpm == 128.0

    # Pre-library data lands in one default library, still selected.
    libraries = db.list_libraries()
    assert [library.name for library in libraries] == ["My library"]
    assert libraries[0].track_count == 2
    assert db.active_library_id() == libraries[0].id
    counts = {s.label: s.track_count for s in db.list_sources(libraries[0].id)}
    assert counts == {"/music": 1, "rekordbox.xml": 1}

    db.init()  # idempotent
    assert len(db.all_tracks()) == 2


def test_migrates_a_v3_database_into_a_default_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """v3 had sources and preferences but no libraries."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v3.db")
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                label TEXT NOT NULL, added_at TEXT NOT NULL, UNIQUE (kind, label)
            );
            CREATE TABLE tracks (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
                ext TEXT NOT NULL, artist TEXT, title TEXT NOT NULL, album TEXT,
                duration_sec REAL, bitrate_kbps INTEGER, bpm REAL, musical_key TEXT,
                tag_source TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ms INTEGER NOT NULL
            );
            CREATE TABLE track_sources (
                track_id TEXT NOT NULL, source_id INTEGER NOT NULL,
                PRIMARY KEY (track_id, source_id)
            );
            CREATE TABLE preferences (
                id TEXT PRIMARY KEY, signature TEXT NOT NULL, artist TEXT NOT NULL,
                title TEXT NOT NULL, track_id TEXT NOT NULL, chosen_at TEXT NOT NULL
            );
            INSERT INTO sources (id, kind, label, added_at)
                VALUES (1, 'folder', '/music', '2026-01-01T00:00:00Z');
            INSERT INTO tracks VALUES ('aaaaaaaaaaaa', '/music/a.mp3', 'a', 'mp3',
                'Artist One', 'Anthem', NULL, 200.0, 320, NULL, NULL, 'tags', 10, 1);
            INSERT INTO track_sources VALUES ('aaaaaaaaaaaa', 1);
            INSERT INTO preferences VALUES ('sig123', 'artist one|anthem||',
                'Artist One', 'Anthem', 'aaaaaaaaaaaa', '2026-01-01T00:00:00Z');
            """
        )

    db.init()

    libraries = db.list_libraries()
    assert [library.name for library in libraries] == ["My library"]
    default = libraries[0].id
    assert [t.path for t in db.library_tracks(default)] == ["/music/a.mp3"]
    # The remembered choice carries over into that library.
    assert db.preference_map(default) == {"sig123": "aaaaaaaaaaaa"}
    assert db.list_preferences(default)[0].file_label == "a.mp3"
    assert db.active_library_id() == default
