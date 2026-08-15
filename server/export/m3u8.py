"""M3U8 playlist — rekordbox: File > Import > Import Playlist.

Paths are emitted verbatim as scanned (backslashes and drive letter on
Windows, POSIX on macOS): rekordbox resolves entries by file path, matching
tracks already in the collection and adding+analyzing new ones. UTF-8, LF,
no BOM (if rekordbox-on-Windows ever garbles accents, a BOM prefix is the
documented one-line fallback).
"""

from server.models import LibraryTrack


def build_m3u8(tracks: list[LibraryTrack]) -> str:
    lines = ["#EXTM3U"]
    for track in tracks:
        seconds = round(track.duration_sec) if track.duration_sec else -1
        label = f"{track.artist} - {track.title}" if track.artist else track.title
        lines.append(f"#EXTINF:{seconds},{label}")
        lines.append(track.path)
    return "\n".join(lines) + "\n"
