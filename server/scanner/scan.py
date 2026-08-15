import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from server.models import LibraryTrack
from server.scanner.cache import cached_track, load_cache, save_cache
from server.scanner.tags import read_track
from server.scanner.walk import walk_library

PARSE_WORKERS = 8


class ScanInProgress(Exception):
    pass


class Scanner:
    """Owns the one in-memory library and the (single) background scan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.tracks: list[LibraryTrack] = []
        self.by_id: dict[str, LibraryTrack] = {}
        self.generation = 0  # bumped per completed scan; lets the matcher cache its index
        self._status: dict = {"state": "idle"}

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def has_library(self) -> bool:
        return bool(self.tracks) and self.status()["state"] == "done"

    def start_scan(self, folder: str, force: bool = False) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ScanInProgress
            self._status = {
                "state": "scanning",
                "found": 0,
                "parsed": 0,
                "from_cache": 0,
                "skipped_drm": 0,
                "errors": [],
            }
            self._thread = threading.Thread(
                target=self._run, args=(folder, force), daemon=True
            )
            self._thread.start()

    def wait(self) -> None:
        """Block until the current scan finishes (used by tests)."""
        thread = self._thread
        if thread is not None:
            thread.join()

    def _set(self, **fields: object) -> None:
        with self._lock:
            self._status.update(fields)

    def _run(self, folder: str, force: bool) -> None:
        started = time.monotonic()
        try:
            root = Path(folder)
            files, drm_count, walk_errors = walk_library(root)
            errors = [{"file": "", "message": message} for message in walk_errors]
            self._set(found=len(files), skipped_drm=drm_count, errors=errors)

            cache = {} if force else load_cache(folder)
            tracks: list[LibraryTrack] = []
            to_parse: list[Path] = []
            from_cache = 0
            for path in files:
                entry = cache.get(str(path))
                track = cached_track(entry) if entry else None
                if (
                    track is not None
                    and entry is not None
                    and self._entry_is_fresh(path, entry)
                ):
                    tracks.append(track)
                    from_cache += 1
                else:
                    to_parse.append(path)
            self._set(from_cache=from_cache)

            parsed = 0
            with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
                for track, error in pool.map(read_track, to_parse):
                    tracks.append(track)
                    parsed += 1
                    if error:
                        errors.append({"file": track.path, "message": error})
                    if parsed % 25 == 0:
                        self._set(parsed=parsed, errors=errors)
            self._set(parsed=parsed, errors=errors)

            tracks.sort(key=lambda t: t.path)
            save_cache(folder, tracks)

            by_ext: dict[str, int] = {}
            for track in tracks:
                by_ext[track.ext] = by_ext.get(track.ext, 0) + 1
            summary = {
                "folder": folder,
                "track_count": len(tracks),
                "by_ext": by_ext,
                "from_cache": from_cache,
                "skipped_drm": drm_count,
                "scan_ms": round((time.monotonic() - started) * 1000),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            }
            with self._lock:
                self.tracks = tracks
                self.by_id = {track.id: track for track in tracks}
                self.generation += 1
                self._status.update(state="done", library=summary)
        except Exception as exc:  # a scan must never leave the app wedged
            self._set(state="error", message=str(exc))

    @staticmethod
    def _entry_is_fresh(path: Path, entry: dict) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        return (
            int(stat.st_mtime * 1000) == entry.get("mtime_ms")
            and stat.st_size == entry.get("size_bytes")
        )


SCANNER = Scanner()
