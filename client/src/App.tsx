import { AppProvider } from './store';
import { LibrarySection } from './sections/LibrarySection';
import { PlaylistSection } from './sections/PlaylistSection';
import { MatchesTable } from './sections/MatchesTable';
import { ExportSection } from './sections/ExportSection';

export default function App() {
  return (
    <AppProvider>
      <main className="mx-auto max-w-5xl px-4 py-8 text-sm text-gray-900">
        <h1 className="text-2xl font-bold">Spotify → rekordbox</h1>
        <p className="mt-1 text-gray-500">
          Match a public Spotify playlist against the music you own, pick the right file per track, export a
          rekordbox playlist. Everything stays on your machine.
        </p>
        <LibrarySection />
        <PlaylistSection />
        <MatchesTable />
        <ExportSection />
      </main>
    </AppProvider>
  );
}
