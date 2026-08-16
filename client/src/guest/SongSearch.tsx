import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../api';
import { formatDuration } from '../format';
import { Close, Search } from '../components/Icons';
import type { SongHit } from '../types';
import type { SongPick } from './store';

const DEBOUNCE_MS = 250;
const MIN_QUERY = 2;

interface SongSearchProps {
  placeholder: string;
  search: (q: string) => Promise<SongHit[]>;
  searchAvailable: boolean;
  onPick: (pick: SongPick) => void;
  compact?: boolean;
  autoFocus?: boolean;
}

/**
 * Typeahead over the server's Spotify search proxy: debounced ~250ms, top 8
 * suggestions, and always a last row to keep the typed text as-is — a song
 * that isn't on Spotify must never block the flow.
 */
export function SongSearch({
  placeholder,
  search,
  searchAvailable,
  onPick,
  compact = false,
  autoFocus = false,
}: SongSearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SongHit[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searchBroken, setSearchBroken] = useState(!searchAvailable);
  const requestSeq = useRef(0);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < MIN_QUERY || searchBroken) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const seq = ++requestSeq.current;
    const timer = window.setTimeout(() => {
      search(q)
        .then((hits) => {
          if (requestSeq.current !== seq) return; // stale response
          setResults(hits);
          setHighlight(0);
          setSearching(false);
        })
        .catch((error: unknown) => {
          if (requestSeq.current !== seq) return;
          setSearching(false);
          if (error instanceof ApiError && error.code === 'RATE_LIMITED') {
            return; // keep the previous suggestions; the next keystroke retries
          }
          // Search proxy down or unconfigured: fall back to free text only.
          setResults([]);
          setSearchBroken(true);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, search, searchBroken]);

  // Tapping elsewhere closes the suggestion list.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open]);

  const trimmed = query.trim();
  const showFreeText = trimmed.length >= MIN_QUERY;
  const optionCount = results.length + (showFreeText ? 1 : 0);

  function pick(index: number) {
    if (index < results.length) {
      onPick(results[index]);
    } else if (showFreeText) {
      onPick({ free_text: trimmed });
    } else {
      return;
    }
    setQuery('');
    setResults([]);
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (!open || optionCount === 0) {
      if (event.key === 'Enter' && showFreeText) {
        event.preventDefault();
        pick(results.length); // no suggestions: keep the typed text
      }
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      setHighlight((current) => (current + delta + optionCount) % optionCount);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      pick(highlight);
    }
  }

  return (
    <div className={`songsearch ${compact ? 'songsearch-compact' : ''}`} ref={rootRef}>
      <div className="songsearch-box">
        <Search size={compact ? 13 : 15} className="songsearch-icon" />
        <input
          className="songsearch-input"
          value={query}
          placeholder={placeholder}
          autoFocus={autoFocus}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          autoComplete="off"
          spellCheck={false}
        />
        {query && (
          <button
            className="icon-btn songsearch-clear"
            aria-label="Clear"
            onClick={() => {
              setQuery('');
              setResults([]);
            }}
          >
            <Close size={13} />
          </button>
        )}
      </div>

      {open && trimmed.length >= MIN_QUERY && (
        <div className="songsearch-drop" role="listbox">
          {searchBroken && (
            <div className="songsearch-note">
              Song search is offline — your text is saved exactly as typed.
            </div>
          )}
          {searching && results.length === 0 && !searchBroken && (
            <div className="songsearch-note">Searching…</div>
          )}
          {results.map((hit, index) => (
            <button
              key={hit.spotify_id ?? `${hit.title}-${index}`}
              className={`songsearch-item ${index === highlight ? 'active' : ''}`}
              role="option"
              aria-selected={index === highlight}
              onMouseEnter={() => setHighlight(index)}
              onClick={() => pick(index)}
            >
              {hit.art_url ? (
                <img className="songsearch-art" src={hit.art_url} alt="" loading="lazy" />
              ) : (
                <span className="songsearch-art songsearch-art-empty" />
              )}
              <span className="songsearch-text">
                <span className="songsearch-title">{hit.title}</span>
                <span className="songsearch-artist">{hit.artist}</span>
              </span>
              <span className="mono songsearch-time">
                {hit.duration_ms != null ? formatDuration(hit.duration_ms / 1000) : ''}
              </span>
            </button>
          ))}
          {showFreeText && (
            <button
              className={`songsearch-item songsearch-freetext ${
                highlight === results.length ? 'active' : ''
              }`}
              role="option"
              aria-selected={highlight === results.length}
              onMouseEnter={() => setHighlight(results.length)}
              onClick={() => pick(results.length)}
            >
              Keep “{trimmed}” exactly as typed
              <span className="songsearch-freetext-sub">for songs not on Spotify</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
