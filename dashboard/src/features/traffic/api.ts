/**
 * The traffic explorer's one data source (T-418).
 *
 * `GET /api/v1/flows` over a bounded window. Until T-418 this screen read
 * `GET /api/v1/alerts` page by page and aggregated client-side, which is why every
 * number on it was a statement about the *alerted* subset of the traffic: volume was
 * the raw-record count the alerts carried, entities were entity ids, and edges were
 * shared correlation traces. The flow read API counts the traffic itself — ingested
 * records and nothing else — and this module is the one place the screen asks for it.
 *
 * Two things this module deliberately does *not* do:
 *
 *   * **No page walk.** The endpoint's counts are the window's, computed where the rows
 *     are, so there is no `complete: false` to propagate and no cap that quietly
 *     shortens a total. What is still capped is the *lists* (addresses, relationships),
 *     and the response says so with `nodes_capped`/`edges_capped` rather than leaving a
 *     screen to infer it from a length.
 *   * **No client-side filtering of traffic.** `protocol` and `direction` are query
 *     parameters because the read model filters by dimension; a filter applied after
 *     the read could not un-count what it excluded.
 */
import {
  fetchFlowAggregate,
  FLOW_EDGE_LIMIT,
  FLOW_ENTITY_LIMIT,
  type FlowAggregate,
  type FlowDirection,
  type FlowProtocol,
} from '../../api/flows';

export type { FlowAggregate };

export interface TrafficRequest {
  /** Inclusive lower bound of the window (R-34). */
  start: Date;
  /** Exclusive upper bound of the window (R-34). */
  end: Date;
  /** The series' resolution in minutes; the endpoint's default applies when omitted. */
  bucketMinutes?: number | undefined;
  /** `undefined` reads every protocol; otherwise the API narrows the read. */
  protocol?: FlowProtocol | undefined;
  /** `undefined` reads every direction; otherwise the API narrows the read. */
  direction?: FlowDirection | undefined;
  signal?: AbortSignal | undefined;
}

/** Read the window the explorer draws. */
export async function fetchTrafficWindow(request: TrafficRequest): Promise<FlowAggregate> {
  return fetchFlowAggregate({
    start: request.start,
    end: request.end,
    bucketMinutes: request.bucketMinutes,
    protocol: request.protocol,
    direction: request.direction,
    // The lists are asked for at the API's own ceiling: the explorer's controls narrow
    // what is *drawn* from what was read, and a list shortened here would make a
    // control look like it hid traffic that was never fetched.
    entityLimit: FLOW_ENTITY_LIMIT,
    edgeLimit: FLOW_EDGE_LIMIT,
    signal: request.signal,
  });
}
