/**
 * Ranked, directed flow relationships for the traffic explorer.
 *
 * The relationship panel stays bounded and deterministic: it lists the highest-volume
 * source → destination conversations rather than running a force simulation or building
 * an address-by-address matrix. Work is O(E log E) for the supplied edge list, and only
 * the top `FLOW_RELATIONSHIP_LIMIT` rows are rendered.
 */
import type { TrafficEdge, TrafficNode } from './aggregate';

/** The maximum number of directed conversations rendered in the panel. */
export const FLOW_RELATIONSHIP_LIMIT = 30;

export interface GraphModel {
  /** Visible addresses used to filter drawable relationships. */
  addressCount: number;
  /** Highest observed bytes first, then flow count and stable address order. */
  relationships: TrafficEdge[];
  /** All drawable directed relationships before the display limit. */
  totalRelationships: number;
}

/**
 * Filter relationships to visible endpoints, rank them, then retain a bounded prefix.
 *
 * `TrafficEdge` is directional; source and destination are never collapsed into an
 * undirected pair. Ties are resolved lexically so a refresh cannot reorder equal rows.
 */
export function buildGraph(
  nodes: readonly TrafficNode[],
  edges: readonly TrafficEdge[],
  limit: number = FLOW_RELATIONSHIP_LIMIT,
): GraphModel {
  const endpointIds = new Set(nodes.map((node) => node.id));
  const ranked = edges
    .filter((edge) => endpointIds.has(edge.source) && endpointIds.has(edge.target))
    .sort(
      (left, right) =>
        right.bytes - left.bytes ||
        right.flows - left.flows ||
        left.source.localeCompare(right.source) ||
        left.target.localeCompare(right.target),
    );
  const boundedLimit = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 0;

  return {
    addressCount: nodes.length,
    relationships: ranked.slice(0, boundedLimit),
    totalRelationships: ranked.length,
  };
}
