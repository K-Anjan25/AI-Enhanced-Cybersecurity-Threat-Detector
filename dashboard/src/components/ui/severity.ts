/**
 * The severity scale, as design.md §5.3 publishes it.
 *
 * One source for the level names and their word labels, so a component cannot
 * invent a seventh level. Colour is never the only encoding (NFR-09): every
 * severity carries its word label, so no symbol is needed.
 *
 * `severity.test.ts` reads the table in §5.3 and asserts these values against it.
 */

export const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info', 'benign'] as const;

export type Severity = (typeof SEVERITIES)[number];

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
