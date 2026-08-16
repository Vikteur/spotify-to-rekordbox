import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/** Secondary flows live in slide-in panels opened from the sidebar. */
export type PanelId = 'sources' | 'addPlaylist' | 'export' | 'remembered' | 'couples';

/** Which filter tab the match table is showing. */
export type TrackTab = 'all' | 'needs' | 'ready' | 'notfound';

/**
 * Pure view state — which panel is open, which row is expanded, the active
 * filter tab and text. Kept out of `store.tsx` on purpose: it has no backend
 * coupling, so the store stays the single owner of server-derived state and
 * its cross-section side effects.
 */
function useUiState() {
  const [activePanel, setActivePanel] = useState<PanelId | null>(null);
  const [panelArg, setPanelArg] = useState<string | undefined>(undefined);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TrackTab>('all');
  const [filterText, setFilterText] = useState('');
  const [showMore, setShowMore] = useState<Record<number, boolean>>({});

  return useMemo(
    () => ({
      activePanel,
      panelArg,
      openPanel: (id: PanelId, arg?: string) => {
        setPanelArg(arg);
        setActivePanel(id);
      },
      closePanel: () => setActivePanel(null),
      expandedRow,
      toggleRow: (index: number) =>
        setExpandedRow((current) => (current === index ? null : index)),
      activeTab,
      setActiveTab,
      filterText,
      setFilterText,
      showMore,
      toggleShowMore: (index: number) =>
        setShowMore((current) => ({ ...current, [index]: !current[index] })),
    }),
    [activePanel, panelArg, expandedRow, activeTab, filterText, showMore],
  );
}

type UiStore = ReturnType<typeof useUiState>;

const UiContext = createContext<UiStore | null>(null);

export function UiProvider({ children }: { children: ReactNode }) {
  return <UiContext.Provider value={useUiState()}>{children}</UiContext.Provider>;
}

export function useUi(): UiStore {
  const store = useContext(UiContext);
  if (!store) throw new Error('useUi must be used within <UiProvider>');
  return store;
}
