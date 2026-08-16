import { useState } from 'react';
import { formatDuration } from '../format';
import { ChevronDown, ChevronUp, Close } from '../components/Icons';
import type { CoupleEntry, ListKind } from '../types';
import { SongSearch } from './SongSearch';
import { useGuest } from './store';

/** The autosave status, always visible in the header. */
export function SaveChip() {
  const { saveState } = useGuest();
  const label =
    saveState === 'saved' ? 'Saved' : saveState === 'saving' ? 'Saving…' : 'Retrying…';
  return (
    <span className={`save-chip save-${saveState}`}>
      <span className="save-dot" />
      {label}
    </span>
  );
}

/** Example placeholders, rotated so a 20-row table doesn't repeat one hint. */
const ROW_EXAMPLES = [
  'e.g. Dancing Queen – ABBA',
  'e.g. One More Time – Daft Punk',
  'e.g. Levels – Avicii',
  'e.g. Mr. Brightside – The Killers',
  'e.g. Crazy in Love – Beyoncé',
  'e.g. Superstition – Stevie Wonder',
];

export function rowPlaceholder(index: number): string {
  return ROW_EXAMPLES[index % ROW_EXAMPLES.length];
}

interface SongCardProps {
  entry: CoupleEntry;
  onRemove?: () => void;
  onMove?: (delta: -1 | 1) => void;
  moveUpDisabled?: boolean;
  moveDownDisabled?: boolean;
  sourceChip?: string | null;
  big?: boolean;
}

/** A filled song row: art, title/artist, duration, and the allowed controls. */
export function SongCard({
  entry,
  onRemove,
  onMove,
  moveUpDisabled,
  moveDownDisabled,
  sourceChip,
  big = false,
}: SongCardProps) {
  return (
    <div className={`songcard ${big ? 'songcard-big' : ''}`}>
      {entry.art_url ? (
        <img className="songcard-art" src={entry.art_url} alt="" loading="lazy" />
      ) : (
        <span className="songcard-art songcard-art-empty" aria-hidden>
          ♪
        </span>
      )}
      <span className="songcard-text">
        <span className="songcard-title">{entry.title}</span>
        <span className="songcard-sub">
          {entry.artist || (entry.spotify_id ? '' : 'as typed — not on Spotify')}
        </span>
      </span>
      {sourceChip && <span className="songcard-chip">{sourceChip}</span>}
      <span className="mono songcard-time">
        {entry.duration_ms != null ? formatDuration(entry.duration_ms / 1000) : ''}
      </span>
      {onMove && (
        <span className="songcard-move">
          <button
            className="icon-btn"
            aria-label="Move up"
            disabled={moveUpDisabled}
            onClick={() => onMove(-1)}
          >
            <ChevronUp size={14} />
          </button>
          <button
            className="icon-btn"
            aria-label="Move down"
            disabled={moveDownDisabled}
            onClick={() => onMove(1)}
          >
            <ChevronDown size={14} />
          </button>
        </span>
      )}
      {onRemove && (
        <button className="icon-btn songcard-remove" aria-label="Remove song" onClick={onRemove}>
          <Close size={14} />
        </button>
      )}
    </div>
  );
}

interface SongTableProps {
  kind: ListKind;
  rows: number;
  canAdd: boolean;
  canRemove: boolean;
  canReorder: boolean;
  showSource?: boolean;
}

/**
 * The numbered fill-in table behind "their top 20", the friends' list and the
 * must-plays: one row per slot, type straight into any empty row.
 */
export function SongTable({
  kind,
  rows,
  canAdd,
  canRemove,
  canReorder,
  showSource = false,
}: SongTableProps) {
  const store = useGuest();
  const entries = store.listOf(kind);
  const byPosition = new Map(entries.map((entry) => [entry.position, entry]));
  const full = entries.length >= rows;
  const viewer = store.data?.scope === 'friends' ? 'friend' : 'couple';

  return (
    <div className="songtable">
      {Array.from({ length: rows }, (_, index) => {
        const entry = byPosition.get(index);
        return (
          <div key={entry?.uid ?? `empty-${index}`} className="songtable-row">
            <span className="mono songtable-num">{index + 1}</span>
            {entry ? (
              <SongCard
                entry={entry}
                onRemove={canRemove ? () => store.removeEntry(entry.uid) : undefined}
                onMove={canReorder ? (delta) => store.moveEntry(kind, entry.uid, delta) : undefined}
                moveUpDisabled={index === 0}
                moveDownDisabled={index === rows - 1}
                sourceChip={
                  showSource && entry.source_token_kind !== viewer
                    ? entry.source_token_kind === 'friend'
                      ? 'a friend'
                      : 'the couple'
                    : null
                }
              />
            ) : canAdd && !full ? (
              <SongSearch
                compact
                placeholder={rowPlaceholder(index)}
                search={store.search}
                searchAvailable={store.data?.search_available ?? false}
                onPick={(pick) => store.pickSong(kind, index, pick)}
              />
            ) : (
              <span className="songtable-empty">—</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Read-only recap row for the reveal screen. */
export function RevealRow({ entry, prefix }: { entry: CoupleEntry; prefix?: string }) {
  return (
    <div className="reveal-row">
      {entry.art_url ? (
        <img className="songcard-art" src={entry.art_url} alt="" loading="lazy" />
      ) : (
        <span className="songcard-art songcard-art-empty" aria-hidden>
          ♪
        </span>
      )}
      <span className="songcard-text">
        <span className="songcard-title">
          {prefix && <span className="reveal-prefix">{prefix} · </span>}
          {entry.title}
        </span>
        <span className="songcard-sub">{entry.artist || 'as typed'}</span>
      </span>
      <span className="mono songcard-time">
        {entry.duration_ms != null ? formatDuration(entry.duration_ms / 1000) : ''}
      </span>
    </div>
  );
}

/** Readonly link + copy button (the shared friends link). */
export function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copylink">
      <input className="input copylink-input" readOnly value={url} onFocus={(e) => e.target.select()} />
      <button
        className="btn btn-primary"
        onClick={() => {
          navigator.clipboard
            .writeText(url)
            .then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1600);
            })
            .catch(() => undefined);
        }}
      >
        {copied ? 'Copied!' : 'Copy link'}
      </button>
    </div>
  );
}
