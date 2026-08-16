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
}

export interface Source {
  id: number;
  library_id: number;
  kind: 'folder' | 'xml';
  label: string;
  added_at: string;
  track_count: number;
}

export interface LibraryInfo {
  id: number;
  name: string;
  created_at: string;
  track_count: number;
  source_count: number;
}

export interface LibrarySummary {
  active_library_id: number | null;
  active_library_name: string | null;
  track_count: number;
  by_ext: Record<string, number>;
  libraries: LibraryInfo[];
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
  playlists: string[];
}

export interface PlaylistInfo {
  id: number;
  library_id: number;
  name: string;
  added_at: string;
  track_count: number;
  missing_count: number;
}

export interface PlaylistImportResult {
  playlist_id: number;
  name: string;
  resolved: number;
  missing: number;
  missing_examples: string[];
  playlists: PlaylistInfo[];
}

export interface MatchResult {
  input: PlaylistTrack;
  input_version: VersionInfo;
  bucket: 'auto' | 'ambiguous' | 'unmatched';
  candidates: ScoredCandidate[];
  auto_selected_id: string | null;
  from_preference: boolean;
}

export interface Preference {
  id: string;
  artist: string;
  title: string;
  track_id: string;
  chosen_at: string;
  file_label: string | null;
}

// --- wedding couple intake (server/couples.py + server/couples_api.py) ------

export type ListKind =
  | 'opening_dance'
  | 'second_third'
  | 'couple_top20'
  | 'friends_top20'
  | 'must_plays'
  | 'playlist_links';

export type StartPref = 'top' | 'chorus' | 'fade';
export type TokenKind = 'couple' | 'friend' | 'dj';

export interface CoupleEntry {
  uid: string;
  kind: ListKind;
  position: number;
  spotify_id: string | null;
  isrc: string | null;
  title: string;
  artist: string;
  duration_ms: number | null;
  art_url: string | null;
  free_text: string | null;
  note: string | null;
  start_pref: StartPref | null;
  source_token_kind: TokenKind;
  created_at: string;
  updated_at: string;
}

export interface BlockEntry {
  uid: string;
  position: number;
  spotify_id: string | null;
  isrc: string | null;
  title: string;
  artist: string;
  duration_ms: number | null;
  art_url: string | null;
  free_text: string | null;
  source_token_kind: TokenKind;
  created_at: string;
}

/** One Spotify search suggestion (metadata only — nothing is downloaded). */
export interface SongHit {
  spotify_id: string | null;
  uri?: string | null;
  isrc: string | null;
  title: string;
  artist: string;
  duration_ms: number | null;
  art_url: string | null;
  album?: string | null;
}

export interface GuestState {
  scope: 'couple' | 'friends';
  names: string;
  wedding_date: string;
  caps: Record<string, number | null>;
  search_available: boolean;
  entries: Partial<Record<ListKind, CoupleEntry[]>>;
  briefing_text?: string;
  blocklist?: BlockEntry[];
  friends_link?: string;
}

export interface CoupleLink {
  token: string;
  path: string;
  revoked: boolean;
  expired: boolean;
}

export interface CoupleChange {
  token_kind: TokenKind;
  action: string;
  kind: string | null;
  uid: string | null;
  summary: string;
  at: string;
}

export interface CoupleSummary {
  id: number;
  names: string;
  wedding_date: string;
  created_at: string;
  counts: Record<string, number>;
  song_count: number;
  last_change_at: string | null;
}

export interface CoupleDetail {
  id: number;
  names: string;
  wedding_date: string;
  briefing_text: string;
  created_at: string;
  links: { couple: CoupleLink; friends: CoupleLink };
  lists: Record<ListKind, CoupleEntry[]>;
  blocklist: BlockEntry[];
  changes: CoupleChange[];
}

export interface CoupleExportSummary {
  couple: { id: number; names: string; wedding_date: string };
  folder: string;              // "Sofie & Jan 2026-09-12" — the rekordbox folder
  library: string | null;
  playlists: { name: string; tracks: number }[];
  matched: number;
  missing: number;             // requested songs this library doesn't have
  blocked: number;             // dropped by the never list
}
