"""A shopping list: the playlist's tracks that your library doesn't have.

Plain "Artist - Title" lines so the file can be pasted straight into a shop's
search box — or back into this app's paste-a-tracklist box once you've bought
them. Context lives in leading `#` comment lines, which every tool that reads
tracklists ignores.
"""

from server.models import MissingTrackInput

HEADER = "# Missing tracks"


def build_missing_txt(
    playlist_name: str, library_name: str | None, tracks: list[MissingTrackInput]
) -> str:
    not_found = [track for track in tracks if not track.had_candidates]
    skipped = [track for track in tracks if track.had_candidates]

    where = f" in {library_name}" if library_name else " in your library"
    lines = [
        HEADER,
        f"# Playlist: {playlist_name}",
        f"# {len(tracks)} track(s) from this playlist are not{where}.",
        "",
    ]
    if not_found:
        if skipped:
            lines.append("# Not found:")
        lines.extend(_label(track) for track in not_found)
        lines.append("")
    if skipped:
        lines.append("# Skipped — these had possible matches you didn't take:")
        lines.extend(_label(track) for track in skipped)
        lines.append("")
    return "\n".join(lines)


def _label(track: MissingTrackInput) -> str:
    artist = track.artist.strip()
    title = track.title.strip()
    return f"{artist} - {title}" if artist else title
