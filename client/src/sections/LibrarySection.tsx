import { formatDuration } from '../format';
import { useApp } from '../store';

export function LibrarySection() {
  const s = useApp();
  const {
    lib, scan, scanError, libNote, importing, newLibName, setNewLibName,
    folder, setFolder, playlists, openLists, plInput, xmlInput, scanned,
    hasLibrary, activeId, libraries, prefs,
  } = s;

  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">1. Your libraries</h2>

      {libraries.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label htmlFor="library-picker" className="text-gray-600">
            Match against:
          </label>
          <select
            id="library-picker"
            className="rounded border border-gray-300 px-2 py-1.5"
            value={activeId ?? ''}
            onChange={(event) => s.selectLibrary(Number(event.target.value))}
          >
            {libraries.map((library) => (
              <option key={library.id} value={library.id}>
                {library.name} — {library.track_count.toLocaleString()} tracks
              </option>
            ))}
          </select>
          <button
            className="rounded border border-gray-300 px-2 py-1.5 text-xs hover:bg-gray-50"
            onClick={s.renameLibrary}
          >
            Rename
          </button>
          <button
            className="rounded border border-gray-300 px-2 py-1.5 text-xs hover:bg-gray-50"
            onClick={s.deleteLibrary}
          >
            Delete
          </button>
        </div>
      ) : (
        <p className="mt-2 text-gray-600">
          Name your first library — one per device works well (“MacBook”, “Studio PC”).
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          className="w-56 rounded border border-gray-300 px-3 py-1.5"
          placeholder="New library name, e.g. Studio PC"
          value={newLibName}
          onChange={(event) => setNewLibName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') s.createLibrary();
          }}
        />
        <button
          className="rounded border border-gray-300 px-3 py-1.5 disabled:opacity-40"
          disabled={!newLibName.trim()}
          onClick={s.createLibrary}
        >
          + Create library
        </button>
      </div>

      {activeId !== null && (hasLibrary ? (
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
                  onClick={() => s.removeSource(source.id)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-2 text-gray-500">
          “{lib?.active_library_name}” is empty — scan a music folder, import a rekordbox XML
          export, or both.
        </p>
      ))}

      <div className="mt-3 flex gap-2">
        <input
          className="w-full rounded border border-gray-300 px-3 py-2 disabled:bg-gray-50"
          placeholder="e.g. /Users/viktor/Music/DJ or C:\Music (iTunes: ~/Music/Music/Media.localized)"
          value={folder}
          disabled={activeId === null}
          onChange={(event) => setFolder(event.target.value)}
        />
        <button
          className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
          disabled={activeId === null || !folder.trim() || scan?.state === 'scanning'}
          onClick={() => s.startScan(false)}
          title={activeId === null ? 'Create a library first' : undefined}
        >
          Scan folder
        </button>
        <button
          className="rounded border border-gray-300 px-3 py-2 disabled:opacity-40"
          disabled={activeId === null || !folder.trim() || scan?.state === 'scanning'}
          onClick={() => s.startScan(true)}
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
          disabled={importing || activeId === null}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) s.importXml(file);
          }}
        />
        {importing && <span>Importing…</span>}
        <span className="text-xs text-gray-400">
          rekordbox › File › Export Collection in xml format
        </span>
      </div>

      {activeId !== null && (
        <div className="mt-3">
          <div className="flex flex-wrap items-center gap-2 text-gray-600">
            <span>Most-played playlists:</span>
            <input
              ref={plInput}
              type="file"
              accept=".m3u8,.m3u,.txt,.pls,.xml"
              className="max-w-xs text-xs file:mr-2 file:rounded file:border file:border-gray-300 file:bg-white file:px-2 file:py-1"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) s.importPlaylist(file);
              }}
            />
            <span className="text-xs text-gray-400">
              rekordbox › right-click a playlist › Export (m3u8, txt, pls or xml)
            </span>
          </div>
          {playlists.length > 0 && (
            <div className="mt-2 rounded border border-gray-200">
              {playlists.map((list) => {
                const contents = openLists[list.id];
                return (
                  <details
                    key={list.id}
                    className="border-b border-gray-100 last:border-b-0"
                    onToggle={(event) => {
                      if (event.currentTarget.open) s.openPlaylist(list.id);
                    }}
                  >
                    <summary className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-gray-50">
                      <span aria-hidden>★</span>
                      <span className="min-w-0 flex-1 truncate">{list.name}</span>
                      <span className="shrink-0 text-gray-500">
                        {list.track_count.toLocaleString()} tracks
                        {list.missing_count > 0 && (
                          <span className="text-amber-700"> · {list.missing_count} not here</span>
                        )}
                      </span>
                      <button
                        className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-white"
                        onClick={(event) => {
                          // Inside a <summary>, a click would also toggle it.
                          event.preventDefault();
                          event.stopPropagation();
                          s.removePlaylist(list.id);
                        }}
                      >
                        Remove
                      </button>
                    </summary>
                    {contents === 'loading' ? (
                      <p className="px-3 pb-2 pl-8 text-gray-500">Loading…</p>
                    ) : (
                      <ol className="pb-2 pl-8 pr-3">
                        {(contents ?? []).map((track, position) => (
                          <li key={track.id} className="flex gap-2 py-0.5 text-gray-600">
                            <span className="w-6 shrink-0 text-right text-gray-400">
                              {position + 1}
                            </span>
                            <span className="min-w-0 flex-1 truncate" title={track.path}>
                              {track.artist ? `${track.artist} – ` : ''}
                              {track.title}
                            </span>
                            <span className="shrink-0 text-xs text-gray-400">
                              {[
                                formatDuration(track.duration_sec),
                                track.bpm ? `${Math.round(track.bpm)} BPM` : '',
                                track.musical_key ?? '',
                              ].filter(Boolean).join(' · ')}
                            </span>
                          </li>
                        ))}
                      </ol>
                    )}
                  </details>
                );
              })}
            </div>
          )}
        </div>
      )}

      {prefs.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-gray-600">
            {prefs.length} remembered version choice{prefs.length === 1 ? '' : 's'}
          </summary>
          <ul className="mt-1 rounded border border-gray-200">
            {prefs.map((preference) => (
              <li
                key={preference.id}
                className="flex items-center gap-2 border-b border-gray-100 px-3 py-1.5 last:border-b-0"
              >
                <span className="min-w-0 flex-1 truncate">
                  {preference.artist || '?'} – {preference.title}
                  <span className="text-gray-400"> → </span>
                  {preference.file_label ?? (
                    <span className="text-amber-700">file not in your library right now</span>
                  )}
                </span>
                <button
                  className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-xs hover:bg-gray-50"
                  onClick={() => s.forgetChoice(preference.id)}
                >
                  Forget
                </button>
              </li>
            ))}
          </ul>
          <button
            className="mt-2 rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-50"
            onClick={s.forgetAllChoices}
          >
            Forget all
          </button>
        </details>
      )}

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
  );
}
