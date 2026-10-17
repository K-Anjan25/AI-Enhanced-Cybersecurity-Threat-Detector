/**
 * Small decisions the overview makes about *what to say*: which panel state a
 * query is in, what a bucket is called, and which tiles
 * exist.
 *
 * They are pure functions in their own module so the page component is left with
 * layout, and so each rule can be tested at its boundary — the staleness threshold
 * and the bucket labels are exactly the kind of thing that is off by one and only
 * shows up at 04:00.
 */
import { type Severity } from '../../components/ui';
import { type SeverityTally } from './aggregate';
import type { Tile } from './components/KpiTiles';

/** The four states a panel can be in (R-29). */
export type PanelState = 'ready' | 'loading' | 'empty' | 'error';

/**
 * Map a query's status onto a panel state.
 *
 * `empty` is a state and not an absence: a window that returned no rows is a real
 * answer, and R-29 requires it to be said rather than drawn as a blank panel.
 */
export function panelState(status: 'pending' | 'error' | 'success', rowCount: number): PanelState {
  if (status === 'pending') return 'loading';
  if (status === 'error') return 'error';
  return rowCount === 0 ? 'empty' : 'ready';
}

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

/**
 * An x-axis label for a bucket.
 *
 * Built from local date parts rather than a locale formatter so the same instant
 * always renders the same string — a chart whose labels depend on the machine's
 * locale is a chart whose screenshots disagree with its tests.
 */
export function bucketLabel(date: Date, spanMs: number): string {
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  if (spanMs > 86_400_000) {
    return `${MONTHS[date.getMonth()] ?? ''} ${String(date.getDate())} ${hours}:${minutes}`;
  }
  return `${hours}:${minutes}`;
}

/** What the verdict tile knows: the mean, and how many verdicts it covers. */
export interface VerdictSummary {
  meanSeconds: number | null;
  measured: number;
}

/** No verdict recorded in the window — the mean has no basis, not a basis of zero. */
export const NO_VERDICTS: VerdictSummary = { meanSeconds: null, measured: 0 };

/**
 * The mean time to verdict, in whole seconds.
 *
 * Whole seconds because that is the precision the tile is read at -- §4.1 draws
 * "41 s" -- and because the server's milliseconds are an arithmetic detail, not a
 * triage speed an operator can act on. `null` stays `null`: a mean over zero
 * verdicts is not `0 s`.
 */
function meanSeconds(mean: number | null): number | null {
  return mean === null ? null : Math.round(mean);
}

/** The five tiles §4.1 puts across the top, in reading order. */
export function kpiTiles(
  tally: SeverityTally,
  open: number,
  windowLabel: string,
  verdict: VerdictSummary = NO_VERDICTS,
): Tile[] {
  const severityTile = (severity: Severity, label: string): Tile => ({
    label,
    value: tally[severity],
    caption: windowLabel,
    severity,
  });

  return [
    severityTile('critical', 'Critical'),
    severityTile('high', 'High'),
    severityTile('medium', 'Medium'),
    { label: 'Open alerts', value: open, caption: windowLabel },
    {
      // design.md §4.1 draws this tile, and T-416 gave it a source: the aggregate
      // returns the mean over the verdicts *with* a recorded time, plus how many
      // those were. A mean of one verdict is not a trend and a window with none has
      // no mean at all, so the count travels with the figure and the empty case
      // says so instead of showing `0 s` — which would claim instant triage.
      label: 'Mean time to verdict',
      value: meanSeconds(verdict.meanSeconds),
      unit: 's',
      caption:
        verdict.meanSeconds === null
          ? 'no verdict recorded in this window \u00b7 target \u2264 60 s'
          : `${String(verdict.measured)} verdict${verdict.measured === 1 ? '' : 's'} measured \u00b7 target \u2264 60 s`,
    },
  ];
}
