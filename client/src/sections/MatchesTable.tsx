import { SKIP, candidateLabel, chipStyles, formatDuration, versionLabel } from '../format';
import { useApp } from '../store';

export function MatchesTable() {
  const s = useApp();
  const { results, selections, rememberNote, unresolvedCount } = s;
  if (!results) return null;

  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold">3. Matches</h2>
      <p className="mt-1 text-gray-600">
        {results.filter((result) => result.bucket === 'auto').length} auto ·{' '}
        {results.filter((result) => result.bucket === 'ambiguous').length} to pick ·{' '}
        {results.filter((result) => result.bucket === 'unmatched').length} not found
        {results.filter((result) => result.from_preference).length > 0 && (
          <span className="text-purple-700">
            {' '}· {results.filter((result) => result.from_preference).length} using a remembered version
          </span>
        )}
        {unresolvedCount > 0 && (
          <span className="text-amber-700"> — {unresolvedCount} still need a choice below</span>
        )}
      </p>
      <p className="mt-1 text-xs text-gray-500">
        Picking a version remembers it: that file becomes this song's default in every future
        playlist. Change the dropdown any time to overwrite it.
      </p>
      {rememberNote && <p className="mt-1 text-xs text-amber-700">{rememberNote}</p>}
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
              const status = s.rowStatus(result);
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
                        onChange={(event) => s.chooseVersion(result, event.target.value)}
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
  );
}
