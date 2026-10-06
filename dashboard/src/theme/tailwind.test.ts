/**
 * @vitest-environment node
 */
/**
 * The Tailwind half of the token layer (T-401, R-27).
 *
 * tokens.test.ts reads src/index.css as text; this suite *compiles* the real
 * tailwind.config.js against the real src/index.css and asserts on what comes out.
 * That is the difference between "the config says `bg-base` maps to a variable"
 * and "`bg-base` compiles to a variable, and `bg-red-500` compiles to nothing at
 * all".
 *
 * The claims, one per sentence of design.md §5 that a config can enforce:
 *
 *   1. every colour utility resolves to a `var(--…)` a theme declares;
 *   2. the palette and the spacing/type/family scales are *closed* — an off-token
 *      colour or an off-scale step emits no CSS at all;
 *   3. the numbers the config implements are the numbers design.md publishes
 *      (read out of the document, not restated here); and
 *   4. no shipped source carries a colour literal or a palette class name, so an
 *      inline style cannot smuggle a colour past the token layer either.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import postcss from 'postcss';
import tailwindcss from 'tailwindcss';
import { describe, expect, it } from 'vitest';

import { VIEWPORT_QUERY } from '../lib/viewport';
import { ROW_HEIGHT_CLASS } from './density';

const CONFIG_PATH = fileURLToPath(new URL('../../tailwind.config.js', import.meta.url));
const SRC = fileURLToPath(new URL('..', import.meta.url));
const INDEX_CSS = fileURLToPath(new URL('../index.css', import.meta.url));
const INDEX_HTML = fileURLToPath(new URL('../../index.html', import.meta.url));
const design = readFileSync(fileURLToPath(new URL('../../../design.md', import.meta.url)), 'utf8');
const css = readFileSync(INDEX_CSS, 'utf8');

interface TailwindConfig {
  content: unknown;
  theme: {
    colors: Record<string, unknown>;
    spacing: Record<string, unknown>;
    fontFamily: Record<string, unknown>;
    screens: Record<string, string>;
  };
  [key: string]: unknown;
}

/** The real config, loaded rather than restated, so it cannot drift. */
const config = ((await import(CONFIG_PATH)) as { default: TailwindConfig }).default;

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info', 'benign'] as const;

/** What the plugin accepts, so the assembled override is checked by TS. */
type PluginOptions = Parameters<typeof tailwindcss>[0];

/** The real config plus an inline candidate list, as the plugin wants it. */
function withCandidates(candidates: string): PluginOptions {
  return {
    ...config,
    content: [{ raw: candidates, extension: 'html' }],
  } as unknown as PluginOptions;
}

const TOKEN_COLOUR_UTILITIES = [
  'bg-base',
  'bg-surface',
  'border-line',
  'text-ink',
  'text-muted',
  'text-accent',
  'text-onAccent',
  'text-onSeverity',
  ...SEVERITIES.map((severity) => `bg-severity-${severity}`),
  ...SEVERITIES.map((severity) => `text-severityText-${severity}`),
];

/** Compile utilities for exactly these class names. */
async function compile(candidates: string): Promise<string> {
  // The application's globs are overridden, so this suite sees its own candidate
  // list and not whatever the app happens to use today.
  const result = await postcss([tailwindcss(withCandidates(candidates))]).process(
    '@tailwind utilities;',
    { from: undefined },
  );
  // Collapsed, so an assertion is about the declarations rather than the
  // indentation this pipeline happens to produce.
  return result.css.replace(/\s+/g, ' ');
}

/** Compile the real stylesheet — preflight, layers and all — for these classes. */
async function compileApp(candidates: string): Promise<string> {
  const result = await postcss([tailwindcss(withCandidates(candidates))]).process(css, {
    from: INDEX_CSS,
  });
  return result.css.replace(/\s+/g, ' ');
}

/** design.md §5.4's steps: `{ display: { size: '32px', lineHeight: '36px', weight: '600' } }`. */
function publishedTypeScale(): Record<
  string,
  { size: string; lineHeight: string; weight: string }
