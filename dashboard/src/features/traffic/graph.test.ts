import { describe, expect, it } from 'vitest';

import type { TrafficEdge, TrafficNode } from './aggregate';
import { FLOW_RELATIONSHIP_LIMIT, buildGraph } from './graph';

function entity(id: string): TrafficNode {
  return {
    id,
    flows: 1,
    bytes: 100,
    packets: 1,
    inbound: 0,
    outbound: 1,
    alerts: 0,
    openAlerts: 0,
    peakSeverity: null,
    maxScore: null,
    firstSeen: null,
    lastSeen: null,
  };
}

function edge(source: string, target: string, flows: number, bytes: number): TrafficEdge {
  return { source, target, flows, bytes };
}

describe('buildGraph', () => {
  it('ranks directed conversations by bytes, then flows and stable address order', () => {
    const model = buildGraph(
      [entity('10.0.0.1'), entity('10.0.0.2'), entity('10.0.0.3')],
      [
        edge('10.0.0.1', '10.0.0.2', 9, 500),
        edge('10.0.0.2', '10.0.0.1', 2, 500),
        edge('10.0.0.1', '10.0.0.3', 20, 900),
      ],
    );

    expect(model.relationships).toEqual([
      edge('10.0.0.1', '10.0.0.3', 20, 900),
      edge('10.0.0.1', '10.0.0.2', 9, 500),
      edge('10.0.0.2', '10.0.0.1', 2, 500),
    ]);
    expect(model.totalRelationships).toBe(3);
  });

  it('preserves opposite directions as distinct conversations', () => {
    const model = buildGraph(
      [entity('10.0.0.1'), entity('10.0.0.2')],
      [edge('10.0.0.1', '10.0.0.2', 4, 400), edge('10.0.0.2', '10.0.0.1', 3, 300)],
    );

    expect(model.relationships.map(({ source, target }) => [source, target])).toEqual([
      ['10.0.0.1', '10.0.0.2'],
      ['10.0.0.2', '10.0.0.1'],
    ]);
  });

  it('drops edges to endpoints removed by the controls', () => {
    const model = buildGraph([entity('10.0.0.1')], [edge('10.0.0.1', '10.0.0.2', 3, 300)]);

    expect(model.relationships).toEqual([]);
    expect(model.totalRelationships).toBe(0);
  });

  it('caps the displayed rows and reports the real total', () => {
    const addresses = Array.from({ length: FLOW_RELATIONSHIP_LIMIT + 7 }, (_unused, index) =>
      entity(`10.0.0.${String(index + 1)}`),
    );
    const edges = addresses
      .slice(1)
      .map((node, index) => edge('10.0.0.1', node.id, index + 1, (index + 1) * 1_000));

    const model = buildGraph(addresses, edges);

    expect(model.relationships).toHaveLength(FLOW_RELATIONSHIP_LIMIT);
    expect(model.totalRelationships).toBe(FLOW_RELATIONSHIP_LIMIT + 6);
    expect(model.relationships[0]?.bytes).toBe((FLOW_RELATIONSHIP_LIMIT + 6) * 1_000);
  });

  it('respects an explicit limit and returns no rows for a non-positive limit', () => {
    const nodes = [entity('10.0.0.1'), entity('10.0.0.2')];
    const edges = [edge('10.0.0.1', '10.0.0.2', 1, 100)];

    expect(buildGraph(nodes, edges, 1).relationships).toHaveLength(1);
    expect(buildGraph(nodes, edges, 0).relationships).toEqual([]);
    expect(buildGraph(nodes, edges, -5).relationships).toEqual([]);
  });

  it('does not mutate the API edge order', () => {
    const nodes = [entity('10.0.0.1'), entity('10.0.0.2'), entity('10.0.0.3')];
    const edges = [edge('10.0.0.1', '10.0.0.2', 1, 100), edge('10.0.0.1', '10.0.0.3', 2, 200)];
    const original = edges.slice();

    buildGraph(nodes, edges);

    expect(edges).toEqual(original);
  });
});
