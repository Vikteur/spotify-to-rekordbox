import { useApp } from '../store';
import { useUi } from '../ui/UiContext';

type Variant = 'library' | 'playlist' | 'match';

export function EmptyState({ variant }: { variant: Variant }) {
  const s = useApp();
  const ui = useUi();

  if (variant === 'library') {
    return (
      <div className="empty">
        <h2 className="empty-title">Point Rekord Match at your music</h2>
        <p className="empty-text">
          Scan a folder or import a rekordbox collection so there's something to match your
          playlists against. Everything stays on this machine.
        </p>
        <button className="btn btn-primary" onClick={() => ui.openPanel('sources')}>
          Import library
        </button>
      </div>
    );
  }

  if (variant === 'playlist') {
    return (
      <div className="empty">
        <h2 className="empty-title">Load a playlist to match</h2>
        <p className="empty-text">
          Paste a public Spotify playlist link — or any “Artist - Title” tracklist — and Rekord
          Match will find the right file for each track.
        </p>
        <button className="btn btn-primary" onClick={() => ui.openPanel('addPlaylist')}>
          Add a playlist
        </button>
      </div>
    );
  }

  return (
    <div className="empty">
      <h2 className="empty-title">{s.playlist?.name}</h2>
      <p className="empty-text">
        {s.playlist?.tracks.length} tracks ready. Match them against{' '}
        <strong>{s.lib?.active_library_name}</strong> to pick the right file for each.
      </p>
      <button className="btn btn-primary" disabled={s.matching} onClick={s.runMatch}>
        {s.matching ? 'Matching…' : 'Match against library'}
      </button>
      {s.matchError && <p className="error">{s.matchError}</p>}
    </div>
  );
}
