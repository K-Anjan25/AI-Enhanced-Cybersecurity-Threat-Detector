/**
 * The information architecture's own checks (design.md §3, §5.6).
 *
 * Three things about `nav.ts` cannot be checked by its types, and all three have
 * been wrong here:
 *
 *   1. **An icon per destination, and no two alike.** The type now requires an icon,
 *      so a missing one is a compile error — but the compiler is happy with the same
 *      symbol on two entries, and a rail that draws `Logs` and `Audit log` as the
 *      same picture is a rail where one of them may as well be missing.
 *   2. **The palette and the rail agree.** `navDestinations` is what the command
 *      palette offers; the rail is what exists. A destination dropped from the
 *      flattening is a screen the palette cannot reach without anything failing
 *      loudly, which is the exact defect T-411 created the function to prevent.
 *   3. **No destination is drawn as text.** §3's rail collapses to icons, and the
 *      rail that did that by printing `label.slice(0, 1)` was a column of letters;
 *      its toggle was two guillemets (`«` / `»`), which are quotation marks. Both
 *      were *characters*, so a screenshot looked like it had icons and the fix
 *      looked cosmetic. This scans the source for the family, because a test that
 *      renders the rail cannot see it: `«` is a text node either way — what marks it
 *      as wrong is that no icon exists, and the DOM cannot tell you what is in an
 *      `aria-hidden` svg.
 *
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { ADMIN_SECTIONS, NAV_ITEMS, navDestinations } from './nav';

/** The repository's `src/`, from this file's own location. */
const SRC = new URL('../../', import.meta.url);

/** Every source file under `src/`, relative and slash-separated, tests excluded. */
function sourceFiles(directory: URL, prefix = ''): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = `${prefix}${entry.name}`;
    if (entry.isDirectory()) {
      files.push(...sourceFiles(new URL(`${entry.name}/`, directory), `${path}/`));
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      files.push(path);
    }
  }
  return files.sort();
}

/**
 * A text glyph where an icon belongs.
 *
 * Both spellings, because the characters were written as escapes: the source that
 * rendered `«` contained the six characters `\u00AB`, so scanning for the rendered
 * character alone finds nothing in the file that had the bug.
 */
const TEXT_GLYPH_ICON = /[\u00AB\u00BB]|\\u00AB|\\u00BB/;

describe('the nav model', () => {
  it('gives every destination its own icon', () => {
    const icons = [
      ...NAV_ITEMS.map((item) => item.icon),
      ...ADMIN_SECTIONS.map((section) => section.icon),
    ];

    // The compiler already insists each one exists; this is the half it cannot see.
    // Fourteen destinations share no symbol, so no two rows of the rail are the same
    // picture.
    expect(icons).toHaveLength(NAV_ITEMS.length + ADMIN_SECTIONS.length);
    expect(new Set(icons).size).toBe(icons.length);
  });

  it('offers the palette every destination the rail has, in the rail’s order', () => {
    const expected: string[] = [];
    for (const item of NAV_ITEMS) {
      expected.push(item.to);
      for (const child of item.children ?? []) expected.push(child.to);
    }

    expect(navDestinations().map((destination) => destination.to)).toEqual(expected);
    // And nothing labelled twice with different targets, which is how a palette row
    // navigates to the wrong screen.
    expect(new Set(navDestinations().map((destination) => destination.to)).size).toBe(
      expected.length,
    );
  });

  it('draws no destination or control as a text glyph', () => {
    // The scan's own detector first: a check that cannot see the defect it is for is
    // worse than no check.
    expect(TEXT_GLYPH_ICON.test("collapsed ? '\\u00BB' : '\\u00AB'")).toBe(true);

    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const text = readFileSync(join(SRC.pathname, file), 'utf8');
      for (const [index, line] of text.split('\n').entries()) {
        if (TEXT_GLYPH_ICON.test(line)) offenders.push(`${file}:${String(index + 1)}`);
      }
    }

    expect(offenders, 'use a Lucide icon (design.md §5.6), not a character').toEqual([]);
  });
});
