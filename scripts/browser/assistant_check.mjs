// Usage: npm i puppeteer-core @sparticuz/chromium axe-core (in a scratch directory), then
//   AEGIS_EMAIL=... AEGIS_PASSWORD=... AEGIS_BROWSER_BASE=http://127.0.0.1:5173 node scripts/browser/assistant_check.mjs
// Sandbox note: @sparticuz/chromium needs its al2023 libraries on LD_LIBRARY_PATH.
// Browser check of the embedded assistant: sign in through the real form, ask a
// question on /assistant, check the answer and the label, check a refusal, then run
// axe-core on the page. Credentials come from env, never from this file.
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import { readFileSync } from 'node:fs';

const BASE = process.env.AEGIS_BROWSER_BASE ?? 'http://127.0.0.1:5173';
const EMAIL = process.env.AEGIS_EMAIL;
const PASSWORD = process.env.AEGIS_PASSWORD;
const AXE = readFileSync(process.env.AXE_PATH ?? new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');

const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  args: chromium.args,
  headless: true,
  defaultViewport: { width: 1280, height: 900 },
});
const results = {};
try {
  const page = await browser.newPage();
  await page.goto(`${BASE}/sign-in`, { waitUntil: 'networkidle0' });
  await page.type('#auth-email', EMAIL);
  await page.type('#auth-password', PASSWORD);
  await Promise.all([
    page.click('button[type="submit"]'),
    page.waitForFunction(() => !location.pathname.startsWith('/sign-in'), { timeout: 20000 }),
  ]);
  results.signedInAt = new URL(page.url()).pathname;

  await page.goto(`${BASE}/assistant`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('#assistant-question');

  const ask = async (text) => {
    await page.click('#assistant-question', { clickCount: 3 });
    await page.type('#assistant-question', text);
    await page.click('form[aria-label="Ask the assistant"] button[type="submit"]');
    await page.waitForFunction(
      (t) => [...document.querySelectorAll('ol[aria-label="Answers"] li strong')].some((n) => n.textContent === t),
      { timeout: 20000 },
      text,
    );
    return page.$eval('ol[aria-label="Answers"] li', (li) => li.innerText);
  };

  results.count = await ask('How many alerts in the last 24 hours?');
  results.refusal = await ask('stop packet capture');
  await page.screenshot({ path: '/home/user/assistant-check.png', fullPage: true });

  await page.evaluate(AXE);
  results.axe = await page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: ['wcag2a', 'wcag2aa'] });
    return r.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`);
  });
} finally {
  await browser.close();
}
console.log(JSON.stringify(results, null, 2));
