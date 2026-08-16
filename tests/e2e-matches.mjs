// End-to-end tests for the match-table pick/undo flow (run: npm run test:e2e).
//
// Covers the "browsing must not commit" bug and its edge cases:
//   1. expanding a row never commits, top candidate is only pre-ringed
//   2. clicking candidates moves the ring but commits nothing
//   3. Use once commits without saving a preference; row leaves "Needs you"
//   4. Undo pick restores the unresolved state
//   5. Use & remember saves a preference; Undo removes it again
//   6. keyboard: 1-9 ring, Enter commits, Esc collapses; inert inside inputs
//   7. S skips, row dims; Undo skip restores
//   8. show-more list; a deep committed pick is always kept visible
//   9. auto rows: manual override then Undo returns to AUTO
//  10. rows remembered on the server show no Undo; override+Undo restores them
//  11. not-found rows with weak candidates are pickable; no-candidate rows inert
//  12. re-match while a row is expanded resets cleanly (no stale draft, no crash)
//
// Serves the real client via its own vite on :5199 with the whole API mocked.
import { spawn } from 'node:child_process';
import { chromium } from 'playwright-core';

const PORT = 5199;
const URL = `http://localhost:${PORT}`;

// ---------------------------------------------------------------- mock data
const track = (id, filename, ext, bpm, key, dur) => ({
  id, path: `C:/Music/${filename}.${ext}`, filename, ext,
  artist: '', title: '', album: null, duration_sec: dur, bitrate_kbps: 320,
  tag_source: 'tags', size_bytes: 0, mtime_ms: 0, bpm, musical_key: key,
});
const cand = (t, score, descriptors = [], playlists = []) => ({
  track: t, score, parts: {}, version: { descriptors, remixer: null },
  duration_delta_sec: 0, playlists,
});
const row = (index, artist, title, dur, bucket, candidates, auto, from_pref = false) => ({
  input: { index, artist, title, duration_sec: dur },
  input_version: { descriptors: [], remixer: null },
  bucket, candidates, auto_selected_id: auto, from_preference: from_pref,
});

const results = [
  row(0, 'Roosevelt', 'Sign', 244, 'auto', [cand(track('t0', 'sign', 'flac', 118, '7B', 244), 0.98)], 't0'),
  row(1, 'Purple Disco Machine', 'Substitution', 204, 'ambiguous', [
    cand(track('t1a', 'Substitution (Extended Mix)', 'mp3', 121, '4A', 256), 0.93, ['Extended', 'Mix']),
    cand(track('t1b', 'Substitution (Radio Edit)', 'mp3', 121, '4A', 193), 0.84, ['Radio', 'Edit']),
    cand(track('t1c', 'substitution_dub', 'wav', 121, '4A', 328), 0.62, ['Dub']),
    cand(track('t1d', 'Substitution (Claptone Remix)', 'mp3', 118, '6A', 401), 0.48, ['Claptone', 'Remix']),
    cand(track('t1e', 'substitution_bootleg', 'mp3', 121, '4A', 300), 0.31, ['Bootleg']),
  ], null),
  row(2, 'deadmau5', 'Strobe', 637, 'auto', [
    cand(track('t2a', 'Strobe (Original Mix)', 'aiff', 128, '5A', 637), 0.99),
    cand(track('t2b', 'strobe_club', 'mp3', 128, '5A', 420), 0.7, ['Club', 'Mix']),
  ], 't2a'),
  row(3, 'Fred again..', 'Delilah (pull me out of this)', 212, 'auto', [
    cand(track('t3a', 'delilah_extended', 'flac', 132, '11A', 212), 0.88, ['Extended']),
    cand(track('t3b', 'delilah_original', 'flac', 132, '11A', 190), 0.8),
  ], 't3a', true),
  row(4, 'Some DJ', 'Only On External Drive', 362, 'unmatched', [
    cand(track('t4a', 'maybe_this_one', 'mp3', 122, '2A', 350), 0.31),
  ], null),
  row(5, 'No Match', 'Zero Cand', 100, 'unmatched', [], null),
];

const library = {
  active_library_id: 1, active_library_name: 'MacBook Pro', track_count: 14203,
  by_ext: { mp3: 9000 },
  libraries: [{ id: 1, name: 'MacBook Pro', created_at: '', track_count: 14203, source_count: 1 }],
  sources: [],
};
const spotify = {
  name: 'Test Warmup', owner_name: null, total: 6, truncated: false,
  tracks: results.map((r) => ({ index: r.input.index, artist: r.input.artist, title: r.input.title, duration_sec: r.input.duration_sec })),
};

