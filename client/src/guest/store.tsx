import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError } from '../api';
import type {
  BlockEntry,
  CoupleEntry,
  GuestState,
  ListKind,
  SongHit,
  StartPref,
} from '../types';
import { GuestApi, type CoupleFields, type EntryPayload } from './api';
import { Saver, type SaveState } from './saver';

/** Why a magic link doesn't work (bad, revoked, or past the wedding). */
export interface LinkProblem {
  status: number;
  code: string;
  message: string;
}

/** A picked Spotify song, or the free-text fallback for songs not on Spotify. */
export type SongPick = SongHit | { free_text: string };

const TEXT_DEBOUNCE_MS = 500;

function entryPayload(entry: CoupleEntry): EntryPayload {
  return {
    kind: entry.kind,
    position: entry.position,
    spotify_id: entry.spotify_id,
    isrc: entry.isrc,
    title: entry.title,
    artist: entry.artist,
    duration_ms: entry.duration_ms,
    art_url: entry.art_url,
    free_text: entry.free_text,
    note: entry.note,
    start_pref: entry.start_pref,
  };
}

function sortByPosition<T extends { position: number }>(list: T[]): T[] {
  return [...list].sort((a, b) => a.position - b.position);
}

/**
 * Guest-side state: the couple's answers, edited optimistically and pushed
 * through the `Saver` queue. Every entry write is an idempotent PUT keyed by
 * a client-generated uid, so autosave can retry freely; text edits debounce,
 * song picks save immediately.
 */
