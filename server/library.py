"""The active library held in memory: the one a playlist is matched against.

Switching libraries reloads this from SQLite and bumps `generation`, which is
what tells the matcher to rebuild its inverted index.
"""

import threading

from server import db
from server.models import LibraryTrack


class ActiveLibrary:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.id: int | None = None
        self.name: str | None = None
        self.tracks: list[LibraryTrack] = []
        self.by_id: dict[str, LibraryTrack] = {}
        self.generation = 0

    def load(self, library_id: int | None = None) -> None:
        """Load `library_id`, or re-read whichever library is currently active."""
        if library_id is None:
            library_id = db.active_library_id()
        else:
            db.set_active_library_id(library_id)

        tracks = db.library_tracks(library_id) if library_id is not None else []
        name = None
        if library_id is not None:
            name = next(
                (lib.name for lib in db.list_libraries() if lib.id == library_id), None
            )
        with self._lock:
            self.id = library_id
            self.name = name
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
            "active_library_id": self.id,
            "active_library_name": self.name,
            "track_count": len(self.tracks),
            "by_ext": by_ext,
            "libraries": [lib.model_dump() for lib in db.list_libraries()],
            "sources": (
                [source.model_dump() for source in db.list_sources(self.id)]
                if self.id is not None
                else []
            ),
        }


LIBRARY = ActiveLibrary()
