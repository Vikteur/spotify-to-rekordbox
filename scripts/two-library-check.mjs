// Exercises named libraries in a real browser:
// create two libraries, scan a folder into each, prove matching and remembered
// versions are scoped to the selected one.
// Usage: node scripts/two-library-check.mjs <macbook-folder> <studio-folder>
import { chromium } from 'playwright-core';

const [MAC, STUDIO] = process.argv.slice(2);
if (!MAC || !STUDIO) {
  console.error('usage: node scripts/two-library-check.mjs <folder-a> <folder-b>');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
const url = process.env.APP_URL ?? 'http://127.0.0.1:8000/';
await page.goto(url);

async function createLibrary(name, folder) {
  await page.getByPlaceholder('New library name, e.g. Studio PC').fill(name);
  await page.getByRole('button', { name: '+ Create library' }).click();
  await page.getByText(`is empty`).waitFor({ timeout: 20000 });
  await page.getByPlaceholder(/Music/).fill(folder);
  await page.getByRole('button', { name: 'Scan folder' }).click();
  await page.getByText(/tracks saved/).waitFor({ timeout: 30000 });
  console.log(`created "${name}" and scanned ${folder.split('/').pop()}`);
}

async function match(lines) {
  // Open the paste panel idempotently — clicking a <details> summary toggles it.
  await page.locator('details:has(textarea)').evaluate((node) => {
    node.open = true;
  });
  await page.locator('textarea').fill(lines);
  await page.getByRole('button', { name: 'Use pasted list' }).click();
  await page.getByRole('button', { name: 'Match against library' }).click();
  await page.getByText(/auto ·/).waitFor({ timeout: 30000 });
  await page.waitForTimeout(250);
}

const rows = async () => {
  const out = [];
  for (const row of await page.locator('table tbody tr').all()) {
    const chip = (await row.locator('span').filter({
      hasText: /^(auto|remembered|manual|pick one|skipped|no match)$/,
    }).first().textContent())?.trim();
    const selected = await row.locator('select option:checked').first().textContent().catch(() => null);
    out.push(`${chip} → ${selected?.split(' —')[0] ?? '—'}`);
  }
  return out;
};

const selectLibrary = async (name) => {
  const value = await page
    .locator('#library-picker option', { hasText: name })
    .first()
    .getAttribute('value');
  await page.locator('#library-picker').selectOption(value);
  await page.getByText(/tracks saved|is empty/).waitFor({ timeout: 20000 });
  await page.waitForTimeout(300);
};

await createLibrary('MacBook', MAC);
await createLibrary('Studio PC', STUDIO);

const PLAYLIST = 'Artist One - Anthem\nStudio Only - Rare Dub';

await match(PLAYLIST);
console.log('\nSTUDIO PC   ', await rows());

// Teach Studio PC to prefer the Club Mix.
const clubValue = await page
  .locator('table select option', { hasText: 'studio-anthem-club' })
  .first()
  .getAttribute('value');
await page.locator('table select').first().selectOption(clubValue);
await page.waitForTimeout(600);
console.log('after picking', await rows());

await selectLibrary('MacBook');
await match(PLAYLIST);
console.log('\nMACBOOK     ', await rows());
console.log('  (the Studio PC choice must NOT appear here)');

await selectLibrary('Studio PC');
await match(PLAYLIST);
console.log('\nSTUDIO PC   ', await rows());
console.log('  (its own remembered choice must be back)');

await page.screenshot({ path: process.env.SHOT ?? '/tmp/two-library.png', fullPage: true });
await browser.close();