> {
  const start = design.indexOf('### 5.4 Typography');
  expect(start).toBeGreaterThanOrEqual(0);
  const scale: Record<string, { size: string; lineHeight: string; weight: string }> = {};
  for (const line of design.slice(start).split('\n')) {
    const row = /^\|\s*`?(type\.[\w-]+)`?\s*\|\s*(\d+)\s*\/\s*(\d+)\s*\|\s*(\d+)\s*\|/.exec(
      line.trim(),
    );
    if (row) {
      scale[row[1]!.replace('type.', '')] = {
        size: `${row[2]}px`,
        lineHeight: `${row[3]}px`,
        weight: row[4]!,
      };
    }
  }
  expect(Object.keys(scale), 'no type steps parsed out of §5.4').toHaveLength(6);
  return scale;
}

/**
 * design.md §8.3's breakpoints, in px, straight out of its table.
 *
 * The four rows are written as `< 768 px`, `768–1023 px`, `1024–1439 px` and
 * `≥ 1440 px`; the *lower* bound of each row above the first is what Tailwind calls a
 * screen, so the three numbers here are 768, 1024 and 1440.
 */
function publishedBreakpoints(): string[] {
  const start = design.indexOf('### 8.3 Responsive breakpoints');
  expect(start).toBeGreaterThanOrEqual(0);
  const section = design.slice(start, design.indexOf('## 9.', start));
  // One row per line, and the *first* number in the row is its lower bound: `< 768 px`
  // is 768, `768–1023 px` is 768 (its upper end is the next row's lower one), and so
  // on. Reading the first number of each row rather than every number in the section
  // is what keeps `1023` and `1439` — the upper ends of the middle rows, which are the
  // next row's lower bound and not a boundary any query may name — out of the list. The
  // table is written widest first, so the set is sorted before it is returned.
  const bounds = new Set<number>();
  for (const line of section.split('\n')) {
    const row = /^\|\s*([^|]*)\|/.exec(line.trim());
    if (row === null) continue;
    const first = /(\d{3,4})/.exec(row[1]!);
    if (first === null) continue;
    bounds.add(Number.parseInt(first[1]!, 10));
  }
  const published = [...bounds].sort((a, b) => a - b).map((width) => `${String(width)}px`);
  expect(published, 'no breakpoint numbers parsed out of §8.3').toEqual([
    '768px',
    '1024px',
    '1440px',
  ]);
  return published;
}

/** The eight documented spacing steps, in px, straight from design.md §5.5. */
function publishedSpacing(): string[] {
  const published = /Spacing scale \(4 px base\):\*\*\s*([\d,\s]+)\./.exec(design);
  expect(published).not.toBeNull();
  return published![1]!.split(',').map((step) => `${step.trim()}px`);
}

