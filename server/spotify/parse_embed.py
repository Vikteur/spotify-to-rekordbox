"""Parse Spotify's public embed page into a playlist dict.

The embed page (open.spotify.com/embed/playlist/<id>) ships its data as JSON
inside a <script id="__NEXT_DATA__"> tag. That JSON is Spotify-internal and can
change shape, so all parsing lives in this pure module where fixture tests pin
it down, with a structure-tolerant fallback search for when Spotify re-nests
things. Plan B if the embed approach breaks entirely: the `spotifyscraper`
package on PyPI implements the same anonymous technique.
"""

import json
import re

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
_PLAYLIST_URL_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[A-Za-z-]+/)?playlist/([A-Za-z0-9]{22})"
)

# Embed pages have never been observed returning more than ~100 tracks; at that
# size with no explicit total we must assume the playlist continues.
TRUNCATION_FLOOR = 100


class BadPlaylistUrl(ValueError):
    pass


class EmbedParseError(Exception):
    pass


def parse_playlist_url(text: str) -> str:
    """Accept a full playlist URL (with ?si=, intl-xx/ segments) or a bare id."""
    text = text.strip().strip("\"'")
    if _BARE_ID_RE.match(text):
        return text
    match = _PLAYLIST_URL_RE.search(text)
    if match:
        return match.group(1)
    if "open.spotify.com" in text:
        raise BadPlaylistUrl(
            "That looks like a Spotify link, but not a playlist link. "
            "Use a URL like https://open.spotify.com/playlist/..."
        )
    raise BadPlaylistUrl("Not a Spotify playlist URL or playlist id.")


def parse_embed_html(html: str) -> dict:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise EmbedParseError("no __NEXT_DATA__ script tag in the embed page")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise EmbedParseError(f"embed page JSON did not parse: {exc}") from exc

    entity = _entity_from(data)
    if entity is None:
        raise EmbedParseError(
            "no playlist entity with a trackList found in the embed data "
            "(private/deleted playlist, or Spotify changed the page format)"
        )

    items = entity["trackList"]
    if isinstance(items, dict):
        items = items.get("items", [])
    tracks = [_track_from(item, i) for i, item in enumerate(items)]

    total = _total_from(entity)
    truncated = (total is not None and total > len(tracks)) or (
        total is None and len(tracks) >= TRUNCATION_FLOOR
    )
    return {
        "name": entity.get("name") or "Spotify playlist",
        "owner_name": entity.get("subtitle") or None,
        "total": total,
        "truncated": truncated,
        "tracks": tracks,
    }


def _looks_like_entity(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    track_list = obj.get("trackList")
    if isinstance(track_list, dict):
        track_list = track_list.get("items")
    if not isinstance(track_list, list):
        return False
    return not track_list or (
        isinstance(track_list[0], dict) and "title" in track_list[0]
    )


def _entity_from(data: dict) -> dict | None:
    try:
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        if _looks_like_entity(entity):
            return entity
    except (KeyError, TypeError):
        pass
    return _find_entity(data)


def _find_entity(node: object) -> dict | None:
    """Fallback: search the whole JSON tree for anything shaped like a playlist."""
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if _looks_like_entity(current):
                return current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _track_from(item: dict, index: int) -> dict:
    artist = item.get("subtitle") or ""
    if not artist and isinstance(item.get("artists"), list):
        artist = ", ".join(
            a.get("name", "") for a in item["artists"] if isinstance(a, dict)
        ).strip(", ")
    return {
        "index": index,
        "artist": artist,
        "title": item.get("title") or "",
        "duration_sec": _duration_sec(item),
    }


def _duration_sec(item: dict) -> int | None:
    ms = item.get("durationMs")
    if ms is None:
        duration = item.get("duration")
        if isinstance(duration, dict):
            ms = duration.get("totalMilliseconds")
        elif isinstance(duration, (int, float)):
            # Historic bare `duration` field is milliseconds; values under
            # 10000 can only plausibly be seconds.
            ms = duration if duration >= 10000 else duration * 1000
    if not isinstance(ms, (int, float)):
        return None
    return round(ms / 1000)


def _total_from(entity: dict) -> int | None:
    for key in ("totalCount", "trackCount", "totalTrackCount", "numTracks"):
        value = entity.get(key)
        if isinstance(value, int):
            return value
    track_list = entity.get("trackList")
    if isinstance(track_list, dict):
        value = track_list.get("totalCount")
        if isinstance(value, int):
            return value
    return None
