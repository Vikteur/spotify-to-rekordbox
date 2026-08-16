import { PanelHost } from '../panels/PanelHost';
import { MainPane } from './MainPane';
import { Sidebar } from './Sidebar';

export function AppShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <MainPane />
      <PanelHost />
    </div>
  );
}
