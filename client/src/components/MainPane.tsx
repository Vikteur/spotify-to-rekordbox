import { useApp } from '../store';
import { modKey } from '../lib/ui-helpers';
import { EmptyState } from './EmptyState';
import { MainHeader } from './MainHeader';
import { TrackTable } from './TrackTable';

/** The right pane: an empty state until there's a library, a playlist and matches. */
export function MainPane() {
  const s = useApp();

  if (!s.hasLibrary) {
    return (
      <main className="main-pane">
        <EmptyState variant="library" />
      </main>
    );
  }

  if (!s.playlist) {
    return (
      <main className="main-pane">
        <EmptyState variant="playlist" />
      </main>
    );
  }

  return (
    <main className="main-pane">
      <MainHeader />
      {s.results ? <TrackTable /> : <EmptyState variant="match" />}
      {s.results && (
        <footer className="main-foot">
          <span className="foot-hint"><span className="kbd">{modKey} F</span> filter tracks</span>
          <span className="foot-hint"><span className="kbd">esc</span> close panel</span>
        </footer>
      )}
    </main>
  );
}
