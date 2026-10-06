import { describe, expect, it } from 'vitest';

import { entityEdges, entityRows, rowsInBrush, trafficSeries } from './aggregate';
import type { AlertRow } from '../../api/alerts';

function row(overrides: Partial<AlertRow> & { id: number }): AlertRow {
  return {
    created_at: '2026-10-06T10:00:00Z',
    entity_id: 1,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: '2026-10-06T09:59:00Z',
    last_seen: '2026-10-06T10:00:00Z',
    occurrence_count: 10,
    trace_id: null,
    ...overrides,
  };
}

const WINDOW = { start: new Date('2026-10-06T10:00:00Z'), end: new Date('2026-10-06T11:00:00Z') };

describe('trafficSeries', () => {
  it('tiles the window with buckets that touch end to end', () => {
    const buckets = trafficSeries([], { ...WINDOW, buckets: 4 });

    expect(buckets).toHaveLength(4);
    expect(buckets[0]?.start.toISOString()).toBe('2026-10-06T10:00:00.000Z');
    expect(buckets[3]?.end.toISOString()).toBe('2026-10-06T11:00:00.000Z');
    for (let index = 1; index < buckets.length; index += 1) {
      expect(buckets[index]?.start.getTime()).toBe(buckets[index - 1]?.end.getTime());
    }
  });

  it('sums record volume and means the score per bucket', () => {
    const buckets = trafficSeries(
      [
        row({ id: 1, created_at: '2026-10-06T10:10:00Z', occurrence_count: 4, score: 0.5 }),
        row({ id: 2, created_at: '2026-10-06T10:20:00Z', occurrence_count: 6, score: 0.9 }),
      ],
      { ...WINDOW, buckets: 2 },
    );

    expect(buckets[0]?.records).toBe(10);
    expect(buckets[0]?.alerts).toBe(2);
    expect(buckets[0]?.score).toBeCloseTo(0.7);
    expect(buckets[1]?.records).toBe(0);
  });

  it('says an empty bucket has no score rather than scoring it zero', () => {
    // A zero would draw a line through the floor of an empty bucket, which reads as
    // "everything was benign" when the truth is "nothing happened".
    const buckets = trafficSeries([row({ id: 1, created_at: '2026-10-06T10:10:00Z' })], {
      ...WINDOW,
      buckets: 2,
    });

    expect(buckets[1]?.score).toBeNull();
    expect(buckets[0]?.score).not.toBeNull();
  });

  it('clamps a row outside the window into the nearest bucket rather than dropping it', () => {
    const buckets = trafficSeries(
      [row({ id: 1, created_at: '2026-10-06T09:00:00Z', occurrence_count: 3 })],
      { ...WINDOW, buckets: 2 },
    );

    expect(buckets[0]?.records).toBe(3);
    expect(buckets.reduce((total, bucket) => total + bucket.records, 0)).toBe(3);
  });

  it('counts a row whose timestamp cannot be parsed nowhere, and does not crash', () => {
    expect(() =>
      trafficSeries([row({ id: 1, created_at: 'not-a-time' })], { ...WINDOW, buckets: 2 }),
    ).not.toThrow();
  });

  it('refuses an inverted or empty window instead of drawing a zero-width chart', () => {
    expect(() => trafficSeries([], { start: WINDOW.end, end: WINDOW.start, buckets: 4 })).toThrow(
      RangeError,
    );
    expect(() => trafficSeries([], { ...WINDOW, buckets: 0 })).toThrow(RangeError);
  });
});

