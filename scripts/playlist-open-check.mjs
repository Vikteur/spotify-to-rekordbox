// Clicks an imported playlist open and reports what the user sees.
// Usage: node scripts/playlist-open-check.mjs <music-folder>
import { chromium } from 'playwright-core';

const MUSIC = process.argv[2];
if (!MUSIC) {
  console.error('usage: node scripts/playlist-open-check.mjs <music-folder>');
  process.exit(2);
}

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
await page.goto(process.env.APP_URL ?? 'http://127.0.0.1:8000/');
await page.getByText(/tracks saved/).waitFor({ timeout: 60000 });

const row = page.locator('details', { has: page.getByText('Most played 2026') }).first();
console.log('collapsed by default:', !(await row.evaluate((node) => node.open)));

await row.locator('summary').click();
await page.waitForTimeout(500);
console.log('open after clicking the row:', await row.evaluate((node) => node.open));
console.log('tracks shown:');
for (const item of await row.locator('ol li').all()) {
  console.log('   ', (await item.innerText()).replace(/\s+/g, ' ').trim());
}

await page.screenshot({ path: process.env.SHOT ?? '/tmp/playlist-open.png', fullPage: true });

// Remove sits inside the summary — clicking it must not toggle the row.
const openBefore = await row.evaluate((node) => node.open);
await row.getByRole('button', { name: 'Remove' }).click();
await page.waitForTimeout(400);
console.log('row was open before pressing Remove:', openBefore);
console.log('playlist gone after Remove:', (await row.count()) === 0);
await browser.close();
