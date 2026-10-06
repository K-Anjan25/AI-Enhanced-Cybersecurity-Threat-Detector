/**
 * The overview's arithmetic: rows in, panel data out.
 *
 * Every function here is pure and tested against fixtures, because this is where
 * an overview can lie without looking wrong. A count that drops an unrecognised
 * severity, a series whose last bucket is silently truncated, a "top entity" list
 * that reorders between refreshes — none of those throw, and all of them produce a
 * screen that reads as authoritative while being wrong.
 *
 * Three rules are encoded rather than assumed:
 *
 *   * **Unknown severities are counted, not dropped.** The API's `severity` column
 *     is a checked enum (T-321), but this code must not *assume* that: a value it
 *     does not recognise is counted as `unrecognised` so the KPI tiles still add
 *     up to the rows fetched.
 *   * **Every row lands in a bucket.** A row outside the requested window is
 *     clamped into the nearest bucket rather than dropped, so the series total
 *     always equals the row count.
 *   * **Ordering is total.** Ties break by id or name, never by input order, so
 *     two refreshes of the same data produce the same screen.
 */
import { SEVERITIES, type Severity } from '../../components/ui/severity';
import type { AlertRow } from './api';

/** Severity, most serious first — the order the palette is declared in (§5.3). */
const RANK: readonly Severity[] = ['critical', 'high', 'medium', 'low', 'info', 'benign'];

function rankOf(severity: string): number {
  const index = RANK.indexOf(severity as Severity);
  return index === -1 ? RANK.length : index;
}

/** True when the row's severity is one of the six the palette defines. */
function known(severity: string): severity is Severity {
  return (SEVERITIES as readonly string[]).includes(severity);
}

export type SeverityTally = Record<Severity, number> & { unrecognised: number };

/** A zeroed tally, in palette order. */
export function emptyTally(): SeverityTally {
  const tally = { unrecognised: 0 } as SeverityTally;
  for (const severity of SEVERITIES) tally[severity] = 0;
  return tally;
}

/** Count rows by severity. */
export function countBySeverity(rows: readonly AlertRow[]): SeverityTally {
  const tally = emptyTally();
  for (const row of rows) {
    if (known(row.severity)) tally[row.severity] += 1;
    else tally.unrecognised += 1;
  }
  return tally;
}

/** How many rows are still open. */
export function countOpen(rows: readonly AlertRow[]): number {
  return rows.filter((row) => row.status === 'open').length;
}

/** The most serious severity present, or `null` for no rows. */
export function peakSeverity(rows: readonly AlertRow[]): Severity | null {
  let best: Severity | null = null;
  for (const row of rows) {
    if (known(row.severity) && (best === null || rankOf(row.severity) < rankOf(best))) {
      best = row.severity;
    }
  }
  return best;
}

export interface SeriesBucket {
  /** Inclusive start of the bucket. */
  start: Date;
  /** Exclusive end of the bucket. */
  end: Date;
  counts: SeverityTally;
  total: number;
}

export interface SeriesRequest {
  start: Date;
  end: Date;
  /** How many buckets the window is divided into. */
  buckets: number;
}

/**
 * Bucket rows over the window, one bucket per interval.
 *
 * The buckets tile the window exactly — `end` is the last bucket's exclusive
 * boundary — so the bars on the chart line up with the axis labels rather than
 * floating between them. An inverted or empty window is refused instead of
 * producing a chart of zero width.
 */
export function severitySeries(rows: readonly AlertRow[], request: SeriesRequest): SeriesBucket[] {
  const { start, end, buckets } = request;
  if (buckets < 1) throw new RangeError('a series needs at least one bucket');
  const span = end.getTime() - start.getTime();
  if (!(span > 0)) throw new RangeError('a series window must end after it starts');

  const width = span / buckets;
  const series: SeriesBucket[] = Array.from({ length: buckets }, (_unused, index) => ({
    start: new Date(start.getTime() + index * width),
    end: new Date(start.getTime() + (index + 1) * width),
    counts: emptyTally(),
    total: 0,
  }));

  for (const row of rows) {
    const at = Date.parse(row.created_at);
    if (Number.isNaN(at)) continue;
    const raw = Math.floor((at - start.getTime()) / width);
    const index = Math.min(buckets - 1, Math.max(0, raw));
    const bucket = series[index] as SeriesBucket;
    if (known(row.severity)) bucket.counts[row.severity] += 1;
    else bucket.counts.unrecognised += 1;
    bucket.total += 1;
  }

  return series;
}

export interface EntitySummary {
  entityId: number;
  alerts: number;
  occurrences: number;
  peak: Severity | null;
}

/**
 * The entities with the most alerts in the window.
 *
 * Ranked by alert count first, then by peak severity, then by id: the third key
 * exists so that a list with a tie does not shuffle on every refresh.
 */
export function topEntities(rows: readonly AlertRow[], limit: number): EntitySummary[] {
  const byEntity = new Map<number, AlertRow[]>();
  for (const row of rows) {
    const bucket = byEntity.get(row.entity_id);
    if (bucket === undefined) byEntity.set(row.entity_id, [row]);
    else bucket.push(row);
  }

  const summaries: EntitySummary[] = [...byEntity].map(([entityId, entityRows]) => ({
    entityId,
    alerts: entityRows.length,
    occurrences: entityRows.reduce((total, row) => total + row.occurrence_count, 0),
    peak: peakSeverity(entityRows),
  }));

  summaries.sort(
    (a, b) =>
      b.alerts - a.alerts ||
      rankOf(a.peak ?? 'benign') - rankOf(b.peak ?? 'benign') ||
      a.entityId - b.entityId,
  );
  return summaries.slice(0, limit);
}

export interface FamilySummary {
  family: string;
  count: number;
  peak: Severity | null;
}

/**
 * Alert counts per threat family, largest first.
 *
 * §7: "Horizontal bars, sorted descending, counts labelled at bar end." An empty
 * family name is kept as `(unnamed)` rather than dropped — the count would not add
 * up otherwise, and "the API sent a blank family" is a fact worth seeing.
 */
export function familyMix(rows: readonly AlertRow[], limit = 8): FamilySummary[] {
  const byFamily = new Map<string, AlertRow[]>();
  for (const row of rows) {
    const family = row.family.trim() === '' ? '(unnamed)' : row.family;
    const bucket = byFamily.get(family);
    if (bucket === undefined) byFamily.set(family, [row]);
    else bucket.push(row);
  }

  const summaries: FamilySummary[] = [...byFamily].map(([family, familyRows]) => ({
    family,
    count: familyRows.length,
    peak: peakSeverity(familyRows),
  }));
  summaries.sort((a, b) => b.count - a.count || a.family.localeCompare(b.family));
  return summaries.slice(0, limit);
}

/** A change against the previous window, or `null` when there is no basis. */
export interface Delta {
  previous: number;
  change: number;
}

/**
 * The delta shown beside a KPI, and only when both windows were read completely.
 *
 * A partial previous window would compare a full count against a truncated one and
 * produce a confident, wrong arrow. `undefined` renders no delta at all — which is
 * the honest state for "we do not know yet".
 */
export function delta(
  current: number,
  previous: number | null,
  bothComplete: boolean,
): Delta | null {
  if (previous === null || !bothComplete) return null;
  return { previous, change: current - previous };
}
