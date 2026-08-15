import httpx

from .parse_embed import parse_embed_html

EMBED_URL = "https://open.spotify.com/embed/playlist/{playlist_id}"
# A browser-like UA: the embed page serves its normal payload to browsers.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en",
}


class SpotifyFetchError(Exception):
    pass


def fetch_playlist(playlist_id: str) -> dict:
    try:
        response = httpx.get(
            EMBED_URL.format(playlist_id=playlist_id),
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SpotifyFetchError(
            f"could not fetch the Spotify embed page: {exc}"
        ) from exc
    result = parse_embed_html(response.text)
    result["playlist_id"] = playlist_id
    return result
