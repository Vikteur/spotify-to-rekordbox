// End-to-end check of the wedding intake (node scripts/couple-intake-check.mjs).
// Boots the real FastAPI server with the built client (run `npm run build` first),
// creates a couple over the API, walks the couple wizard and the friends link in
// a real browser, verifies scope rules and autosave persistence, and screenshots
// every screen into .cache/couple-intake. Only the Spotify /search endpoint is
// mocked in the browser (no credentials needed); every save hits the real server.
// The couple is deleted at the end, so the DJ's data stays untouched.
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const PORT = 8123;
const URL = `http://127.0.0.1:${PORT}`;
const OUT = '.cache/couple-intake';
mkdirSync(OUT, { recursive: true });

const api = spawn('python', ['-m', 'uvicorn', 'server.main:app', '--port', String(PORT)], {
  cwd: process.cwd(),
  stdio: 'ignore',
});

async function waitFor(fn, msg, timeout = 25000) {
  const start = Date.now();
  for (;;) {
    try {
      if (await fn()) return;
    } catch {
      /* retry */
    }
    if (Date.now() - start > timeout) throw new Error(`timeout: ${msg}`);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
}

const HITS = [
  { spotify_id: 'sp1', isrc: 'GB1', title: 'Thinking Out Loud', artist: 'Ed Sheeran', duration_ms: 281000, art_url: null },
  { spotify_id: 'sp2', isrc: 'GB2', title: 'September', artist: 'Earth, Wind & Fire', duration_ms: 215000, art_url: null },
  { spotify_id: 'sp3', isrc: 'GB3', title: 'One More Time', artist: 'Daft Punk', duration_ms: 320000, art_url: null },
];

let browser;
let coupleId;
let ok = 0;
let fail = 0;
const check = (condition, label) => {
  if (condition) {
    ok += 1;
    console.log(`ok  ${label}`);
  } else {
    fail += 1;
    console.log(`FAIL ${label}`);
  }
};

try {
  await waitFor(async () => (await fetch(`${URL}/api/health`)).ok, 'server up');

  const future = new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10);
  const created = await (
    await fetch(`${URL}/api/couples`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names: 'Sofie & Jan', wedding_date: future }),
    })
  ).json();
  coupleId = created.id;
  const coupleToken = created.links.couple.token;
  const friendsToken = created.links.friends.token;
  check(coupleToken && friendsToken && coupleToken !== friendsToken, 'couple created with two distinct links');

  for (const channel of ['msedge', 'chrome']) {
    try {
      browser = await chromium.launch({ channel });
      break;
    } catch {
      /* next */
    }
  }
  if (!browser) browser = await chromium.launch();

  const page = await browser.newPage({ viewport: { width: 760, height: 1000 } });
  // Only the search proxy is mocked (no Spotify credentials on CI machines);
  // the guest-state response is patched so the typeahead believes search works.
  const mockSearch = async (target) => {
    await target.route('**/api/guest/*/search*', (route) => {
      const q = new globalThis.URL(route.request().url()).searchParams.get('q')?.toLowerCase() ?? '';
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          results: HITS.filter((hit) => `${hit.title} ${hit.artist}`.toLowerCase().includes(q)),
        }),
      });
    });
    await target.route('**/api/guest/*', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      if (typeof body === 'object' && body !== null && 'search_available' in body) {
        body.search_available = true;
      }
      await route.fulfill({ response, body: JSON.stringify(body) });
    });
  };
  await mockSearch(page);

  // --- 1 welcome -------------------------------------------------------------
  await page.goto(`${URL}/g/${coupleToken}`, { waitUntil: 'networkidle' });
  check(await page.getByText('Welcome!').isVisible(), 'welcome screen renders');
  check((await page.getByLabel('Your names').inputValue()) === 'Sofie & Jan', 'names prefilled from the DJ record');
  await page.screenshot({ path: `${OUT}/1-welcome.png` });
  await page.getByRole('button', { name: 'Begin' }).click();

  // --- 2 opening dance -------------------------------------------------------
  await page.getByPlaceholder(/Thinking Out Loud/).fill('thinking');
  await page.getByRole('option').first().waitFor();
  await page.getByRole('option', { name: /Thinking Out Loud/ }).click();
  await page.getByRole('button', { name: /From the chorus/ }).click();
  await page.getByLabel(/Anything the DJ should know/).fill('Album version please, cut before the last chorus.');
  await page.screenshot({ path: `${OUT}/2-opening.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 3 second & third ------------------------------------------------------
  await page.getByPlaceholder(/September/).fill('september');
  await page.getByRole('option', { name: /September/ }).click();
  await page.screenshot({ path: `${OUT}/3-second-third.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 4 top 20: one search pick + one free-text fallback --------------------
  await page.locator('.songtable .songsearch-input').first().fill('one more');
  await page.getByRole('option', { name: /One More Time/ }).click();
  await page.locator('.songtable .songsearch-input').first().fill('Opa polka medley');
  await page.getByRole('option', { name: /exactly as typed/ }).click();
  await page.screenshot({ path: `${OUT}/4-top20.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 5 reveal --------------------------------------------------------------
  check(await page.getByText("Here's your soundtrack so far").isVisible(), 'reveal screen reads picks back');
  check(await page.getByText('from the chorus').isVisible(), 'reveal shows the start preference');
  await page.screenshot({ path: `${OUT}/5-reveal.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 6 friends (couple view, share link) -----------------------------------
  const shown = await page.locator('.copylink-input').inputValue();
  check(shown.includes(`/g/${friendsToken}`), 'friends share link is shown to the couple');
  await page.screenshot({ path: `${OUT}/6-friends.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 7 never list ----------------------------------------------------------
  await page.getByPlaceholder(/Macarena/).fill('Macarena band version');
  await page.getByRole('option', { name: /exactly as typed/ }).click();
  await page.screenshot({ path: `${OUT}/7-never.png` });
  await page.getByRole('button', { name: 'Next' }).click();

  // --- 8 finale --------------------------------------------------------------
  await page.locator('.songtable .songsearch-input').first().fill('september');
  await page.getByRole('option', { name: /September/ }).click();
  await page.getByPlaceholder(/Open bar/).fill('Loud 90s crowd, no slow songs before midnight.');
  await page.getByPlaceholder(/open\.spotify\.com\/playlist/).fill('https://open.spotify.com/playlist/abc123');
  await page.getByRole('button', { name: 'Add link' }).click();
  await page.screenshot({ path: `${OUT}/8-finale.png` });
  await page.getByText('Saved', { exact: true }).waitFor({ timeout: 10000 });
  await page.getByRole('button', { name: /Finish/ }).click();
  await page.screenshot({ path: `${OUT}/9-done.png` });

  // --- friends link: append-only, sees the shared list -----------------------
  const friendPage = await browser.newPage({ viewport: { width: 480, height: 900 } });
  await mockSearch(friendPage);
  await friendPage.goto(`${URL}/g/${friendsToken}`, { waitUntil: 'networkidle' });
  check(await friendPage.getByText(/Build Sofie & Jan/).isVisible(), 'friends view renders with couple names');
  await friendPage.locator('.songtable .songsearch-input').first().fill('daft');
  await friendPage.getByRole('option', { name: /One More Time/ }).click();
  await friendPage.getByText('Saved', { exact: true }).waitFor({ timeout: 10000 });
  check((await friendPage.locator('.songcard-remove').count()) === 0, 'friends see no remove buttons');
  check((await friendPage.locator('.songcard-move').count()) === 0, 'friends see no reorder buttons');
  await friendPage.screenshot({ path: `${OUT}/10-friend-view.png` });

  // --- server state: everything really persisted -----------------------------
  const detail = await (await fetch(`${URL}/api/couples/${coupleId}`)).json();
  check(detail.lists.opening_dance.length === 1, 'opening dance persisted');
  check(detail.lists.opening_dance[0].start_pref === 'chorus', 'start preference persisted');
  check(detail.lists.opening_dance[0].note?.includes('Album version'), 'opening note persisted');
  check(detail.lists.second_third.length === 1, 'second song persisted');
  check(detail.lists.couple_top20.length === 2, 'top-20 rows persisted');
  check(
    detail.lists.couple_top20.some((entry) => entry.spotify_id === null && entry.free_text),
    'free-text fallback stored as unmatched',
  );
  check(detail.lists.friends_top20.some((entry) => entry.source_token_kind === 'friend'), "friend's pick attributed to the friend link");
  check(detail.lists.must_plays.length === 1, 'must-play persisted');
  check(detail.lists.playlist_links[0]?.free_text === 'https://open.spotify.com/playlist/abc123', 'playlist link persisted');
  check(detail.blocklist.length === 1, 'never-list entry persisted');
  check(detail.briefing_text.includes('90s'), 'briefing persisted');
  check(detail.changes.some((change) => change.token_kind === 'friend'), 'change log shows the friend write');

  // --- DJ panel --------------------------------------------------------------
  const dj = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await dj.goto(URL, { waitUntil: 'networkidle' });
  await dj.getByRole('button', { name: /Sofie & Jan/ }).click();
  await dj.getByText('Magic links').waitFor();
  await dj.screenshot({ path: `${OUT}/11-dj-panel.png` });

  // "Load & match" puts a chapter into the normal match pipeline.
  const topTwentyRow = dj.locator('.list-block', { hasText: 'Their top 20' });
  await topTwentyRow.getByRole('button', { name: 'Load & match' }).click();
  await dj.locator('.nav-item.active', { hasText: 'Their top 20' }).waitFor();
  check(true, 'chapter loads as the active playlist');
  await dj.screenshot({ path: `${OUT}/12-dj-chapter-loaded.png` });

  console.log(`\n${ok} ok, ${fail} failed — screenshots in ${OUT}`);
  process.exitCode = fail ? 1 : 0;
} finally {
  if (coupleId != null) {
    await fetch(`${URL}/api/couples/${coupleId}`, { method: 'DELETE' }).catch(() => undefined);
  }
  await browser?.close();
  api.kill();
}
