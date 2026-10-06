/**
 * The traffic explorer's arithmetic: rows in, a brushable series and an entity
 * model out.
 *
 * design.md §4.4 asks for four things this file computes and nothing else draws:
 * a time-series of flow volume with the composite score overlaid, an entity table
 * with alert counts, a graph whose nodes are sized by volume and filled by peak
 * severity, and a brush that "filters everything below".
 *
 * Four rules are encoded here rather than left to the components, because this is
 * where a traffic view can lie without looking wrong:
 *
 *   * **What the numbers actually are.** This build has no read API for ingested
 *     flows — only for alerts (T-305) — so "flow volume" here is the **record count
 *     the alerts carry** (`occurrence_count`, the raw records that were grouped into
 *     each alert) and the entity table counts *alerted* entities. The series says so
 *     on screen and the gap is filed as T-418 rather than presented as total traffic.
 *   * **Every row lands in a bucket.** A row outside the window is clamped into the
 *     nearest bucket, so a bucket's record count always adds up to the rows read.
 *   * **Edges are evidence, not decoration.** The alert row carries the `trace_id`
 *     of the ingest request that opened its case, so an edge means "these two
 *     entities were raised in the same correlation trace", weighted by how many
 *     traces they shared. design.md asks for flow-count weights; that needs the
 *     flow read API too, and inventing a number here would make the graph look
 *     more informative than it is.
 *   * **Ordering is total.** Ties break by id, never by input order, so two
 *     refreshes of the same data produce the same screen — and so the adjacency
 *     matrix, which is ranked, is stable between renders.
 */
import { SEVERITIES, type Severity } from '../../components/ui/severity';
import type { AlertRow } from '../../api/alerts';

/** Severity, most serious first — the order the palette is declared in (§5.3). */
const RANK: readonly Severity[] = SEVERITIES;

function rankOf(severity: string): number {
  const index = RANK.indexOf(severity as Severity);
  return index === -1 ? RANK.length : index;
}

function isKnown(severity: string): severity is Severity {
  return (SEVERITIES as readonly string[]).includes(severity);
}

/** One bucket of the brushable series. */
export interface TrafficBucket {
  /** Inclusive start of the bucket. */
  start: Date;
  /** Exclusive end of the bucket. */
  end: Date;
  /** Alerts whose `created_at` falls in this bucket. */
  alerts: number;
  /** Raw records those alerts grouped (`occurrence_count` summed). */
  records: number;
  /**
   * The mean composite score of the bucket's alerts, or `null` for an empty one.
   *
   * `null` rather than `0`: the score axis is drawn on its own scale, and a zero
   * would draw a line through the floor of an empty bucket — reading as "everything
   * was benign" when the truth is "nothing happened".
   */
  score: number | null;
}

export interface SeriesRequest {
  start: Date;
  end: Date;
  buckets: number;
}

/** Rows counted per bucket, tiling the window exactly. */
export function trafficSeries(rows: readonly AlertRow[], request: SeriesRequest): TrafficBucket[] {
  const { start, end, buckets } = request;
  if (buckets < 1) throw new RangeError('a series needs at least one bucket');
  const span = end.getTime() - start.getTime();
  if (!(span > 0)) throw new RangeError('a series window must end after it starts');

  const width = span / buckets;
  const totals = Array.from({ length: buckets }, () => ({ alerts: 0, records: 0, score: 0 }));
  const series: TrafficBucket[] = Array.from({ length: buckets }, (_unused, index) => ({
    start: new Date(start.getTime() + index * width),
    end: new Date(start.getTime() + (index + 1) * width),
    alerts: 0,
    records: 0,
    score: null,
  }));

  for (const row of rows) {
    const at = Date.parse(row.created_at);
    if (Number.isNaN(at)) continue;
    const raw = Math.floor((at - start.getTime()) / width);
    const index = Math.min(buckets - 1, Math.max(0, raw));
    const total = totals[index];
    if (total === undefined) continue;
    total.alerts += 1;
    total.records += Number.isFinite(row.occurrence_count) ? row.occurrence_count : 0;
    total.score += Number.isFinite(row.score) ? row.score : 0;
  }

  return series.map((bucket, index) => {
    const total = totals[index] ?? { alerts: 0, records: 0, score: 0 };
    return {
      ...bucket,
      alerts: total.alerts,
      records: total.records,
      score: total.alerts === 0 ? null : total.score / total.alerts,
    };
  });
}

/** One row of the entity table, and one node of the graph. */
export interface EntityRow {
  entityId: number;
  /** Alerts in the window for this entity. */
  alerts: number;
  /** Raw records those alerts grouped — the §4.4 "volume". */
  records: number;
  /** The most serious severity seen, or `null` when none was recognised. */
  peakSeverity: Severity | null;
  /** True when at least one of the entity's alerts is still open. */
  hasOpen: boolean;
  families: string[];
  firstSeen: string;
  lastSeen: string;
  /** Distinct correlation traces the entity appears in. */
  traces: number;
}

