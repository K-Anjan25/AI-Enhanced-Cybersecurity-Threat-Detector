// Contrast of every text element against the background behind it, measured on rendered pixels.
//
// Method: each page is captured twice. The first capture has the text as designed and gives
// the foreground colour. The second has all text made transparent, so only background is in
// the frame, and it is sampled for every pixel inside the element's box. Anti-aliased glyph
// edges are therefore never counted as background. (An earlier version sampled the text frame
// and counted glyph edges, which made real backgrounds look failing; see D-091 correction.)
//
// Run with a Chromium binary and the dashboard preview on port 4173:
//   npm i puppeteer-core @sparticuz/chromium   (in a scratch directory)
//   AEGIS_BROWSER_BASE=http://127.0.0.1:4173 node scripts/browser/contrast_pass.mjs
// Sandbox note: @sparticuz/chromium needs its al2023 libraries; export LD_LIBRARY_PATH
// to where they are extracted.
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';

const BASE = process.env.AEGIS_BROWSER_BASE || 'http://127.0.0.1:4173';
const browser = await puppeteer.launch({
    executablePath: await chromium.executablePath(),
    args: chromium.args,
    headless: true,
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
await page.goto(BASE + '/', { waitUntil: 'networkidle0', timeout: 60000 });
await new Promise((r) => setTimeout(r, 1000));

// Describe every text-bearing element with its designed colour and box, before hiding text.
const targets = await page.evaluate(() => {
    const els = [...document.querySelectorAll('body *')].filter((el) => {
        const direct = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
        if (!direct) return false;
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        return (
            r.width > 0 &&
            r.height > 0 &&
            r.top >= 0 &&
            r.bottom <= 800 &&
            cs.visibility !== 'hidden' &&
            parseFloat(cs.opacity) > 0.5
        );
    });
    return els.map((el, index) => {
        el.setAttribute('data-contrast-index', String(index));
        // The text's own glyph rectangles, not the element box: a pill-shaped button's box
        // includes its rounded corners, which sit on the page, not behind the label.
        const rects = [];
        for (const node of el.childNodes) {
            if (node.nodeType !== 3 || !node.textContent.trim()) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            rects.push(...range.getClientRects());
        }
        const left = Math.min(...rects.map((q) => q.left));
        const right = Math.max(...rects.map((q) => q.right));
        const top = Math.min(...rects.map((q) => q.top));
        const bottom = Math.max(...rects.map((q) => q.bottom));
        const cs = getComputedStyle(el);
        return {
            index,
            text: [...el.childNodes]
                .filter((n) => n.nodeType === 3)
                .map((n) => n.textContent.trim())
                .join(' ')
                .slice(0, 40),
            color: cs.color,
            size: parseFloat(cs.fontSize),
            weight: parseInt(cs.fontWeight, 10),
            box: { left, top, right, bottom },
        };
    });
});

// Frame with text transparent: background only.
const hideText = await page.addStyleTag({
    content:
        '*, *::before, *::after { color: transparent !important; text-shadow: none !important; -webkit-text-fill-color: transparent !important; caret-color: transparent !important; }',
});
await new Promise((r) => setTimeout(r, 300));
const backgroundB64 = await page.screenshot({ encoding: 'base64' });
await hideText.evaluate((node) => node.remove());

const measured = await page.evaluate(
    async (b64, targets) => {
        const img = new Image();
        img.src = 'data:image/png;base64,' + b64;
        await img.decode();
        const c = document.createElement('canvas');
        c.width = img.width;
        c.height = img.height;
        const ctx = c.getContext('2d');
        ctx.drawImage(img, 0, 0);
        const data = ctx.getImageData(0, 0, c.width, c.height).data;
        const lum = (r, g, b) => {
            const f = (v) => {
                v /= 255;
                return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
        };
        const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        const parse = (s) =>
            s
                .match(/[\d.]+/g)
                .slice(0, 3)
                .map(Number);
        return targets
            .map((t) => {
                const fg = parse(t.color);
                const fgL = lum(...fg);
                const ratios = [];
                const x0 = Math.max(0, Math.floor(t.box.left)),
                    x1 = Math.min(c.width, Math.ceil(t.box.right));
                const y0 = Math.max(0, Math.floor(t.box.top)),
                    y1 = Math.min(c.height, Math.ceil(t.box.bottom));
                for (let y = y0; y < y1; y += 2) {
                    for (let x = x0; x < x1; x += 2) {
                        const i = (y * c.width + x) * 4;
                        ratios.push(ratio(fgL, lum(data[i], data[i + 1], data[i + 2])));
                    }
                }
                if (ratios.length === 0) return null;
                ratios.sort((a, b) => a - b);
                const large = t.size >= 24 || (t.size >= 18.66 && t.weight >= 700);
                const required = large ? 3 : 4.5;
                const share = ratios.filter((v) => v >= required).length / ratios.length;
                return {
                    text: t.text,
                    color: t.color,
                    size: t.size,
                    worst: Math.round(ratios[0] * 100) / 100,
                    p5: Math.round(ratios[Math.floor(ratios.length * 0.05)] * 100) / 100,
                    median: Math.round(ratios[Math.floor(ratios.length / 2)] * 100) / 100,
                    share_passing: Math.round(share * 10000) / 100,
                    required,
                    pass: ratios[0] >= required,
                };
            })
            .filter(Boolean);
    },
    backgroundB64,
    targets,
);

await browser.close();
const fails = measured.filter((m) => !m.pass);
console.log(
    `text elements measured: ${measured.length}; failing at the worst background pixel: ${fails.length}`,
);
for (const m of measured) {
    console.log(
        `${m.pass ? 'pass' : 'FAIL'}  ${m.text.padEnd(42)} need ${m.required}  worst ${m.worst}  p5 ${m.p5}  median ${m.median}  pixels>=need ${m.share_passing}%`,
    );
}
