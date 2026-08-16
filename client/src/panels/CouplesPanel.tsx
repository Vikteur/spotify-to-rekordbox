import { useEffect, useState } from 'react';
import { ApiError, api } from '../api';
import { formatDuration } from '../format';
import { useApp } from '../store';
import type { CoupleDetail, CoupleEntry, ListKind } from '../types';
import { useUi } from '../ui/UiContext';
import { Panel } from './Panel';

/** The chapters a couple fills in, in intake order, with the DJ-side labels. */
const CHAPTERS: { kind: ListKind; label: string }[] = [
  { kind: 'opening_dance', label: 'Opening dance' },
  { kind: 'second_third', label: 'Second & third song' },
  { kind: 'couple_top20', label: 'Their top 20' },
  { kind: 'friends_top20', label: "Friends' top 20" },
  { kind: 'must_plays', label: 'Must-plays' },
];

const message = (error: unknown) =>
  error instanceof ApiError ? error.message : String(error);

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function CopyField({ value, disabled }: { value: string; disabled?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copylink">
      <input
        className="input copylink-input"
        readOnly
        value={value}
        onFocus={(event) => event.target.select()}
      />
      <button
        className="btn btn-sm"
        disabled={disabled}
        onClick={() => {
          navigator.clipboard
            .writeText(value)
            .then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            })
            .catch(() => undefined);
        }}
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
    </div>
  );
}

function EntryLine({ entry }: { entry: CoupleEntry }) {
  return (
    <div className="list-track">
      <span className="list-track-n mono muted">{entry.position + 1}</span>
      <span className="list-main">
        {entry.artist ? `${entry.artist} – ` : ''}
        {entry.title}
        {!entry.spotify_id && <span className="muted"> · as typed</span>}
        {entry.source_token_kind === 'friend' && <span className="muted"> · friend</span>}
      </span>
      <span className="mono muted">
        {entry.duration_ms != null ? formatDuration(entry.duration_ms / 1000) : ''}
      </span>
    </div>
  );
}

/**
 * The DJ's window on one couple: create the record, hand out the two magic
 * links, watch the chapters stream in live, and load any chapter into the
 * match table like a normal playlist.
 */
