import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, api, downloadExport, downloadMissing, parseTextPlaylist } from './api';
import type {
  CoupleDetail,
  CoupleSummary,
  LibrarySummary,
  LibraryTrack,
  ListKind,
  MatchResult,
  Playlist,
  PlaylistInfo,
  Preference,
  ScanStatus,
} from './types';
import { SKIP } from './format';
import { useScanPolling } from './useScanPolling';

const message = (error: unknown) =>
  error instanceof ApiError ? error.message : String(error);

/**
 * The whole app's state and the actions that mutate it, in one hook.
 *
 * `App` calls this once and shares the result through context; the section
 * components (`LibrarySection`, `PlaylistSection`, `MatchesTable`,
 * `ExportSection`) read it via `useApp()`. Keeping every setter and cross-section
 * side effect (a library change clears the match table, a rescan clears the
 * results) in one place is what lets the sections stay presentational.
 */
function useAppStore() {
  // --- Section 1: library (folder scans + rekordbox XML imports) ---
  const [folder, setFolder] = useState(() => localStorage.getItem('lastFolder') ?? '');
  const [lib, setLib] = useState<LibrarySummary | null>(null);
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [scanError, setScanError] = useState('');
  const [libNote, setLibNote] = useState('');
  const [importing, setImporting] = useState(false);
  const [newLibName, setNewLibName] = useState('');
  const [playlists, setPlaylists] = useState<PlaylistInfo[]>([]);
  const [openLists, setOpenLists] = useState<Record<number, LibraryTrack[] | 'loading'>>({});
  const [filterId, setFilterId] = useState<number | null>(null);
  const plInput = useRef<HTMLInputElement | null>(null);
  const xmlInput = useRef<HTMLInputElement | null>(null);

  // --- Section 2: playlist input ---
  const [url, setUrl] = useState('');
  const [pasted, setPasted] = useState('');
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [playlistNote, setPlaylistNote] = useState('');
  const [playlistError, setPlaylistError] = useState('');
  const [fetching, setFetching] = useState(false);

  // --- Section 3: matches ---
  const [results, setResults] = useState<MatchResult[] | null>(null);
  const [selections, setSelections] = useState<Record<number, string>>({});
  const [matching, setMatching] = useState(false);
  const [matchError, setMatchError] = useState('');
  const [prefs, setPrefs] = useState<Preference[]>([]);
  const [remembered, setRemembered] = useState<Record<number, boolean>>({});
  const [rememberNote, setRememberNote] = useState('');

  // --- Section 4: export ---
  const [name, setName] = useState('');
  const [exportError, setExportError] = useState('');

  // --- Section 5: wedding couples ---
  const [couples, setCouples] = useState<CoupleSummary[]>([]);
  // Set while the loaded playlist came from a couple chapter: exports then
  // pass couple_id so the server drops everything on their never list.
  const [activeCouple, setActiveCouple] = useState<{ id: number; names: string } | null>(null);

  useEffect(() => {
    // The library is restored from the database, so a reload needs no rescan.
    api.library().then(setLib).catch(() => undefined);
    api.scanStatus().then(setScan).catch(() => undefined);
    api.preferences().then((r) => setPrefs(r.preferences)).catch(() => undefined);
    api.playlists().then((r) => setPlaylists(r.playlists)).catch(() => undefined);
    api.couples().then((r) => setCouples(r.couples ?? [])).catch(() => undefined);
  }, []);

  useScanPolling(scan, setScan, setLib);

  function libraryChanged() {
    setResults(null);
    setSelections({});
  }

  /** Any action that changes which library is active or what's in it. */
  async function withLibrary(action: () => Promise<LibrarySummary>) {
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      const summary = await action();
      setLib(summary);
      setScan(null);
      setFilterId(null);
      const [{ preferences }, { playlists: lists }] = await Promise.all([
        api.preferences(),
        api.playlists(),
      ]);
      setPrefs(preferences);
      setPlaylists(lists);
      setRemembered({});
    } catch (error) {
      setScanError(message(error));
    }
  }

  async function createLibrary() {
    const trimmed = newLibName.trim();
    if (!trimmed) return;
    await withLibrary(() => api.createLibrary(trimmed));
    setNewLibName('');
  }

  async function renameLibrary() {
    if (!lib?.active_library_id) return;
    const next = window.prompt('Rename library', lib.active_library_name ?? '');
    if (next && next.trim()) {
      await withLibrary(() => api.renameLibrary(lib.active_library_id!, next.trim()));
    }
  }

  async function deleteLibrary() {
    if (!lib?.active_library_id) return;
    const confirmMessage =
      `Delete the library "${lib.active_library_name}"?\n\n` +
      'Its scanned tracks and remembered versions are removed. Your music files are not touched.';
    if (window.confirm(confirmMessage)) {
      await withLibrary(() => api.deleteLibrary(lib.active_library_id!));
    }
  }

  function selectLibrary(id: number) {
    return withLibrary(() => api.selectLibrary(id));
  }

  async function startScan(force: boolean) {
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      localStorage.setItem('lastFolder', folder);
      await api.scan(folder, force);
      setScan({ state: 'scanning', found: 0, parsed: 0 });
    } catch (error) {
      setScanError(message(error));
    }
  }

  async function importXml(file: File) {
    setImporting(true);
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      const result = await api.importXml(file);
      setLib(result.library);
      const missing = result.missing_files
        ? ` ${result.missing_files} of them aren't on this machine right now (external drive not connected?) — they can still be matched, but rekordbox will need the drive to play them.`
        : '';
      setLibNote(`Imported ${result.imported.toLocaleString()} tracks from ${file.name}.${missing}`);
    } catch (error) {
      setScanError(message(error));
    } finally {
      setImporting(false);
      if (xmlInput.current) xmlInput.current.value = '';
    }
  }

  async function importPlaylist(file: File) {
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      const result = await api.importPlaylist(file);
      setPlaylists(result.playlists);
      const missing = result.missing
        ? ` ${result.missing} of its tracks aren't in this library${
            result.missing_examples.length ? ` (e.g. ${result.missing_examples[0]})` : ''
          }.`
        : '';
      setLibNote(`Imported “${result.name}” — ${result.resolved} tracks matched.${missing}`);
    } catch (error) {
      setScanError(message(error));
    } finally {
      if (plInput.current) plInput.current.value = '';
    }
  }

  /** Fetch a playlist's tracks the first time it is expanded. */
  async function openPlaylist(id: number) {
    if (openLists[id]) return;
    setOpenLists((previous) => ({ ...previous, [id]: 'loading' }));
    try {
      const { tracks } = await api.playlistTracks(id);
      setOpenLists((previous) => ({ ...previous, [id]: tracks }));
    } catch (error) {
      setOpenLists((previous) => {
        const next = { ...previous };
        delete next[id];
        return next;
      });
      setScanError(message(error));
    }
  }

  async function removePlaylist(id: number) {
    setScanError('');
    libraryChanged();
    try {
      const { playlists: remaining } = await api.removePlaylist(id);
      setPlaylists(remaining);
      if (filterId === id) setFilterId(null);
    } catch (error) {
      setScanError(message(error));
    }
  }

  async function removeSource(id: number) {
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      setLib(await api.removeSource(id));
    } catch (error) {
      setScanError(message(error));
    }
  }

  async function fetchPlaylist() {
    setFetching(true);
    setPlaylistError('');
    setPlaylistNote('');
    setResults(null);
    setSelections({});
    setActiveCouple(null);
    try {
      const fetched = await api.fetchPlaylist(url);
      setPlaylist(fetched);
      setName(fetched.name);
    } catch (error) {
      setPlaylistError(message(error));
    } finally {
      setFetching(false);
    }
  }

  function usePastedList() {
    setPlaylistError('');
    setResults(null);
    setSelections({});
    setActiveCouple(null);
    const { tracks, unsplit } = parseTextPlaylist(pasted);
    if (!tracks.length) {
      setPlaylistError('Nothing to parse — paste one "Artist - Title" per line.');
      return;
    }
    setPlaylist({ name: name || 'Pasted playlist', owner_name: null, total: tracks.length, truncated: false, tracks });
    if (!name) setName('Pasted playlist');
    setPlaylistNote(
      unsplit.length
        ? `${tracks.length} tracks parsed — ${unsplit.length} line(s) had no "Artist - Title" separator and will match on title alone.`
        : `${tracks.length} tracks parsed.`,
    );
  }

  async function refreshCouples() {
    try {
      setCouples((await api.couples()).couples);
    } catch {
      // sidebar counts only — the panel surfaces real errors
    }
  }

  /**
   * Load one chapter of a couple's answers as the playlist to match. Songs on
   * their never list are dropped up front; the export re-checks server-side,
   * so a blocked song can't sneak out even via manual picks.
   */
  function loadCoupleChapter(detail: CoupleDetail, kind: ListKind, label: string) {
    const entries = detail.lists[kind] ?? [];
    const blockedIds = new Set(
      detail.blocklist.map((block) => block.spotify_id).filter(Boolean),
    );
    const blockedNames = new Set(
      detail.blocklist.map((block) =>
        `${block.artist}|${block.title}`.trim().toLowerCase(),
      ),
    );
    const kept = entries.filter(
      (entry) =>
        !(entry.spotify_id && blockedIds.has(entry.spotify_id)) &&
        !blockedNames.has(`${entry.artist}|${entry.title}`.trim().toLowerCase()),
    );
    const excluded = entries.length - kept.length;
    const playlistName = `${detail.names} — ${label}`;
    setPlaylistError('');
    setResults(null);
    setSelections({});
    setPlaylist({
      name: playlistName,
      owner_name: detail.names,
      total: kept.length,
      truncated: false,
      tracks: kept.map((entry, index) => ({
        index,
        artist: entry.artist,
        title: entry.title,
        duration_sec: entry.duration_ms != null ? entry.duration_ms / 1000 : null,
      })),
    });
    setName(playlistName);
    setActiveCouple({ id: detail.id, names: detail.names });
    setPlaylistNote(
      `Loaded ${label.toLowerCase()} from ${detail.names} — ${kept.length} song${
        kept.length === 1 ? '' : 's'
      }.${excluded ? ` ${excluded} excluded by their never list.` : ''}`,
    );
  }

  async function runMatch() {
    if (!playlist) return;
    setMatching(true);
    setMatchError('');
    try {
      const { results: matched } = await api.match(playlist.tracks, filterId);
      setResults(matched);
      const preset: Record<number, string> = {};
      for (const result of matched) {
        preset[result.input.index] = result.auto_selected_id ?? (result.candidates.length ? '' : SKIP);
      }
      setSelections(preset);
      setRemembered({});
      setRememberNote('');
    } catch (error) {
      setMatchError(message(error));
    } finally {
      setMatching(false);
    }
  }

  /**
   * Point a row at a file. With `remember` (the default), the pick also becomes
   * this song's saved default for every future playlist; "Use once" passes
   * `false` so a one-off choice — or just previewing a candidate — doesn't
   * write a preference.
   */
  async function chooseVersion(result: MatchResult, value: string, remember = true) {
    setSelections((previous) => ({ ...previous, [result.input.index]: value }));
    if (!value || value === SKIP) return;
    if (!remember) {
      // A one-off pick reads as "your pick", not "remembered": drop any
      // remembered flag we may have set on this row earlier.
      setRemembered((previous) => {
        if (!previous[result.input.index]) return previous;
        const next = { ...previous };
        delete next[result.input.index];
        return next;
      });
      return;
    }
    try {
      const { preferences } = await api.rememberChoice(
        result.input.artist,
        result.input.title,
        value,
      );
      setPrefs(preferences);
      setRemembered((previous) => ({ ...previous, [result.input.index]: true }));
    } catch {
      // Remembering is a convenience — never block the export on it, but say so
      // once so the user isn't left wondering why the choice didn't stick.
      setRememberNote("Couldn't save that as a remembered version — your pick still exports fine.");
    }
  }

  /**
   * Undo a row's pick or skip: restore what the match run suggested (the auto
   * pick, "pick one", or skip for no-candidate rows). If the pick was
   * remembered in this session, the saved preference is removed again too.
   */
  async function resetChoice(result: MatchResult) {
    const index = result.input.index;
    const preset = result.auto_selected_id ?? (result.candidates.length ? '' : SKIP);
    setSelections((previous) => ({ ...previous, [index]: preset }));
    if (!remembered[index]) return;
    setRemembered((previous) => {
      const next = { ...previous };
      delete next[index];
      return next;
    });
    const norm = (value: string) => value.trim().toLowerCase();
    const pref = prefs.find(
      (p) => norm(p.artist) === norm(result.input.artist) && norm(p.title) === norm(result.input.title),
    );
    if (!pref) return;
    try {
      const { preferences } = await api.forgetChoice(pref.id);
      setPrefs(preferences);
    } catch {
      setRememberNote("Couldn't remove the remembered version — you can forget it from the Remembered panel.");
    }
  }

  async function forgetChoice(id: string) {
    try {
      const { preferences } = await api.forgetChoice(id);
      setPrefs(preferences);
    } catch (error) {
      setMatchError(message(error));
    }
  }

  async function forgetAllChoices() {
    try {
      const { preferences } = await api.forgetAllChoices();
      setPrefs(preferences);
      setRemembered({});
    } catch (error) {
      setMatchError(message(error));
    }
  }

  function rowStatus(result: MatchResult): string {
    const selection = selections[result.input.index];
    if (selection === SKIP || selection === undefined) {
      return result.bucket === 'unmatched' && !result.candidates.length ? 'no match' : 'skipped';
    }
    if (selection === '') return result.bucket === 'unmatched' ? 'no match' : 'pick one';
    if (selection === result.auto_selected_id) {
      return result.from_preference || remembered[result.input.index] ? 'remembered' : 'auto';
    }
    return remembered[result.input.index] ? 'remembered' : 'manual';
  }

  const chosenIds = results
    ? results
        .map((result) => selections[result.input.index])
        .filter((selection): selection is string => Boolean(selection) && selection !== SKIP)
    : [];
  const leftOut = results
    ? results.filter((result) => {
        const selection = selections[result.input.index];
        return !selection || selection === SKIP;
      })
    : [];
  const unresolvedCount = results
    ? results.filter((result) => selections[result.input.index] === '').length
    : 0;

  async function runExport(format: 'm3u8' | 'xml') {
    setExportError('');
    try {
      await downloadExport(name, format, chosenIds, activeCouple?.id ?? null);
    } catch (error) {
      setExportError(message(error));
    }
  }

  async function runMissingExport() {
    setExportError('');
    try {
      await downloadMissing(
        name,
        leftOut.map((result) => ({
          artist: result.input.artist,
          title: result.input.title,
          // Weak greyed-out suggestions still mean "not in the library" —
          // only a real match you passed on counts as skipped.
          had_candidates: result.bucket !== 'unmatched',
        })),
        activeCouple?.id ?? null,
      );
    } catch (error) {
      setExportError(message(error));
    }
  }

  const scanned = scan?.state === 'done' ? scan.scanned : undefined;
  const hasLibrary = (lib?.track_count ?? 0) > 0;
  const activeId = lib?.active_library_id ?? null;
  const libraries = lib?.libraries ?? [];

  return {
    // library
    folder, setFolder, lib, scan, scanError, libNote, importing,
    newLibName, setNewLibName, playlists, openLists, filterId, setFilterId,
    plInput, xmlInput, scanned, hasLibrary, activeId, libraries, prefs,
    createLibrary, renameLibrary, deleteLibrary, selectLibrary, startScan,
    importXml, importPlaylist, openPlaylist, removePlaylist, removeSource,
    forgetChoice, forgetAllChoices,
    // playlist
    url, setUrl, pasted, setPasted, playlist, playlistNote, playlistError,
    fetching, matching, matchError, fetchPlaylist, usePastedList, runMatch,
    // wedding couples
    couples, activeCouple, refreshCouples, loadCoupleChapter,
    // matches
    results, selections, remembered, rememberNote, chooseVersion, resetChoice,
    rowStatus, unresolvedCount,
    // export
    name, setName, exportError, chosenIds, leftOut, runExport, runMissingExport,
  };
}

type AppStore = ReturnType<typeof useAppStore>;

const AppContext = createContext<AppStore | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  return <AppContext.Provider value={useAppStore()}>{children}</AppContext.Provider>;
}

export function useApp(): AppStore {
  const store = useContext(AppContext);
  if (!store) throw new Error('useApp must be used within <AppProvider>');
  return store;
}
