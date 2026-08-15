import { useEffect, useRef, useState } from 'react';
import { ApiError, api, downloadExport, parseTextPlaylist } from './api';
import type {
  LibrarySummary,
  MatchResult,
  Playlist,
  ScanStatus,
  ScoredCandidate,
} from './types';

const SKIP = '__skip__';

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '?:??';
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

function formatDelta(delta: number | null): string {
  if (delta == null) return '';
  const rounded = Math.round(delta);
  return ` (${rounded >= 0 ? '+' : '−'}${formatDuration(Math.abs(rounded))})`;
}

function versionLabel(descriptors: string[], remixer: string | null): string {
  if (!descriptors.length) return '';
  const name = remixer ? `${remixer} ` : '';
  return `[${name}${descriptors.join('+')}]`;
}

function candidateLabel(candidate: ScoredCandidate): string {
  const { track } = candidate;
  const version = versionLabel(candidate.version.descriptors, candidate.version.remixer);
  const bits = [
    `${track.filename}.${track.ext}`,
    version,
    `${formatDuration(track.duration_sec)}${formatDelta(candidate.duration_delta_sec)}`,
    track.bitrate_kbps ? `${track.ext.toUpperCase()} ${track.bitrate_kbps}` : track.ext.toUpperCase(),
    `${Math.round(candidate.score * 100)}%`,
  ];
  return bits.filter(Boolean).join(' — ');
}

const chipStyles: Record<string, string> = {
  auto: 'bg-green-100 text-green-800',
  manual: 'bg-blue-100 text-blue-800',
  'pick one': 'bg-amber-100 text-amber-900',
  skipped: 'bg-gray-200 text-gray-600',
  'no match': 'bg-red-100 text-red-800',
};

