from pydantic import BaseModel


class LibraryTrack(BaseModel):
    id: str                      # sha1(path)[:12], stable across rescans
    path: str                    # absolute, native separators, verbatim from the filesystem
    filename: str                # basename without extension
    ext: str                     # mp3 | m4a | flac | wav | aiff
    artist: str | None
    title: str
    album: str | None
    duration_sec: float | None
    bitrate_kbps: int | None
    tag_source: str              # "tags" | "filename"
    size_bytes: int
    mtime_ms: int
