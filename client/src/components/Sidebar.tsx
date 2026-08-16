import { useState } from 'react';
import { useApp } from '../store';
import { useUi } from '../ui/UiContext';
import { ThemeToggle } from '../theme/ThemeToggle';
import { ArrowRight, ChevronDown, Folder, Plus } from './Icons';

/** The gradient brand mark — four white "equalizer" bars. */
function LogoMark() {
  return (
    <div className="logo-mark" aria-hidden>
      <span style={{ height: 7 }} />
      <span style={{ height: 12 }} />
      <span style={{ height: 5 }} />
      <span style={{ height: 9, opacity: 0.72 }} />
    </div>
  );
}

export function Sidebar() {
  const s = useApp();
  const ui = useUi();
  const [libOpen, setLibOpen] = useState(false);
  const { lib, libraries, activeId, playlists, playlist, filterId, prefs, results, chosenIds, leftOut, couples } = s;

  const libraryName = lib?.active_library_name ?? 'No library';
  const trackCount = lib?.track_count ?? 0;

  return (
    <aside className="sidebar">
      <div className="brand">
        <LogoMark />
        <span className="brand-name">Rekord Match</span>
        <span className="brand-version">v0.9</span>
      </div>

      {/* The two input flows, always visible — export closes the loop in the dock below */}
      <div className="quick-actions">
        <button
          className="qa-btn qa-primary"
          title="Match a public Spotify link or a pasted tracklist"
          onClick={() => ui.openPanel('addPlaylist')}
        >
          <Plus size={15} /> Add playlist
        </button>
        <button
          className="qa-btn"
          title="Scan music folders or import rekordbox exports"
          onClick={() => ui.openPanel('sources')}
        >
          <Folder size={14} /> Import library
        </button>
      </div>

      {/* Active library selector */}
      <div className="lib-card-wrap">
        <button className="lib-card" onClick={() => setLibOpen((open) => !open)}>
          <div className="lib-card-top">
            <span className="lib-card-name">{libraryName}</span>
            <ChevronDown size={12} className="muted-icon" />
          </div>
          <div className="lib-card-status">
            <span className="dot dot-ok" />
            {trackCount > 0 ? `watching · ${trackCount.toLocaleString()} tracks` : 'no tracks yet'}
          </div>
        </button>
        {libOpen && (
          <>
            <button className="popover-backdrop" aria-label="Close menu" onClick={() => setLibOpen(false)} />
            <div className="popover" role="menu">
              {libraries.map((library) => (
                <button
                  key={library.id}
                  className={`popover-item ${library.id === activeId ? 'active' : ''}`}
                  onClick={() => {
                    if (library.id !== activeId) s.selectLibrary(library.id);
                    setLibOpen(false);
                  }}
                >
                  <span className="list-main">{library.name}</span>
                  <span className="mono muted">{library.track_count.toLocaleString()}</span>
                </button>
              ))}
              <button
                className="popover-item popover-action"
                onClick={() => {
                  setLibOpen(false);
                  ui.openPanel('sources');
                }}
              >
                Manage / add library <ArrowRight size={13} />
              </button>
            </div>
          </>
        )}
      </div>

      {/* Loaded Spotify playlist(s) */}
      <div className="nav-section">
        <div className="nav-head">
          <span className="nav-label">PLAYLISTS</span>
          <button className="nav-add" title="Add a Spotify link or paste a tracklist" onClick={() => ui.openPanel('addPlaylist')}>
            <Plus size={12} /> Add
          </button>
        </div>
        <div className="nav-list">
          {playlist ? (
            <div className="nav-item active">
              <span className="nav-item-name">{playlist.name}</span>
              <span className="mono nav-item-count">{playlist.tracks.length}</span>
            </div>
          ) : (
            <button className="nav-empty" onClick={() => ui.openPanel('addPlaylist')}>
              Add a playlist to match
            </button>
          )}
        </div>
      </div>

      {/* Wedding couples — their intake lists stream in behind magic links */}
      <div className="nav-section">
        <div className="nav-head">
          {/* The label itself opens the overview; + New jumps to the form. */}
          <button
            className={`nav-label nav-label-link ${
              ui.activePanel === 'couples' && !s.activeCouple ? 'active' : ''
            }`}
            title="Open the couples panel"
            onClick={() => ui.openPanel('couples')}
          >
            COUPLES
          </button>
          <button
            className="nav-add"
            title="Create a couple and their magic links"
            onClick={() => ui.openPanel('couples', 'new')}
          >
            <Plus size={12} /> New
          </button>
        </div>
        <div className="nav-list">
          {couples.length === 0 ? (
            <button className="nav-empty" onClick={() => ui.openPanel('couples', 'new')}>
              Create a wedding couple
            </button>
          ) : (
            couples.map((couple) => (
              <button
                key={couple.id}
                className={`nav-item ${s.activeCouple?.id === couple.id ? 'active' : ''}`}
                title={`${couple.names} — ${couple.wedding_date}`}
                onClick={() => ui.openPanel('couples', String(couple.id))}
              >
                <span className="nav-item-name">{couple.names}</span>
                <span className="mono nav-item-count">{couple.song_count}</span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Imported rekordbox "most-played" playlists — used to scope matching */}
      <div className="nav-section">
        <div className="nav-head">
          <span className="nav-label">MOST-PLAYED</span>
          <button className="nav-add" title="Import a rekordbox playlist export" onClick={() => ui.openPanel('sources', 'import')}>
            <Plus size={12} /> Import
          </button>
        </div>
        <div className="nav-list">
          {playlists.length === 0 ? (
            <button className="nav-empty" onClick={() => ui.openPanel('sources', 'import')}>
              Import a rekordbox playlist
            </button>
          ) : (
            playlists.map((list) => (
              <button
                key={list.id}
                className={`nav-item ${filterId === list.id ? 'active' : ''}`}
                title="Scope matching to this playlist (then Re-match)"
                onClick={() => s.setFilterId(filterId === list.id ? null : list.id)}
              >
                <span className="nav-item-name">{list.name}</span>
                <span className="mono nav-item-count">{list.track_count}</span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Match scope */}
      <div className="nav-section">
        <span className="nav-label">SEARCH IN</span>
        <select
          className="search-in"
          value={filterId ?? ''}
          onChange={(event) => s.setFilterId(event.target.value ? Number(event.target.value) : null)}
          aria-label="Search scope"
        >
          <option value="">All tracks</option>
          {playlists.map((list) => (
            <option key={list.id} value={list.id}>★ {list.name} ({list.track_count})</option>
          ))}
        </select>
      </div>

      {/* Footer stats */}
      <div className="foot-stats">
        <button className="stat-row" onClick={() => ui.openPanel('remembered')}>
          <span>Remembered</span>
          <span className="mono muted">{prefs.length}</span>
        </button>
      </div>

      {/* Export dock — always says what's missing when it can't export yet */}
      <div className="export-dock">
        <div className="engine-line">
          <span className="dot dot-ok" />
          engine ready · local only
        </div>
        <button
          className="btn btn-primary btn-block"
          disabled={!results || !chosenIds.length}
          onClick={() => ui.openPanel('export')}
        >
          {results ? `Export ${chosenIds.length} track${chosenIds.length === 1 ? '' : 's'}` : 'Export'}
        </button>
        <div className="dock-note">
          {!playlist
            ? 'add a playlist to get started'
            : !results
              ? 'match the playlist, then export'
              : !chosenIds.length
                ? 'no tracks resolved yet'
                : leftOut.length > 0
                  ? `${leftOut.length} unresolved will be skipped`
                  : 'all tracks resolved'}
        </div>
        <ThemeToggle />
      </div>
    </aside>
  );
}
