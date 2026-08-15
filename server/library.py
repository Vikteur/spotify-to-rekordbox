"""The in-memory library: every track from every source, rebuilt from SQLite.

Sources are merged (a folder scan and a rekordbox XML export can both be
loaded), deduplicated by file path via the track id. `generation` bumps on
every reload so the matcher knows to rebuild its index.
"""

import threading

from server import db
from server.models import LibraryTrack


class Library:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tracks: list[LibraryTrack] = []
        self.by_id: dict[str, LibraryTrack] = {}
        self.generation = 0

    def reload(self) -> None:
        tracks = db.all_tracks()
        with self._lock:
            self.tracks = tracks
            self.by_id = {track.id: track for track in tracks}
            self.generation += 1

    def is_loaded(self) -> bool:
        return bool(self.tracks)

    def summary(self) -> dict:
        by_ext: dict[str, int] = {}
        for track in self.tracks:
            by_ext[track.ext] = by_ext.get(track.ext, 0) + 1
        return {
            "track_count": len(self.tracks),
            "by_ext": by_ext,
            "sources": [source.model_dump() for source in db.list_sources()],
        }


LIBRARY = Library()
