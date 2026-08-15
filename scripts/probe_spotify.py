#!/usr/bin/env python3
"""Live smoke test for the anonymous Spotify playlist fetch.

Run this on your own machine (the fetch needs open internet access):

    python scripts/probe_spotify.py https://open.spotify.com/playlist/<id>

Exit codes: 0 = fetch + parse worked, 1 = failed (output says why).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.spotify.fetch import SpotifyFetchError, fetch_playlist  # noqa: E402
from server.spotify.parse_embed import (  # noqa: E402
    BadPlaylistUrl,
    EmbedParseError,
    parse_playlist_url,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip())
        return 2
    try:
        playlist_id = parse_playlist_url(sys.argv[1])
    except BadPlaylistUrl as exc:
        print(f"BAD URL: {exc}")
        return 1
    try:
        playlist = fetch_playlist(playlist_id)
    except SpotifyFetchError as exc:
        print(f"FETCH FAILED: {exc}")
        return 1
    except EmbedParseError as exc:
        print(f"PARSE FAILED (Spotify may have changed the embed format): {exc}")
        print("Fallback: paste the tracklist as text in the app.")
        return 1

    tracks = playlist["tracks"]
    print(f"OK: “{playlist['name']}” by {playlist['owner_name'] or '?'}")
    print(
        f"    {len(tracks)} tracks fetched, total={playlist['total']}, "
        f"truncated={playlist['truncated']}"
    )
    for track in tracks[:5]:
        duration = track["duration_sec"]
        mins = f"{duration // 60}:{duration % 60:02d}" if duration else "?:??"
        print(f"    {track['index'] + 1:3d}. {track['artist']} - {track['title']} ({mins})")
    if len(tracks) > 5:
        print(f"    ... and {len(tracks) - 5} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
