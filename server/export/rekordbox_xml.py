"""rekordbox XML (DJ_PLAYLISTS 1.0.0) — the xml-bridge import route.

rekordbox: Preferences > Advanced > Database > rekordbox xml → point it at
the exported file, show the rekordbox xml pane (Preferences > View >
Layout), then right-click the playlist in that pane → Import Playlist.
Tracks are linked by Location, so paths must round-trip exactly.
"""

from urllib.parse import quote

from server.models import LibraryTrack

_KIND = {
    "mp3": "MP3 File",
    "m4a": "M4A File",
    "flac": "FLAC File",
    "wav": "WAV File",
    "aiff": "AIFF File",
}


def _kind(ext: str) -> str:
    """rekordbox's display 'Kind' for a file extension.

    Unmapped extensions fall back to a label derived from the extension itself
    (e.g. 'ogg' → 'OGG File') rather than mislabelling everything as an MP3;
    rekordbox re-analyses on import, so the exact string is cosmetic.
    """
    if ext in _KIND:
        return _KIND[ext]
    return f"{ext.upper()} File" if ext else "Unknown"


def path_to_location(native_path: str) -> str:
    """'C:\\Música\\Té st.mp3' → 'file://localhost/C:/M%C3%BAsica/T%C3%A9%20st.mp3'.

    Every segment is percent-encoded (UTF-8) except a Windows drive-letter
    segment, which rekordbox expects verbatim ('C:', never 'C%3A').
    """
    segments = native_path.replace("\\", "/").split("/")
    encoded = [
        segment
        if len(segment) == 2 and segment[1] == ":" and segment[0].isalpha()
        else quote(segment, safe="!'()*~-._")
        for segment in segments
    ]
    return "file://localhost/" + "/".join(encoded).lstrip("/")


def _attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _track_element(track_id: int, track: LibraryTrack) -> str:
    attrs = [
        f'TrackID="{track_id}"',
        f'Name="{_attr(track.title)}"',
        f'Artist="{_attr(track.artist or "")}"',
        f'Album="{_attr(track.album or "")}"',
        f'Kind="{_kind(track.ext)}"',
    ]
    if track.duration_sec:
        attrs.append(f'TotalTime="{round(track.duration_sec)}"')
    attrs.append(f'Location="{_attr(path_to_location(track.path))}"')
    return f'    <TRACK {" ".join(attrs)}/>'


def build_rekordbox_xml(playlist_name: str, tracks: list[LibraryTrack]) -> str:
    collection_lines = []
    key_lines = []
    for track_id, track in enumerate(tracks, start=1):
        collection_lines.append(_track_element(track_id, track))
        key_lines.append(f'        <TRACK Key="{track_id}"/>')

    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<DJ_PLAYLISTS Version="1.0.0">',
            '  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>',
            f'  <COLLECTION Entries="{len(tracks)}">',
            *collection_lines,
            "  </COLLECTION>",
            "  <PLAYLISTS>",
            '    <NODE Type="0" Name="ROOT" Count="1">',
            # Type 1 = playlist; KeyType 0 = child TRACK Keys reference TrackID.
            f'      <NODE Name="{_attr(playlist_name)}" Type="1" KeyType="0" Entries="{len(tracks)}">',
            *key_lines,
            "      </NODE>",
            "    </NODE>",
            "  </PLAYLISTS>",
            "</DJ_PLAYLISTS>",
            "",
        ]
    )


def build_rekordbox_folder_xml(
    folder_name: str, playlists: list[tuple[str, list[LibraryTrack]]]
) -> str:
    """One file, one folder, one playlist per chapter — a whole wedding.

    rekordbox nests with the same element: Type 0 is a folder, Type 1 a
    playlist. Importing this puts a folder in the rekordbox xml pane with the
    couple's chapters inside, in the order given, instead of making the DJ
    export and name each list by hand.

    A track used by two chapters (their top 20 *and* a must-play) is written
    to COLLECTION once and referenced from both — rekordbox links playlist
    entries to collection entries by TrackID, so duplicating it there would
    import the same file twice.
    """
    track_ids: dict[str, int] = {}
    collection_lines: list[str] = []
    for _, tracks in playlists:
        for track in tracks:
            if track.id in track_ids:
                continue
            track_ids[track.id] = len(track_ids) + 1
            collection_lines.append(_track_element(track_ids[track.id], track))

    playlist_lines: list[str] = []
    for name, tracks in playlists:
        playlist_lines.append(
            f'        <NODE Name="{_attr(name)}" Type="1" KeyType="0"'
            f' Entries="{len(tracks)}">'
        )
        playlist_lines.extend(
            f'          <TRACK Key="{track_ids[track.id]}"/>' for track in tracks
        )
        playlist_lines.append("        </NODE>")

    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<DJ_PLAYLISTS Version="1.0.0">',
            '  <PRODUCT Name="rekordbox" Version="6.8.5" Company="AlphaTheta"/>',
            f'  <COLLECTION Entries="{len(track_ids)}">',
            *collection_lines,
            "  </COLLECTION>",
            "  <PLAYLISTS>",
            '    <NODE Type="0" Name="ROOT" Count="1">',
            f'      <NODE Type="0" Name="{_attr(folder_name)}"'
            f' Count="{len(playlists)}">',
            *playlist_lines,
            "      </NODE>",
            "    </NODE>",
            "  </PLAYLISTS>",
            "</DJ_PLAYLISTS>",
            "",
        ]
    )
