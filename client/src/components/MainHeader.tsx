import { useEffect, useRef } from 'react';
import { useApp } from '../store';
import { useUi, type TrackTab } from '../ui/UiContext';
import { durationTotal, formatLongDuration, modKey, tabCounts } from '../lib/ui-helpers';
import { Search } from './Icons';

const TABS: { key: TrackTab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'needs', label: 'Needs you' },
  { key: 'ready', label: 'Ready' },
  { key: 'notfound', label: 'Not found' },
];

export function MainHeader() {
  const s = useApp();
  const ui = useUi();
  const { playlist, results, chosenIds } = s;
  const filterRef = useRef<HTMLInputElement>(null);

  // The chip next to the filter promises Ctrl/⌘+F — honour it.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault();
        filterRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const total = playlist ? durationTotal(playlist.tracks) : null;
  const counts = results ? tabCounts(results, s.rowStatus) : null;
  const pct = results && results.length ? (chosenIds.length / results.length) * 100 : 0;

  return (
    <header className="main-header">
      <div className="mh-top">
        <div>
          <h1 className="mh-title">{playlist?.name ?? 'Playlist'}</h1>
          <div className="mh-sub">
            {playlist ? `${playlist.tracks.length} tracks` : ''}
            {total != null ? ` · ${formatLongDuration(total)}` : ''}
          </div>
        </div>
        {results && (
          <div className="mh-actions">
            <button className="btn btn-ghost" disabled={s.matching} onClick={s.runMatch}>
              {s.matching ? 'Matching…' : 'Re-match'}
            </button>
            <div className="progress">
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="progress-count">
                {chosenIds.length}
                <span className="muted">/{results.length}</span>
              </span>
            </div>
          </div>
        )}
      </div>

      {(s.matchError || s.rememberNote) && (
        <div className="mh-notes">
          {s.matchError && <span className="error">{s.matchError}</span>}
          {s.rememberNote && <span className="warn">{s.rememberNote}</span>}
        </div>
      )}

      {results && counts && (
        <div className="mh-filters">
          <div className="segmented">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                className={`segment ${ui.activeTab === tab.key ? 'active' : ''}`}
                onClick={() => ui.setActiveTab(tab.key)}
              >
                {tab.label} <span className="seg-count">{counts[tab.key]}</span>
              </button>
            ))}
          </div>
          <div className="filter-input">
            <Search size={13} className="muted-icon" />
            <input
              ref={filterRef}
              value={ui.filterText}
              onChange={(event) => ui.setFilterText(event.target.value)}
              placeholder="Filter by artist, title or file"
              aria-label="Filter tracks"
            />
            <span className="kbd">{modKey} F</span>
          </div>
        </div>
      )}
    </header>
  );
}
