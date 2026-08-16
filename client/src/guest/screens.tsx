import { useEffect, useState } from 'react';
import type { StartPref } from '../types';
import { SongSearch } from './SongSearch';
import { CopyLink, RevealRow, SongCard, SongTable } from './parts';
import { useGuest } from './store';

/* ------------------------------------------------ 1 · welcome (mockup 9a) */

export function WelcomeScreen() {
  const store = useGuest();
  const data = store.data!;
  return (
    <div className="g-screen">
      <h1 className="g-title">Welcome!</h1>
      <p className="g-lead">
        Let's build the soundtrack of your wedding, one page at a time. Everything you
        type is <strong>saved automatically</strong> — close this tab whenever you like
        and come back later with the same link to finish or change your answers.
      </p>
      <label className="g-label" htmlFor="g-names">
        Your names
      </label>
      <input
        id="g-names"
        className="input g-input"
        placeholder="e.g. Sofie & Jan"
        value={data.names}
        onChange={(event) => store.patchCouple({ names: event.target.value })}
      />
      <label className="g-label" htmlFor="g-date">
        Wedding date
      </label>
      <input
        id="g-date"
        type="date"
        className="input g-input"
        placeholder="e.g. 2026-09-19"
        value={data.wedding_date}
        onChange={(event) => store.patchCouple({ wedding_date: event.target.value }, false)}
      />
      <p className="hint">Your link stays active until the day after the wedding.</p>
    </div>
  );
}

/* ------------------------------------------ 2 · opening dance (mockup 9b) */

const START_OPTIONS: { value: StartPref; label: string; sub: string }[] = [
  { value: 'top', label: 'From the top', sub: 'the very first note, the classic way' },
  { value: 'chorus', label: 'From the chorus', sub: 'start where everyone knows it' },
  { value: 'fade', label: 'Fade in', sub: 'ease in softly mid-song' },
];

export function OpeningScreen() {
  const store = useGuest();
  const entry = store.listOf('opening_dance')[0];
  return (
    <div className="g-screen">
      <h1 className="g-title">Your opening dance</h1>
      <p className="g-lead">The one song everything opens with. Which is it?</p>
      {entry ? (
        <SongCard entry={entry} big onRemove={() => store.removeEntry(entry.uid)} />
      ) : (
        <SongSearch
          autoFocus
          placeholder="e.g. Thinking Out Loud – Ed Sheeran"
          search={store.search}
          searchAvailable={store.data?.search_available ?? false}
          onPick={(pick) => store.pickSong('opening_dance', 0, pick)}
        />
      )}

      <h2 className="g-subtitle">How should it start?</h2>
      {!entry && <p className="hint">Pick your song first, then choose how it starts.</p>}
      <div className="g-options">
        {START_OPTIONS.map((option) => (
          <button
            key={option.value}
            className={`g-option ${entry?.start_pref === option.value ? 'active' : ''}`}
            disabled={!entry}
            onClick={() => entry && store.setEntryExtras(entry.uid, { start_pref: option.value })}
          >
            <span className={`radio ${entry?.start_pref === option.value ? 'on' : ''}`} />
            <span className="g-option-text">
              <span className="g-option-label">{option.label}</span>
              <span className="g-option-sub">{option.sub}</span>
            </span>
          </button>
        ))}
      </div>

      <label className="g-label" htmlFor="g-opening-note">
        Anything the DJ should know about this moment?
      </label>
      <textarea
        id="g-opening-note"
        className="textarea g-textarea"
        placeholder="e.g. It's the song from our first date — please play the album version, and cut it before the rap part."
        value={entry?.note ?? ''}
        disabled={!entry}
        onChange={(event) =>
          entry && store.setEntryExtras(entry.uid, { note: event.target.value }, true)
        }
      />
    </div>
  );
}

/* ------------------------------------- 3 · second & third song (mockup 9c) */

