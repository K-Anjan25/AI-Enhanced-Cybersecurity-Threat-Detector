/**
 * @vitest-environment node
 */
/**
 * Motion tokens (T-402, design.md §8.2).
 *
 * §8.2 is four sentences, and every one of them is checkable:
 *
 *   * "Durations: 120 ms micro-feedback, 200 ms panels, 300 ms page transitions."
 *   * "Nothing over 300 ms."
 *   * "Easing: `ease-out` for entering, `ease-in` for leaving."
 *   * "**All** motion respects `prefers-reduced-motion: reduce`."
 *
 * T-402 is the first task to make anything move (the Button's colour feedback, the
 * nav rail's width, the spinner), so it declares the durations and the guard. The
 * numbers are read back out of the document rather than restated, so a revision to
 * §8.2 fails here instead of shipping.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const INDEX_CSS = fileURLToPath(new URL('../index.css', import.meta.url));
const CONFIG_PATH = fileURLToPath(new URL('../../tailwind.config.js', import.meta.url));
const SRC = fileURLToPath(new URL('..', import.meta.url));
const design = readFileSync(fileURLToPath(new URL('../../../design.md', import.meta.url)), 'utf8');
const css = readFileSync(INDEX_CSS, 'utf8');

interface TailwindConfig {
  theme: { extend: { transitionDuration: Record<string, string> } };
}

const config = ((await import(CONFIG_PATH)) as { default: TailwindConfig }).default;

/** The three named durations, in the order §8.2 names them. */
const TOKENS = ['micro', 'panel', 'page'] as const;
type Token = (typeof TOKENS)[number];

function section(heading: string): string {
  const start = design.indexOf(heading);
  expect(start, `${heading} is in design.md`).toBeGreaterThanOrEqual(0);
  const end = design.indexOf('\n### ', start + heading.length);
  return design.slice(start, end === -1 ? undefined : end);
}

/** `--duration-x: 120ms;` out of the token layer. */
function declared(token: Token): number {
  const match = new RegExp(`--duration-${token}:\\s*(\\d+)ms;`).exec(css);
  expect(match, `--duration-${token} is declared`).not.toBeNull();
  return Number((match as RegExpExecArray)[1]);
}

/** Every `--duration-*` declaration in the stylesheet. */
function everyDeclaredDuration(): number[] {
  return [...css.matchAll(/--duration-[a-z-]+:\s*\d+ms;/g)].map((match) =>
    Number(/\d+/.exec(match[0])?.[0]),
  );
}

/** Shipped sources: everything under src/ that is not a test. */
function shipped(): [string, string][] {
  const found: [string, string][] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(path);
      } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
        found.push([path.slice(SRC.length + 1), readFileSync(path, 'utf8')]);
      }
    }
  };
  walk(SRC);
  return found;
}

const motion = section('### 8.2 Motion');

describe('motion tokens', () => {
  it('declares the three durations design.md §8.2 publishes', () => {
    const published =
      /Durations:\s*(\d+) ms micro-feedback,\s*(\d+) ms panels,\s*(\d+) ms page/.exec(motion);
    expect(published, '§8.2 states the three durations').not.toBeNull();
    const [micro, panel, page] = (published as RegExpExecArray).slice(1).map(Number);

    expect(declared('micro')).toBe(micro);
    expect(declared('panel')).toBe(panel);
    expect(declared('page')).toBe(page);
  });

  it('publishes nothing over the documented ceiling', () => {
    const ceiling = /Nothing over (\d+) ms/.exec(motion);
    expect(ceiling, '§8.2 states the ceiling').not.toBeNull();
    const limit = Number((ceiling as RegExpExecArray)[1]);

    const durations = everyDeclaredDuration();
    expect(durations.length).toBeGreaterThanOrEqual(TOKENS.length);
    for (const value of durations) expect(value).toBeLessThanOrEqual(limit);
  });

  it('disables animation and transitions under prefers-reduced-motion', () => {
    expect(motion).toMatch(/prefers-reduced-motion: reduce/);

    const start = css.indexOf('@media (prefers-reduced-motion: reduce)');
    expect(start, 'the guard is in the token layer').toBeGreaterThanOrEqual(0);
    const guard = css.slice(start, css.indexOf('@layer base {', start));

    // Animation and transition both, and the iteration count too: a spinner that
    // keeps spinning on a single 1 ms frame is still motion.
    expect(guard).toMatch(/animation-duration:\s*1ms\s*!important/);
    expect(guard).toMatch(/animation-iteration-count:\s*1\s*!important/);
    expect(guard).toMatch(/transition-duration:\s*1ms\s*!important/);
  });

  it('maps each duration to a utility, and to the variable it declares', () => {
    const utilities = config.theme.extend.transitionDuration;
    expect(Object.keys(utilities).sort()).toEqual([...TOKENS].sort());
    for (const token of TOKENS) expect(utilities[token]).toBe(`var(--duration-${token})`);
  });

  it('uses no duration utility outside the three, in shipped sources', () => {
    const used = new Set<string>();
    for (const [, source] of shipped()) {
      for (const match of source.matchAll(/\bduration-([a-z[\]0-9-]+)/g)) {
        const token = match[1] ?? '';
        // `transition-duration` in prose is not a class; class names here are the
        // utilities, which are single words.
        if (token.startsWith('[')) continue;
        used.add(token);
      }
    }
    expect([...used].sort()).toEqual(['micro', 'panel']);
  });

  it('uses only the easings §8.2 publishes', () => {
    const published = new Set(['out', 'in']);
    for (const [name, source] of shipped()) {
      for (const match of source.matchAll(/\bease-([a-z-]+)/g)) {
        const easing = match[1] ?? '';
        expect(published.has(easing), `${name} uses ease-${easing}`).toBe(true);
      }
    }
  });
});
