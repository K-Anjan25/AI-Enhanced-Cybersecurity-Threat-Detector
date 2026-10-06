/**
 * Display formatting — small, pure, and shared, so two panels cannot disagree
 * about what "1,204 flows/s" or "2 m ago" looks like.
 *
 * The age formatter is the one with a rule behind it. design.md §8.1: when live
 * data stops arriving the screen must show `last update 2 m ago` "rather than
 * silently showing old numbers". A number that rounds to zero would read as
 * live, so the first band says "just now" and every later band names its unit.
 * Past a day the unit becomes coarse — an operator reading "3 d ago" is looking
 * at a screen that has been dead for days and needs the magnitude, not seconds.
 */

const SECOND = 1;
const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * A human age for a duration in seconds.
 *
 * Negative input cannot render as "-3 s ago": it lands in the first band. The
 * clamp is defence in depth rather than the mechanism — the mutation battery
 * proved it, because no input distinguishes this line from its absence at the
 * current bands, so the *ordering* of the bands is what the test pins down.
 */
export function formatAge(seconds: number): string {
  const value = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  if (value < 10 * SECOND) return 'just now';
  if (value < MINUTE) return `${String(Math.floor(value / SECOND))} s ago`;
  if (value < HOUR) return `${String(Math.floor(value / MINUTE))} m ago`;
  if (value < DAY) {
    const hours = Math.floor(value / HOUR);
    const minutes = Math.floor((value % HOUR) / MINUTE);
    return minutes === 0 ? `${String(hours)} h ago` : `${String(hours)} h ${String(minutes)} m ago`;
  }
  return `${String(Math.floor(value / DAY))} d ago`;
}

/** Group digits the way the design's examples do ("1,204"). */
export function formatCount(value: number): string {
  return Number.isFinite(value) ? Math.round(value).toLocaleString('en-US') : '—';
}

/** A rate with its unit, e.g. `1,204 flows/s`. */
export function formatRate(perSecond: number, unit: string): string {
  return `${formatCount(perSecond)} ${unit}/s`;
}

/**
 * A latency budget in milliseconds.
 *
 * Sub-second values stay in milliseconds because that is the unit the budgets in
 * architecture.md §5 are published in; above a second the seconds form is what a
 * person reads without arithmetic.
 */
export function formatMilliseconds(ms: number): string {
  if (!Number.isFinite(ms)) return '—';
  if (ms < 1_000) return `${String(Math.round(ms))} ms`;
  return `${(ms / 1_000).toFixed(2)} s`;
}

/** A proportion as a whole-number percentage, for coverage and reject rates. */
export function formatPercent(ratio: number): string {
  if (!Number.isFinite(ratio)) return '—';
  return `${String(Math.round(ratio * 100))}%`;
}
