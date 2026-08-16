import { useEffect, type ReactNode } from 'react';
import { Close } from '../components/Icons';
import { useUi } from '../ui/UiContext';

/** A right-side slide-in drawer. Closes on ESC, on the close button, or on an overlay click. */
export function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const { closePanel } = useUi();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closePanel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closePanel]);

  return (
    <div className="panel-overlay" onMouseDown={closePanel}>
      <aside
        className="panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="panel-header">
          <div className="panel-heading">
            <h2 className="panel-title">{title}</h2>
            {subtitle && <p className="panel-subtitle">{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={closePanel} aria-label="Close">
            <Close />
          </button>
        </header>
        <div className="panel-body">{children}</div>
      </aside>
    </div>
  );
}