export default function App() {
  // --- Section 1: library (folder scans + rekordbox XML imports) ---
  const [folder, setFolder] = useState(() => localStorage.getItem('lastFolder') ?? '');
  const [lib, setLib] = useState<LibrarySummary | null>(null);
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [scanError, setScanError] = useState('');
  const [libNote, setLibNote] = useState('');
  const [importing, setImporting] = useState(false);
  const xmlInput = useRef<HTMLInputElement | null>(null);
  const polling = useRef<number | null>(null);

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

  // --- Section 4: export ---
  const [name, setName] = useState('');
  const [exportError, setExportError] = useState('');

  useEffect(() => {
    // The library is restored from the database, so a reload needs no rescan.
    api.library().then(setLib).catch(() => undefined);
    api.scanStatus().then(setScan).catch(() => undefined);
    return () => {
      if (polling.current) window.clearInterval(polling.current);
    };
  }, []);

  useEffect(() => {
    if (scan?.state === 'scanning' && polling.current == null) {
      polling.current = window.setInterval(async () => {
        try {
          const status = await api.scanStatus();
          setScan(status);
          if (status.state !== 'scanning' && polling.current) {
            window.clearInterval(polling.current);
            polling.current = null;
            if (status.library) setLib(status.library);
          }
        } catch {
          // transient poll failure: keep polling
        }
      }, 500);
    }
  }, [scan]);

  function libraryChanged() {
    setResults(null);
    setSelections({});
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
      setScanError(error instanceof ApiError ? error.message : String(error));
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
      setScanError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setImporting(false);
      if (xmlInput.current) xmlInput.current.value = '';
    }
  }

  async function removeSource(id: number) {
    setScanError('');
    setLibNote('');
    libraryChanged();
    try {
      setLib(await api.removeSource(id));
    } catch (error) {
      setScanError(error instanceof ApiError ? error.message : String(error));
    }
  }

  async function fetchPlaylist() {
    setFetching(true);
    setPlaylistError('');
    setPlaylistNote('');
    setResults(null);
    setSelections({});
    try {
      const fetched = await api.fetchPlaylist(url);
      setPlaylist(fetched);
      setName(fetched.name);
    } catch (error) {
      setPlaylistError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setFetching(false);
    }
  }

  function usePastedList() {
    setPlaylistError('');
    setResults(null);
    setSelections({});
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

  async function runMatch() {
    if (!playlist) return;
    setMatching(true);
    setMatchError('');
    try {
      const { results: matched } = await api.match(playlist.tracks);
      setResults(matched);
      const preset: Record<number, string> = {};
      for (const result of matched) {
        preset[result.input.index] = result.auto_selected_id ?? (result.candidates.length ? '' : SKIP);
      }
      setSelections(preset);
    } catch (error) {
      setMatchError(error instanceof ApiError ? error.message : String(error));
    } finally {
      setMatching(false);
    }
  }

  function rowStatus(result: MatchResult): string {
    const selection = selections[result.input.index];
    if (selection === SKIP || selection === undefined) {
      return result.bucket === 'unmatched' && !result.candidates.length ? 'no match' : 'skipped';
    }
    if (selection === '') return result.bucket === 'unmatched' ? 'no match' : 'pick one';
    if (selection === result.auto_selected_id) return 'auto';
    return 'manual';
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
      await downloadExport(name, format, chosenIds);
    } catch (error) {
      setExportError(error instanceof ApiError ? error.message : String(error));
    }
  }

  const scanned = scan?.state === 'done' ? scan.scanned : undefined;
  const hasLibrary = (lib?.track_count ?? 0) > 0;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 text-sm text-gray-900">
      <h1 className="text-2xl font-bold">Spotify → rekordbox</h1>
      <p className="mt-1 text-gray-500">
        Match a public Spotify playlist against the music you own, pick the right file per track, export a
        rekordbox playlist. Everything stays on your machine.
      </p>

      {/* 1 — Library */}
      <section className="mt-8">
        <h2 className="text-lg font-semibold">1. Your library</h2>

        {hasLibrary ? (
          <div className="mt-2 rounded border border-gray-200">
            <p className="border-b border-gray-100 px-3 py-2 text-gray-700">
              <span className="font-medium">{lib!.track_count.toLocaleString()} tracks</span> saved (
              {Object.entries(lib!.by_ext).map(([ext, count]) => `${count} ${ext}`).join(', ')})
              {' — kept in a local database, so no rescan on restart.'}
            </p>
            <ul>
              {lib!.sources.map((source) => (
                <li key={source.id} className="flex items-center gap-2 px-3 py-2 text-gray-700">
                  <span title={source.kind === 'folder' ? 'scanned folder' : 'rekordbox XML export'}>
                    {source.kind === 'folder' ? '📁' : '📄'}
                  </span>
                  <span className="min-w-0 flex-1 truncate" title={source.label}>{source.label}</span>
                  <span className="shrink-0 text-gray-500">
                    {source.track_count.toLocaleString()} tracks
                  </span>
                  <button
                    className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-50"
                    onClick={() => removeSource(source.id)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-2 text-gray-500">
            Nothing loaded yet — scan a music folder, import a rekordbox XML export, or both.
          </p>
        )}

        <div className="mt-3 flex gap-2">
          <input
            className="w-full rounded border border-gray-300 px-3 py-2"
            placeholder="e.g. /Users/viktor/Music/DJ or C:\Music (iTunes: ~/Music/Music/Media.localized)"
            value={folder}
            onChange={(event) => setFolder(event.target.value)}
          />
          <button
            className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
            disabled={!folder.trim() || scan?.state === 'scanning'}
            onClick={() => startScan(false)}
          >
            Scan folder
          </button>
          <button
            className="rounded border border-gray-300 px-3 py-2 disabled:opacity-40"
            disabled={!folder.trim() || scan?.state === 'scanning'}
            onClick={() => startScan(true)}
            title="Re-read every file instead of trusting the saved database"
          >
            Force rescan
          </button>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-gray-600">
          <span>or import a rekordbox collection:</span>
          <input
            ref={xmlInput}
            type="file"
            accept=".xml,text/xml,application/xml"
            className="max-w-xs text-xs file:mr-2 file:rounded file:border file:border-gray-300 file:bg-white file:px-2 file:py-1"
            disabled={importing}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) importXml(file);
            }}
          />
          {importing && <span>Importing…</span>}
          <span className="text-xs text-gray-400">
            rekordbox › File › Export Collection in xml format
          </span>
        </div>

        {scanError && <p className="mt-2 text-red-700">{scanError}</p>}
        {libNote && <p className="mt-2 text-gray-700">{libNote}</p>}
        {scan?.state === 'scanning' && (
          <p className="mt-2 text-gray-600">
            Scanning… found {scan.found ?? 0} files — parsed {scan.parsed ?? 0}, {scan.from_cache ?? 0} unchanged
          </p>
        )}
        {scan?.state === 'error' && <p className="mt-2 text-red-700">Scan failed: {scan.message}</p>}
        {scanned && (
          <p className="mt-2 text-gray-600">
            Scanned {scanned.track_count.toLocaleString()} files in {(scanned.scan_ms / 1000).toFixed(1)}s
            {scanned.from_cache > 0 && ` (${scanned.from_cache.toLocaleString()} unchanged since last scan)`}
            {scanned.skipped_drm > 0 && (
              <span className="text-amber-700">
                {' '}— {scanned.skipped_drm} DRM-protected iTunes file(s) skipped (rekordbox can't play .m4p)
              </span>
            )}
            {scan?.errors && scan.errors.length > 0 && (
              <span className="text-amber-700"> — {scan.errors.length} unreadable file(s)</span>
            )}
          </p>
        )}
      </section>

      {/* 2 — Playlist */}
      <section className="mt-8">
        <h2 className="text-lg font-semibold">2. Spotify playlist</h2>
        <div className="mt-2 flex gap-2">
          <input
            className="w-full rounded border border-gray-300 px-3 py-2"
            placeholder="https://open.spotify.com/playlist/… (must be public)"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <button
            className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
            disabled={!url.trim() || fetching}
            onClick={fetchPlaylist}
          >
            {fetching ? 'Fetching…' : 'Fetch'}
          </button>
        </div>
        {playlistError && <p className="mt-2 text-red-700">{playlistError}</p>}
        <details className="mt-2">
          <summary className="cursor-pointer text-gray-500">
            Or paste the tracklist as text (one “Artist - Title” per line)
          </summary>
          <textarea
            className="mt-2 h-32 w-full rounded border border-gray-300 px-3 py-2 font-mono text-xs"
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
            placeholder={'Étienne de Crécy - Am I Wrong\nPurple Disco Machine - Substitution'}
          />
          <button
            className="mt-2 rounded border border-gray-300 px-3 py-2 disabled:opacity-40"
            disabled={!pasted.trim()}
            onClick={usePastedList}
          >
            Use pasted list
          </button>
        </details>
        {playlist && (
          <p className="mt-2 text-gray-700">
            <span className="font-medium">{playlist.name}</span>
            {playlist.owner_name ? ` by ${playlist.owner_name}` : ''} — {playlist.tracks.length} tracks
          </p>
        )}
        {playlistNote && <p className="mt-1 text-gray-600">{playlistNote}</p>}
        {playlist?.truncated && (
          <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-amber-900">
            ⚠ Spotify's public embed only returned the first {playlist.tracks.length} of{' '}
            {playlist.total ?? '100+'} tracks. Paste the full tracklist as text to match everything.
          </p>
        )}
        <button
          className="mt-3 rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
          disabled={!playlist || !hasLibrary || matching}
          title={!hasLibrary ? 'Add a library first (scan a folder or import a rekordbox XML)' : undefined}
          onClick={runMatch}
        >
          {matching ? 'Matching…' : 'Match against library'}
        </button>
        {matchError && <p className="mt-2 text-red-700">{matchError}</p>}
      </section>

      {/* 3 — Matches */}
      {results && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">3. Matches</h2>
          <p className="mt-1 text-gray-600">
            {results.filter((result) => result.bucket === 'auto').length} auto ·{' '}
            {results.filter((result) => result.bucket === 'ambiguous').length} to pick ·{' '}
            {results.filter((result) => result.bucket === 'unmatched').length} not found
            {unresolvedCount > 0 && (
              <span className="text-amber-700"> — {unresolvedCount} still need a choice below</span>
            )}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-gray-300 text-xs uppercase text-gray-500">
                  <th className="py-2 pr-2">#</th>
                  <th className="py-2 pr-4">Spotify track</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2">Your file</th>
                </tr>
              </thead>
              <tbody>
                {results.map((result) => {
                  const status = rowStatus(result);
                  return (
                    <tr key={result.input.index} className="border-b border-gray-100 align-top">
                      <td className="py-2 pr-2 text-gray-400">{result.input.index + 1}</td>
                      <td className="py-2 pr-4">
                        <span className="font-medium">{result.input.artist || '?'}</span>
                        {' – '}
                        {result.input.title}
                        <span className="text-gray-400"> ({formatDuration(result.input.duration_sec)})</span>
                        {result.input_version.descriptors.length > 0 && (
                          <span className="ml-1 text-xs text-purple-700">
                            {versionLabel(result.input_version.descriptors, result.input_version.remixer)}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${chipStyles[status]}`}>
                          {status}
                        </span>
                      </td>
                      <td className="py-2">
                        {result.candidates.length ? (
                          <select
                            className="w-full max-w-xl rounded border border-gray-300 px-2 py-1"
                            value={selections[result.input.index] ?? SKIP}
                            onChange={(event) =>
                              setSelections((previous) => ({
                                ...previous,
                                [result.input.index]: event.target.value,
                              }))
                            }
                          >
                            {selections[result.input.index] === '' && <option value="">— choose —</option>}
                            {result.candidates.map((candidate) => (
                              <option key={candidate.track.id} value={candidate.track.id}>
                                {candidateLabel(candidate)}
                              </option>
                            ))}
                            <option value={SKIP}>— skip this track —</option>
                          </select>
                        ) : (
                          <span className="text-gray-400">no match in your library</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 4 — Export */}
      {results && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">4. Export</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              className="w-72 rounded border border-gray-300 px-3 py-2"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Playlist name"
            />
            <button
              className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
              disabled={!chosenIds.length}
              onClick={() => runExport('m3u8')}
            >
              Download .m3u8 (recommended)
            </button>
            <button
              className="rounded border border-gray-300 px-4 py-2 disabled:opacity-40"
              disabled={!chosenIds.length}
              onClick={() => runExport('xml')}
            >
              Download rekordbox .xml
            </button>
          </div>
          <p className="mt-2 text-gray-700">
            {chosenIds.length} of {results.length} tracks will be exported.
          </p>
          {exportError && <p className="mt-1 text-red-700">{exportError}</p>}
          {leftOut.length > 0 && (
            <details className="mt-2 text-gray-600">
              <summary className="cursor-pointer">
                {leftOut.length} track(s) left out — your shopping list
              </summary>
              <ul className="mt-1 list-inside list-disc">
                {leftOut.map((result) => (
                  <li key={result.input.index}>
                    {result.input.artist || '?'} – {result.input.title}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="mt-3 text-xs text-gray-500">
            Import in rekordbox: <span className="font-medium">.m3u8</span> → File › Import › Import
            Playlist. <span className="font-medium">.xml</span> → Preferences › Advanced › Database ›
            rekordbox xml → select the file, then right-click the playlist in the “rekordbox xml” tree
            section › Import Playlist.
          </p>
        </section>
      )}
    </main>
  );
}
