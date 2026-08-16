import { useApp } from '../store';
import { Panel } from './Panel';

/** Name the playlist and download it for rekordbox, or the missing-tracks shopping list. */
export function ExportPanel() {
  const s = useApp();
  const { results, name, setName, chosenIds, leftOut, exportError } = s;

  return (
    <Panel
      title="Export"
      subtitle={results ? `${chosenIds.length} of ${results.length} tracks resolved` : undefined}
    >
      <section className="panel-section">
        <label className="field-label" htmlFor="export-name">Playlist name</label>
        <input
          id="export-name"
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="e.g. Friday Warmup — how it will appear in rekordbox"
        />
      </section>

      <section className="panel-section">
        <div className="stack">
          <button className="btn btn-primary" disabled={!chosenIds.length} onClick={() => s.runExport('m3u8')}>
            Download .m3u8 (recommended)
          </button>
          <button className="btn btn-ghost" disabled={!chosenIds.length} onClick={() => s.runExport('xml')}>
            Download rekordbox .xml
          </button>
          <button
            className="btn btn-ghost"
            disabled={!leftOut.length}
            title="The tracks you don't have — paste it into a shop's search"
            onClick={s.runMissingExport}
          >
            Download missing .txt
          </button>
        </div>
        {exportError && <p className="error">{exportError}</p>}
      </section>

      {leftOut.length > 0 && (
        <section className="panel-section">
          <h3 className="panel-section-title">{leftOut.length} track(s) left out — your shopping list</h3>
          <ul className="list">
            {leftOut.map((result) => (
              <li key={result.input.index} className="list-row">
                <span className="list-main">
                  {result.input.artist || '?'} – {result.input.title}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="hint">
        Import in rekordbox: <strong>.m3u8</strong> → File › Import › Import Playlist.{' '}
        <strong>.xml</strong> → Preferences › Advanced › Database › rekordbox xml → select the file,
        then right-click the playlist in the “rekordbox xml” tree › Import Playlist.
      </p>
    </Panel>
  );
}