export function CouplesPanel() {
  const s = useApp();
  const { panelArg, closePanel } = useUi();
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const parsed = Number(panelArg);
    return panelArg && panelArg !== 'new' && Number.isInteger(parsed) ? parsed : null;
  });
  const [detail, setDetail] = useState<CoupleDetail | null>(null);
  const [names, setNames] = useState('');
  const [date, setDate] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // The couple answers from home — poll while their page is open so the
  // lists stream in live.
  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      return;
    }
    let alive = true;
    const load = () =>
      api
        .couple(selectedId)
        .then((fresh) => {
          if (alive) setDetail(fresh);
        })
        .catch((err: unknown) => {
          if (alive) setError(message(err));
        });
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [selectedId]);

  async function create() {
    setBusy(true);
    setError('');
    try {
      const created = await api.createCouple(names.trim(), date);
      setNames('');
      setDate('');
      setSelectedId(created.id);
      setDetail(created);
      await s.refreshCouples();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(couple: CoupleDetail) {
    const sure = window.confirm(
      `Delete ${couple.names}?\n\nAll their answers, links and the never list are removed.`,
    );
    if (!sure) return;
    try {
      await api.deleteCouple(couple.id);
      setSelectedId(null);
      await s.refreshCouples();
    } catch (err) {
      setError(message(err));
    }
  }

  async function tokenAction(
    couple: CoupleDetail,
    kind: 'couple' | 'friends',
    action: 'rotate' | 'revoke' | 'enable',
  ) {
    setError('');
    try {
      if (action === 'rotate') {
        const sure = window.confirm(
          `Rotate the ${kind} link?\n\nThe old link stops working immediately — send the new one afterwards.`,
        );
        if (!sure) return;
        setDetail(await api.rotateCoupleToken(couple.id, kind));
      } else {
        setDetail(await api.revokeCoupleToken(couple.id, kind, action === 'revoke'));
      }
    } catch (err) {
      setError(message(err));
    }
  }

  function loadChapter(couple: CoupleDetail, kind: ListKind, label: string) {
    s.loadCoupleChapter(couple, kind, label);
    closePanel();
  }

  if (detail === null) {
    return (
      <Panel title="Couples" subtitle="One record per wedding — the couple fills it in from home.">
        <section className="panel-section">
          <h3 className="panel-section-title">New couple</h3>
          <div className="field-row">
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder="e.g. Sofie & Jan"
              value={names}
              onChange={(event) => setNames(event.target.value)}
            />
            <input
              className="input"
              style={{ width: 150 }}
              type="date"
              placeholder="2026-09-19"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="field-row">
            <button
              className="btn btn-primary"
              disabled={!names.trim() || !date || busy}
              onClick={create}
            >
              {busy ? 'Creating…' : 'Create couple'}
            </button>
          </div>
          <p className="hint">
            Creating a couple makes their two magic links: one for the couple, one shared
            link for their friends.
          </p>
        </section>

        <section className="panel-section">
          <h3 className="panel-section-title">All couples</h3>
          {s.couples.length === 0 && <p className="muted">No couples yet.</p>}
          <div className="list">
            {s.couples.map((couple) => (
              <button
                key={couple.id}
                className="list-row couple-row"
                onClick={() => setSelectedId(couple.id)}
              >
                <span className="list-main">
                  <strong>{couple.names}</strong>
                  <span className="muted"> · {couple.wedding_date}</span>
                </span>
                <span className="mono muted">{couple.song_count} songs</span>
              </button>
            ))}
          </div>
        </section>
        {error && <p className="error">{error}</p>}
      </Panel>
    );
  }

  const couple = detail;
  return (
    <Panel
      title={couple.names}
      subtitle={`Wedding on ${couple.wedding_date} — answers stream in live while they type.`}
    >
      <section className="panel-section">
        <button className="btn btn-sm" onClick={() => setSelectedId(null)}>
          ‹ All couples
        </button>
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">Magic links</h3>
        {(['couple', 'friends'] as const).map((kind) => {
          const link = couple.links[kind];
          const url = `${window.location.origin}${link.path}`;
          return (
            <div key={kind} className="couple-link">
              <span className="field-label">
                {kind === 'couple' ? 'Couple link — the whole intake' : "Friends link — their top 20 only"}
                {link.revoked && <span className="warn"> · revoked</span>}
                {link.expired && <span className="warn"> · expired (wedding passed)</span>}
              </span>
              <CopyField value={url} disabled={link.revoked || link.expired} />
              <div className="field-row">
                <button className="btn btn-sm" onClick={() => tokenAction(couple, kind, 'rotate')}>
                  Rotate link
                </button>
                <button
                  className="btn btn-sm"
                  onClick={() =>
                    tokenAction(couple, kind, link.revoked ? 'enable' : 'revoke')
                  }
                >
                  {link.revoked ? 'Re-enable' : 'Revoke'}
                </button>
              </div>
            </div>
          );
        })}
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">Chapters</h3>
        <div className="list">
          {CHAPTERS.map(({ kind, label }) => {
            const entries = couple.lists[kind] ?? [];
            const opening = kind === 'opening_dance' ? entries[0] : undefined;
            return (
              <details key={kind} className="list-block">
                <summary className="list-row list-summary">
                  <span className="list-main">{label}</span>
                  <span className="mono muted">{entries.length}</span>
                  <button
                    className="btn btn-sm"
                    disabled={entries.length === 0}
                    onClick={(event) => {
                      event.preventDefault();
                      loadChapter(couple, kind, label);
                    }}
                  >
                    Load & match
                  </button>
                </summary>
                <div className="list-detail">
                  {entries.length === 0 && <p className="muted">Nothing here yet.</p>}
                  {entries.map((entry) => (
                    <EntryLine key={entry.uid} entry={entry} />
                  ))}
                  {opening?.start_pref && (
                    <p className="hint">
                      Start: {opening.start_pref === 'top'
                        ? 'from the top'
                        : opening.start_pref === 'chorus'
                          ? 'from the chorus'
                          : 'fade in'}
                    </p>
                  )}
                  {opening?.note && <p className="hint">Note: “{opening.note}”</p>}
                </div>
              </details>
            );
          })}

          <details className="list-block">
            <summary className="list-row list-summary">
              <span className="list-main">Playlist links</span>
              <span className="mono muted">{(couple.lists.playlist_links ?? []).length}</span>
            </summary>
            <div className="list-detail">
              {(couple.lists.playlist_links ?? []).length === 0 && (
                <p className="muted">No playlists pasted.</p>
              )}
              {(couple.lists.playlist_links ?? []).map((entry) => (
                <p key={entry.uid} className="couple-plink">
                  <a href={entry.free_text ?? '#'} target="_blank" rel="noreferrer">
                    {entry.free_text}
                  </a>
                </p>
              ))}
              <p className="hint">Open a link and pull it in via “Add playlist”.</p>
            </div>
          </details>

          <details className="list-block">
            <summary className="list-row list-summary">
              <span className="list-main warn">Never list — blocked in every export</span>
              <span className="mono muted">{couple.blocklist.length}</span>
            </summary>
            <div className="list-detail">
              {couple.blocklist.length === 0 && <p className="muted">Nothing banned.</p>}
              {couple.blocklist.map((block) => (
                <div key={block.uid} className="list-track">
                  <span className="list-main">
                    {block.artist ? `${block.artist} – ` : ''}
                    {block.title}
                  </span>
                </div>
              ))}
            </div>
          </details>
        </div>
        <p className="hint">
          “Load &amp; match” drops the chapter into the match table — match and export it
          exactly like any playlist. Never-list songs are excluded automatically.
        </p>
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">How they party</h3>
        <p className={couple.briefing_text ? 'couple-briefing' : 'muted'}>
          {couple.briefing_text || 'No briefing yet — it appears as they fill in the finale.'}
        </p>
      </section>

      <section className="panel-section">
        <h3 className="panel-section-title">Recent changes</h3>
        {couple.changes.length === 0 && <p className="muted">No activity yet.</p>}
        {couple.changes.slice(0, 12).map((change, index) => (
          <p key={`${change.at}-${index}`} className="couple-change">
            <span className="mono muted">{timeAgo(change.at)}</span>{' '}
            <span className={`couple-actor couple-actor-${change.token_kind}`}>
              {change.token_kind}
            </span>{' '}
            {change.summary}
          </p>
        ))}
      </section>

      <section className="panel-section">
        <button className="btn btn-sm couple-delete" onClick={() => remove(couple)}>
          Delete this couple
        </button>
      </section>
      {error && <p className="error">{error}</p>}
    </Panel>
  );
}
