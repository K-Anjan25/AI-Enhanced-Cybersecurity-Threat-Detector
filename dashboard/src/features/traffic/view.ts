/**
 * The traffic explorer's view model: one pipeline, one place where a filter is applied.
 *
 * design.md §4.4's promise is that "brushing filters everything below", and since T-418
 * the way to keep that promise is different from before — and stronger. The brush is no
 * longer applied to a row set in the browser; a committed brush is a **new window**, and
 * the page re-reads it from the flow API (`hooks.ts`). Every number below the series is
 * then the server's own count for the brushed window, which is what the panel's caption
 * claims and what a client-side filter over an already-aggregated list could not do: a
 * list of the window's top addresses cannot be re-narrowed to a sub-window after the
 * fact, because the addresses it left out are exactly the ones the sub-window might have
 * had.
 *
 * So this module holds the parts that really are view state:
 *
 *   1. `nodes` and `edges` come from the aggregate for the window on screen — the
 *      brushed window when a brush is set, the whole window otherwise.
 *   2. the entity controls (`minFlows`, `openAlertsOnly`) narrow that list, because
 *      they are thresholds over the aggregate rather than questions the API answers.
 *   3. pinning — last, and *widening* rather than narrowing: a pinned address keeps its
 *      neighbours in view, because the question a pin asks is "what is this address
 *      connected to?".
 *
 * And the caveats: the source's own sentences are carried through **verbatim** (the
 * T-419 rule — a reworded caveat is a second, unreviewed claim about the data), with
 * only the client-side facts added: which sub-window the numbers describe, how many
 * entities the controls hid, and what the ranked matrix left undrawn.
 *
 * What this module does *not* own any more: the selection's caption. The brush used
 * to filter a bucket list in the browser, and this module reported the selected
 * buckets in words for a caption under the chart. Since T-418 the chart's own
 * `spanLabel` states the range it has selected (the brush is the chart's state), and
 * the three things left over here — `brushed`, `brushLabel` and `bucketsInBrush` —
 * were dead code kept alive by their own tests. The audit removed them: a helper
 * nothing renders is a sentence nothing says.
 */
import {
  trafficEdges,
  trafficNodes,
  trafficSeries,
  type BrushRange,
  type FlowAggregate,
  type FlowDirection,
  type FlowProtocol,
  type TrafficBucket,
  type TrafficEdge,
  type TrafficNode,
} from './aggregate';
import {
  ADJACENCY_ROWS,
  adjacencyMatrix,
  buildGraph,
  type AdjacencyMatrix,
  type GraphModel,
} from './graph';

/** The controls §4.4 names, as state the page holds. */
export interface TrafficFilters {
  /** `'all'`, or one protocol. The read is narrowed server-side when it is set. */
  protocol: FlowProtocol | 'all';
  /** `'all'`, or one direction. The read is narrowed server-side when it is set. */
  direction: FlowDirection | 'all';
  /** Hide addresses whose flow count is below this. */
  minFlows: number;
  /** Keep only addresses with at least one open alert. */
  openAlertsOnly: boolean;
}

export const DEFAULT_FILTERS: TrafficFilters = {
  protocol: 'all',
  direction: 'all',
  minFlows: 0,
  openAlertsOnly: false,
};

/** How wide a bucket is, in minutes, at each offered range. */
export const BUCKET_MINUTES: Record<'1h' | '24h' | '7d', number> = {
  '1h': 1,
  '24h': 15,
  '7d': 60,
};

export interface TrafficView {
  /** The brushable series: one bucket per interval across the whole window. */
  series: TrafficBucket[];
  /** The addresses in the window on screen, after the controls. */
  nodes: TrafficNode[];
  /** Every relationship the read returned; `buildGraph` keeps the drawable ones. */
  edges: TrafficEdge[];
  graph: GraphModel;
  /** Present only in adjacency mode — computed when the mode needs it. */
  matrix: AdjacencyMatrix | null;
  pinned: TrafficNode | null;
  /** Caveats that belong to this data, rendered rather than remembered. */
  notes: string[];
  /** What the entity controls removed, so a filtered-away address is never a mystery. */
  hiddenByControls: number;
}

export interface TrafficViewInput {
  /** The whole window's aggregate: the series is drawn from this one, always. */
  aggregate: FlowAggregate;
  /** The aggregate the panels describe: the brushed window when one is set. */
  panels: FlowAggregate;
  brush: BrushRange | null;
  filters: TrafficFilters;
  pinnedId: string | null;
}

export function buildTrafficView(input: TrafficViewInput): TrafficView {
  const series = trafficSeries(input.aggregate);
  const flagged = trafficNodes(input.panels);
  const guarded = flagged.filter(
    (node) =>
      node.flows >= input.filters.minFlows &&
      (!input.filters.openAlertsOnly || node.openAlerts > 0),
  );

  // Every relationship the read returned: the graph prunes the ones whose endpoint the
  // controls removed, so the pruning rule lives in one place (`buildGraph`).
  const edges = trafficEdges(input.panels);

  const pinned =
    input.pinnedId === null ? null : (flagged.find((node) => node.id === input.pinnedId) ?? null);
  let nodes = guarded;
  if (pinned !== null) {
    const neighbours = new Set<string>();
    for (const edge of edges) {
      if (edge.source === pinned.id) neighbours.add(edge.target);
      if (edge.target === pinned.id) neighbours.add(edge.source);
    }
    // Widening, in three parts: the pin leads (it is what was asked about, and it
    // survives the controls that would have hidden it), its neighbours come from the
    // *unfiltered* set — a relationship the controls hid is what the pin was asked to
    // reveal — and everything already on screen stays on screen. Narrowing to the
    // neighbourhood would answer a different question than the one the pin asks.
    const promoted = [pinned, ...flagged.filter((node) => neighbours.has(node.id))];
    const promotedIds = new Set(promoted.map((node) => node.id));
    nodes = [...promoted, ...guarded.filter((node) => !promotedIds.has(node.id))];
  }

  const graph = buildGraph(nodes, edges);

  return {
    series,
    nodes,
    edges,
    graph,
    matrix: graph.mode === 'adjacency' ? adjacencyMatrix(graph) : null,
    pinned,
    notes: notesFor(input, graph),
    hiddenByControls: flagged.length - guarded.length,
  };
}

function notesFor(input: TrafficViewInput, graph: GraphModel): string[] {
  // The source's caveats come first and unchanged: which read model answered, what a
  // cap did to a list, and why a window is empty are claims only the server can make,
  // and a screen that reworded one would be making its own.
  const notes = [...input.panels.caveats];

  if (input.brush !== null) {
    // Which window the numbers below describe, so a brush cannot be mistaken for a
    // zoom on a list that still covers the whole window.
    const from = new Date(input.brush.from).toISOString().slice(11, 16);
    const to = new Date(input.brush.to).toISOString().slice(11, 16);
    notes.push(`The table and the graph describe the brushed window (${from}–${to} UTC).`);
  }
  if (graph.mode === 'adjacency') {
    const drawn = Math.min(graph.nodes.length, ADJACENCY_ROWS);
    notes.push(
      `The matrix draws the ${String(drawn)} most active of ${String(graph.nodes.length)} addresses; the rest are counted, not drawn.`,
    );
  }
  return notes;
}
