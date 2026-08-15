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


def build_rekordbox_xml(playlist_name: str, tracks: list[LibraryTrack]) -> str:
    collection_lines = []
    key_lines = []
    for track_id, track in enumerate(tracks, start=1):
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
        collection_lines.append(f'    <TRACK {" ".join(attrs)}/>')
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
