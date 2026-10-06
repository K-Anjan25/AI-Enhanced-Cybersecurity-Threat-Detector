import { describe, expect, it } from 'vitest';

import { entityRows, type EntityRow } from './aggregate';
import {
  ADJACENCY_ROWS,
  GRAPH_NODE_LIMIT,
  adjacencyMatrix,
  buildGraph,
  layoutGraph,
  nodeRadius,
} from './graph';
import type { AlertRow } from '../../api/alerts';

function entity(
  entityId: number,
  records: number,
  severity: EntityRow['peakSeverity'] = 'high',
): EntityRow {
  return {
    entityId,
    alerts: 2,
    records,
    peakSeverity: severity,
    hasOpen: true,
    families: ['exfiltration'],
    firstSeen: '2026-10-06T10:00:00Z',
    lastSeen: '2026-10-06T10:30:00Z',
    traces: 1,
  };
}

function bare(count: number): EntityRow[] {
  return Array.from({ length: count }, (_unused, index) => entity(index + 1, count - index));
}

describe('buildGraph', () => {
  it('draws a force layout below the limit, and says so', () => {
    const model = buildGraph(
      [entity(1, 10), entity(2, 5)],
      [{ source: 1, target: 2, sharedTraces: 1 }],
    );

    expect(model.mode).toBe('force');
    expect(model.reason).toContain('Force layout');
    expect(model.edges).toHaveLength(1);
  });

  it('switches to the adjacency matrix past 2,000 nodes, and labels the switch', () => {
    // design.md §4.4: "a force simulation at that size is unusable — we switch to a
    // ranked adjacency matrix and *say so*". The label is in the model, so a panel
    // cannot render the mode without the explanation.
    const nodes = bare(GRAPH_NODE_LIMIT + 1);

    const model = buildGraph(nodes, []);

    expect(model.mode).toBe('adjacency');
    expect(model.reason).toContain('ranked adjacency matrix');
    expect(model.reason).toContain(String(GRAPH_NODE_LIMIT));
    expect(model.reason).toContain(String(GRAPH_NODE_LIMIT + 1));
  });

  it('stays in force mode exactly at the limit', () => {
    expect(buildGraph(bare(GRAPH_NODE_LIMIT), []).mode).toBe('force');
  });

  it('drops an edge whose endpoint was filtered away', () => {
    const model = buildGraph([entity(1, 10)], [{ source: 1, target: 99, sharedTraces: 3 }]);

    expect(model.edges).toEqual([]);
  });
});

describe('nodeRadius', () => {
  it('scales by area, not by length, so a 100x volume is not a 100x radius', () => {
    const small = nodeRadius(1, 100);
    const large = nodeRadius(100, 100);

    // Radius grows with the square root of the share: the *area* is what a reader
    // compares, and a linear radius would overstate the difference by 100x.
    expect(large).toBeGreaterThan(small);
    expect(large / small).toBeLessThan(100 / 4);
  });

  it('never returns a radius that would draw nothing', () => {
    expect(nodeRadius(0, 0)).toBeGreaterThan(0);
    expect(nodeRadius(-5, 10)).toBeGreaterThan(0);
  });

  it('is capped, so one enormous entity cannot fill the panel', () => {
    expect(nodeRadius(1_000_000, 1_000_000)).toBeLessThanOrEqual(22);
    // Also when a caller passes a volume above the ceiling: the cap is what keeps a
    // single entity from drawing a disc that swallows the panel.
    expect(nodeRadius(200, 100)).toBeLessThanOrEqual(22);
  });

  it('gives every node the radius its own volume earned', () => {
    const nodes = entityRows([rowFixture(1, 1, 100), rowFixture(2, 2, 25)]);

    const layout = layoutGraph(buildGraph(nodes, []), { width: 400, height: 300 });

    const byId = new Map(layout.nodes.map((node) => [node.node.entityId, node.radius]));
    // Literal numbers, not calls back into `nodeRadius`: comparing the layout with the
    // function it uses would pass whatever that function did.
    expect(byId.get(1)).toBe(22); // the busiest entity gets the cap
    expect(byId.get(2)).toBe(13); // 4 + 18 * sqrt(25 / 100)
  });
});

