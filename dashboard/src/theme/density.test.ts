/**
 * @vitest-environment node
 */
/**
 * Density modes (T-401, design.md §5.5).
 *
 * The threshold is the only part worth testing: "compact is the default for tables
 * with more than 50 rows" is exclusive, so 50 is comfortable and 51 is compact, and
 * a table cannot disagree with another table about which mode it is in.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  COMPACT_ROW_THRESHOLD,
  defaultDensity,
  ROW_HEIGHT_CLASS,
  ROW_HEIGHT_PX,
  rowHeightClass,
  rowHeightPx,
} from './density';

const design = readFileSync(fileURLToPath(new URL('../../../design.md', import.meta.url)), 'utf8');

describe('density', () => {
  it('puts the threshold where design.md puts it', () => {
    expect(COMPACT_ROW_THRESHOLD).toBe(50);
  });

  it('is comfortable up to and including the threshold', () => {
    for (const rows of [0, 1, 25, 49, 50]) {
      expect(defaultDensity(rows), `${rows} rows`).toBe('comfortable');
    }
  });

  it('is compact above the threshold', () => {
    for (const rows of [51, 200, 1_000]) {
      expect(defaultDensity(rows), `${rows} rows`).toBe('compact');
    }
  });

  it('refuses a row count that is not a count', () => {
    // NaN silently compares false against everything and would render every table
    // comfortable; a negative count is a caller bug, not a density.
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, -1]) {
      expect(() => defaultDensity(bad)).toThrow(RangeError);
    }
  });

  it('publishes the row heights design.md §5.5 publishes, as pixels', () => {
    // A virtualised table positions row `n` at `n * px`, so the number has to be
    // the height the utility actually applies. The figure is read out of §5.5 —
    // "comfortable (row 44 px) and compact (row 32 px)" — not restated.
    const published = /comfortable \(row (\d+) px\) and compact \(row (\d+) px\)/.exec(design);
    expect(published, '§5.5 states both row heights').not.toBeNull();
    const [comfortable, compact] = (published as RegExpExecArray).slice(1).map(Number);

    expect(ROW_HEIGHT_PX).toEqual({ comfortable, compact });
    expect(rowHeightPx('comfortable')).toBe(comfortable);
    expect(rowHeightPx('compact')).toBe(compact);
  });

  it('names the token utility for each mode', () => {
    expect(rowHeightClass('comfortable')).toBe('h-row-comfortable');
    expect(rowHeightClass('compact')).toBe('h-row-compact');
    expect(Object.keys(ROW_HEIGHT_CLASS).sort()).toEqual(['comfortable', 'compact']);
  });
});
