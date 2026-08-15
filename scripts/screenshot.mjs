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
await page.goto('http://127.0.0.1:8000/');

await page.getByPlaceholder(/Music/).fill(MUSIC);
await page.getByRole('button', { name: 'Scan', exact: true }).click();
await page.getByText(/tracks.*from cache/).waitFor({ timeout: 30000 });

await page.getByText('Or paste the tracklist as text', { exact: false }).click();
await page.locator('textarea').fill(
  [
    'Étienne de Crécy - Am I Wrong',
    'Purple Disco Machine - Substitution',
    'Ghost Artist - Not In My Library',
    'Artist X - Some Song',
  ].join('\n'),
);
await page.getByRole('button', { name: 'Use pasted list' }).click();

await page.getByRole('button', { name: 'Match against library' }).click();
await page.getByText(/auto ·/).waitFor({ timeout: 30000 });
await page.waitForTimeout(300);

await page.screenshot({ path: OUT, fullPage: true });
await browser.close();
console.log('saved', OUT);
