import { useApp } from '../store';
import { useUi } from '../ui/UiContext';
import { matchesTab, matchesText } from '../lib/ui-helpers';
import { TrackRow } from './TrackRow';

export function TrackTable() {
  const s = useApp();
  const ui = useUi();
  const { results, selections } = s;
  if (!results) return null;

  const rows = results.filter((result) => {
    const status = s.rowStatus(result);
    return matchesTab(status, ui.activeTab) && matchesText(result, selections, ui.filterText);
  });

  return (
    <div className="track-table">
      <div className="track-head track-grid">
        <span>#</span>
        <span>TRACK</span>
        <span>ANALYSIS</span>
        <span className="ta-right">MATCH</span>
        <span />
      </div>
      <div className="track-body">
        {rows.length === 0 ? (
          <div className="table-empty">No tracks match this filter.</div>
        ) : (
          rows.map((result) => <TrackRow key={result.input.index} result={result} />)
        )}
      </div>
    </div>
  );
}
