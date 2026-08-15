from pydantic import BaseModel


class PlaylistTrackInput(BaseModel):
    index: int
    artist: str = ""             # may be empty for pasted lines that didn't split
    title: str
    duration_sec: float | None = None


class VersionOut(BaseModel):
    descriptors: list[str]
    remixer: str | None


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
    tag_source: str              # "tags" | "filename" | "rekordbox"
    size_bytes: int
    mtime_ms: int
    bpm: float | None = None          # rekordbox XML only
    musical_key: str | None = None    # rekordbox XML only (Tonality)


class Source(BaseModel):
    id: int
    kind: str                    # "folder" | "xml"
    label: str                   # folder path, or XML filename
    added_at: str
    track_count: int


class ScoredCandidate(BaseModel):
    track: LibraryTrack
    score: float
    parts: dict[str, float | None]   # facet breakdown: title/artist/combined/version/duration
    version: VersionOut              # extracted from the candidate's title
    duration_delta_sec: float | None # candidate minus query, when both known


class MatchResult(BaseModel):
    input: PlaylistTrackInput
    input_version: VersionOut        # what the Spotify title asked for
    bucket: str                      # "auto" | "ambiguous" | "unmatched"
    candidates: list[ScoredCandidate]
    auto_selected_id: str | None
