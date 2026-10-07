/**
 * The overview's arithmetic: one aggregate in, panel data out.
 *
 * Before T-416 this module counted rows the browser had *read*, which is why every
 * function here took `AlertRow[]` and why the page had to admit a partial window
 * past the page cap. The server now aggregates where the rows are, so this module
 * is the opposite kind of code: a handful of pure, total mappings from the wire
 * shape (`GET /api/v1/overview`) to the shapes the panels render. Keeping them
 * pure and separate is still the point — a mapping is exactly where a screen can
 * lie without looking wrong.
 *
 * Two rules are encoded rather than assumed, and both are about not losing a row:
 *
 *   * **Unknown bands are counted, not dropped.** The API's `severity` column is a
 *     checked enum (T-321) and the palette is the client's own list, so they can
 *     disagree: a band the palette does not know lands in `unrecognised` so the
 *     tiles still add up to the window's own total (`alerts`).
 *   * **A blank family is a fact, not a gap.** The server sends `(unnamed)` for an
 *     attribution the model did not make, and the mix renders it as a bar rather
 *     than dropping it — dropped, the bars would not add up to the window.
 */
import { SEVERITIES, type Severity } from '../../components/ui/severity';
import type { OverviewBucket, OverviewEntity, OverviewFamily, OverviewTotals } from './api';

/** True when the band is one the palette defines. */
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

/**
 * Fold one band map into a tally the palette can render.
 *
 * `total` is the authority on how many rows the map describes. Whatever the known
 * bands do not account for — the server's `unrecognised_severity` plus any band
 * this client's palette has never heard of — is `unrecognised`, so
 * `sum(tally) + unrecognised === total` holds for a bucket the same way it holds
 * for the window.
 */
export function tallyOf(counts: Record<string, number>, total: number): SeverityTally {
  const tally = emptyTally();
  let counted = 0;
  for (const [band, count] of Object.entries(counts)) {
    if (!known(band)) continue;
    tally[band] += count;
    counted += count;
  }
  tally.unrecognised = Math.max(0, total - counted);
  return tally;
}

/** The window's tally, from the totals the endpoint returns. */
export function tallyFromOverview(totals: OverviewTotals): SeverityTally {
  return tallyOf(totals.by_severity, totals.alerts);
}

export interface SeriesPoint {
  /** Inclusive start of the bucket. */
  start: Date;
  counts: SeverityTally;
  total: number;
}

/**
 * The severity series, oldest bucket first.
 *
 * The server buckets the window; this only turns the ISO instants into `Date`s and
 * the band maps into tallies. A bucket's `total` is the authority on its own rows,
 * never the sum of the bands a client happens to know.
 */
export function seriesFromOverview(buckets: readonly OverviewBucket[]): SeriesPoint[] {
  return buckets.map((bucket) => ({
    start: new Date(bucket.start),
    counts: tallyOf(bucket.by_severity, bucket.total),
    total: bucket.total,
  }));
}

/** One entity as the panel renders it. */
export interface EntitySummary {
  entityId: number;
  /** Whether `kind`/`value` name this entity, or it is known only by id. */
  named: boolean;
  kind: string | null;
  value: string | null;
  alerts: number;
  occurrences: number;
  peak: Severity | null;
}

/**
 * The entity list, in the order the server ranked it.
 *
 * Deliberately not re-sorted: the server ranks by alert count with a total
 * tie-break, and a client that re-sorted would be a second opinion about the order
 * — the one thing a "top N" cannot have. A `worst_severity` the palette does not
 * know renders as no pill rather than as a band it made up.
 */
export function entitiesFromOverview(entities: readonly OverviewEntity[]): EntitySummary[] {
  return entities.map((entity) => ({
    entityId: entity.entity_id,
    named: entity.named,
    kind: entity.kind,
    value: entity.value,
    alerts: entity.alerts,
    occurrences: entity.occurrences,
    peak: known(entity.worst_severity) ? entity.worst_severity : null,
  }));
}

export interface FamilySummary {
  family: string;
  count: number;
  peak: Severity | null;
}

/**
 * The family mix, largest first.
 *
 * §7: "Horizontal bars, sorted descending, counts labelled at bar end." The order
 * the server ranked is kept, for the same reason the entity list keeps its own.
 */
export function familiesFromOverview(families: readonly OverviewFamily[]): FamilySummary[] {
  return families.map((family) => ({
    family: family.family,
    count: family.alerts,
    peak: known(family.worst_severity) ? family.worst_severity : null,
  }));
}

/** A change against the previous window, or `null` when there is no basis. */
export interface Delta {
  previous: number;
  change: number;
}

/**
 * The delta shown beside a KPI, and only when both windows are known.
 *
 * A previous window that failed to load would compare a full count against nothing
 * and produce a confident, wrong arrow. `null` renders no delta at all — which is
 * the honest state for "we do not know yet". The completeness question is the
 * caller's: it knows whether the previous number came from a read that succeeded.
 */
export function delta(
  current: number,
  previous: number | null,
  bothComplete: boolean,
): Delta | null {
  if (previous === null || !bothComplete) return null;
  return { previous, change: current - previous };
}