function useGuestStore(token: string) {
  const api = useMemo(() => new GuestApi(token), [token]);
  const [data, setData] = useState<GuestState | null>(null);
  const [problem, setProblem] = useState<LinkProblem | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('saved');
  const saverRef = useRef<Saver | null>(null);
  if (saverRef.current === null) saverRef.current = new Saver(setSaveState);
  const saver = saverRef.current;
  const pendingCouple = useRef<CoupleFields>({});

  useEffect(() => {
    api
      .state()
      .then(setData)
      .catch((error: unknown) => {
        if (error instanceof ApiError) {
          setProblem({ status: error.status, code: error.code, message: error.message });
        } else {
          setProblem({ status: 0, code: 'OFFLINE', message: 'Could not reach the server.' });
        }
      });
  }, [api]);

  // A closing tab (or a phone switching apps) pushes pending writes out with
  // keepalive requests — the "nothing is lost mid-answer" guarantee.
  useEffect(() => {
    const flush = () => saver.flushKeepalive();
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flush();
    };
    window.addEventListener('pagehide', flush);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('pagehide', flush);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [saver]);

  const listOf = (kind: ListKind): CoupleEntry[] => data?.entries[kind] ?? [];

  function setList(kind: ListKind, list: CoupleEntry[]): void {
    setData((previous) =>
      previous
        ? { ...previous, entries: { ...previous.entries, [kind]: sortByPosition(list) } }
        : previous,
    );
  }

  function upsertLocal(entry: CoupleEntry): void {
    setData((previous) => {
      if (!previous) return previous;
      const list = previous.entries[entry.kind] ?? [];
      const without = list.filter((item) => item.uid !== entry.uid);
      return {
        ...previous,
        entries: {
          ...previous.entries,
          [entry.kind]: sortByPosition([...without, entry]),
        },
      };
    });
  }

  /** Fold the server's answer back in — mainly the position it really got
   * (two friends can race for the same row). Skips fields when a newer local
   * edit is still waiting to be saved. */
  function applyServerEntry(server: CoupleEntry): void {
    setData((previous) => {
      if (!previous) return previous;
      const list = previous.entries[server.kind] ?? [];
      const local = list.find((item) => item.uid === server.uid);
      if (!local) return previous; // removed while the save was in flight
      const newerEditPending = saver.isPending(`entry:${server.uid}`);
      const merged = newerEditPending ? { ...local, position: server.position } : server;
      return {
        ...previous,
        entries: {
          ...previous.entries,
          [server.kind]: sortByPosition([
            ...list.filter((item) => item.uid !== server.uid),
            merged,
          ]),
        },
      };
    });
  }

  function saveEntry(entry: CoupleEntry, delayMs = 0): void {
    upsertLocal(entry);
    const payload = entryPayload(entry);
    saver.schedule(
      `entry:${entry.uid}`,
      async (keepalive) => {
        const result = await api.putEntry(entry.uid, payload, keepalive);
        if (!keepalive) applyServerEntry(result.entry);
      },
      delayMs,
    );
  }

  /** Put a song (or typed text) into a list slot; replaces the slot's uid if given. */
  function pickSong(
    kind: ListKind,
    position: number,
    pick: SongPick,
    replaceUid?: string,
  ): CoupleEntry {
    const existing = replaceUid
      ? listOf(kind).find((item) => item.uid === replaceUid)
      : undefined;
    const now = new Date().toISOString();
    const fromSearch = 'title' in pick;
    const entry: CoupleEntry = {
      uid: existing?.uid ?? crypto.randomUUID(),
      kind,
      position: existing?.position ?? position,
      spotify_id: fromSearch ? pick.spotify_id : null,
      isrc: fromSearch ? pick.isrc : null,
      title: fromSearch ? pick.title : pick.free_text,
      artist: fromSearch ? pick.artist : '',
      duration_ms: fromSearch ? pick.duration_ms : null,
      art_url: fromSearch ? pick.art_url : null,
      free_text: fromSearch ? null : pick.free_text,
      note: existing?.note ?? null,
      start_pref: existing?.start_pref ?? null,
      source_token_kind: data?.scope === 'friends' ? 'friend' : 'couple',
      created_at: existing?.created_at ?? now,
      updated_at: now,
    };
    saveEntry(entry);
    return entry;
  }

  /** Update an entry's note / start preference (opening dance details). */
  function setEntryExtras(
    uid: string,
    extras: { note?: string | null; start_pref?: StartPref | null },
    debounce = false,
  ): void {
    const entry = Object.values(data?.entries ?? {})
      .flat()
      .find((item) => item.uid === uid);
    if (!entry) return;
    saveEntry({ ...entry, ...extras }, debounce ? TEXT_DEBOUNCE_MS : 0);
  }

  function removeEntry(uid: string): void {
    const entry = Object.values(data?.entries ?? {})
      .flat()
      .find((item) => item.uid === uid);
    if (!entry) return;
    saver.cancel(`entry:${uid}`);
    setList(entry.kind, listOf(entry.kind).filter((item) => item.uid !== uid));
    saver.schedule(`delete:${uid}`, async (keepalive) => {
      await api.deleteEntry(uid, keepalive);
    });
  }

  /** Move a row up or down: swap with the neighbour, or slide into a free slot. */
  function moveEntry(kind: ListKind, uid: string, delta: -1 | 1): void {
    const list = listOf(kind);
    const entry = list.find((item) => item.uid === uid);
    if (!entry) return;
    const cap = data?.caps[kind] ?? null;
    const target = entry.position + delta;
    if (target < 0 || (cap !== null && target >= cap)) return;
    const occupant = list.find((item) => item.position === target);
    const moved = list.map((item) => {
      if (item.uid === uid) return { ...item, position: target };
      if (occupant && item.uid === occupant.uid) return { ...item, position: entry.position };
      return item;
    });
    setList(kind, moved);
    const positions = sortByPosition(moved).map((item) => ({
      uid: item.uid,
      position: item.position,
    }));
    saver.schedule(`order:${kind}`, async (keepalive) => {
      await api.putOrder(kind, positions, keepalive);
    });
  }

  // --- never list ------------------------------------------------------------

  function addBlock(pick: SongPick): void {
    const list = data?.blocklist ?? [];
    const fromSearch = 'title' in pick;
    const block: BlockEntry = {
      uid: crypto.randomUUID(),
      position: list.reduce((max, item) => Math.max(max, item.position), -1) + 1,
      spotify_id: fromSearch ? pick.spotify_id : null,
      isrc: fromSearch ? pick.isrc : null,
      title: fromSearch ? pick.title : pick.free_text,
      artist: fromSearch ? pick.artist : '',
      duration_ms: fromSearch ? pick.duration_ms : null,
      art_url: fromSearch ? pick.art_url : null,
      free_text: fromSearch ? null : pick.free_text,
      source_token_kind: 'couple',
      created_at: new Date().toISOString(),
    };
    setData((previous) =>
      previous ? { ...previous, blocklist: [...(previous.blocklist ?? []), block] } : previous,
    );
    saver.schedule(`block:${block.uid}`, async (keepalive) => {
      await api.putBlock(
        block.uid,
        {
          spotify_id: block.spotify_id,
          isrc: block.isrc,
          title: block.title,
          artist: block.artist,
          duration_ms: block.duration_ms,
          art_url: block.art_url,
          free_text: block.free_text,
        },
        keepalive,
      );
    });
  }

  function removeBlock(uid: string): void {
    saver.cancel(`block:${uid}`);
    setData((previous) =>
      previous
        ? { ...previous, blocklist: (previous.blocklist ?? []).filter((b) => b.uid !== uid) }
        : previous,
    );
    saver.schedule(`unblock:${uid}`, async (keepalive) => {
      await api.deleteBlock(uid, keepalive);
    });
  }

  // --- couple record fields --------------------------------------------------

  function patchCouple(fields: CoupleFields, debounce = true): void {
    setData((previous) => (previous ? { ...previous, ...fields } : previous));
    pendingCouple.current = { ...pendingCouple.current, ...fields };
    const snapshot = { ...pendingCouple.current };
    saver.schedule(
      'couple',
      async (keepalive) => {
        await api.patchCouple(snapshot, keepalive);
      },
      debounce ? TEXT_DEBOUNCE_MS : 0,
    );
  }

  /** Re-pull server state (friends adding songs) — skipped while edits are in flight. */
  async function refresh(): Promise<void> {
    if (saver.hasPending()) return;
    try {
      const fresh = await api.state();
      if (!saver.hasPending()) setData(fresh);
    } catch (error) {
      if (error instanceof ApiError && [403, 404, 410].includes(error.status)) {
        setProblem({ status: error.status, code: error.code, message: error.message });
      }
      // transient network errors: keep showing what we have
    }
  }

  return {
    token,
    data,
    problem,
    saveState,
    search: (q: string) => api.search(q),
    listOf,
    pickSong,
    setEntryExtras,
    removeEntry,
    moveEntry,
    addBlock,
    removeBlock,
    patchCouple,
    refresh,
  };
}

export type GuestStore = ReturnType<typeof useGuestStore>;

const GuestContext = createContext<GuestStore | null>(null);

export function GuestProvider({ token, children }: { token: string; children: ReactNode }) {
  return <GuestContext.Provider value={useGuestStore(token)}>{children}</GuestContext.Provider>;
}

export function useGuest(): GuestStore {
  const store = useContext(GuestContext);
  if (!store) throw new Error('useGuest must be used within <GuestProvider>');
  return store;
}
