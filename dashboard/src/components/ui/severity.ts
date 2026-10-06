/**
 * The severity scale, as design.md §5.3 publishes it.
 *
 * One source for the level names, the labels and the glyphs, so a component cannot
 * invent a seventh level or a different mark for an existing one. The glyph is not
 * decoration: §5.3 pairs every level with one, and NFR-09 forbids colour as the
 * only encoding — a badge, a rail or a pill carries both.
 *
 * `severity.test.ts` reads the table in §5.3 and asserts these values against it.
 */

export const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info', 'benign'] as const;

export type Severity = (typeof SEVERITIES)[number];

/** §5.3, Glyph column: filled for high and above, half for medium, hollow below. */
export const SEVERITY_GLYPHS: Record<Severity, string> = {
  critical: '\u25CF', // ● filled, with a solid ring
  high: '\u25CF', // ● filled
  medium: '\u25D0', // ◐ half
  low: '\u25CB', // ○ hollow
  info: '\u25CB', // ○ hollow
  benign: '\u2713', // ✓
};

/** Title-case labels, so a badge reads "Critical" rather than "critical". */
export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
  benign: 'Benign',
};

/** Narrow an arbitrary string to a severity, for data arriving from the API. */
export function isSeverity(value: string): value is Severity {
  return (SEVERITIES as readonly string[]).includes(value);
}
