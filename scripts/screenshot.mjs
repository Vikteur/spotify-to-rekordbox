// Drives the running app headlessly and saves a full-page screenshot.
// Usage: node scripts/screenshot.mjs <music-folder> [out.png]
// Requires the app on http://127.0.0.1:8000 (npm run build && npm start).
import { chromium } from 'playwright-core';

const MUSIC = process.argv[2];
const OUT = process.argv[3] ?? 'docs/screenshot.png';
if (!MUSIC) {
  console.error('usage: node scripts/screenshot.mjs <music-folder> [out.png]');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
await page.goto(process.env.APP_URL ?? 'http://127.0.0.1:8000/');

// Only scan when the saved library is empty — normally it is restored from the database.
if (await page.getByText('Nothing loaded yet').isVisible().catch(() => false)) {
  await page.getByPlaceholder(/Music/).fill(MUSIC);
  await page.getByRole('button', { name: 'Scan folder' }).click();
}
await page.getByText(/tracks<\/span> saved|tracks saved/).waitFor({ timeout: 60000 });

await page.getByText('Or paste the tracklist as text', { exact: false }).click();
await page.locator('textarea').fill(
  [
    'Étienne de Crécy - Am I Wrong',
    'Some DJ - Only On External Drive',
    'deadmau5 - Strobe',
    'Ghost Artist - Not In My Library',
  ].join('\n'),
);
await page.getByRole('button', { name: 'Use pasted list' }).click();

await page.getByRole('button', { name: 'Match against library' }).click();
await page.getByText(/auto ·/).waitFor({ timeout: 60000 });
await page.waitForTimeout(300);

await page.screenshot({ path: OUT, fullPage: true });
await browser.close();
console.log('saved', OUT);
