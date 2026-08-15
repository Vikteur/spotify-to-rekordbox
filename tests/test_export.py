import xml.etree.ElementTree as ET

import pytest

from server.export.m3u8 import build_m3u8
from server.export.missing import build_missing_txt
from server.export.rekordbox_xml import build_rekordbox_xml, path_to_location
from server.models import LibraryTrack, MissingTrackInput


def track(path: str, artist: str | None, title: str, duration: float | None,
          ext: str = "mp3", album: str | None = None) -> LibraryTrack:
    return LibraryTrack(
        id="x" * 12, path=path, filename=title, ext=ext, artist=artist,
        title=title, album=album, duration_sec=duration, bitrate_kbps=320,
        tag_source="tags", size_bytes=1, mtime_ms=1,
    )


MAC = track("/Users/viktor/Music/DJ/Étienne de Crécy - Am I Wrong.mp3",
            "Étienne de Crécy", "Am I Wrong", 371.2, album="Super Discount")
WIN = track("C:\\Music\\DJ\\Purple Disco Machine - Substitution (Extended Mix).mp3",
            "Purple Disco Machine", "Substitution (Extended Mix)", 213.0)
NO_DURATION = track("/mnt/music/Mystery & Friends.wav", None, "Mystery & Friends", None, ext="wav")


def test_m3u8_exact_output() -> None:
    assert build_m3u8([MAC, WIN, NO_DURATION]) == (
        "#EXTM3U\n"
        "#EXTINF:371,Étienne de Crécy - Am I Wrong\n"
        "/Users/viktor/Music/DJ/Étienne de Crécy - Am I Wrong.mp3\n"
        "#EXTINF:213,Purple Disco Machine - Substitution (Extended Mix)\n"
        "C:\\Music\\DJ\\Purple Disco Machine - Substitution (Extended Mix).mp3\n"
        "#EXTINF:-1,Mystery & Friends\n"
        "/mnt/music/Mystery & Friends.wav\n"
    )


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        ("C:\\Música\\Té st.mp3", "file://localhost/C:/M%C3%BAsica/T%C3%A9%20st.mp3"),
        (
            "/Users/viktor/Music/Étienne - Am I Wrong.mp3",
            "file://localhost/Users/viktor/Music/%C3%89tienne%20-%20Am%20I%20Wrong.mp3",
        ),
        ("D:\\a\\b (Remix).mp3", "file://localhost/D:/a/b%20(Remix).mp3"),
        ("/plain/path/song.mp3", "file://localhost/plain/path/song.mp3"),
    ],
)
def test_path_to_location(native: str, expected: str) -> None:
    assert path_to_location(native) == expected


def test_rekordbox_xml_structure_roundtrip() -> None:
    xml = build_rekordbox_xml("Friday & Warmup", [MAC, WIN])
    root = ET.fromstring(xml)  # also proves well-formedness incl. & escaping

    assert root.tag == "DJ_PLAYLISTS" and root.get("Version") == "1.0.0"
    collection = root.find("COLLECTION")
    assert collection is not None and collection.get("Entries") == "2"
    tracks = collection.findall("TRACK")
    assert [t.get("TrackID") for t in tracks] == ["1", "2"]
    assert tracks[0].get("Artist") == "Étienne de Crécy"
    assert tracks[0].get("TotalTime") == "371"
    assert tracks[0].get("Location") == (
        "file://localhost/Users/viktor/Music/DJ/"
        "%C3%89tienne%20de%20Cr%C3%A9cy%20-%20Am%20I%20Wrong.mp3"
    )
    assert tracks[1].get("Location") == (
        "file://localhost/C:/Music/DJ/"
        "Purple%20Disco%20Machine%20-%20Substitution%20(Extended%20Mix).mp3"
    )
    assert tracks[1].get("Kind") == "MP3 File"

    playlists_root = root.find("PLAYLISTS/NODE")
    assert playlists_root is not None
    assert playlists_root.get("Type") == "0" and playlists_root.get("Count") == "1"
    playlist = playlists_root.find("NODE")
    assert playlist is not None
    assert playlist.get("Name") == "Friday & Warmup"
    assert playlist.get("Type") == "1"
    assert playlist.get("KeyType") == "0"
    assert playlist.get("Entries") == "2"
    assert [k.get("Key") for k in playlist.findall("TRACK")] == ["1", "2"]


def missing(artist: str, title: str, had_candidates: bool = False) -> MissingTrackInput:
    return MissingTrackInput(artist=artist, title=title, had_candidates=had_candidates)


def test_missing_txt_lists_tracks_you_can_paste_into_a_shop() -> None:
    text = build_missing_txt(
        "Friday Warmup",
        "MacBook",
        [missing("Étienne de Crécy", "Am I Wrong"), missing("Some DJ", "Rare Dub")],
    )
    lines = text.splitlines()
    assert lines[0] == "# Missing tracks"
    assert lines[1] == "# Playlist: Friday Warmup"
    assert "2 track(s)" in lines[2] and "MacBook" in lines[2]
    # Everything that isn't a comment is a plain, pasteable "Artist - Title".
    entries = [line for line in lines if line and not line.startswith("#")]
    assert entries == ["Étienne de Crécy - Am I Wrong", "Some DJ - Rare Dub"]


def test_missing_txt_separates_skipped_from_not_found() -> None:
    text = build_missing_txt(
        "Set",
        "MacBook",
        [missing("A", "Nowhere"), missing("B", "Passed On", had_candidates=True)],
    )
    assert "# Not found:" in text
    assert "# Skipped" in text
    # Not-found comes first: that is the part you actually go and buy.
    assert text.index("A - Nowhere") < text.index("B - Passed On")


def test_missing_txt_without_skipped_has_no_section_headers() -> None:
    text = build_missing_txt("Set", "MacBook", [missing("A", "Nowhere")])
    assert "# Not found:" not in text
    assert "# Skipped" not in text


def test_missing_txt_handles_a_pasted_line_with_no_artist() -> None:
    text = build_missing_txt("Set", None, [missing("", "Just A Title")])
    assert "Just A Title" in text
    assert " - Just A Title" not in text
    assert "your library" in text  # falls back when no library is named


def test_xml_omits_duration_when_unknown_and_defaults_kind() -> None:
    xml = build_rekordbox_xml("List", [NO_DURATION])
    root = ET.fromstring(xml)
    entry = root.find("COLLECTION/TRACK")
    assert entry is not None
    assert entry.get("TotalTime") is None
    assert entry.get("Kind") == "WAV File"
    assert entry.get("Artist") == ""
