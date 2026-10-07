/**
 * The traffic explorer's model: the read API's wire shapes, mapped once (T-418).
 *
 * design.md §4.4 asks for four things this feature draws: a time-series of flow volume
 * with the composite score overlaid, an entity table with alert counts, a graph whose
 * nodes are sized by volume and filled by peak severity, and a brush that "filters
 * everything below". Since T-418 the *arithmetic* behind all four happens where the
 * rows are — in the flow read model — and what is left here is the mapping from the
 * wire to what a component wants, plus the brush.
 *
 * Three rules are encoded here rather than left to the components:
 *
 *   * **What the numbers are.** `flows`, `bytes` and `packets` are ingested traffic;
 *     `alerts` and `score` are the alert overlay joined on by the endpoint. A component
 *     cannot render one as the other because they arrive in different fields, and the
 *     caveats that qualify them arrive with them.
 *   * **A bucket has an end.** The API reports each bucket's start (one row per
 *     non-empty bucket, with the empties materialised by the store or the rollup), so
 *     the end is the next bucket's start and the last bucket ends where the window
 *     does — half-open everywhere, so two adjacent buckets never claim one record.
 *   * **Ordering is total.** Addresses are ordered by the API (busiest first, ties by
 *     bytes then address) and the graph's ranked mode depends on that order being
 *     stable between two reads of the same window.
 */
import { SEVERITIES, type Severity } from '../../components/ui/severity';
import type {
  FlowAggregate,
  FlowBucket,
  FlowDirection,
  FlowEdge,
  FlowEntity,
  FlowProtocol,
} from '../../api/flows';

export type { FlowAggregate, FlowDirection, FlowProtocol };

function isKnown(severity: string): severity is Severity {
  return (SEVERITIES as readonly string[]).includes(severity);
}

/** One bucket of the brushable series. */
export interface TrafficBucket {
  /** Inclusive start of the bucket. */
  start: Date;
  /** Exclusive end of the bucket. */
  end: Date;
  /** Flow records in the bucket — traffic, not alerts. */
  flows: number;
  /** Bytes those records carried. */
  bytes: number;
  /** Alerts raised in the bucket, drawn against the traffic. */
  alerts: number;
  /**
   * The mean composite score of the bucket's alerts, or `null` for an empty one.
   *
   * `null` rather than `0`: the score axis is drawn on its own scale, and a zero would
   * draw a line through the floor of an empty bucket — reading as "everything was
   * benign" when the truth is "nothing happened".
   */
  score: number | null;
}

/** One row of the entity table, and one node of the graph. */
export interface TrafficNode {
  /** The address — what the flow read model counts an entity by. */
  id: string;
  /** Flow records in which this address was an end. */
  flows: number;
  bytes: number;
  packets: number;
  /** Records in which it was the destination. */
  inbound: number;
  /** Records in which it was the source. */
  outbound: number;
  /** Alerts whose entity value is this address. */
  alerts: number;
  /** How many of those are still open. */
  openAlerts: number;
  /** The most serious band among them, or `null` when none was recognised. */
  peakSeverity: Severity | null;
  /** The highest score among them, or `null` for an address with no alert. */
  maxScore: number | null;
  firstSeen: string | null;
  lastSeen: string | null;
}

/** One graph edge: two addresses that exchanged traffic, in one direction. */
export interface TrafficEdge {
  /** The source address. */
  source: string;
  /** The destination address. */
  target: string;
  /** Records between them, in that direction. */
  flows: number;
  bytes: number;
}

/** The brush: a selected sub-window, in epoch milliseconds. */
export interface BrushRange {
  from: number;
  to: number;
}

/**
 * The series, with each bucket's end filled in from the next bucket's start.
 *
 * The API's window is the authority on where the series ends: a last bucket that ends
 * anywhere else would leave a gap (or an overlap) between the series and the window the
 * totals describe.
 */
export function trafficSeries(aggregate: FlowAggregate): TrafficBucket[] {
  const windowEnd = Date.parse(aggregate.window.end);
  return aggregate.series.map((bucket: FlowBucket, index) => {
    const next = aggregate.series[index + 1];
    const start = Date.parse(bucket.start);
    return {
      start: new Date(start),
      end: new Date(next === undefined ? windowEnd : Date.parse(next.start)),
      flows: bucket.flows,
      bytes: bucket.bytes,
      alerts: bucket.alerts,
      score: bucket.score,
    };
  });
}

/**
 * Keep buckets whose span overlaps the brush.
 *
 * Overlap rather than containment, and the same rule the in-process rollup applies to
 * its minute atoms: a bucket that starts before the brush and ends inside it holds
 * traffic the brush selected, and hiding it would draw a series whose bars do not add
 * up to the selection. Half-open on both ends (`start < to && end > from`), so two
 * adjacent brushes never both claim a bucket.
 */
export function bucketsInBrush(
  buckets: readonly TrafficBucket[],
  range: BrushRange | null,
): TrafficBucket[] {
  if (range === null) return [...buckets];
  return buckets.filter(
    (bucket) => bucket.start.getTime() < range.to && bucket.end.getTime() > range.from,
  );
}

/** The addresses, as the table and the graph want them. */
export function trafficNodes(aggregate: FlowAggregate): TrafficNode[] {
  return aggregate.entities.map((entity: FlowEntity) => ({
    id: entity.ip,
    flows: entity.flows,
    bytes: entity.bytes,
    packets: entity.packets,
    inbound: entity.inbound,
    outbound: entity.outbound,
    alerts: entity.alerts,
    openAlerts: entity.open_alerts,
    peakSeverity:
      entity.worst_severity !== null && isKnown(entity.worst_severity)
        ? entity.worst_severity
        : null,
    maxScore: entity.max_score,
    firstSeen: entity.first_seen,
    lastSeen: entity.last_seen,
  }));
}

/** The relationships, as the graph wants them: directional, weighted by records. */
export function trafficEdges(aggregate: FlowAggregate): TrafficEdge[] {
  return aggregate.edges.map((edge: FlowEdge) => ({
    source: edge.source,
    target: edge.target,
    flows: edge.flows,
    bytes: edge.bytes,
  }));
}
