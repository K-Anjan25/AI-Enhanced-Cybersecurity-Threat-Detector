// Run with a Chromium binary and the dashboard preview serving on port 4173:
//   npm i puppeteer-core @sparticuz/chromium axe-core   (in a scratch directory)
//   AEGIS_BROWSER_BASE=http://127.0.0.1:4173 AXE_PATH=<scratch>/node_modules/axe-core/axe.min.js node scripts/browser/contrast_pass.mjs
// Sandbox note: @sparticuz/chromium needs its al2023 libraries; export LD_LIBRARY_PATH
// to where they are extracted. Credentials come from env, never from the file.
// Worst-case WCAG contrast over the real rendered pixels behind each text element.
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
const b64 = await page.screenshot({ encoding: 'base64' });
const out = await page.evaluate(async (b64) => {
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
    const results = [];
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
    for (const el of els) {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        const fg = parse(cs.color);
        const fgL = lum(...fg);
        let worst = Infinity,
            samples = 0;
        const ratios = [];
        const x0 = Math.max(0, Math.floor(r.left)),
            x1 = Math.min(c.width, Math.ceil(r.right));
        const y0 = Math.max(0, Math.floor(r.top)),
            y1 = Math.min(c.height, Math.ceil(r.bottom));
        for (let y = y0; y < y1; y += 2)
            for (let x = x0; x < x1; x += 2) {
                const i = (y * c.width + x) * 4;
                const px = [data[i], data[i + 1], data[i + 2]];
                // Skip anti-aliased glyph pixels: close to the text colour, not background.
                if (Math.hypot(px[0] - fg[0], px[1] - fg[1], px[2] - fg[2]) < 60) continue;
                samples++;
                const rr = ratio(fgL, lum(...px));
                ratios.push(rr);
                worst = Math.min(worst, rr);
            }
        if (samples === 0) continue;
        ratios.sort((a, b) => a - b);
        const median = ratios[Math.floor(ratios.length / 2)];
        const size = parseFloat(cs.fontSize),
            weight = parseInt(cs.fontWeight, 10);
        const large = size >= 24 || (size >= 18.66 && weight >= 700);
        results.push({
            text: [...el.childNodes]
                .filter((n) => n.nodeType === 3)
                .map((n) => n.textContent.trim())
                .join(' ')
                .slice(0, 40),
            color: cs.color,
            size,
            weight,
            median: Math.round(median * 100) / 100,
            worst: Math.round(worst * 100) / 100,
            required: large ? 3 : 4.5,
            pass: worst >= (large ? 3 : 4.5),
        });
    }
    return results;
}, b64);
await browser.close();
const fails = out.filter((o) => !o.pass);
console.log(`text elements measured: ${out.length}; below AA: ${fails.length}`);
console.log(
    'by worst pixel, lowest five:',
    out
        .slice()
        .sort((a, b) => a.worst - b.worst)
        .slice(0, 5)
        .map((o) => `${o.text} worst=${o.worst} median=${o.median}`),
);
console.log(
    'failing on median background:',
    out
        .filter((o) => o.median < o.required)
        .map((o) => `${o.text} median=${o.median} need=${o.required}`),
);
console.log('failing on worst pixel:', fails.length);
