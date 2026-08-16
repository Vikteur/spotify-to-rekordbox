import { useEffect, useState } from 'react';
import { SKIP } from '../format';
import { useApp } from '../store';
import { useUi } from '../ui/UiContext';
import type { MatchResult, ScoredCandidate } from '../types';
import {
  analysisLine,
  artGradient,
  confidence,
  rowSubtitle,
  statusMeta,
  trackAnalysis,
} from '../lib/ui-helpers';
import { ChevronDown, ChevronUp, Star } from './Icons';

function versionName(candidate: ScoredCandidate): string {
  const { descriptors, remixer } = candidate.version;
  if (remixer) return `${remixer} ${descriptors.join(' ')}`.trim();
  if (descriptors.length) return descriptors.join(' ');
  return 'Original';
}

function Badge({ status }: { status: string }) {
  const meta = statusMeta(status);
  return (
    <span className={`badge badge-${meta.badge}`}>
      <span className="badge-dot" />
      {meta.label}
    </span>
  );
}

/**
 * The pick-one interaction. Clicking a candidate only moves the ring (a local
 * draft) — nothing is applied until "Use & remember", "Use once", Enter or
 * Skip, so browsing 23 remixes never silently commits the first click. Undo
 * restores whatever the match run suggested.
 */
function ExpandedCandidates({ result }: { result: MatchResult }) {
  const s = useApp();
  const ui = useUi();
  const index = result.input.index;
  const committed = s.selections[index] ?? '';
  const committedId = committed && committed !== SKIP ? committed : '';
  const matchPreset = result.auto_selected_id ?? (result.candidates.length ? '' : SKIP);
  const canUndo = committed !== matchPreset || Boolean(s.remembered[index]);

  const initialDraft = () =>
    committedId || result.auto_selected_id || result.candidates[0]?.track.id || '';
  const [draft, setDraft] = useState<string>(initialDraft);

  // A re-match can rebuild the candidate list while this row stays open —
  // never leave the ring pointing at a track id that no longer exists.
  useEffect(() => {
    if (draft && !result.candidates.some((c) => c.track.id === draft)) {
      setDraft(initialDraft());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const draftIdx = result.candidates.findIndex((c) => c.track.id === draft);
  const forceAll = draftIdx >= 3; // the ringed version must stay visible
  const showAll = Boolean(ui.showMore[index]) || forceAll;
  const visible = showAll ? result.candidates : result.candidates.slice(0, 3);
  const hidden = result.candidates.length - visible.length;

  /** Apply a decision and collapse the row — the decision is made. */
  const commit = (value: string, remember = false) => {
    s.chooseVersion(result, value, remember);
    ui.toggleRow(index);
  };
  const undo = () => {
    s.resetChoice(result);
    setDraft(result.auto_selected_id || result.candidates[0]?.track.id || '');
  };

  // Keyboard: ↵ use & remember, 1–9 move the ring, S skip, Esc collapse.
  // Mounted only while this row is expanded; inert while a panel is open or
  // the user is typing in an input.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (ui.activePanel) return;
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.key === 'Enter') {
        if (draft) {
          event.preventDefault();
          commit(draft, true);
        }
      } else if (event.key === 's' || event.key === 'S') {
        event.preventDefault();
        commit(SKIP);
      } else if (event.key === 'Escape') {
        ui.toggleRow(index);
      } else if (/^[1-9]$/.test(event.key)) {
        const candidate = visible[Number(event.key) - 1];
        if (candidate) setDraft(candidate.track.id);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  return (
    <div className="expanded-body">
      <div className="cand-list">
        {visible.map((candidate, position) => {
          const selected = candidate.track.id === draft;
          const score = Math.round(candidate.score * 100);
          return (
            <button
              key={candidate.track.id}
              className={`cand ${selected ? 'selected' : ''}`}
              onClick={() => setDraft(candidate.track.id)}
            >
              <span className={`radio ${selected ? 'on' : ''}`} />
              <span className="cand-name">
                <span className="cand-version">{versionName(candidate)}</span>
                <span className="cand-file">{candidate.track.filename}.{candidate.track.ext}</span>
              </span>
              <span className="cand-analysis">{trackAnalysis(candidate.track)}</span>
              <span className="cand-match">
                {position === 0 && <span className="tag-best">BEST</span>}
                {candidate.playlists.length > 0 && (
                  <span className="tag-star" title={`in ${candidate.playlists.join(', ')}`}>
                    <Star size={11} />
                  </span>
                )}
                <span className="conf conf-accent">
                  <span className="conf-pct">{score}%</span>
                </span>
              </span>
            </button>
          );
        })}
        {hidden > 0 && (
          <button className="show-more" onClick={() => ui.toggleShowMore(index)}>
            Show {hidden} more version{hidden === 1 ? '' : 's'} <ChevronDown size={11} />
          </button>
        )}
        {showAll && !forceAll && result.candidates.length > 3 && (
          <button className="show-more" onClick={() => ui.toggleShowMore(index)}>
            Show fewer <ChevronUp size={11} />
          </button>
        )}
      </div>

      <div className="cand-actions">
        <button
          className="btn btn-primary btn-sm"
          disabled={!draft}
          onClick={() => draft && commit(draft, true)}
        >
          Use &amp; remember
        </button>
        <button
          className="btn btn-ghost btn-sm"
          disabled={!draft}
          onClick={() => draft && commit(draft, false)}
        >
          Use once
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => commit(SKIP)}>
          Skip
        </button>
        {canUndo && (
          <button
            className="btn btn-ghost btn-sm"
            title="Back to what the match suggested"
            onClick={undo}
          >
            {committed === SKIP ? 'Undo skip' : 'Undo pick'}
          </button>
        )}
        <div className="kbd-hints">
          <span><span className="kbd">↵</span> use</span>
          <span><span className="kbd">1–{Math.min(visible.length, 9)}</span> pick</span>
          <span><span className="kbd">S</span> skip</span>
        </div>
      </div>
    </div>
  );
}

export function TrackRow({ result }: { result: MatchResult }) {
  const s = useApp();
  const ui = useUi();
  const status = s.rowStatus(result);
  const conf = confidence(result, status, s.selections);
  const expanded = ui.expandedRow === result.input.index;
  const hasCandidates = result.candidates.length > 0;
  const artist = result.input.artist || '?';
  const idx = String(result.input.index + 1).padStart(2, '0');

  return (
    <div className={`track-row-wrap ${expanded ? 'expanded' : ''} ${status === 'skipped' ? 'dim' : ''}`}>
      <div
        className={`track-row track-grid ${hasCandidates ? 'clickable' : ''}`}
        onClick={() => hasCandidates && ui.toggleRow(result.input.index)}
      >
        <span className="track-idx">{idx}</span>
        <div className="track-cell">
          <span className="art" style={{ backgroundImage: artGradient(artist, result.input.title) }} />
          <span className="track-text">
            <span className="track-title">{artist} – {result.input.title}</span>
            <span className="track-sub">{rowSubtitle(result, status, s.selections)}</span>
          </span>
        </div>
        <span className="analysis">{analysisLine(result, s.selections)}</span>
        <div className="match-cell">
          <Badge status={status} />
          {conf.pct != null ? (
            <span className={`conf conf-${conf.tone}`}>
              <span className="conf-pct">{conf.pct}%</span>
            </span>
          ) : (
            <span className="conf-dash">—</span>
          )}
        </div>
        <span className="chevron">
          {hasCandidates && (expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
        </span>
      </div>
      {expanded && hasCandidates && <ExpandedCandidates result={result} />}
    </div>
  );
}
