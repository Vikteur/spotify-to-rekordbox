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
  tag_source: 'tags' | 'filename' | 'rekordbox';
  size_bytes: number;
  mtime_ms: number;
  bpm: number | null;
  musical_key: string | null;
  source_id: number | null;
}

export interface Source {
  id: number;
  kind: 'folder' | 'xml';
  label: string;
  added_at: string;
  track_count: number;
}

export interface LibrarySummary {
  track_count: number;
  by_ext: Record<string, number>;
  sources: Source[];
}

export interface ScanReport {
  folder: string;
  track_count: number;
  from_cache: number;
  skipped_drm: number;
  scan_ms: number;
  scanned_at: string;
}

export interface ScanStatus {
  state: 'idle' | 'scanning' | 'done' | 'error';
  folder?: string;
  found?: number;
  parsed?: number;
  from_cache?: number;
  skipped_drm?: number;
  errors?: { file: string; message: string }[];
  library?: LibrarySummary;
  scanned?: ScanReport;
  message?: string;
}

export interface XmlImportResult {
  imported: number;
  missing_files: number;
  warnings: string[];
  library: LibrarySummary;
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
