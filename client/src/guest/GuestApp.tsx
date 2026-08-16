import { useEffect, useState } from 'react';
import { SaveChip, SongTable } from './parts';
import {
  DoneScreen,
  FinaleScreen,
  FriendsScreen,
  NeverScreen,
  OpeningScreen,
  RevealScreen,
  SecondThirdScreen,
  TopTwentyScreen,
  WelcomeScreen,
} from './screens';
import { GuestProvider, useGuest, type LinkProblem } from './store';

/** The couple's eight pages, in the order they meet them (mockups 9a–9h). */
const STEPS = [
  'Welcome',
  'Opening dance',
  'Second & third',
  'Your top 20',
  'The reveal',
  "Friends' top 20",
  'Never list',
  'Finale',
];
const DONE_STEP = STEPS.length;

function GuestLogo() {
  return (
    <span className="g-brand">
      <span className="logo-mark" aria-hidden>
        <span style={{ height: 7 }} />
        <span style={{ height: 12 }} />
        <span style={{ height: 5 }} />
        <span style={{ height: 9, opacity: 0.72 }} />
      </span>
      <span className="g-brand-name">Rekord Match</span>
    </span>
  );
}

function ProblemView({ problem }: { problem: LinkProblem }) {
  const title =
    problem.code === 'LINK_EXPIRED'
      ? 'This link has retired'
      : problem.code === 'LINK_REVOKED'
        ? 'This link is switched off'
        : problem.code === 'OFFLINE'
          ? "Can't reach the server"
          : "This link doesn't work";
  return (
    <div className="guest-shell">
      <header className="g-head">
        <GuestLogo />
      </header>
      <main className="g-main">
        <div className="g-card g-problem">
          <h1 className="g-title">{title}</h1>
          <p className="g-lead">{problem.message}</p>
        </div>
      </main>
    </div>
  );
}

/** What a friend sees through the shared link: just the friends' top 20. */
function FriendsView() {
  const store = useGuest();
  const data = store.data!;
  // Other friends type at the same time — keep the shared table live.
  useEffect(() => {
    const timer = window.setInterval(() => void store.refresh(), 5000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const count = store.listOf('friends_top20').length;
  return (
    <div className="guest-shell">
      <header className="g-head">
        <GuestLogo />
        <SaveChip />
      </header>
      <main className="g-main">
        <div className="g-card">
          <div className="g-screen">
            <h1 className="g-title">Build {data.names || 'the couple'}'s party</h1>
            <p className="g-lead">
              You and the other friends share twenty spots for the wedding
              {data.wedding_date ? ` on ${data.wedding_date}` : ''}. Type a song into any
              free row — everyone sees the list grow, and every pick is saved instantly.
            </p>
            <p className="g-count mono">{count} / 20</p>
            {count >= 20 && (
              <p className="g-full">All twenty spots are taken — the list is complete! 🎉</p>
            )}
            <SongTable
              kind="friends_top20"
              rows={20}
              canAdd
              canRemove={false}
              canReorder={false}
              showSource
            />
            <p className="hint">
              Songs from the other friends appear here automatically. Picks can't be
              removed or reshuffled from this link — the couple curates the final list.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

function CoupleWizard({ token }: { token: string }) {
  const store = useGuest();
  const data = store.data!;
  const storageKey = `rm-guest-step:${token.slice(0, 12)}`;
  const [step, setStep] = useState(() => {
    const saved = Number(window.localStorage.getItem(storageKey));
    return Number.isInteger(saved) && saved >= 0 && saved <= DONE_STEP ? saved : 0;
  });
  useEffect(() => {
    window.localStorage.setItem(storageKey, String(step));
    window.scrollTo({ top: 0 });
  }, [step, storageKey]);

  /** What still blocks "Next" on this step, if anything. */
  function blockedHint(): string | null {
    if (step === 0) {
      if (!data.names.trim()) return 'Fill in your names to begin.';
      if (!data.wedding_date) return 'Pick your wedding date to begin.';
    }
    if (step === 1 && store.listOf('opening_dance').length === 0) {
      return 'Choose your opening dance to continue.';
    }
    if (step === 2 && !store.listOf('second_third').some((entry) => entry.position === 0)) {
      return 'The second song is the one required pick here.';
    }
    return null;
  }
  const hint = blockedHint();

  const screen = [
    <WelcomeScreen key="welcome" />,
    <OpeningScreen key="opening" />,
    <SecondThirdScreen key="secondthird" />,
    <TopTwentyScreen key="top20" />,
    <RevealScreen key="reveal" />,
    <FriendsScreen key="friends" />,
    <NeverScreen key="never" />,
    <FinaleScreen key="finale" onFinish={() => setStep(DONE_STEP)} />,
    <DoneScreen key="done" onReview={() => setStep(0)} />,
  ][step];

  return (
    <div className="guest-shell">
      <header className="g-head">
        <GuestLogo />
        <span className="g-head-names">{data.names}</span>
        <SaveChip />
      </header>
      <main className="g-main">
        {step < DONE_STEP && (
          <nav className="g-progress" aria-label="Steps">
            {STEPS.map((label, index) => (
              <button
                key={label}
                className={`g-dot ${index === step ? 'active' : ''} ${index < step ? 'seen' : ''}`}
                title={label}
                aria-label={`${label} (step ${index + 1} of ${STEPS.length})`}
                onClick={() => setStep(index)}
              />
            ))}
            <span className="g-progress-label">
              {step + 1} / {STEPS.length} · {STEPS[step]}
            </span>
          </nav>
        )}
        <div className="g-card">{screen}</div>
        {step < DONE_STEP && (
          <footer className="g-nav">
            <button
              className="btn g-back"
              disabled={step === 0}
              onClick={() => setStep((current) => Math.max(0, current - 1))}
            >
              Back
            </button>
            <span className="g-nav-hint">{hint ?? ''}</span>
            {step < STEPS.length - 1 && (
              <button
                className="btn btn-primary g-next"
                disabled={hint !== null}
                onClick={() => setStep((current) => current + 1)}
              >
                {step === 0 ? 'Begin' : 'Next'}
              </button>
            )}
          </footer>
        )}
      </main>
    </div>
  );
}

function GuestInner({ token }: { token: string }) {
  const store = useGuest();
  if (store.problem) return <ProblemView problem={store.problem} />;
  if (!store.data) {
    return (
      <div className="guest-shell">
        <header className="g-head">
          <GuestLogo />
        </header>
        <main className="g-main">
          <div className="g-card g-problem">
            <p className="g-lead">Loading…</p>
          </div>
        </main>
      </div>
    );
  }
  return store.data.scope === 'friends' ? <FriendsView /> : <CoupleWizard token={token} />;
}

/** Everything behind a magic link (`/g/<token>`) — couple wizard or friends view. */
export function GuestApp({ token }: { token: string }) {
  return (
    <GuestProvider token={token}>
      <GuestInner token={token} />
    </GuestProvider>
  );
}
