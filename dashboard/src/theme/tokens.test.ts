/**
 * @vitest-environment node
 */
/**
 * Design-token conformance and contrast regression (T-401).
 *
 * design.md §5 is the specification: every colour, every contrast ratio, every
 * type step and every scale step is published there as a number. This suite reads
 * the *published* values out of design.md and the *shipped* values out of
 * src/index.css and asserts they agree — the token file cannot drift from the
 * document without this failing, and the document cannot drift either.
 *
 * The ratios written as comments beside each token are checked too. They are what
 * a reader trusts when they change a value, and a stale comment is how a contrast
 * claim rots.
 *
 * Ratios are compared at the precision design.md prints (two decimals), since
 * that is the claim being made.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { AA_LARGE_AND_UI, AA_NORMAL_TEXT, contrastRatio } from '../lib/contrast';

const css = readFileSync(fileURLToPath(new URL('../index.css', import.meta.url)), 'utf8');
const html = readFileSync(fileURLToPath(new URL('../../index.html', import.meta.url)), 'utf8');
const design = readFileSync(fileURLToPath(new URL('../../../design.md', import.meta.url)), 'utf8');

const COLOUR_SECTIONS = {
  dark: '### 5.1 Colour — dark theme (default)',
  light: '### 5.2 Colour — light theme',
} as const;
const SEVERITY_SECTION = '### 5.3 Severity palette';
const TYPE_SECTION = '### 5.4 Typography';
const SCALE_SECTION = '### 5.5 Spacing, radius, elevation';
const ICON_SECTION = '### 5.6 Iconography';

const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info', 'benign'] as const;

/** CSS token name for a design.md colour token name, e.g. `text.muted`. */
const CSS_NAME: Record<string, string> = {
  'bg.base': '--color-bg-base',
  'bg.surface': '--color-bg-surface',
  'border.default': '--color-border',
  'text.primary': '--color-text-primary',
  'text.muted': '--color-text-muted',
  accent: '--color-accent',
};

const DARK_SELECTOR = "[data-theme='dark']";
const LIGHT_SELECTOR = "[data-theme='light']";

/** The body of one CSS selector block in index.css. */
function bodyFor(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `selector ${selector} not found in index.css`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf('{', start);
  const close = css.indexOf('}', open);
  return css.slice(open + 1, close);
}

/** Extract the `--name: #hex` pairs declared inside one selector block. */
function blockFor(selector: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const match of bodyFor(selector).matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    tokens[match[1] as string] = match[2] as string;
  }
  return tokens;
}

/**
 * The `| … |` table rows of a markdown section, header and separator included,
 * with the backticks design.md wraps code in removed.
 */
