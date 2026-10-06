/**
 * Density modes (design.md §5.5).
 *
 * "Density modes: comfortable (row 44 px) and compact (row 32 px), persisted per
 * user. Compact is the default for tables with more than 50 rows."
 *
 * One module decides, so two tables cannot disagree about which mode a row count
 * implies, and the class names it hands out are the token-driven utilities from
 * tailwind.config.js — asserted against the compiled stylesheet by
 * src/theme/density.test.ts.
 */

/** Row heights from design.md §5.5, as Tailwind utilities. */
export const ROW_HEIGHT_CLASS = {
  comfortable: 'h-row-comfortable',
  compact: 'h-row-compact',
} as const;

export type Density = keyof typeof ROW_HEIGHT_CLASS;

/** Above this many rows, a table is compact by default (design.md §5.5). */
export const COMPACT_ROW_THRESHOLD = 50;

/**
 * The density a table of this size defaults to.
 *
 * Deliberately exclusive (`>`): the rule is "more than 50 rows", so a 50-row
 * table is still comfortable.
 */
export function defaultDensity(rowCount: number): Density {
  if (!Number.isFinite(rowCount) || rowCount < 0) {
    throw new RangeError(`row count must be a non-negative number, got ${rowCount}`);
  }
  return rowCount > COMPACT_ROW_THRESHOLD ? 'compact' : 'comfortable';
}

/** The class that gives a table row its height in this density. */
export function rowHeightClass(density: Density): string {
  return ROW_HEIGHT_CLASS[density];
}
