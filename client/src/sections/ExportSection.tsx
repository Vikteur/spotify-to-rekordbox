import { useApp } from '../store';

export function ExportSection() {
  const s = useApp();
  const { results, name, setName, chosenIds, leftOut, exportError } = s;
  if (!results) return null;

  return (
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
          onClick={() => s.runExport('m3u8')}
        >
          Download .m3u8 (recommended)
        </button>
        <button
          className="rounded border border-gray-300 px-4 py-2 disabled:opacity-40"
          disabled={!chosenIds.length}
          onClick={() => s.runExport('xml')}
        >
          Download rekordbox .xml
        </button>
        <button
          className="rounded border border-gray-300 px-4 py-2 disabled:opacity-40"
          disabled={!leftOut.length}
          title="The tracks you don't have — paste it into a shop's search"
          onClick={s.runMissingExport}
        >
          Download missing .txt
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
  );
}