/** Fold rows into one entry per entity, ordered by volume then id. */
export function entityRows(rows: readonly AlertRow[]): EntityRow[] {
  const byEntity = new Map<number, EntityRow & { traceIds: Set<string>; familySet: Set<string> }>();

  for (const row of rows) {
    const entityId = row.entity_id;
    let entry = byEntity.get(entityId);
    if (entry === undefined) {
      entry = {
        entityId,
        alerts: 0,
        records: 0,
        peakSeverity: null,
        hasOpen: false,
        families: [],
        firstSeen: row.first_seen,
        lastSeen: row.last_seen,
        traces: 0,
        traceIds: new Set<string>(),
        familySet: new Set<string>(),
      };
      byEntity.set(entityId, entry);
    }
    entry.alerts += 1;
    entry.records += Number.isFinite(row.occurrence_count) ? row.occurrence_count : 0;
    if (
      isKnown(row.severity) &&
      (entry.peakSeverity === null || rankOf(row.severity) < rankOf(entry.peakSeverity))
    ) {
      entry.peakSeverity = row.severity;
    }
    if (row.status === 'open') entry.hasOpen = true;
    entry.familySet.add(row.family);
    if (row.trace_id !== null) entry.traceIds.add(row.trace_id);
    // Compared as instants, not strings: a payload with a different offset would
    // sort wrongly as text (T-404's rule).
    if (Date.parse(row.first_seen) < Date.parse(entry.firstSeen)) entry.firstSeen = row.first_seen;
    if (Date.parse(row.last_seen) > Date.parse(entry.lastSeen)) entry.lastSeen = row.last_seen;
  }

  return [...byEntity.values()]
    .map((entry) => ({
      entityId: entry.entityId,
      alerts: entry.alerts,
      records: entry.records,
      peakSeverity: entry.peakSeverity,
      hasOpen: entry.hasOpen,
      families: [...entry.familySet].sort(),
      firstSeen: entry.firstSeen,
      lastSeen: entry.lastSeen,
      traces: entry.traceIds.size,
    }))
    .sort((left, right) => right.records - left.records || left.entityId - right.entityId);
}

/** One graph edge: two entities raised in the same correlation traces. */
export interface EntityEdge {
  /** Always the smaller id first, so an edge has one spelling. */
  source: number;
  target: number;
  /** How many distinct traces raised alerts for both entities. */
  sharedTraces: number;
}

/**
 * Edges from shared correlation traces.
 *
 * A trace that raised alerts for one entity produces no edge (an edge needs two
 * ends), and a trace raising an alert for the *same* entity twice produces none
 * either — a self-loop is not a relationship. Pairs are keyed smaller-id-first so
 * `(3,9)` and `(9,3)` are one edge counted twice, not two edges counted once each.
 */
export function entityEdges(rows: readonly AlertRow[]): EntityEdge[] {
  const byTrace = new Map<string, Set<number>>();
  for (const row of rows) {
    if (row.trace_id === null) continue;
    const entities = byTrace.get(row.trace_id) ?? new Set<number>();
    entities.add(row.entity_id);
    byTrace.set(row.trace_id, entities);
  }

  const counts = new Map<string, EntityEdge>();
  for (const entities of byTrace.values()) {
    const ids = [...entities].sort((left, right) => left - right);
    for (let i = 0; i < ids.length; i += 1) {
      for (let j = i + 1; j < ids.length; j += 1) {
        const source = ids[i] as number;
        const target = ids[j] as number;
        const key = `${String(source)}-${String(target)}`;
        const existing = counts.get(key);
        counts.set(key, { source, target, sharedTraces: (existing?.sharedTraces ?? 0) + 1 });
      }
    }
  }

  return [...counts.values()].sort(
    (left, right) =>
      right.sharedTraces - left.sharedTraces ||
      left.source - right.source ||
      left.target - right.target,
  );
}

/** The brush: a selected sub-window, in epoch milliseconds. */
export interface BrushRange {
  from: number;
  to: number;
}

/**
 * Keep rows whose instant is inside the brush, half-open on the right.
 *
 * Half-open (`from <= t < to`) for the same reason the API's window is: two
 * adjacent brushes must not both claim a row that sits exactly on the boundary.
 */
export function rowsInBrush(rows: readonly AlertRow[], range: BrushRange | null): AlertRow[] {
  if (range === null) return [...rows];
  return rows.filter((row) => {
    const at = Date.parse(row.created_at);
    return !Number.isNaN(at) && at >= range.from && at < range.to;
  });
}
