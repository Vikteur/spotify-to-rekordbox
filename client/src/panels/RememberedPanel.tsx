import { useApp } from '../store';
import { Panel } from './Panel';

/** The remembered version choices — the file this app defaults to per song. */
export function RememberedPanel() {
  const s = useApp();
  const { prefs } = s;

  return (
    <Panel
      title="Remembered versions"
      subtitle="Each pick becomes this song's default in every future playlist."
    >
      {prefs.length === 0 ? (
        <p className="muted">
          Nothing remembered yet. When you pick a file with “Use &amp; remember”, it shows up here.
        </p>
      ) : (
        <>
          <ul className="list">
            {prefs.map((preference) => (
              <li key={preference.id} className="list-row">
                <span className="list-main">
                  {preference.artist || '?'} – {preference.title}
                  <span className="muted"> → </span>
                  {preference.file_label ?? <span className="warn">file not in your library right now</span>}
                </span>
                <button className="btn btn-ghost btn-sm" onClick={() => s.forgetChoice(preference.id)}>
                  Forget
                </button>
              </li>
            ))}
          </ul>
          <div className="field-row">
            <button className="btn btn-ghost" onClick={s.forgetAllChoices}>Forget all</button>
          </div>
        </>
      )}
    </Panel>
  );
}