describe('entityRows', () => {
  it('folds rows into one entry per entity, counting alerts and records', () => {
    const entities = entityRows([
      row({ id: 1, entity_id: 7, occurrence_count: 5, family: 'exfiltration' }),
      row({ id: 2, entity_id: 7, occurrence_count: 3, family: 'scan' }),
      row({ id: 3, entity_id: 9, occurrence_count: 1 }),
    ]);

    expect(entities).toHaveLength(2);
    expect(entities[0]).toMatchObject({
      entityId: 7,
      alerts: 2,
      records: 8,
      families: ['exfiltration', 'scan'],
    });
    expect(entities[1]).toMatchObject({ entityId: 9, alerts: 1, records: 1 });
  });

  it('keeps the most serious severity seen, whatever order the rows arrive in', () => {
    const entities = entityRows([
      row({ id: 1, entity_id: 4, severity: 'low' }),
      row({ id: 2, entity_id: 4, severity: 'critical' }),
      row({ id: 3, entity_id: 4, severity: 'medium' }),
    ]);

    expect(entities[0]?.peakSeverity).toBe('critical');
  });

  it('leaves the peak null when no severity is recognised, rather than inventing one', () => {
    const entities = entityRows([row({ id: 1, entity_id: 4, severity: 'catastrophic' })]);

    expect(entities[0]?.peakSeverity).toBeNull();
  });

  it('marks an entity whose alerts are all judged as not open', () => {
    const entities = entityRows([
      row({ id: 1, entity_id: 4, status: 'resolved' }),
      row({ id: 2, entity_id: 4, status: 'benign' }),
    ]);

    expect(entities[0]?.hasOpen).toBe(false);
  });

  it('widens first and last seen to the extremes, compared as instants', () => {
    const entities = entityRows([
      row({
        id: 1,
        entity_id: 4,
        first_seen: '2026-10-06T09:00:00Z',
        last_seen: '2026-10-06T09:30:00Z',
      }),
      row({
        id: 2,
        entity_id: 4,
        // A different offset for the same instant must not sort later as text.
        first_seen: '2026-10-06T08:00:00+00:00',
        last_seen: '2026-10-06T11:00:00Z',
      }),
    ]);

    expect(Date.parse(entities[0]?.firstSeen ?? '')).toBe(Date.parse('2026-10-06T08:00:00Z'));
    expect(Date.parse(entities[0]?.lastSeen ?? '')).toBe(Date.parse('2026-10-06T11:00:00Z'));
  });

  it('counts distinct traces per entity', () => {
    const entities = entityRows([
      row({ id: 1, entity_id: 4, trace_id: 'trace-a' }),
      row({ id: 2, entity_id: 4, trace_id: 'trace-a' }),
      row({ id: 3, entity_id: 4, trace_id: 'trace-b' }),
      row({ id: 4, entity_id: 4, trace_id: null }),
    ]);

    expect(entities[0]?.traces).toBe(2);
  });

  it('orders by volume and breaks ties by id, so two refreshes agree', () => {
    const rows = [
      row({ id: 1, entity_id: 9, occurrence_count: 1 }),
      row({ id: 2, entity_id: 3, occurrence_count: 5 }),
      row({ id: 3, entity_id: 5, occurrence_count: 1 }),
    ];

    expect(entityRows(rows).map((entity) => entity.entityId)).toEqual([3, 5, 9]);
    expect(entityRows([...rows].reverse()).map((entity) => entity.entityId)).toEqual([3, 5, 9]);
  });
});