/** The stylesheet with every custom-property declaration removed. */
function withoutTokenDeclarations(compiled: string): string {
  // Comments go first: index.css documents the badge rule with a literal in prose.
  // Then the token *definitions* are stripped — they are the one place a colour
  // literal belongs — which leaves the ordinary declarations, where a stray colour
  // would hide (`color: #9ca3af`, `background: rgb(...)`).
  return compiled.replace(/\/\*[\s\S]*?\*\//g, '').replace(/--[\w-]+:\s*[^;]+;?/g, '');
}

describe('compiled colour utilities', () => {
  it('resolves every token utility to its own rule and a variable', async () => {
    const compiled = await compile(TOKEN_COLOUR_UTILITIES.join(' '));
    for (const cls of TOKEN_COLOUR_UTILITIES) {
      expect(compiled, `${cls} did not compile`).toMatch(new RegExp(`\\.${cls} \\{[^}]*var\\(--`));
    }
  });

  it('references only variables the token file declares', async () => {
    const compiled = await compileApp(TOKEN_COLOUR_UTILITIES.join(' '));
    const referenced = new Set(
      [...compiled.matchAll(/var\((--[\w-]+)/g)].map((match) => match[1]!),
    );
    const declared = new Set([...css.matchAll(/(--[\w-]+):/g)].map((match) => match[1]!));
    expect(referenced.size).toBeGreaterThanOrEqual(TOKEN_COLOUR_UTILITIES.length);
    for (const name of referenced) {
      expect(declared, `${name} is used but never declared in index.css`).toContain(name);
    }
  });

  it('compiles no colour literal except Tailwind’s own two defaults', async () => {
    const compiled = withoutTokenDeclarations(await compileApp(TOKEN_COLOUR_UTILITIES.join(' ')));
    // Exactly one literal survives: `#9ca3af`, preflight's placeholder fallback
    // for the gray-400 this palette replaced (`#0000` was `transparent` inside
    // Tailwind's shadow resets, which the custom-property strip removed). The next
    // test asserts the muted token overrides it, so it is never seen.
    expect([
      ...new Set([...compiled.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map((match) => match[0])),
    ]).toEqual(['#9ca3af']);
    expect(compiled).not.toMatch(/rgba?\(/);
  });

  it('overrides the placeholder fallback with the muted token, later and equally specific', async () => {
    const compiled = await compileApp('');
    const rules = [
      ...compiled.matchAll(/input::placeholder,\s*textarea::placeholder\s*\{([^}]*)\}/g),
    ].map((match) => match[1]!);
    expect(rules.length, 'expected preflight and the token rule').toBe(2);
    expect(rules[0]).toContain('#9ca3af');
    expect(rules.at(-1)).toContain('color: var(--color-text-muted)');
  });

  it('emits nothing for an off-token colour or severity level', async () => {
    const compiled = await compile(
      'bg-red-500 text-white border-gray-200 ring-blue-500 bg-severity-urgent text-severityText-none',
    );
    for (const cls of [
      'bg-red-500',
      'text-white',
      'border-gray-200',
      'ring-blue-500',
      'bg-severity-urgent',
      'text-severityText-none',
    ]) {
      expect(compiled, `${cls} compiled — the palette is not closed`).not.toMatch(
        new RegExp(`\\.${cls}[\\s{,:]`),
      );
    }
  });

  it('defaults a bare border and a ring to tokens rather than to a palette', async () => {
    const compiled = await compileApp('border ring');
    // Preflight's universal default, so a hairline nobody coloured is on-token.
    expect(compiled).toContain('border-color: var(--color-border)');
    expect(compiled).toContain('--tw-ring-color: var(--focus-ring)');
    expect(compiled).toContain('--tw-ring-offset-color: var(--color-bg-base)');
  });

  it('maps the colour scale onto the documented names and nothing else', () => {
    expect(Object.keys(config.theme.colors).sort()).toEqual(
      [
        'base',
        'surface',
        'line',
        'ink',
        'muted',
        'accent',
        'severity',
        'severityText',
        'onAccent',
        'onSeverity',
        'transparent',
        'current',
        'inherit',
      ].sort(),
    );
    for (const [name, value] of Object.entries(
      config.theme.colors.severity as Record<string, string>,
    )) {
      expect(value, `severity.${name} is not a token reference`).toMatch(
        /^var\(--severity-[\w-]+\)$/,
      );
    }
    for (const name of Object.keys(config.theme.colors.severity as Record<string, string>)) {
      expect(SEVERITIES).toContain(name);
    }
  });
});

describe('closed scales', () => {
  it('declares the documented spacing scale and no other step', () => {
    expect(config.theme.spacing).toEqual({
      0: '0px',
      1: '4px',
      2: '8px',
      3: '12px',
      4: '16px',
      6: '24px',
      8: '32px',
      12: '48px',
      16: '64px',
    });
    expect(Object.values(config.theme.spacing).slice(1)).toEqual(publishedSpacing());
  });

  it('compiles every documented spacing step and nothing off the scale', async () => {
    const documented = publishedSpacing();
    const keys = ['p-1', 'p-2', 'p-3', 'p-4', 'p-6', 'p-8', 'p-12', 'p-16'];
    const compiled = await compile(keys.join(' '));
    for (const [index, key] of keys.entries()) {
      expect(compiled, `${key} did not emit ${documented[index]}`).toContain(
        `.${key} { padding: ${documented[index]}`,
      );
    }
    const offScale = await compile('p-5 p-7 p-9 p-10 p-11 p-14 p-20');
    for (const key of ['p-5', 'p-7', 'p-9', 'p-10', 'p-11', 'p-14', 'p-20']) {
      expect(offScale, `${key} compiled — the spacing scale is not closed`).not.toMatch(
        new RegExp(`\\.${key}[\\s{,:]`),
      );
    }
  });

  it('compiles exactly the published type scale, and no other step', async () => {
    const published = publishedTypeScale();
    const compiled = await compile(
      Object.keys(published)
        .map((name) => `text-${name}`)
        .join(' '),
    );
    for (const [name, { size, lineHeight, weight }] of Object.entries(published)) {
      expect(compiled, `text-${name} size`).toContain(`font-size: ${size}`);
      expect(compiled, `text-${name} line-height`).toContain(`line-height: ${lineHeight}`);
      expect(compiled, `text-${name} weight`).toContain(`font-weight: ${weight}`);
    }
    // design.md's floor, read from the document rather than restated.
    expect(design).toContain('Minimum text size is 12 px');
    expect(Math.min(...Object.values(published).map((step) => Number.parseFloat(step.size)))).toBe(
      12,
    );
    const stray = await compile('text-lg text-3xl text-xs text-sm');
    for (const key of ['text-lg', 'text-3xl', 'text-xs', 'text-sm']) {
      expect(stray, `${key} compiled — the type scale is not closed`).not.toMatch(
        new RegExp(`\\.${key}[\\s{,:]`),
      );
    }
  });

  it('closes the font families to the two design.md names', async () => {
    expect(Object.keys(config.theme.fontFamily).sort()).toEqual(['mono', 'sans']);
    const compiled = await compile('font-sans font-mono font-serif');
    expect(compiled).toContain('Inter');
    expect(compiled).toContain('JetBrains Mono');
    expect(compiled).not.toMatch(/\.font-serif[\s{,:]/);
    expect(design).toContain('Inter, system-ui fallback');
    expect(design).toContain('JetBrains Mono, ui-monospace fallback');
  });

  it('compiles the documented radius, density, icon, rail and elevation tokens', async () => {
    const compiled = await compile(
      'rounded-input rounded-card rounded-modal rounded-pill h-row-comfortable h-row-compact size-icon-sm size-icon-md border-l-rail shadow-overlay',
    );
    for (const radius of ['4px', '8px', '12px', '999px']) {
      expect(compiled, `no radius of ${radius}`).toContain(`border-radius: ${radius}`);
    }
    expect(compiled, 'the elevation token is not used').toContain(
      '--tw-shadow: var(--shadow-overlay)',
    );
    for (const [utility, declaration] of [
      ['h-row-comfortable', 'height: 44px'],
      ['h-row-compact', 'height: 32px'],
      ['size-icon-sm', 'width: 16px; height: 16px'],
      ['size-icon-md', 'width: 20px; height: 20px'],
      ['border-l-rail', 'border-left-width: 3px'],
    ] as const) {
      expect(compiled, `${utility} did not emit ${declaration}`).toContain(
        `.${utility} { ${declaration}`,
      );
      // The number is design.md's, in the document's own spacing.
      const number = declaration.match(/\d+px/)![0].replace('px', '');
      expect(design, `design.md no longer publishes ${number} px`).toContain(`${number} px`);
    }
  });

  it('closes the breakpoints to design.md §8.3’s three numbers (T-412)', async () => {
    // The breakpoints are a scale like the others: Tailwind's defaults are 640, 768,
    // 1024, 1280 and 1536, and §8.3 publishes three of those numbers plus 1440. Leaving
    // the defaults in place would let `sm:` and `2xl:` define two breakpoints no
    // document mentions, and a screen written against them would be a layout decision
    // nobody made.
    expect(config.theme.screens).toEqual({ md: '768px', lg: '1024px', xl: '1440px' });
    const published = publishedBreakpoints();
    expect(Object.values(config.theme.screens)).toEqual(published);

    const compiled = await compile('md:flex-row lg:grid-cols-2 xl:grid-cols-4');
    for (const [prefix, width] of [
      ['md', published[0]],
      ['lg', published[1]],
      ['xl', published[2]],
    ] as const) {
      expect(compiled, `${prefix}: did not compile to ${width}`).toContain(
        `@media (min-width: ${width})`,
      );
    }
  });

  it('emits nothing for a breakpoint design.md does not publish', async () => {
    const compiled = await compile('sm:flex-row 2xl:grid-cols-6');
    for (const cls of ['sm:flex-row', '2xl:grid-cols-6']) {
      expect(compiled, `${cls} compiled — the breakpoints are not closed`).not.toContain(
        cls.replace(':', '\\:'),
      );
    }
    expect(compiled).not.toContain('@media');
  });

  it('agrees with the media queries the viewport hook builds', async () => {
    // Two spellings of one boundary: Tailwind's `max-md:` variant and
    // `VIEWPORT_QUERY.narrow` from lib/viewport.ts. A panel hidden by the first and a
    // page hidden by the second have to hide at the same width, which is only true
    // while both are derived from the same numbers.
    const [md, lg] = publishedBreakpoints();
    const compiled = await compile('max-md:hidden max-lg:hidden');
    const bound = (px: string): string => (Number.parseFloat(px) - 0.02).toFixed(2);
    expect(compiled).toContain(`@media not all and (min-width: ${md})`);
    expect(compiled).toContain(`@media not all and (min-width: ${lg})`);
    expect(VIEWPORT_QUERY.narrow).toBe(`(max-width: ${bound(md!)}px)`);
    expect(VIEWPORT_QUERY.narrowOrCompact).toBe(`(max-width: ${bound(lg!)}px)`);
  });

  it('keeps the density helper and the compiled token in agreement', async () => {
    const compiled = await compile(Object.values(ROW_HEIGHT_CLASS).join(' '));
    expect(compiled).toContain('.h-row-comfortable { height: 44px');
    expect(compiled).toContain('.h-row-compact { height: 32px');
  });
});

describe('shipped sources', () => {
  const shipped = readdirSync(SRC, { recursive: true })
    .map((entry) => String(entry))
    .filter((name) => /\.(ts|tsx|css)$/.test(name))
    // The token file is where colour literals belong, and tests quote design.md's
    // values on purpose: neither is a shipped style.
    .filter(
      (name) => name !== 'index.css' && !/\.test\.tsx?$/.test(name) && !name.startsWith('test/'),
    )
    .map((name) => [name, readFileSync(`${SRC}/${name}`, 'utf8')] as const);

  it('scans the sources that exist, so the scan cannot pass vacuously', () => {
    expect(shipped.length).toBeGreaterThanOrEqual(4);
    expect(shipped.map(([name]) => name)).toContain('components/ui/ConnectionStatus.tsx');
  });

  it('carries no colour literal outside the token file (R-27)', () => {
    const literal = /#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(/;
    const named =
      /['"`](?:white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|maroon|navy|teal|olive|lime|aqua|fuchsia)['"`]/i;
    for (const [name, source] of shipped) {
      expect(source, `${name} carries a colour literal`).not.toMatch(literal);
      expect(source, `${name} names a colour outside the tokens`).not.toMatch(named);
    }
  });

  it('uses no class from the palette Tailwind no longer has', () => {
    const palette =
      /(?:^|[\s'"`:])(?:bg|text|border|ring|divide|fill|stroke|from|via|to)-(?:red|blue|green|slate|gray|grey|zinc|neutral|stone|amber|orange|yellow|lime|emerald|teal|cyan|sky|indigo|violet|purple|fuchsia|pink|rose|white|black)(?:-\d{2,3})?(?=[\s'"`]|$)/;
    for (const [name, source] of shipped) {
      const found = palette.exec(source);
      expect(found?.[0] ?? null, `${name} uses the off-token class ${found?.[0]}`).toBeNull();
    }
  });

  it('compiles every colour utility the shipped sources name', async () => {
    // The palette check above catches `bg-red-500`; it cannot catch a *misspelled
    // token* like `text-severity-critical-text`, which is not an off-token palette
    // colour but an off-token name — and since `theme.colors` is closed, it compiles
    // to nothing at all and the element silently keeps the default text colour. Two
    // error messages in the hunt console shipped that way (T-408) and rendered in
    // normal ink; T-409 found it while adding the models screens. Compiling what the
    // sources actually contain is the general form of the check, and it is the one
    // that would have caught the typo the day it was typed.
    // The trailing lookahead keeps a *partial* utility out of the set: a prose
    // reference like `bg-severity-*` and a template such as `bg-severity-${tone}`
    // are fragments, not classes, and Tailwind would emit nothing for either. A
    // hyphen after the longest match means the token did not end there.
    const utility =
      /\b(?:bg|text|border|divide|ring|fill|stroke)-[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?![-\w*$])/g;
    const candidates = new Set<string>();
    for (const [, source] of shipped) {
      for (const match of source.matchAll(utility)) candidates.add(match[0]);
    }
    // A regex that matched nothing would make the assertion below vacuous.
    expect(candidates.size).toBeGreaterThanOrEqual(20);
    const compiled = await compile([...candidates].join(' '));
    const missing = [...candidates].filter((name) => !compiled.includes(`.${name} {`));
    expect(missing, 'utilities that emit no CSS at all').toEqual([]);
  });

  it('keeps index.html free of colour literals as well', () => {
    expect(readFileSync(INDEX_HTML, 'utf8')).not.toMatch(/#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(/);
  });

  it('scans the application, not an empty list, in the real build', () => {
    // A build whose content globs match nothing ships no styles at all, and every
    // assertion above would still pass.
    expect(config.content).toEqual(['./index.html', './src/**/*.{ts,tsx}']);
  });
});