// Stateful preferences mock + call log.
let prefSeq = 0;
let prefs = [{ id: 'p0', artist: 'Fred again..', title: 'Delilah (pull me out of this)', track_id: 't3a', chosen_at: '', file_label: 'delilah_extended.flac' }];
const prefPosts = [];
const prefDeletes = [];

// ------------------------------------------------------------------ helpers
let failures = 0;
let passes = 0;
function assert(condition, name, detail = '') {
  if (condition) {
    passes += 1;
    console.log(`  ok  ${name}`);
  } else {
    failures += 1;
    console.log(`FAIL  ${name}${detail ? ` — ${detail}` : ''}`);
  }
}
function assertEq(actual, expected, name) {
  assert(actual === expected, name, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}
async function waitFor(fn, msg, timeout = 4000) {
  const start = Date.now();
  let last;
  for (;;) {
    try {
      last = await fn();
      if (last) return last;
    } catch (error) {
      last = error?.message;
    }
    if (Date.now() - start > timeout) throw new Error(`timeout: ${msg} (last: ${last})`);
    await new Promise((r) => setTimeout(r, 100));
  }
}

// --------------------------------------------------------------- vite + page
const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--port', String(PORT), '--strictPort'], {
  cwd: process.cwd(),
  stdio: 'ignore',
});
async function launch() {
  for (const channel of ['msedge', 'chrome']) {
    try { return await chromium.launch({ channel }); } catch { /* next */ }
  }
  return chromium.launch();
}

