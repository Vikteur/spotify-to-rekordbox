import type {
  LibrarySummary,
  MatchResult,
  Playlist,
  PlaylistImportResult,
  PlaylistInfo,
  PlaylistTrack,
  Preference,
  ScanStatus,
  XmlImportResult,
} from './types';

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    let code = 'UNKNOWN';
    let message = `Request failed (${response.status})`;
    try {
      const detail = (await response.json()).detail;
      if (detail?.code) code = detail.code;
      if (detail?.message) message = detail.message;
    } catch {
      // non-JSON error body: keep the generic message
    }
    throw new ApiError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  library: () => request<LibrarySummary>('/api/library'),
  createLibrary: (name: string) =>
    request<LibrarySummary>('/api/libraries', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  selectLibrary: (id: number) =>
    request<LibrarySummary>(`/api/libraries/${id}/select`, { method: 'POST' }),
  renameLibrary: (id: number, name: string) =>
    request<LibrarySummary>(`/api/libraries/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),
  deleteLibrary: (id: number) =>
    request<LibrarySummary>(`/api/libraries/${id}`, { method: 'DELETE' }),
  removeSource: (id: number) =>
    request<LibrarySummary>(`/api/library/sources/${id}`, { method: 'DELETE' }),
  importXml: async (file: File): Promise<XmlImportResult> => {
    // Sent as a raw body rather than multipart — keeps the server dependency-free.
    const response = await fetch(`/api/library/xml?name=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/xml' },
      body: file,
    });
    if (!response.ok) {
      const detail = (await response.json()).detail;
      throw new ApiError(response.status, detail?.code ?? 'UNKNOWN', detail?.message ?? 'Import failed');
    }
    return response.json() as Promise<XmlImportResult>;
  },
  scan: (folder: string, force: boolean) =>
    request<{ started: boolean }>('/api/scan', {
      method: 'POST',
      body: JSON.stringify({ folder, force }),
    }),
  scanStatus: () => request<ScanStatus>('/api/scan/status'),
  fetchPlaylist: (url: string) =>
    request<Playlist>('/api/spotify/playlist', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  match: (tracks: PlaylistTrack[], playlistId: number | null) =>
    request<{ results: MatchResult[]; library_size: number; library_name: string }>(
      '/api/match',
      { method: 'POST', body: JSON.stringify({ tracks, playlist_id: playlistId }) },
    ),
  playlists: () => request<{ playlists: PlaylistInfo[] }>('/api/library/playlists'),
  importPlaylist: async (file: File): Promise<PlaylistImportResult> => {
    const response = await fetch(
      `/api/library/playlists?name=${encodeURIComponent(file.name)}`,
      { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: file },
    );
    if (!response.ok) {
      const detail = (await response.json()).detail;
      throw new ApiError(response.status, detail?.code ?? 'UNKNOWN', detail?.message ?? 'Import failed');
    }
    return response.json() as Promise<PlaylistImportResult>;
  },
  removePlaylist: (id: number) =>
    request<{ playlists: PlaylistInfo[] }>(`/api/library/playlists/${id}`, {
      method: 'DELETE',
    }),
  preferences: () => request<{ preferences: Preference[] }>('/api/preferences'),
  rememberChoice: (artist: string, title: string, trackId: string) =>
    request<{ preferences: Preference[] }>('/api/preferences', {
      method: 'POST',
      body: JSON.stringify({ artist, title, track_id: trackId }),
    }),
  forgetChoice: (id: string) =>
    request<{ preferences: Preference[] }>(`/api/preferences/${id}`, { method: 'DELETE' }),
  forgetAllChoices: () =>
    request<{ preferences: Preference[] }>('/api/preferences', { method: 'DELETE' }),
};

export async function downloadExport(
  name: string,
  format: 'm3u8' | 'xml',
  trackIds: string[],
): Promise<void> {
  const response = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, format, track_ids: trackIds }),
  });
  if (!response.ok) {
    const detail = (await response.json()).detail;
    throw new ApiError(response.status, detail?.code ?? 'UNKNOWN', detail?.message ?? 'Export failed');
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${name.trim() || 'playlist'}.${format === 'xml' ? 'rekordbox.xml' : 'm3u8'}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// Paste-text fallback: one "Artist - Title" per line (numbering tolerated).
export function parseTextPlaylist(text: string): {
  tracks: PlaylistTrack[];
  unsplit: string[];
} {
  const tracks: PlaylistTrack[] = [];
  const unsplit: string[] = [];
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim().replace(/^\d{1,3}\s*[.)-]?\s+/, '');
    if (!line) continue;
    const match = line.match(/ - | – | — |\t/);
    if (match && match.index !== undefined) {
      tracks.push({
        index: tracks.length,
        artist: line.slice(0, match.index).trim(),
        title: line.slice(match.index + match[0].length).trim(),
        duration_sec: null,
      });
    } else {
      unsplit.push(line);
      tracks.push({ index: tracks.length, artist: '', title: line, duration_sec: null });
    }
  }
  return { tracks, unsplit };
}
