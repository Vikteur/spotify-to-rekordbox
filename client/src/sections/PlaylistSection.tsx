import { useApp } from '../store';

export function PlaylistSection() {
  const s = useApp();
  const {
    url, setUrl, pasted, setPasted, playlist, playlistNote, playlistError,
    fetching, matching, matchError, hasLibrary, playlists, filterId,
    setFilterId, lib,
  } = s;

  return (
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
          onClick={s.fetchPlaylist}
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
          onClick={s.usePastedList}
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
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          className="rounded bg-gray-900 px-4 py-2 font-medium text-white disabled:opacity-40"
          disabled={!playlist || !hasLibrary || matching}
          title={!hasLibrary ? 'Add a library first (scan a folder or import a rekordbox XML)' : undefined}
          onClick={s.runMatch}
        >
          {matching ? 'Matching…' : 'Match against library'}
        </button>
        {playlists.length > 0 && (
          <label className="flex items-center gap-2 text-gray-600">
            limited to:
            <select
              className="rounded border border-gray-300 px-2 py-1.5"
              value={filterId ?? ''}
              onChange={(event) =>
                setFilterId(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">everything in {lib?.active_library_name}</option>
              {playlists.map((list) => (
                <option key={list.id} value={list.id}>
                  ★ {list.name} ({list.track_count})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {matchError && <p className="mt-2 text-red-700">{matchError}</p>}
    </section>
  );
}
