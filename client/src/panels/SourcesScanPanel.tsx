import { useEffect, useRef } from 'react';
import { formatDuration } from '../format';
import { useApp } from '../store';
import { useUi } from '../ui/UiContext';
import { Folder, Doc, Star } from '../components/Icons';
import { Panel } from './Panel';

/**
 * Everything about building a library: pick/create/rename/delete a library,
 * scan a folder, import a rekordbox XML collection, manage sources, and import
 * "most-played" rekordbox playlist exports. Ported from the old LibrarySection.
 */
export function SourcesScanPanel() {
  const s = useApp();
  const { panelArg } = useUi();
  const {
    lib, scan, scanError, libNote, importing, newLibName, setNewLibName,
    folder, setFolder, playlists, openLists, plInput, xmlInput, scanned,
    hasLibrary, activeId, libraries,
  } = s;

  // "+ Import" next to MOST-PLAYED opens this panel with arg 'import' —
  // jump straight to that section instead of making the user hunt for it.
  const mostPlayedRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (panelArg === 'import') mostPlayedRef.current?.scrollIntoView({ block: 'start' });
  }, [panelArg]);

  return (
    <Panel title="Import library" subtitle="Build the library Rekord Match searches — scan folders or import rekordbox exports, all local to this machine.">
      <section className="panel-section">
        <h3 className="panel-section-title">Library</h3>
        {libraries.length > 0 ? (
          <div className="field-row">
            <select
              className="input"
              value={activeId ?? ''}
              onChange={(event) => s.selectLibrary(Number(event.target.value))}
              aria-label="Active library"
            >
              {libraries.map((library) => (
                <option key={library.id} value={library.id}>
                  {library.name} — {library.track_count.toLocaleString()} tracks
                </option>
              ))}
            </select>
            <button className="btn btn-ghost" onClick={s.renameLibrary}>Rename</button>
            <button className="btn btn-ghost" onClick={s.deleteLibrary}>Delete</button>
          </div>
        ) : (
          <p className="muted">Name your first library — one per device works well (“MacBook”, “Studio PC”).</p>
        )}
        <div className="field-row">
          <input
            className="input"
            placeholder="New library name, e.g. Studio PC"
            value={newLibName}
            onChange={(event) => setNewLibName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') s.createLibrary();
            }}
          />
          <button className="btn btn-ghost" disabled={!newLibName.trim()} onClick={s.createLibrary}>
            + Create
          </button>
        </div>
        {activeId !== null && !hasLibrary && (
          <p className="muted">
            “{lib?.active_library_name}” is empty — scan a music folder, import a rekordbox XML
            export, or both.
          </p>
        )}
        {activeId !== null && hasLibrary && lib && (
          <p className="muted">
            <strong>{lib.track_count.toLocaleString()} tracks</strong> saved (
            {Object.entries(lib.by_ext).map(([ext, count]) => `${count} ${ext}`).join(', ')}) — kept
            in a local database, so no rescan on restart.
          </p>
        )}
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">Scan a folder</h3>
        <div className="field-row">
          <input
            className="input"
            placeholder="e.g. C:\Music or /Users/you/Music/DJ"
            value={folder}
            disabled={activeId === null}
            onChange={(event) => setFolder(event.target.value)}
          />
        </div>
        <div className="field-row">
          <button
            className="btn btn-primary"
            disabled={activeId === null || !folder.trim() || scan?.state === 'scanning'}
            onClick={() => s.startScan(false)}
          >
            Scan folder
          </button>
          <button
            className="btn btn-ghost"
            disabled={activeId === null || !folder.trim() || scan?.state === 'scanning'}
            onClick={() => s.startScan(true)}
            title="Re-read every file instead of trusting the saved database"
          >
            Force rescan
          </button>
        </div>
        {scan?.state === 'scanning' && (
          <p className="muted">
            Scanning… found {scan.found ?? 0} files — parsed {scan.parsed ?? 0}, {scan.from_cache ?? 0} unchanged
          </p>
        )}
        {scan?.state === 'error' && <p className="error">Scan failed: {scan.message}</p>}
        {scanned && (
          <>
            <p className="muted">
              Scanned {scanned.track_count.toLocaleString()} files in {(scanned.scan_ms / 1000).toFixed(1)}s
              {scanned.from_cache > 0 && ` (${scanned.from_cache.toLocaleString()} unchanged)`}
              {(scanned.skipped_drm > 0 || (scan?.errors?.length ?? 0) > 0) && (
                <>
                  {' — '}
                  {/* Plain GET: the server already holds the last scan's result. */}
                  <a href="/api/export/skipped" download="skipped files.txt">
                    download the skipped list (.txt)
                  </a>
                </>
              )}
            </p>
            {scanned.skipped_drm > 0 && (
              <details className="skipped-list">
                <summary className="warn">
                  {scanned.skipped_drm} DRM-protected file(s) skipped — rekordbox can't play .m4p
                </summary>
                <p className="muted">
                  Apple Music subscription downloads and iTunes purchases from before 2010.
                  They are locked to your Apple account, so no DJ software can open them —
                  the only fix is owning the track outright.
                </p>
                <ul>
                  {(scanned.skipped_drm_files ?? []).map((path) => (
                    <li key={path} title={path}>{path}</li>
                  ))}
                </ul>
                {scanned.skipped_drm > (scanned.skipped_drm_files?.length ?? 0) && (
                  <p className="muted">
                    …and {scanned.skipped_drm - (scanned.skipped_drm_files?.length ?? 0)} more.
                  </p>
                )}
              </details>
            )}
            {scan?.errors && scan.errors.length > 0 && (
              <details className="skipped-list">
                <summary className="warn">{scan.errors.length} file(s) could not be read</summary>
                <p className="muted">
                  Corrupt or truncated, not really audio despite the extension, or a folder
                  that could not be opened. Each line says why.
                </p>
                <ul>
                  {scan.errors.map((entry, index) => (
                    <li key={`${entry.file}-${index}`} title={entry.message}>
                      {entry.file || entry.message}
                      {entry.file && <span className="muted"> — {entry.message}</span>}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">Import a rekordbox collection</h3>
        <div className="field-row">
          <input
            ref={xmlInput}
            type="file"
            accept=".xml,text/xml,application/xml"
            className="file-input"
            disabled={importing || activeId === null}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) s.importXml(file);
            }}
          />
          {importing && <span className="muted">Importing…</span>}
        </div>
        <p className="hint">rekordbox › File › Export Collection in xml format</p>
      </section>

      {activeId !== null && hasLibrary && lib && lib.sources.length > 0 && (
        <section className="panel-section">
          <h3 className="panel-section-title">Sources</h3>
          <ul className="list">
            {lib.sources.map((source) => (
              <li key={source.id} className="list-row">
                <span className="list-icon">{source.kind === 'folder' ? <Folder /> : <Doc />}</span>
                <span className="list-main" title={source.label}>{source.label}</span>
                <span className="mono muted">{source.track_count.toLocaleString()}</span>
                <button className="btn btn-ghost btn-sm" onClick={() => s.removeSource(source.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {activeId !== null && (
        <section className="panel-section" ref={mostPlayedRef}>
          <h3 className="panel-section-title">Most-played playlists</h3>
          <p className="hint">rekordbox › right-click a playlist › Export (m3u8, txt, pls or xml)</p>
          <div className="field-row">
            <input
              ref={plInput}
              type="file"
              accept=".m3u8,.m3u,.txt,.pls,.xml"
              className="file-input"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) s.importPlaylist(file);
              }}
            />
          </div>
          {playlists.length > 0 && (
            <ul className="list">
              {playlists.map((list) => {
                const contents = openLists[list.id];
                return (
                  <li key={list.id} className="list-block">
                    <details onToggle={(event) => {
                      if (event.currentTarget.open) s.openPlaylist(list.id);
                    }}>
                      <summary className="list-row list-summary">
                        <span className="list-icon"><Star /></span>
                        <span className="list-main">{list.name}</span>
                        <span className="mono muted">
                          {list.track_count.toLocaleString()}
                          {list.missing_count > 0 && <span className="warn"> · {list.missing_count} missing</span>}
                        </span>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            s.removePlaylist(list.id);
                          }}
                        >
                          Remove
                        </button>
                      </summary>
                      {contents === 'loading' ? (
                        <p className="muted list-detail">Loading…</p>
                      ) : (
                        <ol className="list-detail">
                          {(contents ?? []).map((track, position) => (
                            <li key={track.id} className="list-track">
                              <span className="mono muted list-track-n">{position + 1}</span>
                              <span className="list-main" title={track.path}>
                                {track.artist ? `${track.artist} – ` : ''}
                                {track.title}
                              </span>
                              <span className="mono muted">
                                {[
                                  formatDuration(track.duration_sec),
                                  track.bpm ? `${Math.round(track.bpm)}` : '',
                                  track.musical_key ?? '',
                                ].filter(Boolean).join(' · ')}
                              </span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </details>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      {scanError && <p className="error">{scanError}</p>}
      {libNote && <p className="muted">{libNote}</p>}
    </Panel>
  );
}
