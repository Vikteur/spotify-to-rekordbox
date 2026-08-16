import { ApiError } from '../api';
import type { BlockEntry, CoupleEntry, GuestState, ListKind, SongHit } from '../types';

/** What a PUT of one entry sends — everything the server stores about a song. */
export interface EntryPayload {
  kind: ListKind;
  position?: number;
  spotify_id?: string | null;
  isrc?: string | null;
  title?: string;
  artist?: string;
  duration_ms?: number | null;
  art_url?: string | null;
  free_text?: string | null;
  note?: string | null;
  start_pref?: string | null;
}

export interface CoupleFields {
  names?: string;
  wedding_date?: string;
  briefing_text?: string;
}

async function parse<T>(response: Response): Promise<T> {
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

/**
 * The guest-side API: every call carries the magic-link token in the path —
 * that token *is* the login. `keepalive` lets the autosaver push its last
 * writes out while the tab is closing.
 */
export class GuestApi {
  private base: string;

  constructor(token: string) {
    this.base = `/api/guest/${encodeURIComponent(token)}`;
  }

  private request<T>(path: string, init?: RequestInit & { keepalive?: boolean }): Promise<T> {
    return fetch(`${this.base}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    }).then((response) => parse<T>(response));
  }

  state(): Promise<GuestState> {
    return this.request<GuestState>('');
  }

  patchCouple(fields: CoupleFields, keepalive = false): Promise<GuestState> {
    return this.request<GuestState>('/couple', {
      method: 'PATCH',
      body: JSON.stringify(fields),
      keepalive,
    });
  }

  putEntry(
    uid: string,
    payload: EntryPayload,
    keepalive = false,
  ): Promise<{ entry: CoupleEntry; entries: Partial<Record<ListKind, CoupleEntry[]>> }> {
    return this.request(`/entries/${encodeURIComponent(uid)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      keepalive,
    });
  }

  deleteEntry(
    uid: string,
    keepalive = false,
  ): Promise<{ entries: Partial<Record<ListKind, CoupleEntry[]>> }> {
    return this.request(`/entries/${encodeURIComponent(uid)}`, {
      method: 'DELETE',
      keepalive,
    });
  }

  putOrder(
    kind: ListKind,
    positions: { uid: string; position: number }[],
    keepalive = false,
  ): Promise<{ entries: Partial<Record<ListKind, CoupleEntry[]>> }> {
    return this.request(`/order/${kind}`, {
      method: 'PUT',
      body: JSON.stringify({ positions }),
      keepalive,
    });
  }

  putBlock(
    uid: string,
    payload: Omit<EntryPayload, 'kind' | 'position' | 'note' | 'start_pref'>,
    keepalive = false,
  ): Promise<{ entry: BlockEntry; blocklist: BlockEntry[] }> {
    return this.request(`/blocklist/${encodeURIComponent(uid)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
      keepalive,
    });
  }

  deleteBlock(uid: string, keepalive = false): Promise<{ blocklist: BlockEntry[] }> {
    return this.request(`/blocklist/${encodeURIComponent(uid)}`, {
      method: 'DELETE',
      keepalive,
    });
  }

  async search(q: string): Promise<SongHit[]> {
    const { results } = await this.request<{ results: SongHit[] }>(
      `/search?q=${encodeURIComponent(q)}`,
    );
    return results;
  }
}
