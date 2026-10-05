/**
 * @vitest-environment node
 */
/**
 * Contrast regression test (T-401 acceptance criterion).
 *
 * design.md §5 publishes a contrast ratio for every text token. This test reads
 * the real values out of src/index.css and recomputes each ratio, so a token
 * cannot drift away from the documented accessibility guarantee.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { AA_LARGE_AND_UI, AA_NORMAL_TEXT, contrastRatio } from '../lib/contrast';

const css = readFileSync(fileURLToPath(new URL('../index.css', import.meta.url)), 'utf8');

/** Extract the `--name: #hex` pairs declared inside one selector block. */
function blockFor(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  expect(start, `selector ${selector} not found in index.css`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf('{', start);
  const close = css.indexOf('}', open);
  const body = css.slice(open + 1, close);
  const tokens: Record<string, string> = {};
  for (const match of body.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    tokens[match[1] as string] = match[2] as string;
  }
  return tokens;
}

const dark = blockFor("[data-theme='dark']");
const light = blockFor("[data-theme='light']");

/** Every severity level, so a new one cannot skip the accessibility checks. */
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info', 'benign'] as const;

describe.each([
  ['dark', dark],
  ['light', light],
])('%s theme', (_theme, tokens) => {
  it('defines every required token', () => {
    const required = [
      '--color-bg-base',
      '--color-bg-surface',
      '--color-border',
      '--color-text-primary',
      '--color-text-muted',
      '--color-accent',
      '--color-on-severity',
    ];
    for (const name of required) {
      expect(tokens[name], `missing ${name}`).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
    for (const severity of SEVERITIES) {
      expect(tokens[`--severity-${severity}`], `missing base hue for ${severity}`).toBeDefined();
      expect(
        tokens[`--severity-text-${severity}`],
        `missing text variant for ${severity}`,
      ).toBeDefined();
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

  it('has a focus ring visible against the page background', () => {
    const ratio = contrastRatio(tokens['--focus-ring']!, tokens['--color-bg-base']!);
    expect(ratio).toBeGreaterThanOrEqual(AA_LARGE_AND_UI);
  });
});

describe('token themes', () => {
  it('does not use white badge text, which fails on the severity fills', () => {
    // Guards the specific failure documented in design.md §5.3.
    for (const tokens of [dark, light]) {
      expect(tokens['--color-on-severity']).not.toBe('#ffffff');
      for (const severity of SEVERITIES) {
        expect(contrastRatio('#ffffff', tokens[`--severity-${severity}`]!)).toBeLessThan(
          AA_NORMAL_TEXT,
        );
      }
    }
  });
});