function rows(section: string): string[][] {
  return section
    .split('\n')
    .filter((line) => line.trim().startsWith('|'))
    .map((line) =>
      line
        .split('|')
        .slice(1, -1)
        .map((cell) => cell.trim().replace(/`/g, '')),
    );
}

/**
 * The rows of a markdown table that carry data: everything after the `|---|`
 * rule, so the header cannot be mistaken for a token.
 */
function dataRows(section: string): string[][] {
  const all = rows(section);
  const rule = all.findIndex((row) => row.length > 0 && row.every((cell) => /^-{3}:?$/.test(cell)));
  expect(rule, 'the table has no header rule').toBeGreaterThanOrEqual(0);
  return all.slice(rule + 1);
}

/** A markdown section, from its heading to the next heading of the same level. */
function section(heading: string): string {
  const start = design.indexOf(heading);
  expect(start, `design.md has no ${heading}`).toBeGreaterThanOrEqual(0);
  const rest = design.slice(start + heading.length);
  const end = rest.search(/\n#{2,3} /);
  return rest.slice(0, end === -1 ? undefined : end);
}

/** `bg.base` → `#0B0E14`, straight out of the published table. */
function documentedColours(heading: string): Record<string, string> {
  const table: Record<string, string> = {};
  for (const row of dataRows(section(heading))) {
    if (row[0] === undefined || row[1] === undefined) continue;
    table[row[0]] = row[1];
  }
  return table;
}

/** The published colour rows of one theme: `[token, value, contrast cell]`. */
function colourRows(theme: 'dark' | 'light'): [string, string, string][] {
  return dataRows(section(COLOUR_SECTIONS[theme]))
    .filter((row) => row[1]?.startsWith('#'))
    .map((row) => [row[0]!, row[1]!, row[2] ?? '']);
}

/** `7.50 : 1 on bg.base · 6.79 : 1 on bg.surface` → `[['7.50', 'bg.base'], …]`. */
function documentedRatios(cell: string): [string, string][] {
  return cell
    .split('·')
    .map((part) => /([\d.]+)\s*:\s*1\s*on\s*(\S+)/.exec(part.trim().replace(/`/g, '')))
    .filter((match): match is RegExpExecArray => match !== null)
    .map((match) => [match[1] as string, match[2] as string]);
}

/**
 * The ratios written as comments beside the tokens, e.g.
 * `/* 7.50:1 on base, 6.79:1 on surface *\/` → `[['--color-text-muted', '7.50', 'base'], …]`.
 *
 * A pair with no background named is read as base/surface, which is the
 * convention §5.3 states for the severity table.
 */
function inlineRatios(selector: string): [string, string, 'base' | 'surface'][] {
  const found: [string, string, 'base' | 'surface'][] = [];
  for (const line of bodyFor(selector).split('\n')) {
    const declaration = /(--[\w-]+):\s*#[0-9a-fA-F]{6};?\s*\/\*(.*)\*\//.exec(line);
    if (!declaration) continue;
    const [, token, comment] = declaration;
    const matches = [...comment!.matchAll(/([\d.]+)\s*:\s*1(?:\s*(?:on|against)\s+(\w+))?/g)];
    // Where a comment names a background it is a measurement; where it names
    // none it is the §5.3 pair (base, then surface) — and where it names one and
    // also mentions a number without a background (the focus ring's "above the
    // 3:1 requirement"), only the named one is a measurement.
    const measured = matches.filter((match) => match[2] !== undefined);
    const pairs = measured.length > 0 ? measured : matches;
    for (const [index, match] of pairs.entries()) {
      const [, ratio, named] = match;
      const background = named ?? (pairs.length > 1 && index === 1 ? 'surface' : 'base');
      found.push([token!, ratio!, background as 'base' | 'surface']);
    }
  }
  return found;
}

const dark = blockFor(DARK_SELECTOR);
const light = blockFor(LIGHT_SELECTOR);

const THEMES = [
  { name: 'dark', selector: DARK_SELECTOR, tokens: dark },
  { name: 'light', selector: LIGHT_SELECTOR, tokens: light },
] as const;

describe.each(THEMES)('$name theme', ({ selector, tokens }) => {
  it('writes the ratios it documents beside each token, and they hold', () => {
    const ratios = inlineRatios(selector);
    expect(
      ratios.length,
      'no inline ratios found — has the comment style changed?',
    ).toBeGreaterThan(0);
    for (const [token, published, background] of ratios) {
      const against = tokens[`--color-bg-${background}`]!;
      expect(
        contrastRatio(tokens[token]!, against),
        `${token} comment claims ${published}:1 on ${background}`,
      ).toBeCloseTo(Number(published), 2);
    }
  });

  it('meets WCAG AA for body text on both backgrounds', () => {
    for (const bg of ['--color-bg-base', '--color-bg-surface']) {
      const ratio = contrastRatio(tokens['--color-text-primary']!, tokens[bg]!);
      expect(ratio, `text.primary on ${bg}`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });

  it('meets WCAG AA for muted text on both backgrounds', () => {
    for (const bg of ['--color-bg-base', '--color-bg-surface']) {
      const ratio = contrastRatio(tokens['--color-text-muted']!, tokens[bg]!);
      expect(ratio, `text.muted on ${bg}`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });

  it('meets WCAG AA for the accent colour on both backgrounds', () => {
    for (const bg of ['--color-bg-base', '--color-bg-surface']) {
      const ratio = contrastRatio(tokens['--color-accent']!, tokens[bg]!);
      expect(ratio, `accent on ${bg}`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });

  it('meets WCAG AA for every severity text variant on both backgrounds', () => {
    // This is why the text variants exist: the base hues fail as text, notably
    // in the light theme (critical 3.91:1, medium 1.58:1).
    for (const severity of SEVERITIES) {
      for (const bg of ['--color-bg-base', '--color-bg-surface']) {
        const ratio = contrastRatio(tokens[`--severity-text-${severity}`]!, tokens[bg]!);
        expect(ratio, `severity-text-${severity} on ${bg}`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      }
    }
  });

  it('meets WCAG AA for badge text on every severity fill', () => {
    // design.md §5.3 badge rule: base-hue fill with --color-on-severity text.
    // White text is prohibited here because it measures 3.91:1 on critical.
    for (const severity of SEVERITIES) {
      const ratio = contrastRatio(
        tokens['--color-on-severity']!,
        tokens[`--severity-${severity}`]!,
      );
      expect(ratio, `badge text on ${severity} fill`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    }
  });

  it('keeps the on-accent text readable on the accent fill', () => {
    const ratio = contrastRatio(tokens['--color-on-accent']!, tokens['--color-accent']!);
    expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it('has a focus ring visible against the page background', () => {
    const ratio = contrastRatio(tokens['--focus-ring']!, tokens['--color-bg-base']!);
    expect(ratio).toBeGreaterThanOrEqual(AA_LARGE_AND_UI);
  });
});

describe('design.md agreement', () => {
  it('recomputes the published ratio for every colour row that states one', () => {
    for (const theme of ['dark', 'light'] as const) {
      const published = documentedColours(COLOUR_SECTIONS[theme]);
      for (const [name, value, contrast] of colourRows(theme)) {
        const ratios = documentedRatios(contrast);
        // Two rows state a use case rather than a ratio ("—", "decorative"):
        // background colours are not read as text.
        if (ratios.length === 0) {
          expect(contrast, `${theme} ${name} states neither a ratio nor a reason`).toMatch(
            /^(—|decorative)$/,
          );
          continue;
        }
        for (const [ratio, background] of ratios) {
          expect(
            published[background],
            `${theme} ${name} cites unknown ${background}`,
          ).toBeDefined();
          expect(
            contrastRatio(value, published[background]!),
            `${theme} ${name}: design.md says ${ratio}`,
          ).toBeCloseTo(Number(ratio), 2);
        }
      }
    }
  });

  it('shipped tokens hold the values design.md publishes for their theme', () => {
    for (const { name, tokens } of THEMES) {
      for (const [published, value] of Object.entries(documentedColours(COLOUR_SECTIONS[name]))) {
        const token = CSS_NAME[published];
        expect(token, `no CSS name mapped for ${published}`).toBeDefined();
        expect(tokens[token as string], `${name} ${published} drifted from design.md`).toBe(
          value.toLowerCase(),
        );
      }
    }
  });

  it('publishes exactly the six colour rows per theme, in the same order', () => {
    for (const theme of ['dark', 'light'] as const) {
      expect(colourRows(theme).map(([token]) => token)).toEqual([
        'bg.base',
        'bg.surface',
        'border.default',
        'text.primary',
        'text.muted',
        'accent',
      ]);
    }
  });

  it('defines the same token names in both themes, and exactly these', () => {
    expect(Object.keys(light).sort()).toEqual(Object.keys(dark).sort());
    expect(Object.keys(dark).sort()).toEqual(
      [
        '--color-accent',
        '--color-bg-base',
        '--color-bg-surface',
        '--color-border',
        '--color-on-accent',
        '--color-on-severity',
        '--color-text-muted',
        '--color-text-primary',
        '--focus-ring',
        ...SEVERITIES.map((severity) => `--severity-${severity}`),
        ...SEVERITIES.map((severity) => `--severity-text-${severity}`),
      ].sort(),
    );
  });

  it('uses the dark theme as the default, as the SOC context requires', () => {
    // `:root` carries the dark values, so a page that never sets data-theme is
    // dark; index.html also states it, so there is no flash of the wrong theme.
    const root = css.indexOf(':root,');
    expect(root).toBeGreaterThanOrEqual(0);
    expect(root).toBeLessThan(css.indexOf(DARK_SELECTOR));
    expect(html).toContain('data-theme="dark"');
  });

  it('implements the badge rule with the published ratios', () => {
    expect(dark['--color-on-severity']).toBe('#050510');
    expect(light['--color-on-severity']).toBe(dark['--color-on-severity']);
    const rule = section('**Badge rule.**');
    for (const severity of SEVERITIES) {
      const published = new RegExp(`${severity} ([\\d.]+)`).exec(rule);
      expect(published, `design.md publishes no badge ratio for ${severity}`).not.toBeNull();
      expect(
        contrastRatio(dark['--color-on-severity']!, dark[`--severity-${severity}`]!),
      ).toBeCloseTo(Number(published![1]), 2);
    }
    // The prohibition §5.3 states explicitly.
    expect(rule).toContain('White text on these fills fails');
    for (const severity of SEVERITIES) {
      expect(contrastRatio('#ffffff', dark[`--severity-${severity}`]!)).toBeLessThan(
        AA_NORMAL_TEXT,
      );
    }
  });

  it('keeps the focus ring at the published ratios', () => {
    const published = section('**Focus ring.**').match(/([\d.]+)\s*:\s*1 \(dark\) and ([\d.]+)/);
    expect(published).not.toBeNull();
    expect(contrastRatio(dark['--focus-ring']!, dark['--color-bg-base']!)).toBeCloseTo(
      Number(published![1]),
      2,
    );
    expect(contrastRatio(light['--focus-ring']!, light['--color-bg-base']!)).toBeCloseTo(
      Number(published![2]),
      2,
    );
  });

  it('publishes the type scale, and nothing below the 12px floor', () => {
    const rows_ = dataRows(section(TYPE_SECTION));
    // The section's first two rows are families, not steps: their second cell is
    // a stack, not a size.
    const families = new Map(
      rows_.filter((row) => row[1]?.includes(',')).map((row) => [row[0]!, row[1]!]),
    );
    expect(families.get('font.sans')).toBe('Rajdhani, Inter, system-ui fallback');
    expect(families.get('font.mono')).toBe('JetBrains Mono, ui-monospace fallback');
    const published = new Map(
      rows_.filter((row) => /^\d+ \/ \d+$/.test(row[1] ?? '')).map((row) => [row[0]!, row[1]!]),
    );
    expect(published.size, 'no type steps parsed out of §5.4').toBe(6);
    expect(published.get('type.display')).toBe('32 / 36');
    expect(published.get('type.h1')).toBe('24 / 32');
    expect(published.get('type.h2')).toBe('18 / 26');
    expect(published.get('type.body')).toBe('14 / 20');
    expect(published.get('type.body-sm')).toBe('13 / 18');
    expect(published.get('type.caption')).toBe('12 / 16');
    for (const [token, size] of published) {
      expect(Number(size.split('/')[0]), `${token} is below the 12px floor`).toBeGreaterThanOrEqual(
        12,
      );
    }
  });

  it('publishes the spacing, radius, density, icon and rail numbers the config implements', () => {
    expect(section('**Spacing scale (4 px base):**')).toContain('4, 8, 12, 16, 24, 32, 48, 64');
    const scale = section(SCALE_SECTION);
    for (const step of ['4 px inputs and badges', '8 px cards', '12 px modals', '999 px pills']) {
      expect(scale, `design.md no longer publishes ${step}`).toContain(step);
    }
    expect(scale).toContain('comfortable (row 44 px)');
    expect(scale).toContain('compact (row 32 px)');
    expect(scale).toContain('more than 50 rows');
    expect(section(ICON_SECTION)).toContain('16 px in dense contexts and 20 px elsewhere');
    expect(section(SEVERITY_SECTION)).toContain('3 px alert rail');
  });
});
