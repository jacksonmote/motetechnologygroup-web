// Loads every page from the local server and fails if any request leaves
// that origin (the site promises no third-party requests), or if the
// console logs an error (resources blocked by the CSP, missing files).
//
// Usage: node .github/scripts/no-external-requests.mjs [base URL]
// Uses the installed Google Chrome (channel "chrome"), so no browser download.

import { chromium } from 'playwright';

const base = new URL(process.argv[2] || 'http://localhost:8000/');
const pages = ['/', '/home/', '/business/', '/faq/', '/404.html'];
const viewports = [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'phone', width: 390, height: 844 },
];
const schemes = ['light', 'dark'];

const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
const problems = [];

for (const path of pages) {
  for (const viewport of viewports) {
    for (const colorScheme of schemes) {
      const label = `${path} (${viewport.name}, ${colorScheme})`;
      const context = await browser.newContext({ viewport, colorScheme });
      const page = await context.newPage();
      const requests = new Set();

      page.on('request', (req) => {
        const url = new URL(req.url());
        if (url.protocol === 'data:' || url.protocol === 'blob:') return;
        requests.add(url.href);
        if (url.origin !== base.origin) problems.push(`${label}: outside request to ${url.href}`);
      });
      page.on('requestfailed', (req) => problems.push(`${label}: request failed: ${req.url()} (${req.failure()?.errorText})`));
      page.on('response', (res) => {
        if (res.status() >= 400) problems.push(`${label}: HTTP ${res.status()} for ${res.url()}`);
      });
      page.on('console', (msg) => {
        if (msg.type() === 'error') problems.push(`${label}: console error: ${msg.text()}`);
      });
      page.on('pageerror', (err) => problems.push(`${label}: page error: ${err.message}`));

      await page.goto(new URL(path, base).href, { waitUntil: 'load' });
      // Scroll to the bottom so lazy images (the headshot) load too. "instant"
      // overrides the site's smooth scrolling, which would stall the loop.
      await page.evaluate(async () => {
        for (let y = 0; y < document.documentElement.scrollHeight; y += 400) {
          window.scrollTo({ top: y, behavior: 'instant' });
          await new Promise((r) => setTimeout(r, 50));
        }
      });
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(250);
      console.log(`${label}: ${requests.size} requests`);
      await context.close();
    }
  }
}

await browser.close();

if (problems.length) {
  console.error(`\n${problems.length} problem(s):`);
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}
console.log('\nNo outside requests and no console errors.');
