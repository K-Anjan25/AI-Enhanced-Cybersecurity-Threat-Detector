/**
 * The traffic model's mapping, and the brush (T-418).
 *
 * What is left in `aggregate.ts` after the arithmetic moved to the flow read model: the
 * wire→component mapping and two rules that could silently mislead a reader.
 *
 *   * **Every bucket has an end**, taken from the next bucket's start and the window's
 *     own end for the last one — so the series tiles the window the totals describe.
 *   * **The brush selects by overlap**, because a bucket that starts before the selection
 *     and ends inside it holds traffic the analyst selected.
 */
import { describe, expect, it } from 'vitest';

import { trafficEdges, trafficNodes, trafficSeries } from './aggregate';
import type { FlowAggregate, FlowBucket, FlowEntity } from '../../api/flows';

const START = Date.parse('2026-10-06T10:00:00Z');

function bucket(overrides: Partial<FlowBucket> & { start: string }): FlowBucket {
  return {
    flows: 1,
    bytes: 140,
    packets: 3,
    alerts: 0,
    score: null,
    ...overrides,
  };
}

function entity(overrides: Partial<FlowEntity> & { ip: string }): FlowEntity {
  return {
    flows: 1,
    bytes: 140,
    packets: 3,
    inbound: 0,
    outbound: 1,
    first_seen: new Date(START).toISOString(),
    last_seen: new Date(START).toISOString(),
    alerts: 0,
    open_alerts: 0,
    worst_severity: null,
    max_score: null,
    ...overrides,
  };
}

function aggregate(overrides: Partial<FlowAggregate> = {}): FlowAggregate {
  return {
    window: {
      start: new Date(START).toISOString(),
      end: new Date(START + 3_600_000).toISOString(),
      hours: 1,
    },
    bucket_minutes: 5,
    source: 'rollup',
    filters: { protocol: null, direction: null },
    series: [],
    entities: [],
    edges: [],
    totals: {
      flows: 0,
      bytes: 0,
      packets: 0,
      nodes: 0,
      edges: 0,
      nodes_capped: false,
      edges_capped: false,
      untracked_address_flows: 0,
      untracked_pair_flows: 0,
    },
    caveats: [],
    ...overrides,
  };
}

describe('trafficSeries', () => {
  it('fills each bucket end from the next bucket start', () => {
    const series = trafficSeries(
      aggregate({
        series: [
          bucket({ start: new Date(START).toISOString() }),
          bucket({ start: new Date(START + 300_000).toISOString() }),
        ],
      }),
    );

    expect(series[0]?.end.getTime()).toBe(START + 300_000);
  });

  it('ends the last bucket where the window ends', () => {
    // The API's window is the authority: a last bucket ending anywhere else would leave
    // a gap (or an overlap) between the series and the totals that describe it.
    const series = trafficSeries(
      aggregate({ series: [bucket({ start: new Date(START).toISOString() })] }),
    );

    expect(series[0]?.end.getTime()).toBe(START + 3_600_000);
  });

  it('carries flows, bytes, alerts and the score through unchanged', () => {
    const series = trafficSeries(
      aggregate({
        series: [
          bucket({
            start: new Date(START).toISOString(),
            flows: 7,
            bytes: 900,
            alerts: 2,
            score: 0.75,
          }),
        ],
      }),
    );

    expect(series[0]).toMatchObject({ flows: 7, bytes: 900, alerts: 2, score: 0.75 });
  });

  it('keeps a null score null rather than turning it into zero', () => {
    // A zero here draws the score line along the floor of a bucket where nothing
    // happened, which reads as "everything was benign".
    const series = trafficSeries(
      aggregate({ series: [bucket({ start: new Date(START).toISOString() })] }),
    );

    expect(series[0]?.score).toBeNull();
  });
});

describe('trafficNodes', () => {
  it('keys an address by its value, not by an id', () => {
    const nodes = trafficNodes(aggregate({ entities: [entity({ ip: '10.0.0.7' })] }));

    expect(nodes[0]?.id).toBe('10.0.0.7');
  });

  it('keeps the read model’s directions and counters', () => {
    const nodes = trafficNodes(
      aggregate({
        entities: [entity({ ip: '10.0.0.7', flows: 9, inbound: 4, outbound: 5, bytes: 500 })],
      }),
    );

    expect(nodes[0]).toMatchObject({ flows: 9, inbound: 4, outbound: 5, bytes: 500 });
  });

  it('carries the alert side through', () => {
    const nodes = trafficNodes(
      aggregate({
        entities: [
          entity({
            ip: '10.0.0.7',
            alerts: 3,
            open_alerts: 1,
            worst_severity: 'critical',
            max_score: 0.97,
          }),
        ],
      }),
    );

    expect(nodes[0]).toMatchObject({
      alerts: 3,
      openAlerts: 1,
      peakSeverity: 'critical',
      maxScore: 0.97,
    });
  });

  it('treats an unknown severity band as no severity rather than as a band', () => {
    // The palette only has the four declared severities; a band this build does not know
    // would otherwise be passed to a colour lookup that has no entry for it.
    const nodes = trafficNodes(
      aggregate({ entities: [entity({ ip: '10.0.0.7', worst_severity: 'catastrophic' })] }),
    );

    expect(nodes[0]?.peakSeverity).toBeNull();
  });

  it('leaves an address with no alert without a score or a severity', () => {
    const nodes = trafficNodes(aggregate({ entities: [entity({ ip: '10.0.0.7' })] }));

    expect(nodes[0]?.peakSeverity).toBeNull();
    expect(nodes[0]?.maxScore).toBeNull();
    expect(nodes[0]?.alerts).toBe(0);
  });
});

describe('trafficEdges', () => {
  it('keeps the direction the read model reported', () => {
    const edges = trafficEdges(
      aggregate({
        edges: [
          { source: '10.0.0.1', target: '10.0.0.2', flows: 3, bytes: 300 },
          { source: '10.0.0.2', target: '10.0.0.1', flows: 1, bytes: 100 },
        ],
      }),
    );

    expect(edges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      '10.0.0.1->10.0.0.2',
      '10.0.0.2->10.0.0.1',
    ]);
  });

  it('weights an edge by its records', () => {
    const edges = trafficEdges(
      aggregate({ edges: [{ source: '10.0.0.1', target: '10.0.0.2', flows: 12, bytes: 3_000 }] }),
    );

    expect(edges[0]?.flows).toBe(12);
  });

  it('preserves the read model’s order, busiest first', () => {
    const edges = trafficEdges(
      aggregate({
        edges: [
          { source: '10.0.0.1', target: '10.0.0.2', flows: 9, bytes: 1 },
          { source: '10.0.0.3', target: '10.0.0.4', flows: 2, bytes: 1 },
        ],
      }),
    );

    expect(edges[0]?.flows).toBe(9);
  });
});
