import hashlib
import json
import os
from pathlib import Path

from server.models import LibraryTrack

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"


def cache_file(folder: str) -> Path:
    digest = hashlib.sha1(folder.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"scan-{digest}.json"


def load_cache(folder: str) -> dict[str, dict]:
    """path → {mtime_ms, size_bytes, track} for the previous scan of folder."""
    try:
        raw = json.loads(cache_file(folder).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = raw.get("entries")
    return entries if isinstance(entries, dict) else {}


def save_cache(folder: str, tracks: list[LibraryTrack]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    entries = {
        track.path: {
            "mtime_ms": track.mtime_ms,
            "size_bytes": track.size_bytes,
            "track": track.model_dump(),
        }
        for track in tracks
    }
    target = cache_file(folder)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"entries": entries}), "utf-8")
    os.replace(tmp, target)


def cached_track(entry: dict) -> LibraryTrack | None:
    try:
        return LibraryTrack.model_validate(entry["track"])
    except Exception:
        return None