describe('entityEdges', () => {
  it('builds one edge per pair that shared a correlation trace', () => {
    const edges = entityEdges([
      row({ id: 1, entity_id: 9, trace_id: 'trace-1' }),
      row({ id: 2, entity_id: 3, trace_id: 'trace-1' }),
    ]);

    expect(edges).toEqual([{ source: 3, target: 9, sharedTraces: 1 }]);
  });

  it('spells a pair the same way whichever side arrives first', () => {
    const edges = entityEdges([
      row({ id: 1, entity_id: 9, trace_id: 'trace-1' }),
      row({ id: 2, entity_id: 3, trace_id: 'trace-1' }),
    ]);

    // Smaller id first, always: `(3,9)` and `(9,3)` must be one edge, not two.
    expect(edges[0]?.source).toBe(3);
    expect(edges[0]?.target).toBe(9);
  });

  it('counts the traces two entities share, not the alerts', () => {
    const edges = entityEdges([
      row({ id: 1, entity_id: 1, trace_id: 'trace-1' }),
      row({ id: 2, entity_id: 2, trace_id: 'trace-1' }),
      row({ id: 3, entity_id: 1, trace_id: 'trace-1' }),
      row({ id: 4, entity_id: 2, trace_id: 'trace-2' }),
      row({ id: 5, entity_id: 1, trace_id: 'trace-2' }),
    ]);

    expect(edges).toEqual([{ source: 1, target: 2, sharedTraces: 2 }]);
  });

  it('groups nothing by a missing trace, however many rows share one', () => {
    // `null` is a valid Map key, so the guard is not decoration: without it every
    // alert that never had a trace context lands in one bucket and the graph draws a
    // relationship out of the fact that two unrelated alerts were both untraced.
    const edges = entityEdges([
      row({ id: 1, entity_id: 1, trace_id: null }),
      row({ id: 2, entity_id: 2, trace_id: null }),
      row({ id: 3, entity_id: 3, trace_id: null }),
    ]);

    expect(edges).toEqual([]);
  });

  it('draws no edge from a trace that touched one entity, and no self-loop', () => {
    const edges = entityEdges([
      row({ id: 1, entity_id: 1, trace_id: 'trace-1' }),
      row({ id: 2, entity_id: 1, trace_id: 'trace-1' }),
      row({ id: 3, entity_id: 2, trace_id: null }),
    ]);

    expect(edges).toEqual([]);
  });

  it('orders edges by weight, then by both ends', () => {
    // The input order deliberately disagrees with the output order three ways: the
    // heavy pair comes last, one pair lists its higher id first, and the light pairs
    // arrive (3,4) before (2,9). Entities 1 and 2 share *two* distinct traces — so the
    // weight is 2, which is what "counts traces, not alerts" means: four alerts in one
    // trace are one edge.
    const edges = entityEdges([
      row({ id: 1, entity_id: 3, trace_id: 't3' }),
      row({ id: 2, entity_id: 4, trace_id: 't3' }),
      row({ id: 3, entity_id: 9, trace_id: 't8' }),
      row({ id: 4, entity_id: 2, trace_id: 't8' }),
      row({ id: 5, entity_id: 1, trace_id: 't1' }),
      row({ id: 6, entity_id: 2, trace_id: 't1' }),
      row({ id: 7, entity_id: 1, trace_id: 't2' }),
      row({ id: 8, entity_id: 2, trace_id: 't2' }),
      row({ id: 9, entity_id: 5, trace_id: 't5' }),
      row({ id: 10, entity_id: 5, trace_id: 't5' }),
    ]);

    expect(edges.map((edge) => [edge.source, edge.target, edge.sharedTraces])).toEqual([
      [1, 2, 2],
      [2, 9, 1],
      [3, 4, 1],
    ]);
  });
});

describe('rowsInBrush', () => {
  const rows = [
    row({ id: 1, created_at: '2026-10-06T10:00:00Z' }),
    row({ id: 2, created_at: '2026-10-06T10:30:00Z' }),
    row({ id: 3, created_at: '2026-10-06T11:00:00Z' }),
  ];

  it('passes everything through with no brush', () => {
    expect(rowsInBrush(rows, null)).toHaveLength(3);
  });

  it('drops a row before the brush, not only one after it', () => {
    const earlier = [
      row({ id: 0, created_at: '2026-10-06T09:30:00Z' }),
      row({ id: 1, created_at: '2026-10-06T10:00:00Z' }),
      row({ id: 2, created_at: '2026-10-06T10:30:00Z' }),
      row({ id: 3, created_at: '2026-10-06T11:00:00Z' }),
    ];

    const kept = rowsInBrush(earlier, {
      from: Date.parse('2026-10-06T10:00:00Z'),
      to: Date.parse('2026-10-06T11:00:00Z'),
    });

    expect(kept.map((entry) => entry.id)).toEqual([1, 2]);
  });

  it('keeps a row on the left edge and drops one on the right', () => {
    // Half-open, exactly like the API's window: two adjacent brushes must not both
    // claim a row sitting on the boundary.
    const kept = rowsInBrush(rows, {
      from: Date.parse('2026-10-06T10:00:00Z'),
      to: Date.parse('2026-10-06T11:00:00Z'),
    });

    expect(kept.map((entry) => entry.id)).toEqual([1, 2]);
  });
});
