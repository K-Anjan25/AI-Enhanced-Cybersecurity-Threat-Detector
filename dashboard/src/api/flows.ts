/**
 * The flow read API's wire shapes and path (T-418, FR-52).
 *
 * `GET /api/v1/flows` answers one window of traffic with everything the explorer draws
 * from: the volume series with the alert overlay, the addresses, the relationships and
 * the caveats. One request, one window — so the three panels cannot disagree about
 * which window they describe the way three requests could (the rule D-060 recorded for
 * the overview, here applied to traffic).
 *
 * Four things about this contract are rules rather than formatting:
 *
 *   * **`start` and `end` are mandatory**, and the span is capped by whichever read
 *     model answers — the in-process rollup's own retention (an hour by default) or the
 *     store's 92 days (R-34). `FlowParams` has no defaults for them, so no caller can
 *     build a path that reads "the traffic, as far as it goes"; and every response
 *     carries `source`, so a caller knows which bound applied rather than inferring it.
 *   * **The caveats are carried, not paraphrased.** `caveats` is what the source said
 *     about its own numbers — which read model answered, what a cap did to a list, why
 *     a window is empty. The screen renders them as they arrive, because a reworded
 *     caveat is a second, unreviewed claim about the data (the T-419 rule).
 *   * **A score is `null`, never `0`, where no alert fell.** An empty bucket is not a
 *     benign one, and a zero would draw a line along the floor of a quiet interval.
 *   * **Nothing absolute** (R-23): `src/api/client.ts` turns this path into a URL.
 */
import { getJson, query } from './client';

/** The protocols `flow@1` defines. */
export const FLOW_PROTOCOLS = ['tcp', 'udp', 'icmp'] as const;
export type FlowProtocol = (typeof FLOW_PROTOCOLS)[number];

/** The directions `flow@1` defines. */
export const FLOW_DIRECTIONS = ['inbound', 'outbound', 'internal'] as const;
export type FlowDirection = (typeof FLOW_DIRECTIONS)[number];

/** Which read model answered: the flow store, or the process's own rollup. */
export type FlowSource = 'store' | 'rollup';

/** One point of the volume series, with the alert overlay drawn against it. */
export interface FlowBucket {
  /** Inclusive lower bound of the bucket, ISO-8601 with an offset. */
  start: string;
  /** Flow records in the bucket. */
  flows: number;
  /** Bytes those records carried. */
  bytes: number;
  /** Packets those records carried. */
  packets: number;
  /** Alerts raised in the bucket. */
  alerts: number;
  /** Mean composite score of those alerts, or `null` for a bucket that held none. */
  score: number | null;
}

/** One address's share of the window, and the alerts that attach to it. */
export interface FlowEntity {
  /** The address, as it appeared on the wire. */
  ip: string;
  /** Records in which it was an end. */
  flows: number;
  bytes: number;
  packets: number;
  /** Records in which it was the destination. */
  inbound: number;
  /** Records in which it was the source. */
  outbound: number;
  first_seen: string | null;
  last_seen: string | null;
  /** Alerts in the window whose entity value is this address. */
  alerts: number;
  open_alerts: number;
  worst_severity: string | null;
  max_score: number | null;
}

/** One directional relationship: two addresses that exchanged traffic. */
export interface FlowEdge {
  source: string;
  target: string;
  flows: number;
  bytes: number;
}

/** The window's counts, and what each cap did to the lists above them. */
export interface FlowTotals {
  flows: number;
  bytes: number;
  packets: number;
  /** Distinct addresses in the window — every one of them, cap or no cap. */
  nodes: number;
  /** Distinct directional pairs in the window. */
  edges: number;
  /** True when more addresses were seen than the entity list holds. */
  nodes_capped: boolean;
  /** True when more relationships were seen than the edge list holds. */
  edges_capped: boolean;
  /** Records the in-process rollup could not attribute to an address. Always 0 for a store. */
  untracked_address_flows: number;
  /** Records the in-process rollup could not attribute to a pair. */
  untracked_pair_flows: number;
}

/** The window a read answered about, echoed so a caller never guesses it. */
export interface FlowWindow {
  start: string;
  end: string;
  hours: number;
}

/** The narrowing the read applied, so a filter is never invisible on the wire. */
export interface FlowFilters {
  protocol: string | null;
  direction: string | null;
}

/** One window of traffic: the three panels, the counts behind them and the caveats. */
export interface FlowAggregate {
  window: FlowWindow;
  bucket_minutes: number;
  source: FlowSource;
  filters: FlowFilters;
  series: FlowBucket[];
  entities: FlowEntity[];
  edges: FlowEdge[];
  totals: FlowTotals;
  caveats: string[];
}

/** What one read asks for. */
export interface FlowParams {
  /** Inclusive lower bound of the window (R-34). */
  start: Date;
  /** Exclusive upper bound of the window (R-34). */
  end: Date;
  /** The series' resolution; the server's default applies when omitted. */
  bucketMinutes?: number | undefined;
  /** How many addresses the list holds. The counts are unaffected. */
  entityLimit?: number | undefined;
  /** How many relationships the list holds. The counts are unaffected. */
  edgeLimit?: number | undefined;
  /** Narrow to one protocol, or `undefined` for every protocol. */
  protocol?: FlowProtocol | undefined;
  /** Narrow to one direction, or `undefined` for all of them. */
  direction?: FlowDirection | undefined;
  signal?: AbortSignal | undefined;
}

/** How many addresses and relationships the explorer asks for. */
export const FLOW_ENTITY_LIMIT = 200;
export const FLOW_EDGE_LIMIT = 400;

function flowPath(params: FlowParams): string {
  return `/api/v1/flows${query({
    start: params.start.toISOString(),
    end: params.end.toISOString(),
    bucket_minutes: params.bucketMinutes,
    entity_limit: params.entityLimit,
    edge_limit: params.edgeLimit,
    protocol: params.protocol,
    direction: params.direction,
  })}`;
}

/** Read one window of traffic: the series, the addresses, the relationships. */
export async function fetchFlowAggregate(params: FlowParams): Promise<FlowAggregate> {
  return getJson<FlowAggregate>(flowPath(params), { signal: params.signal });
}
