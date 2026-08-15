import pytest

from server.export.rekordbox_xml import build_rekordbox_xml, path_to_location
from server.models import LibraryTrack
from server.rekordbox_import import (
    RekordboxXmlError,
    location_to_path,
    parse_collection,
)


def collection_xml(*track_attrs: str) -> bytes:
    entries = "\n".join(f"    <TRACK {attrs}/>" for attrs in track_attrs)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<DJ_PLAYLISTS Version="1.0.0">\n'
        '  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>\n'
        f'  <COLLECTION Entries="{len(track_attrs)}">\n{entries}\n  </COLLECTION>\n'
        '  <PLAYLISTS>\n'
        '    <NODE Type="0" Name="ROOT" Count="1">\n'
        '      <NODE Name="Some Playlist" Type="1" KeyType="0" Entries="1">\n'
        '        <TRACK Key="1"/>\n'
        '      </NODE>\n'
        '    </NODE>\n'
        '  </PLAYLISTS>\n'
        '</DJ_PLAYLISTS>\n'
    ).encode("utf-8")


@pytest.mark.parametrize(
    "native",
    [
        "/Users/viktor/Music/DJ/Étienne de Crécy - Am I Wrong.mp3",
        "C:\\Música\\Té st.mp3",
        "D:\\a\\b (Remix).mp3",
        "/mnt/music/Mystery & Friends.m4a",
        "/plain/path/song.flac",
    ],
)
def test_location_path_roundtrip(native: str) -> None:
    assert location_to_path(path_to_location(native)) == native


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("file://localhost/Users/v/song.mp3", "/Users/v/song.mp3"),
        ("file:///Users/v/song.mp3", "/Users/v/song.mp3"),
        ("file://localhost/C:/Music/song.mp3", "C:\\Music\\song.mp3"),
        (
            "file://localhost/Users/v/%C3%89tienne%20-%20Am%20I%20Wrong.mp3",
            "/Users/v/Étienne - Am I Wrong.mp3",
        ),
    ],
)
def test_location_to_path(location: str, expected: str) -> None:
    assert location_to_path(location) == expected


def test_parses_collection_tracks() -> None:
    data = collection_xml(
        'TrackID="1" Name="Am I Wrong" Artist="Étienne de Crécy" Album="Super Discount" '
        'Kind="MP3 File" Size="8388608" TotalTime="371" AverageBpm="124.00" '
        'BitRate="320" Tonality="Am" '
        'Location="file://localhost/Users/v/Music/am-i-wrong.mp3"',
        'TrackID="2" Name="Substitution" Artist="Purple Disco Machine" Mix="Extended Mix" '
        'Kind="MP3 File" TotalTime="213" Location="file://localhost/Users/v/Music/sub.mp3"',
    )
    tracks, warnings = parse_collection(data)
    assert warnings == []
    assert len(tracks) == 2  # the PLAYLISTS <TRACK Key="1"/> is not a collection entry

    first = tracks[0]
    assert first.artist == "Étienne de Crécy"
    assert first.title == "Am I Wrong"
    assert first.album == "Super Discount"
    assert first.duration_sec == 371
    assert first.bitrate_kbps == 320
    assert first.bpm == 124.0
    assert first.musical_key == "Am"
    assert first.ext == "mp3"
    assert first.filename == "am-i-wrong"
    assert first.path == "/Users/v/Music/am-i-wrong.mp3"
    assert first.tag_source == "rekordbox"
    assert first.size_bytes == 8388608

    # A separate Mix attribute is folded into the title so version matching sees it.
    assert tracks[1].title == "Substitution (Extended Mix)"


def test_mix_already_in_name_is_not_duplicated() -> None:
    tracks, _ = parse_collection(
        collection_xml(
            'Name="Substitution (Extended Mix)" Mix="Extended Mix" Artist="A" '
            'TotalTime="213" Location="file://localhost/m/s.mp3"'
        )
    )
    assert tracks[0].title == "Substitution (Extended Mix)"


def test_missing_optional_fields_are_none() -> None:
    tracks, _ = parse_collection(
        collection_xml('Name="Bare" Location="file://localhost/m/bare.mp3"')
    )
    track = tracks[0]
    assert track.artist is None
    assert track.album is None
    assert track.duration_sec is None
    assert track.bpm is None
    assert track.musical_key is None
    assert track.size_bytes == 0


def test_non_audio_and_duplicate_entries_are_skipped() -> None:
    tracks, warnings = parse_collection(
        collection_xml(
            'Name="Video" Location="file://localhost/m/clip.mp4"',
            'Name="Song" Location="file://localhost/m/song.mp3"',
            'Name="Song again" Location="file://localhost/m/song.mp3"',
        )
    )
    assert [track.filename for track in tracks] == ["song"]
    assert any("clip.mp4" in warning for warning in warnings)


def test_windows_export_keeps_native_separators() -> None:
    tracks, _ = parse_collection(
        collection_xml(
            'Name="W" Location="file://localhost/C:/Music/DJ/track.mp3"'
        )
    )
    assert tracks[0].path == "C:\\Music\\DJ\\track.mp3"
    assert tracks[0].filename == "track"


def test_round_trip_through_our_own_exporter() -> None:
    """A playlist we export must import back as the same tracks."""
    original = LibraryTrack(
        id="a" * 12, path="/Users/v/Music/Étienne - Am I Wrong.mp3",
        filename="Étienne - Am I Wrong", ext="mp3", artist="Étienne de Crécy",
        title="Am I Wrong", album="Super Discount", duration_sec=371.0,
        bitrate_kbps=320, tag_source="tags", size_bytes=1, mtime_ms=1,
    )
    xml = build_rekordbox_xml("Some Playlist", [original]).encode("utf-8")
    tracks, _ = parse_collection(xml)
    assert len(tracks) == 1
    assert tracks[0].path == original.path
    assert tracks[0].artist == original.artist
    assert tracks[0].title == original.title
    assert tracks[0].duration_sec == original.duration_sec


def test_rejects_non_rekordbox_xml() -> None:
    with pytest.raises(RekordboxXmlError, match="no rekordbox collection"):
        parse_collection(b"<?xml version='1.0'?><rss><channel/></rss>")


def test_rejects_malformed_xml() -> None:
    with pytest.raises(RekordboxXmlError, match="not valid XML"):
        parse_collection(b"<DJ_PLAYLISTS><COLLECTION>")


def test_rejects_empty_collection() -> None:
    with pytest.raises(RekordboxXmlError, match="empty"):
        parse_collection(collection_xml())
