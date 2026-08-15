import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from server import db
from server.library import LIBRARY
from server.models import LibraryTrack
from server.scanner.tags import read_track
from server.scanner.walk import walk_library

PARSE_WORKERS = 8


class ScanInProgress(Exception):
    pass


class Scanner:
    """Runs one folder scan at a time, writing results through to SQLite."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status: dict = {"state": "idle"}

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def is_scanning(self) -> bool:
        return self.status()["state"] == "scanning"

    def start_scan(self, folder: str, force: bool = False) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ScanInProgress
            self._status = {
                "state": "scanning",
                "folder": folder,
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
            files, drm_count, walk_errors = walk_library(Path(folder))
            errors = [{"file": "", "message": message} for message in walk_errors]
            self._set(found=len(files), skipped_drm=drm_count, errors=errors)

            source_id = db.upsert_source("folder", folder)
            known = {} if force else db.source_tracks(source_id)

            tracks: list[LibraryTrack] = []
            to_parse: list[Path] = []
            for path in files:
                stored = known.get(str(path))
                if stored is not None and _unchanged(path, stored):
                    tracks.append(stored)
                else:
                    to_parse.append(path)
            from_cache = len(tracks)
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

            tracks.sort(key=lambda track: track.path)
            db.replace_source_tracks(source_id, tracks)
            LIBRARY.reload()

            self._set(
                state="done",
                library=LIBRARY.summary(),
                scanned={
                    "folder": folder,
                    "track_count": len(tracks),
                    "from_cache": from_cache,
                    "skipped_drm": drm_count,
                    "scan_ms": round((time.monotonic() - started) * 1000),
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:  # a failed scan must never wedge the app
            self._set(state="error", message=str(exc))


def _unchanged(path: Path, stored: LibraryTrack) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return (
        int(stat.st_mtime * 1000) == stored.mtime_ms
        and stat.st_size == stored.size_bytes
    )


SCANNER = Scanner()
