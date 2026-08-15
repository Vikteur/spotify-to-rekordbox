// Clicks the "Download missing .txt" button in a real browser and prints the
// file the user would actually get.
// Usage: node scripts/missing-download-check.mjs <music-folder>
import { chromium } from 'playwright-core';
import { readFile } from 'node:fs/promises';

const MUSIC = process.argv[2];
if (!MUSIC) {
  console.error('usage: node scripts/missing-download-check.mjs <music-folder>');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const page = await browser.newPage({ acceptDownloads: true });
await page.goto(process.env.APP_URL ?? 'http://127.0.0.1:8000/');

if (await page.getByText('Nothing loaded yet').isVisible().catch(() => false)) {
  await page.getByPlaceholder(/Music/).fill(MUSIC);
  await page.getByRole('button', { name: 'Scan folder' }).click();
}
await page.getByText(/tracks saved/).waitFor({ timeout: 60000 });

await page.locator('details:has(textarea)').evaluate((node) => {
  node.open = true;
});
await page.locator('textarea').fill(
  [
    'Étienne de Crécy - Am I Wrong',      // present
    'Ghost Artist - Not In My Library',   // absent
    'Another Ghost - Also Missing',       // absent
    'Artist One - Anthem',                // present, several versions
  ].join('\n'),
);
await page.getByRole('button', { name: 'Use pasted list' }).click();
await page.getByRole('button', { name: 'Match against library' }).click();
await page.getByText(/auto ·/).waitFor({ timeout: 60000 });

await page.locator('input[placeholder="Playlist name"]').fill('Friday Warmup');
const [download] = await Promise.all([
  page.waitForEvent('download'),
  page.getByRole('button', { name: 'Download missing .txt' }).click(),
]);
console.log('filename:', download.suggestedFilename());
console.log('--- file contents ---');
console.log(await readFile(await download.path(), 'utf-8'));

await browser.close();