describe('layoutGraph', () => {
  const model = buildGraph(
    [entity(1, 30), entity(2, 20), entity(3, 10)],
    [
      { source: 1, target: 2, sharedTraces: 2 },
      { source: 2, target: 3, sharedTraces: 1 },
    ],
  );

  it('places every node inside the panel', () => {
    const layout = layoutGraph(model, { width: 400, height: 300 });

    expect(layout.nodes).toHaveLength(3);
    for (const node of layout.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0);
      expect(node.x).toBeLessThanOrEqual(400);
      expect(node.y).toBeGreaterThanOrEqual(0);
      expect(node.y).toBeLessThanOrEqual(300);
    }
  });

  it('lays the same graph out the same way twice', () => {
    // Deterministic initial positions, d3's fixed-seed jitter and our fixed tick
    // count: after a refresh the analyst is looking at the same picture, not a
    // reshuffled one. A caller-chosen seed would be a knob with no observable
    // effect — measured across four graph sizes, not assumed — so there is none.
    const first = layoutGraph(model, { width: 400, height: 300 });
    const second = layoutGraph(model, { width: 400, height: 300 });

    expect(first.nodes.map((node) => [node.x, node.y])).toEqual(
      second.nodes.map((node) => [node.x, node.y]),
    );
  });

  it('positions the panel centre for a single node instead of collapsing to a point', () => {
    const single = buildGraph([entity(1, 5)], []);

    const layout = layoutGraph(single, { width: 200, height: 100 });

    expect(layout.nodes[0]).toMatchObject({ x: 100, y: 50 });
  });

  it('lays out nothing for no nodes, without dividing by zero', () => {
    expect(layoutGraph(buildGraph([], []), { width: 200, height: 100 })).toEqual({
      nodes: [],
      edges: [],
    });
  });

  it('carries each edge to the nodes it connects', () => {
    const layout = layoutGraph(model, { width: 400, height: 300 });

    expect(layout.edges).toHaveLength(2);
    for (const edge of layout.edges) {
      expect(edge.source.node.entityId).toBe(edge.edge.source);
      expect(edge.target.node.entityId).toBe(edge.edge.target);
    }
  });
});

describe('adjacencyMatrix', () => {
  it('draws both halves of every pair, and no diagonal', () => {
    const model = buildGraph(
      [entity(1, 10), entity(2, 5)],
      [{ source: 1, target: 2, sharedTraces: 4 }],
    );

    const matrix = adjacencyMatrix(model);

    expect(matrix.cells).toEqual([
      { sourceId: 1, targetId: 2, sharedTraces: 4 },
      { sourceId: 2, targetId: 1, sharedTraces: 4 },
    ]);
    expect(matrix.cells.some((cell) => cell.sourceId === cell.targetId)).toBe(false);
  });

  it('orders the cells for reading, not by weight', () => {
    // Weight and id order disagree on purpose here: (1,2) is the heavy pair, but (1,3)
    // comes first in reading order, so a sort by weight would be visible.
    const model = buildGraph(
      [entity(1, 10), entity(2, 5), entity(3, 4)],
      [
        { source: 1, target: 2, sharedTraces: 9 },
        { source: 1, target: 3, sharedTraces: 1 },
      ],
    );

    const cells = adjacencyMatrix(model).cells;

    expect(cells.map((cell) => [cell.sourceId, cell.targetId])).toEqual([
      [1, 2],
      [1, 3],
      [2, 1],
      [3, 1],
    ]);
  });

  it('caps the axis and reports how many entities it did not draw', () => {
    const nodes = bare(ADJACENCY_ROWS + 10);
    const model = buildGraph(nodes, []);

    const matrix = adjacencyMatrix(model);

    expect(matrix.axis).toHaveLength(ADJACENCY_ROWS);
    expect(matrix.total).toBe(ADJACENCY_ROWS + 10);
  });

  it('ranks the axis the way the nodes are ordered: busiest first', () => {
    const nodes = entityRows([{ ...rowFixture(1, 1, 2) }, { ...rowFixture(2, 2, 50) }]);

    const matrix = adjacencyMatrix(buildGraph(nodes, []));

    expect(matrix.axis.map((entry) => entry.entityId)).toEqual([2, 1]);
  });

  it('drops a cell whose endpoint is off the axis', () => {
    const model = buildGraph(bare(ADJACENCY_ROWS + 5), [
      { source: ADJACENCY_ROWS + 5, target: 1, sharedTraces: 9 },
    ]);

    expect(adjacencyMatrix(model).cells).toEqual([]);
  });

  it('reports the peak weight for shading, and zero when there is nothing to shade', () => {
    const model = buildGraph(
      [entity(1, 10), entity(2, 5)],
      [{ source: 1, target: 2, sharedTraces: 7 }],
    );

    expect(adjacencyMatrix(model).peak).toBe(7);
    expect(adjacencyMatrix(buildGraph([entity(1, 10)], [])).peak).toBe(0);
  });
});

/** One alert row, for the ranking test. */
function rowFixture(id: number, entityId: number, occurrences: number): AlertRow {
  return {
    id,
    created_at: '2026-10-06T10:00:00Z',
    entity_id: entityId,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: '2026-10-06T09:00:00Z',
    last_seen: '2026-10-06T10:00:00Z',
    occurrence_count: occurrences,
    trace_id: null,
  };
}