export function SecondThirdScreen() {
  const store = useGuest();
  const entries = store.listOf('second_third');
  const slots: { position: number; label: string; required: boolean; placeholder: string }[] = [
    { position: 0, label: 'Second song', required: true, placeholder: 'e.g. September – Earth, Wind & Fire' },
    { position: 1, label: 'Third song', required: false, placeholder: 'e.g. Uptown Funk – Bruno Mars' },
  ];
  return (
    <div className="g-screen">
      <h1 className="g-title">Second &amp; third song</h1>
      <p className="g-lead">
        What follows the opening dance? The second song is when everyone joins you on the
        floor — the third keeps them there.
      </p>
      {slots.map((slot) => {
        const entry = entries.find((item) => item.position === slot.position);
        return (
          <div key={slot.position} className="g-slot">
            <label className="g-label">
              {slot.label}
              <span className={slot.required ? 'g-required' : 'g-optional'}>
                {slot.required ? 'required' : 'optional'}
              </span>
            </label>
            {entry ? (
              <SongCard entry={entry} onRemove={() => store.removeEntry(entry.uid)} />
            ) : (
              <SongSearch
                placeholder={slot.placeholder}
                search={store.search}
                searchAvailable={store.data?.search_available ?? false}
                onPick={(pick) => store.pickSong('second_third', slot.position, pick)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* --------------------------------------------- 4 · their top 20 (mockup 9d) */

export function TopTwentyScreen() {
  const store = useGuest();
  const count = store.listOf('couple_top20').length;
  return (
    <div className="g-screen">
      <h1 className="g-title">Your top 20</h1>
      <p className="g-lead">
        The twenty songs that are simply <em>you</em>. Type straight into any row — order
        them later with the arrows if you care about ranking.
      </p>
      <p className="g-count mono">{count} / 20</p>
      <SongTable kind="couple_top20" rows={20} canAdd canRemove canReorder />
    </div>
  );
}

/* -------------------------------------------------- 5 · reveal (mockup 9e) */

const START_LABELS: Record<StartPref, string> = {
  top: 'from the top',
  chorus: 'from the chorus',
  fade: 'faded in',
};

export function RevealScreen() {
  const store = useGuest();
  const opening = store.listOf('opening_dance')[0];
  const secondThird = store.listOf('second_third');
  const top20 = store.listOf('couple_top20');
  return (
    <div className="g-screen">
      <h1 className="g-title">Here's your soundtrack so far</h1>
      <p className="g-lead">
        Read it back, let it sink in. If something feels off, hop back and change it —
        nothing is locked.
      </p>

      <h2 className="g-subtitle">The opening</h2>
      {opening ? (
        <>
          <RevealRow entry={opening} />
          <p className="reveal-note">
            Played {opening.start_pref ? START_LABELS[opening.start_pref] : 'from the top'}
            {opening.note ? (
              <>
                {' — '}
                <em>“{opening.note}”</em>
              </>
            ) : null}
          </p>
        </>
      ) : (
        <p className="muted">No opening dance picked yet.</p>
      )}

      <h2 className="g-subtitle">Then</h2>
      {secondThird.length ? (
        secondThird.map((entry) => (
          <RevealRow key={entry.uid} entry={entry} prefix={entry.position === 0 ? '2nd' : '3rd'} />
        ))
      ) : (
        <p className="muted">No second song yet.</p>
      )}

      <h2 className="g-subtitle">Your top {top20.length || 20}</h2>
      {top20.length ? (
        <div className="reveal-grid">
          {top20.map((entry, index) => (
            <RevealRow key={entry.uid} entry={entry} prefix={String(index + 1)} />
          ))}
        </div>
      ) : (
        <p className="muted">The top-20 table is still empty.</p>
      )}
    </div>
  );
}

/* ------------------------------------------ 6 · friends' top 20 (mockup 9f) */

export function FriendsScreen() {
  const store = useGuest();
  const link = store.data?.friends_link
    ? `${window.location.origin}${store.data.friends_link}`
    : '';
  // Friends fill this list from their own phones — keep it fresh while open.
  useEffect(() => {
    const timer = window.setInterval(() => void store.refresh(), 5000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const count = store.listOf('friends_top20').length;
  return (
    <div className="g-screen">
      <h1 className="g-title">Your friends' top 20</h1>
      <p className="g-lead">
        One shared link, twenty spots. Send it to whoever should have a say — everyone
        sees the same list grow, and you keep the final word here.
      </p>
      {link && (
        <>
          <label className="g-label">The link to share</label>
          <CopyLink url={link} />
        </>
      )}
      <p className="g-count mono">{count} / 20</p>
      <SongTable kind="friends_top20" rows={20} canAdd canRemove canReorder showSource />
      <p className="hint">
        Friends can add songs and see each other's picks; only you two can remove or
        reorder them.
      </p>
    </div>
  );
}

/* ---------------------------------------------- 7 · never list (mockup 9g) */

export function NeverScreen() {
  const store = useGuest();
  const blocklist = store.data?.blocklist ?? [];
  return (
    <div className="g-screen">
      <h1 className="g-title">The never list</h1>
      <p className="g-lead">
        Songs that must not be played — not even by request, not even the remix. Add as
        many as you like.
      </p>
      <SongSearch
        placeholder="e.g. Macarena – Los Del Rio"
        search={store.search}
        searchAvailable={store.data?.search_available ?? false}
        onPick={(pick) => store.addBlock(pick)}
      />
      <div className="blocklist">
        {blocklist.map((block) => (
          <div key={block.uid} className="songcard blockcard">
            {block.art_url ? (
              <img className="songcard-art" src={block.art_url} alt="" loading="lazy" />
            ) : (
              <span className="songcard-art songcard-art-empty" aria-hidden>
                ♪
              </span>
            )}
            <span className="songcard-text">
              <span className="songcard-title">{block.title}</span>
              <span className="songcard-sub">{block.artist || 'as typed'}</span>
            </span>
            <button
              className="icon-btn songcard-remove"
              aria-label="Allow this song again"
              onClick={() => store.removeBlock(block.uid)}
            >
              ✕
            </button>
          </div>
        ))}
        {!blocklist.length && (
          <p className="muted">Nothing banned yet — lucky DJ.</p>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------- 8 · finale (mockup 9h) */

export function FinaleScreen({ onFinish }: { onFinish: () => void }) {
  const store = useGuest();
  const data = store.data!;
  const links = store.listOf('playlist_links');
  const [url, setUrl] = useState('');

  function addLink() {
    const trimmed = url.trim();
    if (!/^https?:\/\//i.test(trimmed)) return;
    const nextPosition =
      links.reduce((max, item) => Math.max(max, item.position), -1) + 1;
    store.pickSong('playlist_links', nextPosition, { free_text: trimmed });
    setUrl('');
  }

  return (
    <div className="g-screen">
      <h1 className="g-title">The finale</h1>
      <p className="g-lead">Last page — the guarantees, and how your crowd parties.</p>

      <h2 className="g-subtitle">Up to five must-plays</h2>
      <p className="hint">These are promises: they will be played, whatever the night does.</p>
      <SongTable kind="must_plays" rows={5} canAdd canRemove canReorder />

      <h2 className="g-subtitle">How do you party?</h2>
      <textarea
        className="textarea g-textarea"
        placeholder="e.g. Open bar and a loud 90s hip-hop crowd. Grandparents leave around 23:00 — after that, anything goes. No slow songs before midnight."
        value={data.briefing_text ?? ''}
        onChange={(event) => store.patchCouple({ briefing_text: event.target.value })}
      />

      <h2 className="g-subtitle">Playlists we already have</h2>
      <p className="hint">Optional — paste links to Spotify playlists that feel like you.</p>
      <div className="g-linkrow">
        <input
          className="input g-input"
          placeholder="https://open.spotify.com/playlist/…"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') addLink();
          }}
        />
        <button className="btn" disabled={!/^https?:\/\//i.test(url.trim())} onClick={addLink}>
          Add link
        </button>
      </div>
      {links.map((entry) => (
        <div key={entry.uid} className="g-linkitem">
          <a href={entry.free_text ?? '#'} target="_blank" rel="noreferrer">
            {entry.free_text}
          </a>
          <button
            className="icon-btn songcard-remove"
            aria-label="Remove link"
            onClick={() => store.removeEntry(entry.uid)}
          >
            ✕
          </button>
        </div>
      ))}

      <div className="g-finish">
        <button className="btn btn-primary btn-block g-finish-btn" onClick={onFinish}>
          Finish — everything is saved
        </button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- 9 · done */

export function DoneScreen({ onReview }: { onReview: () => void }) {
  const store = useGuest();
  const data = store.data!;
  return (
    <div className="g-screen g-done">
      <div className="g-done-mark" aria-hidden>
        ✓
      </div>
      <h1 className="g-title">That's it — thank you!</h1>
      <p className="g-lead">
        Every answer is saved and already with your DJ. You can come back with this same
        link to change anything until {data.wedding_date || 'the wedding'}.
      </p>
      <button className="btn" onClick={onReview}>
        Review my answers from the start
      </button>
    </div>
  );
}
