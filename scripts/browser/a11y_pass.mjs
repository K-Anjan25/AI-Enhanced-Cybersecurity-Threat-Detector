// Run with a Chromium binary and the dashboard preview serving on port 4173:
//   npm i puppeteer-core @sparticuz/chromium axe-core   (in a scratch directory)
//   AEGIS_BROWSER_BASE=http://127.0.0.1:4173 AXE_PATH=<scratch>/node_modules/axe-core/axe.min.js node scripts/browser/a11y_pass.mjs
// Sandbox note: @sparticuz/chromium needs its al2023 libraries; export LD_LIBRARY_PATH
// to where they are extracted. Credentials come from env, never from the file.
// Browser pass: real Chromium computes colour contrast; axe-core runs WCAG 2.x AA rules;
// a keyboard walk records focus order and whether a focus indicator is visible.
import fs from 'node:fs';
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';

const BASE = process.env.AEGIS_BROWSER_BASE || 'http://127.0.0.1:4173';
const EMAIL = process.env.AEGIS_BROWSER_EMAIL;
const PASSWORD = process.env.AEGIS_BROWSER_PASSWORD;
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const PUBLIC = ['/'];
const SIGNED_IN = ['/overview', '/triage', '/traffic', '/models', '/hunt', '/admin'];
fs.mkdirSync(process.env.AEGIS_BROWSER_SHOTS || '/tmp/aegis-shots', { recursive: true });

const axeSource = fs.readFileSync(process.env.AXE_PATH, 'utf8');
const browser = await puppeteer.launch({
    executablePath: await chromium.executablePath(),
    args: chromium.args,
    headless: true,
});

async function runAxe(page) {
    await page.addScriptTag({ content: axeSource });
    return page.evaluate(async (tags) => {
        const r = await window.axe.run(document, { runOnly: { type: 'tag', values: tags } });
        const pick = (list) =>
            list.map((v) => ({
                id: v.id,
                impact: v.impact,
                help: v.help,
                nodes: v.nodes.length,
                targets: v.nodes.slice(0, 3).map((n) => n.target.join(' ')),
                summary: (v.nodes[0]?.failureSummary || '').replace(/\s+/g, ' ').slice(0, 240),
            }));
        return { violations: pick(r.violations), incomplete: pick(r.incomplete) };
    }, AXE_TAGS);
}

async function keyboardWalk(page) {
    await page.evaluate(() => {
        document.activeElement?.blur();
        window.scrollTo(0, 0);
    });
    const seen = [];
    let focusVisible = null;
    for (let i = 0; i < 80; i++) {
        await page.keyboard.press('Tab');
        const state = await page.evaluate(() => {
            const el = document.activeElement;
            if (!el || el === document.body) return null;
            const cs = getComputedStyle(el);
            const label =
                el.getAttribute('aria-label') ||
                el.getAttribute('title') ||
                (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60) ||
                el.getAttribute('name') ||
                el.id;
            const outlined =
                (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) ||
                (cs.boxShadow && cs.boxShadow !== 'none');
            return { tag: el.tagName.toLowerCase(), label, outlined, outline: cs.outline };
        });
        if (!state) break;
        seen.push(state);
    }
    // Keyboard trap: the same element focused over and over without the list moving on.
    const labels = seen.map((s) => `${s.tag}:${s.label}`);
    let maxRepeat = 0;
    let run = 1;
    for (let i = 1; i < labels.length; i++) {
        run = labels[i] === labels[i - 1] ? run + 1 : 1;
        maxRepeat = Math.max(maxRepeat, run);
    }
    const unique = new Set(labels).size;
    focusVisible = seen.length ? seen.filter((s) => s.outlined).length / seen.length : null;
    return {
        stops: seen.length,
        unique,
        maxRepeat,
        focusVisibleShare: focusVisible,
        firstFive: labels.slice(0, 5),
        unindicated: seen
            .filter((s) => !s.outlined)
            .slice(0, 5)
            .map((s) => `${s.tag}:${s.label}`),
    };
}

async function check(page, name, url) {
    await page.goto(url, { waitUntil: 'networkidle0', timeout: 60000 });
    await new Promise((r) => setTimeout(r, 800));
    await page.screenshot({
        path: `${process.env.AEGIS_BROWSER_SHOTS || '/tmp/aegis-shots'}/${name}.png`,
        fullPage: false,
    });
    const axe = await runAxe(page);
    const keyboard = await keyboardWalk(page);
    return { page: url, axe, keyboard };
}

const results = [];
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });

for (const path of PUBLIC) {
    results.push(await check(page, path === '/' ? 'landing' : path.slice(1), BASE + path));
}

// Sign-in page (what every app route shows when signed out).
results.push(await check(page, 'signin', BASE + '/overview'));

// Sign in through the form, then visit the signed-in routes.
await page.goto(BASE + '/overview', { waitUntil: 'networkidle0', timeout: 60000 });
await page.type('input[type=email]', EMAIL);
await page.type('input[type=password]', PASSWORD);
await Promise.all([
    page.click('button[type=submit]'),
    page.waitForNetworkIdle({ idleTime: 700, timeout: 30000 }).catch(() => {}),
]);
await new Promise((r) => setTimeout(r, 1500));

for (const path of SIGNED_IN) {
    results.push(await check(page, path.slice(1), BASE + path));
}

await browser.close();
fs.writeFileSync(
    process.env.AEGIS_BROWSER_RESULTS || '/tmp/aegis-a11y-results.json',
    JSON.stringify(results, null, 2),
);

for (const r of results) {
    const v = r.axe.violations;
    console.log(
        `${r.page}  axe violations=${v.length} (${v.map((x) => x.id + '/' + x.impact).join(', ') || 'none'})` +
            `  incomplete=${r.axe.incomplete.length}` +
            `  tab stops=${r.keyboard.stops} unique=${r.keyboard.unique} maxRepeat=${r.keyboard.maxRepeat}` +
            ` focusVisible=${r.keyboard.focusVisibleShare?.toFixed(2)}`,
    );
}
