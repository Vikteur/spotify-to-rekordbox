"""Spotify track search, proxied server-side for the guest intake flow.

The browser never sees Spotify credentials: guests call our
`/api/guest/<token>/search` endpoint and this module talks to Spotify with
the **Client Credentials** flow (app token, no user login). The secret lives
in environment variables — `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` —
or, for setups without env management, in `data/spotify_credentials.json`
(`{"client_id": "...", "client_secret": "..."}`).

Only metadata is ever requested (title, artists, duration, ISRC, album art
URL) — no audio is downloaded from Spotify, here or anywhere else.

Guardrails, because the callers are anonymous wedding guests:
- identical queries are served from a small TTL cache (typeahead repeats a
  lot: backspacing, two friends typing the same song);
- cache *misses* are rate-limited per guest token with a sliding window.
"""

import json
import os
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path

import httpx

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
CREDENTIALS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "spotify_credentials.json"

RESULT_LIMIT = 8
CACHE_TTL_SEC = 600
CACHE_MAX = 512
RATE_WINDOW_SEC = 10.0
RATE_MAX_MISSES = 20     # upstream calls per guest token per window


class SearchUnavailable(Exception):
    """Credentials missing or Spotify unreachable — free text still works."""


class SearchRateLimited(Exception):
    pass


_lock = threading.Lock()
_token: str | None = None
_token_expires_at = 0.0
_cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()
_recent_misses: dict[str, deque] = {}


def reset() -> None:
    """Forget cached token/results/limits (tests, credential changes)."""
    global _token, _token_expires_at
    with _lock:
        _token = None
        _token_expires_at = 0.0
        _cache.clear()
        _recent_misses.clear()


def credentials() -> tuple[str, str] | None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        return client_id, client_secret
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        client_id = str(data.get("client_id", "")).strip()
        client_secret = str(data.get("client_secret", "")).strip()
        if client_id and client_secret:
            return client_id, client_secret
    except (OSError, ValueError):
        pass
    return None


def is_configured() -> bool:
    return credentials() is not None


def search_tracks(query: str, *, limiter_key: str) -> list[dict]:
    """Top matches for a typeahead query, cheapest source first."""
    q = " ".join(query.split()).lower()
    if not q:
        return []
    cached = _cache_get(q)
    if cached is not None:
        return cached
    _rate_check(limiter_key)
    results = _upstream_search(q)
    _cache_put(q, results)
    return results


# --- cache and rate limit ---------------------------------------------------

def _cache_get(q: str) -> list[dict] | None:
    with _lock:
        hit = _cache.get(q)
        if hit is None:
            return None
        stored_at, results = hit
        if time.time() - stored_at > CACHE_TTL_SEC:
            del _cache[q]
            return None
        _cache.move_to_end(q)
        return results


def _cache_put(q: str, results: list[dict]) -> None:
    with _lock:
        _cache[q] = (time.time(), results)
        _cache.move_to_end(q)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)


def _rate_check(limiter_key: str) -> None:
    now = time.time()
    with _lock:
        window = _recent_misses.setdefault(limiter_key, deque())
        while window and now - window[0] > RATE_WINDOW_SEC:
            window.popleft()
        if len(window) >= RATE_MAX_MISSES:
            raise SearchRateLimited("Searching a little too fast — give it a second.")
        window.append(now)


# --- Spotify ----------------------------------------------------------------

def _get_app_token() -> str:
    """The cached client-credentials token, refreshed just before it expires."""
    global _token, _token_expires_at
    with _lock:
        if _token and time.time() < _token_expires_at:
            return _token
    creds = credentials()
    if creds is None:
        raise SearchUnavailable(
            "Spotify search isn't configured (set SPOTIFY_CLIENT_ID and"
            " SPOTIFY_CLIENT_SECRET). Songs can still be typed in by hand."
        )
    client_id, client_secret = creds
    try:
        response = httpx.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SearchUnavailable(f"Spotify token request failed: {exc}") from exc
    token = payload.get("access_token")
    if not token:
        raise SearchUnavailable("Spotify token response had no access_token.")
    with _lock:
        _token = token
        # Refresh a minute early so an in-flight search never carries a dead token.
        _token_expires_at = time.time() + max(60, int(payload.get("expires_in", 3600)) - 60)
    return token


def _invalidate_token() -> None:
    global _token, _token_expires_at
    with _lock:
        _token = None
        _token_expires_at = 0.0


def _upstream_search(q: str) -> list[dict]:
    token = _get_app_token()
    params = {"q": q, "type": "track", "limit": RESULT_LIMIT}
    try:
        response = httpx.get(
            SEARCH_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 401:
            # Token aged out server-side: refresh once and retry.
            _invalidate_token()
            response = httpx.get(
                SEARCH_URL,
                params=params,
                headers={"Authorization": f"Bearer {_get_app_token()}"},
                timeout=10,
            )
        if response.status_code == 429:
            raise SearchRateLimited("Spotify asked us to slow down — try again in a moment.")
        response.raise_for_status()
        payload = response.json()
    except SearchRateLimited:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise SearchUnavailable(f"Spotify search failed: {exc}") from exc
    items = (payload.get("tracks") or {}).get("items") or []
    return [_map_track(item) for item in items if item]


def _map_track(item: dict) -> dict:
    album = item.get("album") or {}
    images = album.get("images") or []
    # Spotify sorts images large→small; the smallest is plenty for a 40px tile.
    art_url = images[-1]["url"] if images else None
    return {
        "spotify_id": item.get("id"),
        "uri": item.get("uri"),
        "isrc": (item.get("external_ids") or {}).get("isrc"),
        "title": item.get("name") or "",
        "artist": ", ".join(
            artist.get("name", "") for artist in item.get("artists") or [] if artist
        ),
        "duration_ms": item.get("duration_ms"),
        "art_url": art_url,
        "album": album.get("name"),
    }
