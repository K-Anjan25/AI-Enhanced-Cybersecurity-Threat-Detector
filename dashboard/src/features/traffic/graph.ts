/**
 * The entity graph: which mode it is drawn in, and where the nodes go.
 *
 * design.md §4.4 asks for a force-directed graph and, in the same paragraph, for
 * the admission that a force simulation stops being usable at scale: "a static
 * layout fallback for >2,000 nodes (a force simulation at that size is unusable —
 * we switch to a ranked adjacency matrix and say so)".
 *
 * So the *mode* is a decision this module makes and states, not a rendering
 * detail:
 *
 *   * `force` below the limit — `d3-force` (D-007: D3 for custom visuals), ticked
 *     a fixed number of times and with no timer, so a layout is reproducible,
 *     testable, and never animates when the analyst has asked for reduced motion.
 *     Reproducible here is a property of the whole call, not of a seed: d3 starts
 *     nodes from a deterministic spiral, its own jitter source is a fixed-seed LCG,
 *     and the tick count is ours — so the same graph lands in the same places.
 *   * `adjacency` above it — a ranked matrix, which is what an analyst can actually
 *     read at that size. It is capped in *displayed* rank and says how many of N it
 *     is showing; a 3,000-column matrix drawn in full would be a wall of pixels.
 *
 * The `reason` string is carried with the mode because the rule that started this
 * task is "the graph switches to adjacency mode **and labels the switch**": the
 * label is data here, so the panel cannot render the mode without the explanation.
 */
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';

import type { EntityEdge, EntityRow } from './aggregate';

/**
 * The node count at which the force simulation is abandoned.
 *
 * §4.4's number, kept as a named constant because the test that pins the switch
 * needs a boundary and a boundary spelled `2000` in two files is a boundary that
 * can disagree with itself.
 */
export const GRAPH_NODE_LIMIT = 2_000;

/**
 * How many ranked nodes the adjacency matrix draws.
 *
 * A matrix is O(n²) cells; past this the cells are smaller than a pixel and the
 * reader learns nothing. The panel says "showing the N most active of M" — the
 * count it did not draw is stated, never implied.
 */
export const ADJACENCY_ROWS = 40;

export type GraphMode = 'force' | 'adjacency';

/** What the panel renders, and why. */
export interface GraphModel {
  mode: GraphMode;
  /** The switch's explanation, rendered wherever the mode is. */
  reason: string;
  nodes: EntityRow[];
  edges: EntityEdge[];
}

/**
 * Decide the mode and keep the edges the nodes can still carry.
 *
 * An edge whose endpoint was filtered out is dropped rather than drawn to nowhere —
 * a half-edge would make the graph claim a relationship to an entity the analyst
 * has filtered away.
 */
export function buildGraph(nodes: readonly EntityRow[], edges: readonly EntityEdge[]): GraphModel {
  const kept = [...nodes];
  const ids = new Set(kept.map((node) => node.entityId));
  const drawable = edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const mode: GraphMode = kept.length > GRAPH_NODE_LIMIT ? 'adjacency' : 'force';

  return {
    mode,
    reason:
      mode === 'adjacency'
        ? `Showing a ranked adjacency matrix: ${String(kept.length)} entities is past the ${String(GRAPH_NODE_LIMIT)}-node limit for a force layout.`
        : `Force layout for ${String(kept.length)} entities.`,
    nodes: kept,
    edges: drawable,
  };
}

export interface LayoutRequest {
  width: number;
  height: number;
  /** Simulation ticks. Fixed, so the same input always produces the same picture. */
  iterations?: number;
}

export interface PositionedNode {
  node: EntityRow;
  x: number;
  y: number;
  /** Radius in user units, from the node's record count. */
  radius: number;
}

export interface PositionedEdge {
  edge: EntityEdge;
  source: PositionedNode;
  target: PositionedNode;
}

export interface GraphLayout {
  nodes: PositionedNode[];
  edges: PositionedEdge[];
}

/**
 * The simulation's own node type.
 *
 * d3-force writes `x`, `y`, `vx` and `vy` onto whatever it is handed, so the node
 * type has to be d3's `SimulationNodeDatum` plus the identity this module keys on.
 */
type SimNode = SimulationNodeDatum & { id: number };

/** A link whose ends are entity ids, before the simulation rewrites them. */
type SimLink = SimulationLinkDatum<SimNode> & { source: number; target: number };

/**
 * Radius for a node, on the square root of its volume.
 *
 * Area is what a reader compares, and area grows with the square of the radius —
 * so a linear radius would draw a 100-record entity a hundred times the ink of a
 * 1-record one and read as a claim the data does not make.
 */
export function nodeRadius(records: number, maxRecords: number): number {
  const MIN = 4;
  const MAX = 22;
  if (!(maxRecords > 0)) return MIN;
  const share = Math.max(0, Math.min(1, records / maxRecords));
  return MIN + (MAX - MIN) * Math.sqrt(share);
}

