import { AppProvider } from './store';
import { UiProvider } from './ui/UiContext';
import { AppShell } from './components/AppShell';

export default function App() {
  return (
    <AppProvider>
      <UiProvider>
        <AppShell />
      </UiProvider>
    </AppProvider>
  );
}
