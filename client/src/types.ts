// Mirrors the JSON shapes served by server/models.py + server/main.py.

export interface LibraryTrack {
  id: string;
  path: string;
  filename: string;
  ext: string;
  artist: string | null;
  title: string;
  album: string | null;
  duration_sec: number | null;
  bitrate_kbps: number | null;
  tag_source: 'tags' | 'filename';
  size_bytes: number;
  mtime_ms: number;
}

export interface LibrarySummary {
  folder: string;
  track_count: number;
  by_ext: Record<string, number>;
  from_cache: number;
  skipped_drm: number;
  scan_ms: number;
  scanned_at: string;
}

export interface ScanStatus {
  state: 'idle' | 'scanning' | 'done' | 'error';
  found?: number;
  parsed?: number;
  from_cache?: number;
  skipped_drm?: number;
  errors?: { file: string; message: string }[];
  library?: LibrarySummary;
  message?: string;
}

export interface PlaylistTrack {
  index: number;
  artist: string;
  title: string;
  duration_sec: number | null;
}

export interface Playlist {
  name: string;
  owner_name: string | null;
  total: number | null;
  truncated: boolean;
  tracks: PlaylistTrack[];
}

export interface VersionInfo {
  descriptors: string[];
  remixer: string | null;
}

export interface ScoredCandidate {
  track: LibraryTrack;
  score: number;
  parts: Record<string, number | null>;
  version: VersionInfo;
  duration_delta_sec: number | null;
}

export interface MatchResult {
  input: PlaylistTrack;
  input_version: VersionInfo;
  bucket: 'auto' | 'ambiguous' | 'unmatched';
  candidates: ScoredCandidate[];
  auto_selected_id: string | null;
}