/** The span of a layout: a graph with one node has no extent, and must not divide by zero. */
function extent(values: readonly number[]): [number, number] {
  let min = Infinity;
  let max = -Infinity;
  for (const value of values) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 0];
  if (min === max) return [min - 1, max + 1];
  return [min, max];
}

/**
 * Lay the graph out, deterministically, inside the given box.
 *
 * The simulation is run to a fixed tick count and then mapped into the panel's
 * coordinates here rather than by d3's `forceCenter`, so the same graph fills the
 * same panel the same way on every render and in every test. Nodes are drawn with
 * padding for their own radius, so a large node is never half outside the frame.
 */
export function layoutGraph(model: GraphModel, request: LayoutRequest): GraphLayout {
  const { width, height } = request;
  const iterations = request.iterations ?? 120;
  const pad = 24;
  const innerWidth = Math.max(1, width - pad * 2);
  const innerHeight = Math.max(1, height - pad * 2);

  const maxRecords = model.nodes.reduce((best, node) => Math.max(best, node.records), 0);
  const radii = new Map(
    model.nodes.map((node) => [node.entityId, nodeRadius(node.records, maxRecords)]),
  );

  if (model.nodes.length === 0) return { nodes: [], edges: [] };

  // One node: a simulation would place it by its own forces; the honest answer is
  // the centre of the panel.
  if (model.nodes.length === 1) {
    const only = model.nodes[0] as EntityRow;
    const positioned: PositionedNode = {
      node: only,
      x: width / 2,
      y: height / 2,
      radius: radii.get(only.entityId) ?? 4,
    };
    return { nodes: [positioned], edges: [] };
  }

  const simulation = forceSimulation<SimNode>(model.nodes.map((node) => ({ id: node.entityId })))
    .force('charge', forceManyBody<SimNode>().strength(-120))
    .force(
      'link',
      forceLink<SimNode, SimLink>(
        model.edges.map((edge) => ({ source: edge.source, target: edge.target })),
      )
        .id((node) => node.id)
        .distance(60)
        .strength(0.3),
    )
    .force('center', forceCenter(0, 0))
    .force('collide', forceCollide<SimNode>(8))
    .stop();

  for (let tick = 0; tick < iterations; tick += 1) simulation.tick();

  const raw = simulation.nodes();
  // `x`/`y` are optional in d3's type (a simulation initialises them itself), so
  // the read is a pull with a defined fallback rather than a non-null assertion: a
  // node the simulation never placed belongs at the origin, not at a crash.
  const [minX, maxX] = extent(raw.map((node) => node.x ?? 0));
  const [minY, maxY] = extent(raw.map((node) => node.y ?? 0));

  const byId = new Map(model.nodes.map((node) => [node.entityId, node]));
  const positioned: PositionedNode[] = [];
  for (const node of raw) {
    const source = byId.get(node.id);
    if (source === undefined) continue;
    const radius = radii.get(source.entityId) ?? 4;
    positioned.push({
      node: source,
      x: pad + (((node.x ?? 0) - minX) / (maxX - minX)) * innerWidth,
      y: pad + (((node.y ?? 0) - minY) / (maxY - minY)) * innerHeight,
      radius,
    });
  }

  const positions = new Map(positioned.map((node) => [node.node.entityId, node]));
  const edges: PositionedEdge[] = [];
  for (const edge of model.edges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (source === undefined || target === undefined) continue;
    edges.push({ edge, source, target });
  }

  return { nodes: positioned, edges };
}

/** One cell of the adjacency matrix. */
export interface MatrixCell {
  sourceId: number;
  targetId: number;
  sharedTraces: number;
}

export interface AdjacencyMatrix {
  /** The entities drawn, most active first — and the same order on both axes. */
  axis: EntityRow[];
  /** How many entities exist, so the panel can say how many it is not drawing. */
  total: number;
  cells: MatrixCell[];
  /** The largest shared-trace count, for shading. `0` when there are no edges. */
  peak: number;
}

/**
 * A ranked adjacency matrix over the most active entities.
 *
 * Symmetric by construction: a cell is written for both `(a,b)` and `(b,a)` so the
 * reader does not have to know which axis is which to find a relationship, and the
 * diagonal stays empty because an entity is not related to itself.
 */
export function adjacencyMatrix(
  model: GraphModel,
  limit: number = ADJACENCY_ROWS,
): AdjacencyMatrix {
  const axis = [...model.nodes].slice(0, Math.max(0, limit));
  const drawn = new Set(axis.map((node) => node.entityId));
  const cells: MatrixCell[] = [];
  let peak = 0;

  for (const edge of model.edges) {
    if (!drawn.has(edge.source) || !drawn.has(edge.target)) continue;
    cells.push({ sourceId: edge.source, targetId: edge.target, sharedTraces: edge.sharedTraces });
    cells.push({ sourceId: edge.target, targetId: edge.source, sharedTraces: edge.sharedTraces });
    peak = Math.max(peak, edge.sharedTraces);
  }

  cells.sort((left, right) => left.sourceId - right.sourceId || left.targetId - right.targetId);

  return { axis, total: model.nodes.length, cells, peak };
}
