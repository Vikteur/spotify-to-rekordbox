// One-off visual check for the discoverability rework (node tests/screenshot-ui.mjs).
// Boots vite with the API mocked (same shapes as e2e-matches.mjs) and captures:
//   1. fresh app  — sidebar quick actions + playlist empty state
//   2. the "Import library" panel opened from the new sidebar button
//   3. matched table — labeled section buttons, export dock note, honest footer
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright-core';

const PORT = 5198;
const URL = `http://localhost:${PORT}`;
const OUT = '.cache/ui-verify';
mkdirSync(OUT, { recursive: true });

const track = (id, filename, ext, bpm, key, dur) => ({
  id, path: `C:/Music/${filename}.${ext}`, filename, ext,
  artist: '', title: '', album: null, duration_sec: dur, bitrate_kbps: 320,
  tag_source: 'tags', size_bytes: 0, mtime_ms: 0, bpm, musical_key: key,
});
const cand = (t, score, descriptors = []) => ({
  track: t, score, parts: {}, version: { descriptors, remixer: null },
  duration_delta_sec: 0, playlists: [],
});
const row = (index, artist, title, dur, bucket, candidates, auto) => ({
  input: { index, artist, title, duration_sec: dur },
  input_version: { descriptors: [], remixer: null },
  bucket, candidates, auto_selected_id: auto, from_preference: false,
});
const results = [
  row(0, 'Roosevelt', 'Sign', 244, 'auto', [cand(track('t0', 'sign', 'flac', 118, '7B', 244), 0.98)], 't0'),
  row(1, 'Purple Disco Machine', 'Substitution', 204, 'ambiguous', [
    cand(track('t1a', 'Substitution (Extended Mix)', 'mp3', 121, '4A', 256), 0.93, ['Extended', 'Mix']),
    cand(track('t1b', 'Substitution (Radio Edit)', 'mp3', 121, '4A', 193), 0.84, ['Radio', 'Edit']),
  ], null),
  row(2, 'No Match', 'Zero Cand', 100, 'unmatched', [], null),
];
const library = {
  active_library_id: 1, active_library_name: 'Studio PC', track_count: 14203,
  by_ext: { mp3: 9000, flac: 5203 },
  libraries: [{ id: 1, name: 'Studio PC', created_at: '', track_count: 14203, source_count: 1 }],
  sources: [{ id: 1, kind: 'folder', label: 'C:/Music', track_count: 14203 }],
};
const spotify = {
  name: 'Test Warmup', owner_name: null, total: 3, truncated: false,
  tracks: results.map((r) => ({ index: r.input.index, artist: r.input.artist, title: r.input.title, duration_sec: r.input.duration_sec })),
};

const vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--port', String(PORT), '--strictPort'], {
  cwd: process.cwd(), stdio: 'ignore',
});
async function waitFor(fn, msg, timeout = 20000) {
  const start = Date.now();
  for (;;) {
    try { if (await fn()) return; } catch { /* retry */ }
    if (Date.now() - start > timeout) throw new Error(`timeout: ${msg}`);
    await new Promise((r) => setTimeout(r, 150));
  }
}

let browser;
try {
  await waitFor(async () => (await fetch(URL)).ok, 'vite up');
  for (const channel of ['msedge', 'chrome']) {
    try { browser = await chromium.launch({ channel }); break; } catch { /* next */ }
  }
  if (!browser) browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const json = (obj) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(obj) });
  await page.route('**/api/**', (route) => {
    const url = route.request().url();
    if (url.endsWith('/api/preferences')) return route.fulfill(json({ preferences: [] }));
    if (url.includes('/api/couples')) return route.fulfill(json({ couples: [] }));
    if (url.includes('/api/library/playlists')) return route.fulfill(json({ playlists: [] }));
    if (url.includes('/api/library')) return route.fulfill(json(library));
    if (url.includes('/api/scan/status')) return route.fulfill(json({ state: 'idle' }));
    if (url.includes('/api/spotify/playlist')) return route.fulfill(json(spotify));
    if (url.includes('/api/match')) return route.fulfill(json({ results, library_size: 14203, library_name: 'Studio PC' }));
    return route.fulfill(json({}));
  });

  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForSelector('.sidebar');
  await page.screenshot({ path: `${OUT}/1-fresh.png` });

  await page.getByRole('button', { name: 'Import library' }).first().click();
  await page.waitForSelector('.panel');
  await page.screenshot({ path: `${OUT}/2-import-panel.png` });
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'Add playlist', exact: true }).click();
  await page.getByPlaceholder(/open\.spotify/).fill('https://open.spotify.com/playlist/x');
  await page.getByRole('button', { name: 'Fetch' }).click();
  await page.getByRole('button', { name: /Done/ }).click();
  await page.getByRole('button', { name: 'Match against library' }).click();
  await page.waitForSelector('.track-row');

  // Ctrl+F must focus the filter input now that the chip advertises it.
  await page.keyboard.press('Control+f');
  const focused = await page.evaluate(() => document.activeElement?.getAttribute('aria-label'));
  console.log(focused === 'Filter tracks' ? 'ok  Ctrl+F focuses the filter' : `FAIL Ctrl+F focus — got ${focused}`);
  await page.screenshot({ path: `${OUT}/3-matched.png` });
  console.log(`screenshots in ${OUT}`);
} finally {
  await browser?.close();
  vite.kill();
}