let browser;
try {
  await waitFor(async () => (await fetch(URL)).ok, 'vite dev server up', 20000);
  browser = await launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));

  const json = (obj) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(obj) });
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const url = req.url();
    const method = req.method();
    if (/\/api\/preferences\/[^/]+$/.test(url) && method === 'DELETE') {
      const id = url.split('/').pop();
      prefDeletes.push(id);
      prefs = prefs.filter((p) => p.id !== id);
      return route.fulfill(json({ preferences: prefs }));
    }
    if (url.endsWith('/api/preferences') && method === 'POST') {
      const body = req.postDataJSON();
      prefPosts.push(body);
      prefSeq += 1;
      prefs = prefs.filter((p) => !(p.artist === body.artist && p.title === body.title));
      prefs.push({ id: `p${prefSeq}`, artist: body.artist, title: body.title, track_id: body.track_id, chosen_at: '', file_label: 'x.mp3' });
      return route.fulfill(json({ preferences: prefs }));
    }
    if (url.endsWith('/api/preferences') && method === 'DELETE') {
      prefs = [];
      return route.fulfill(json({ preferences: prefs }));
    }
    if (url.endsWith('/api/preferences')) return route.fulfill(json({ preferences: prefs }));
    if (url.includes('/api/couples')) return route.fulfill(json({ couples: [] }));
    if (url.includes('/api/library/playlists')) return route.fulfill(json({ playlists: [] }));
    if (url.includes('/api/library')) return route.fulfill(json(library));
    if (url.includes('/api/scan/status')) return route.fulfill(json({ state: 'idle' }));
    if (url.includes('/api/spotify/playlist')) return route.fulfill(json(spotify));
    if (url.includes('/api/match')) return route.fulfill(json({ results, library_size: 14203, library_name: 'MacBook Pro' }));
    return route.fulfill(json({}));
  });

  const SUB = 'Purple Disco Machine – Substitution';
  const STROBE = 'deadmau5 – Strobe';
  const DELILAH = 'Fred again.. – Delilah (pull me out of this)';
  const EXT = 'Some DJ – Only On External Drive';
  const ZERO = 'No Match – Zero Cand';

  const rowOf = (title) => page.locator('.track-row', { hasText: title });
  const wrapOf = (title) => page.locator('.track-row-wrap', { hasText: title });
  const badgeOf = async (title) => (await rowOf(title).locator('.badge').innerText()).trim();
  const expandedCount = () => page.locator('.expanded-body').count();
  const ringVersion = () => page.locator('.cand.selected .cand-version').innerText();
  const expand = async (title) => {
    await rowOf(title).click();
    await waitFor(async () => (await expandedCount()) === 1, `expanded ${title}`);
  };
  const collapse = async (title) => {
    await rowOf(title).click();
    await waitFor(async () => (await expandedCount()) === 0, `collapsed ${title}`);
  };

  // --- S0 boot: load playlist and match --------------------------------------
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForSelector('.sidebar');
  await page.getByRole('button', { name: 'Add a playlist', exact: true }).click();
  await page.getByPlaceholder(/open\.spotify/).fill('https://open.spotify.com/playlist/x');
  await page.getByRole('button', { name: 'Fetch' }).click();
  await page.getByRole('button', { name: /Done/ }).click();
  await page.getByRole('button', { name: 'Match against library' }).click();
  await page.waitForSelector('.track-row');

  console.log('\n1. expanding never commits');
  assertEq(await badgeOf(SUB), 'PICK ONE', 'starts as PICK ONE');
  await expand(SUB);
  assertEq(await badgeOf(SUB), 'PICK ONE', 'still PICK ONE after expanding');
  assertEq(prefPosts.length, 0, 'no preference saved by expanding');
  assertEq(await ringVersion(), 'Extended Mix', 'best candidate pre-ringed only');
  assertEq((await rowOf(SUB).locator('.conf-pct').innerText()).trim(), '93%', 'header % unchanged');

  console.log('\n2. clicking candidates only moves the ring');
  await page.locator('.cand', { hasText: 'Radio Edit' }).click();
  assertEq(await ringVersion(), 'Radio Edit', 'ring moved');
  assertEq(await badgeOf(SUB), 'PICK ONE', 'still uncommitted');
  assertEq(prefPosts.length, 0, 'still no preference saved');

  console.log('\n3. Use once commits without remembering');
  await page.getByRole('button', { name: 'Use once' }).click();
  await waitFor(async () => (await expandedCount()) === 0, 'row collapsed after commit');
  assertEq(await badgeOf(SUB), 'YOUR PICK', 'badge YOUR PICK');
  assertEq(prefPosts.length, 0, 'no preference saved by Use once');
  assert((await rowOf(SUB).locator('.track-sub').innerText()).includes('Radio Edit'), 'subtitle shows chosen file');
  assert((await page.locator('.segment', { hasText: 'Needs you' }).innerText()).includes('0'), 'Needs-you count is 0');
  await page.locator('.segment', { hasText: 'Needs you' }).click();
  assertEq(await page.locator('.table-empty').count(), 1, 'row left the Needs-you tab');
  await page.locator('.segment', { hasText: 'All' }).click();

  console.log('\n4. Undo pick restores the unresolved state');
  await expand(SUB);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'badge back to PICK ONE');
  assert((await page.locator('.segment', { hasText: 'Needs you' }).innerText()).includes('1'), 'Needs-you count back to 1');
  assertEq(await ringVersion(), 'Extended Mix', 'ring reset to best');
  assertEq(await page.getByRole('button', { name: 'Undo pick' }).count(), 0, 'Undo hidden once back at preset');
  assertEq(await expandedCount(), 1, 'undo keeps the row open');
  await collapse(SUB);

  console.log('\n5. Use & remember saves, Undo forgets again');
  await expand(SUB);
  await page.getByRole('button', { name: 'Use & remember' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'REMEMBERED', 'badge REMEMBERED');
  assertEq(prefPosts.length, 1, 'preference POSTed once');
  assertEq(await expandedCount(), 0, 'collapsed after commit');
  await expand(SUB);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'badge back to PICK ONE');
  assertEq(prefDeletes.length, 1, 'preference DELETEd on undo');
  await collapse(SUB);

  console.log('\n6. keyboard: 1-9 ring, Enter commits, Esc collapses, inputs guarded');
  await expand(SUB);
  await page.keyboard.press('2');
  assertEq(await ringVersion(), 'Radio Edit', '"2" rings the 2nd candidate');
  await page.keyboard.press('Enter');
  await waitFor(async () => (await badgeOf(SUB)) === 'REMEMBERED', 'Enter = use & remember');
  assertEq(prefPosts.length, 2, 'Enter POSTed a preference');
  assertEq(await expandedCount(), 0, 'Enter collapsed the row');
  await expand(SUB);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'undo after Enter');
  assertEq(prefDeletes.length, 2, 'preference DELETEd again');
  await page.keyboard.press('Escape');
  await waitFor(async () => (await expandedCount()) === 0, 'Esc collapses');
  await expand(SUB);
  await page.locator('.filter-input input').click();
  await page.keyboard.type('s');
  assertEq(await badgeOf(SUB), 'PICK ONE', 'typing "s" in filter does not skip');
  await page.keyboard.press('Escape');
  assertEq(await expandedCount(), 1, 'Esc inside an input is ignored');
  await page.locator('.filter-input input').fill('');
  await collapse(SUB);

  console.log('\n7. S skips, Undo skip restores');
  await expand(SUB);
  await page.keyboard.press('s');
  await waitFor(async () => (await badgeOf(SUB)) === 'SKIPPED', 'badge SKIPPED');
  assertEq(await expandedCount(), 0, 'collapsed after skip');
  assert((await wrapOf(SUB).getAttribute('class')).includes('dim'), 'skipped row is dimmed');
  await expand(SUB);
  await page.getByRole('button', { name: 'Undo skip' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'skip undone');
  await collapse(SUB);

  console.log('\n8. show-more; a deep pick stays visible on reopen');
  await expand(SUB);
  assertEq(await page.locator('.cand').count(), 3, 'top 3 shown by default');
  await page.locator('.show-more', { hasText: 'more version' }).click();
  assertEq(await page.locator('.cand').count(), 5, 'all 5 after show more');
  await page.locator('.cand', { hasText: 'Bootleg' }).click();
  await page.getByRole('button', { name: 'Use once' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'YOUR PICK', 'deep pick committed');
  await expand(SUB);
  assertEq(await page.locator('.cand').count(), 5, 'reopen keeps the picked version visible');
  assertEq(await ringVersion(), 'Bootleg', 'ring on the deep pick');
  assertEq(await page.locator('.show-more', { hasText: 'Show fewer' }).count(), 0, 'no "Show fewer" while pick is deep');
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'deep pick undone');
  await collapse(SUB);

  console.log('\n9. auto row: override then Undo returns to AUTO');
  assertEq(await badgeOf(STROBE), 'AUTO', 'starts AUTO');
  await expand(STROBE);
  assertEq(await ringVersion(), 'Original', 'auto pick ringed');
  await page.locator('.cand', { hasText: 'Club Mix' }).click();
  await page.getByRole('button', { name: 'Use once' }).click();
  await waitFor(async () => (await badgeOf(STROBE)) === 'YOUR PICK', 'override committed');
  await expand(STROBE);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(STROBE)) === 'AUTO', 'back to AUTO');
  await collapse(STROBE);

  console.log('\n10. server-remembered row: no Undo, override+Undo restores');
  assertEq(await badgeOf(DELILAH), 'REMEMBERED', 'starts REMEMBERED (server pref)');
  await expand(DELILAH);
  assertEq(await page.getByRole('button', { name: 'Undo pick' }).count(), 0, 'no Undo at preset');
  await page.locator('.cand', { hasText: 'delilah_original' }).click();
  await page.getByRole('button', { name: 'Use once' }).click();
  await waitFor(async () => (await badgeOf(DELILAH)) === 'YOUR PICK', 'override committed');
  const deletesBefore = prefDeletes.length;
  await expand(DELILAH);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(DELILAH)) === 'REMEMBERED', 'restored to REMEMBERED');
  assertEq(prefDeletes.length, deletesBefore, 'server preference untouched by undo');
  await collapse(DELILAH);

  console.log('\n11. not-found rows: weak candidates pickable, zero-candidate inert');
  assertEq(await badgeOf(EXT), 'NOT FOUND', 'weak row starts NOT FOUND');
  await expand(EXT);
  await page.locator('.cand', { hasText: 'maybe_this_one' }).click();
  await page.getByRole('button', { name: 'Use once' }).click();
  await waitFor(async () => (await badgeOf(EXT)) === 'YOUR PICK', 'weak candidate usable');
  await expand(EXT);
  await page.getByRole('button', { name: 'Undo pick' }).click();
  await waitFor(async () => (await badgeOf(EXT)) === 'NOT FOUND', 'undo restores NOT FOUND');
  await collapse(EXT);
  assertEq(await badgeOf(ZERO), 'NOT FOUND', 'zero-candidate row NOT FOUND');
  assertEq((await rowOf(ZERO).locator('.conf-dash').innerText()).trim(), '—', 'no confidence shown');
  await rowOf(ZERO).click();
  assertEq(await expandedCount(), 0, 'zero-candidate row does not expand');

  console.log('\n12. re-match with a row expanded resets cleanly');
  await expand(SUB);
  await page.getByRole('button', { name: 'Re-match' }).click();
  await waitFor(async () => (await badgeOf(SUB)) === 'PICK ONE', 'selections reset');
  assertEq(await badgeOf(STROBE), 'AUTO', 'auto rows reset');
  assertEq(await expandedCount(), 1, 'expanded row survives re-match');
  assert((await page.locator('.cand.selected').count()) === 1, 'draft ring still valid after re-match');

  assertEq(pageErrors.length, 0, `no page errors (${pageErrors.join('; ')})`);

  console.log(`\n${passes} passed, ${failures} failed`);
} catch (error) {
  failures += 1;
  console.error('\nABORTED:', error);
} finally {
  await browser?.close().catch(() => undefined);
  vite.kill();
}
process.exit(failures ? 1 : 0);
