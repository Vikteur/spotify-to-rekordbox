import { useState } from 'react';
import { useApp } from '../store';
import { useUi } from '../ui/UiContext';
import { Panel } from './Panel';

/** Load the tracklist to match: a public Spotify URL, or pasted "Artist - Title" lines. */
export function AddPlaylistPanel() {
  const s = useApp();
  const { closePanel } = useUi();
  const [tab, setTab] = useState<'url' | 'paste'>('url');
  const { url, setUrl, pasted, setPasted, playlist, playlistNote, playlistError, fetching } = s;

  return (
    <Panel title="Add a playlist" subtitle="Match a public Spotify playlist, or paste any tracklist.">
      <div className="segmented">
        <button className={`segment ${tab === 'url' ? 'active' : ''}`} onClick={() => setTab('url')}>
          Spotify link
        </button>
        <button className={`segment ${tab === 'paste' ? 'active' : ''}`} onClick={() => setTab('paste')}>
          Paste tracklist
        </button>
      </div>

      {tab === 'url' ? (
        <section className="panel-section">
          <div className="field-row">
            <input
              className="input"
              placeholder="https://open.spotify.com/playlist/… (must be public)"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && url.trim() && !fetching) s.fetchPlaylist();
              }}
            />
            <button className="btn btn-primary" disabled={!url.trim() || fetching} onClick={s.fetchPlaylist}>
              {fetching ? 'Fetching…' : 'Fetch'}
            </button>
          </div>
        </section>
      ) : (
        <section className="panel-section">
          <textarea
            className="textarea"
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
            placeholder={'Étienne de Crécy - Am I Wrong\nPurple Disco Machine - Substitution'}
          />
          <div className="field-row">
            <button className="btn btn-primary" disabled={!pasted.trim()} onClick={s.usePastedList}>
              Use pasted list
            </button>
          </div>
        </section>
      )}

      {playlistError && <p className="error">{playlistError}</p>}
      {playlistNote && <p className="muted">{playlistNote}</p>}

      {playlist && !playlistError && (
        <section className="panel-section">
          <p className="muted">
            Loaded <strong>{playlist.name}</strong>
            {playlist.owner_name ? ` by ${playlist.owner_name}` : ''} — {playlist.tracks.length} tracks.
          </p>
          {playlist.truncated && (
            <p className="warn">
              ⚠ Spotify's public embed only returned the first {playlist.tracks.length} of{' '}
              {playlist.total ?? '100+'} tracks. Paste the full tracklist to match everything.
            </p>
          )}
          <div className="field-row">
            <button className="btn btn-primary" onClick={closePanel}>Done — go match</button>
          </div>
        </section>
      )}
    </Panel>
  );
}
