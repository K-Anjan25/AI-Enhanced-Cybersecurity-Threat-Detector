/**
 * The traffic explorer's derived model: one pipeline, one place where a filter is
 * applied.
 *
 * design.md §4.4's promise is that "brushing filters everything below", and the way
 * to keep that promise is structural: the brush, the controls and the pinned entity
 * are folded into **one** row set here, and the series, the table and the graph are
 * all derived from that row set. Three panels each remembering to apply the brush is
 * three chances for one of them to keep showing what the analyst just excluded.
 *
 * The pipeline, in order, with the reason each step is where it is:
 *
 *   1. `rowsInBrush` — the brush is the outermost filter, because it is the one the
 *      analyst draws on the time axis and expects to be absolute.
 *   2. entity aggregation — from the brushed rows, so an entity's counts are the
 *      counts *in the brush*, not for the whole window.
 *   3. `minRecords` and `openOnly` — the entity-level filters, which can only be
 *      applied after the fold.
 *   4. pinning — last, and *widening* rather than narrowing: a pinned entity keeps
 *      its neighbours in view, because the question a pin asks is "what is this
 *      entity connected to?".
 *
 * Everything the screen cannot show is a `note` in the model rather than a comment
 * in a component, so the panel renders the caveats that belong to the data it was
 * actually given (design.md §8.1's partial state, R-70's "never an empty success").
 */
import type { AlertRow } from '../../api/alerts';
import type { Severity } from '../../components/ui/severity';
import {
  entityEdges,
  entityRows,
  rowsInBrush,
  trafficSeries,
  type BrushRange,
  type EntityEdge,
  type EntityRow,
  type TrafficBucket,
} from './aggregate';
import {
  ADJACENCY_ROWS,
  adjacencyMatrix,
  buildGraph,
  type AdjacencyMatrix,
  type GraphModel,
} from './graph';

/** The graph controls §4.4 names, as state the page holds. */
export interface TrafficFilters {
  /** `'all'`, or one severity. The read is narrowed server-side when it is set. */
  severity: Severity | 'all';
  /** Hide entities whose alerted record count is below this. */
  minRecords: number;
  /** Keep only entities with at least one open alert. */
  openOnly: boolean;
}

export const DEFAULT_FILTERS: TrafficFilters = { severity: 'all', minRecords: 0, openOnly: false };

/** How many buckets the series is divided into. */
export const SERIES_BUCKETS = 60;

export interface TrafficView {
  /** The brushable series: one bucket per interval across the whole window. */
  series: TrafficBucket[];
  /** The rows the brush selected. */
  rows: AlertRow[];
  /** Entities derived from the brushed rows, after the controls. */
  entities: EntityRow[];
  /** Every edge among the brushed rows; `buildGraph` keeps the drawable ones. */
  edges: EntityEdge[];
  graph: GraphModel;
  /** Present only in adjacency mode — computed when the mode needs it. */
  matrix: AdjacencyMatrix | null;
  pinned: EntityRow | null;
  /** Caveats that belong to this data, rendered rather than remembered. */
  notes: string[];
  /** What the entity controls removed, so a filtered-away entity is never a mystery. */
  hiddenByControls: number;
}

export interface TrafficViewInput {
  rows: readonly AlertRow[];
  start: Date;
  end: Date;
  complete: boolean;
  pagesFetched: number;
  brush: BrushRange | null;
  filters: TrafficFilters;
  pinnedEntityId: number | null;
  buckets?: number;
}

export function buildTrafficView(input: TrafficViewInput): TrafficView {
  // The brush first: everything below the series is derived from the rows it kept,
  // which is exactly what "brushing filters everything below" has to mean. The
  // *series* is still drawn from the whole window — it is the axis the analyst
  // brushes, and a series drawn from its own selection could never be re-brushed.
  const brushed = rowsInBrush(input.rows, input.brush);

  const flagged = entityRows(brushed);
  const guarded = flagged.filter(
    (entity) =>
      entity.records >= input.filters.minRecords && (!input.filters.openOnly || entity.hasOpen),
  );

  // Every edge among the brushed rows: the graph prunes the ones whose endpoint the
  // controls removed, so the pruning rule lives in one place (`buildGraph`).
  const edges = entityEdges(brushed);

  const pinned =
    input.pinnedEntityId === null
      ? null
      : (flagged.find((entity) => entity.entityId === input.pinnedEntityId) ?? null);
  let entities = guarded;
  if (pinned !== null) {
    const neighbours = new Set<number>();
    for (const edge of edges) {
      if (edge.source === pinned.entityId) neighbours.add(edge.target);
      if (edge.target === pinned.entityId) neighbours.add(edge.source);
    }
    // Widening, in three parts: the pin leads (it is what was asked about, and it
    // survives the controls that would have hidden it), its neighbours come from the
    // *unfiltered* brushed set — a relationship the controls hid is what the pin was
    // asked to reveal — and everything already on screen stays on screen. Narrowing to
    // the neighbourhood would answer a different question than the one the pin asks.
    const promoted = [pinned, ...flagged.filter((entity) => neighbours.has(entity.entityId))];
    const promotedIds = new Set(promoted.map((entity) => entity.entityId));
    entities = [...promoted, ...guarded.filter((entity) => !promotedIds.has(entity.entityId))];
  }

  const graph = buildGraph(entities, edges);

  return {
    series: trafficSeries(input.rows, {
      start: input.start,
      end: input.end,
      buckets: input.buckets ?? SERIES_BUCKETS,
    }),
    rows: brushed,
    entities,
    edges,
    graph,
    matrix: graph.mode === 'adjacency' ? adjacencyMatrix(graph) : null,
    pinned,
    notes: notesFor({ ...input, graph }),
    hiddenByControls: flagged.length - guarded.length,
  };
}

function notesFor(input: TrafficViewInput & { graph: GraphModel }): string[] {
  // The permanent caveat's wording is a decision, not a sentence: this screen reads
  // alerts, so every number on it is about records that were *alerted on*, and
  // saying "flow volume" about it would be a different claim.
  const notes = [
    'Volume is the raw-record count carried by alerts, not total traffic: this build has no read API for ingested flows (T-418). Edges are shared correlation traces rather than flow counts, and entities are shown by id because the alert API returns no host or user value (T-416).',
  ];

  if (!input.complete) {
    notes.push(
      `Only the first ${String(input.pagesFetched)} pages were read, so every total below is partial.`,
    );
  }
  if (input.graph.mode === 'adjacency') {
    const drawn = Math.min(input.graph.nodes.length, ADJACENCY_ROWS);
    notes.push(
      `The matrix draws the ${String(drawn)} most active of ${String(input.graph.nodes.length)} entities; the rest are counted, not drawn.`,
    );
  }
  return notes;
}

/** The window the brush currently selects, in words, for the panels' captions. */
export function brushLabel(brush: BrushRange | null): string {
  if (brush === null) return 'the whole window';
  return `${new Date(brush.from).toISOString().slice(11, 16)}–${new Date(brush.to).toISOString().slice(11, 16)} UTC`;
}
