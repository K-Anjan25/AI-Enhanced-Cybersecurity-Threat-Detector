import { describe, expect, it } from 'vitest';

import { brushLabel, buildTrafficView, DEFAULT_FILTERS, type TrafficFilters } from './view';
import { GRAPH_NODE_LIMIT } from './graph';
import type { AlertRow } from '../../api/alerts';

const START = new Date('2026-10-06T10:00:00Z');
const END = new Date('2026-10-06T11:00:00Z');

function row(overrides: Partial<AlertRow> & { id: number }): AlertRow {
  return {
    created_at: '2026-10-06T10:30:00Z',
    entity_id: 1,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: '2026-10-06T10:00:00Z',
    last_seen: '2026-10-06T10:30:00Z',
    occurrence_count: 10,
    trace_id: null,
    ...overrides,
  };
}

function view(
  rows: AlertRow[],
  overrides: {
    brush?: { from: number; to: number } | null;
    filters?: Partial<TrafficFilters>;
    pinnedEntityId?: number | null;
    complete?: boolean;
    pagesFetched?: number;
  } = {},
) {
  return buildTrafficView({
    rows,
    start: START,
    end: END,
    complete: overrides.complete ?? true,
    pagesFetched: overrides.pagesFetched ?? 1,
    brush: overrides.brush ?? null,
    filters: { ...DEFAULT_FILTERS, ...overrides.filters },
    pinnedEntityId: overrides.pinnedEntityId ?? null,
    buckets: 4,
  });
}

describe('buildTrafficView', () => {
  const rows = [
    row({
      id: 1,
      entity_id: 1,
      created_at: '2026-10-06T10:05:00Z',
      occurrence_count: 40,
      trace_id: 't1',
    }),
    row({
      id: 2,
      entity_id: 2,
      created_at: '2026-10-06T10:10:00Z',
      occurrence_count: 5,
      trace_id: 't1',
    }),
    row({
      id: 3,
      entity_id: 3,
      created_at: '2026-10-06T10:50:00Z',
      occurrence_count: 7,
      trace_id: null,
    }),
  ];

  it('draws the series from the whole window even when a brush is set', () => {
    // The series is the axis the brush is drawn on: a series derived from its own
    // selection could never be re-brushed, and the reference position would vanish.
    const brushed = view(rows, {
      brush: { from: START.getTime(), to: START.getTime() + 1_800_000 },
    });

    expect(brushed.series.reduce((total, bucket) => total + bucket.alerts, 0)).toBe(3);
  });

  it('filters the entities, the edges and the rows by the brush', () => {
    const brushed = view(rows, {
      brush: { from: START.getTime(), to: START.getTime() + 1_800_000 },
    });

    expect(brushed.rows.map((entry) => entry.id)).toEqual([1, 2]);
    expect(brushed.entities.map((entry) => entry.entityId)).toEqual([1, 2]);
    expect(brushed.edges).toHaveLength(1);
    expect(brushed.graph.nodes).toHaveLength(2);
  });

  it('drops an edge that only existed inside the brushed-away part of the window', () => {
    const spread = [
      row({ id: 1, entity_id: 1, created_at: '2026-10-06T10:05:00Z', trace_id: 'early' }),
      row({ id: 2, entity_id: 2, created_at: '2026-10-06T10:06:00Z', trace_id: 'early' }),
      row({ id: 3, entity_id: 3, created_at: '2026-10-06T10:50:00Z', trace_id: 'late' }),
      row({ id: 4, entity_id: 4, created_at: '2026-10-06T10:51:00Z', trace_id: 'late' }),
    ];

    const whole = view(spread);
    expect(whole.edges).toHaveLength(2);

    // Brushing the second half of the window removes the early trace's edge as well as
    // the entities it connected: an edge is a claim about the selection, not about the
    // window the selection was drawn on.
    const late = view(spread, {
      brush: { from: Date.parse('2026-10-06T10:30:00Z'), to: END.getTime() },
    });

    expect(late.entities.map((entry) => entry.entityId)).toEqual([3, 4]);
    expect(late.edges).toEqual([{ source: 3, target: 4, sharedTraces: 1 }]);
  });

  it('reports how many entities the controls removed, rather than shrinking silently', () => {
    const filtered = view(rows, { filters: { minRecords: 10 } });

    expect(filtered.entities.map((entry) => entry.entityId)).toEqual([1]);
    expect(filtered.hiddenByControls).toBe(2);
  });

  it('keeps only entities with an open alert when asked', () => {
    const judged = [
      row({ id: 1, entity_id: 1, status: 'resolved' }),
      row({ id: 2, entity_id: 2, status: 'open' }),
    ];

    const filtered = view(judged, { filters: { openOnly: true } });

    expect(filtered.entities.map((entry) => entry.entityId)).toEqual([2]);
  });

  it('keeps a pinned entity even when the controls would have hidden it', () => {
    // The pin is a question about one entity, so no threshold may remove it from the
    // answer. Entity 3 has volume 7 and no trace context: `minRecords: 100` hides it,
    // it has no neighbour to bring back, and the view is the pin alone rather than the
    // pin plus whatever happened not to be filtered out.
    const pinned = view(rows, { filters: { minRecords: 100 }, pinnedEntityId: 3 });

    expect(pinned.pinned?.entityId).toBe(3);
    expect(pinned.entities.map((entry) => entry.entityId)).toEqual([3]);
    expect(pinned.graph.nodes.map((node) => node.entityId)).toEqual([3]);
  });

  it('keeps the controlled view on screen when a pin is added to it', () => {
    // Widening, not a switch to focus mode: whatever the analyst was already looking
    // at stays, with the pin and its neighbourhood promoted above it.
    const others = [
      row({ id: 1, entity_id: 1, occurrence_count: 40, trace_id: 't1' }),
      row({ id: 2, entity_id: 2, occurrence_count: 30, trace_id: null }),
      row({ id: 3, entity_id: 3, occurrence_count: 7, trace_id: 't1' }),
      row({ id: 4, entity_id: 4, occurrence_count: 20, trace_id: null }),
    ];

    const pinned = view(others, { filters: { minRecords: 10 }, pinnedEntityId: 3 });

    expect(pinned.entities.map((entry) => entry.entityId)).toEqual([3, 1, 2, 4]);
  });

  it('brings a pinned entity’s neighbours back into view', () => {
    const withNeighbour = [
      row({ id: 1, entity_id: 1, occurrence_count: 1, trace_id: 't1' }),
      row({ id: 2, entity_id: 3, occurrence_count: 99, trace_id: 't1' }),
      row({ id: 3, entity_id: 4, occurrence_count: 80, trace_id: null }),
    ];

    // Entity 3 is the pin and is connected to entity 1; entity 1's own volume is below
    // the threshold and entity 4 is above it but unrelated. So: the pin leads, the
    // neighbour comes back because the pin asked for it, and the unrelated entity keeps
    // its place.
    const pinned = view(withNeighbour, { filters: { minRecords: 50 }, pinnedEntityId: 3 });

    expect(pinned.pinned?.entityId).toBe(3);
    expect(pinned.entities.map((entry) => entry.entityId)).toEqual([3, 1, 4]);
    expect(pinned.entities.filter((entry) => entry.entityId === 3)).toHaveLength(1);
  });

  it('reports a partial read when the page cap stopped the walk', () => {
    const partial = view(rows, { complete: false, pagesFetched: 5 });

    expect(partial.notes.some((note) => note.includes('first 5 pages'))).toBe(true);
  });

  it('says what the numbers are and are not, on every view', () => {
    // The permanent caveat is part of the model, so a panel cannot render the chart
    // without it: volume is alerted records, edges are shared traces, entities are
    // ids — each one a place this build cannot show what §4.4 draws.
    const notes = view(rows).notes.join(' ');

    expect(notes).toContain('raw-record count carried by alerts');
    expect(notes).toContain('shared correlation traces');
    expect(notes).toContain('T-416');
  });

  it('explains the matrix switch, with the counts it is showing and hiding', () => {
    const many = Array.from({ length: GRAPH_NODE_LIMIT + 1 }, (_unused, index) =>
      row({ id: index + 1, entity_id: index + 1, occurrence_count: 1 }),
    );

    const switched = view(many);

    expect(switched.matrix).not.toBeNull();
    // The label lives with the mode (so a panel cannot draw one without the other),
    // and the note carries the counts: drawn, and counted-but-not-drawn.
    expect(switched.graph.reason).toContain('ranked adjacency matrix');
    expect(switched.graph.reason).toContain(String(GRAPH_NODE_LIMIT + 1));
    expect(switched.notes.some((note) => note.includes('counted, not drawn'))).toBe(true);
  });

  it('computes no matrix when the graph is in force mode', () => {
    expect(view(rows).matrix).toBeNull();
  });

  it('leaves the pin null when it names an entity that is not in the selection', () => {
    expect(view(rows, { pinnedEntityId: 999 }).pinned).toBeNull();
  });

  it('keeps a pinned entity out of the list twice', () => {
    const pinned = view(rows, { pinnedEntityId: 1 });

    expect(pinned.entities.filter((entry) => entry.entityId === 1)).toHaveLength(1);
    expect(pinned.entities[0]?.entityId).toBe(1);
  });

  it('never throws on an empty window', () => {
    const empty = view([]);

    expect(empty.entities).toEqual([]);
    expect(empty.graph.mode).toBe('force');
    expect(empty.series.every((bucket) => bucket.score === null)).toBe(true);
  });
});

describe('brushLabel', () => {
  it('says "the whole window" when nothing is selected', () => {
    expect(brushLabel(null)).toBe('the whole window');
  });

  it('names the two instants in UTC, so the label cannot be read in the wrong zone', () => {
    expect(
      brushLabel({
        from: Date.parse('2026-10-06T10:15:00Z'),
        to: Date.parse('2026-10-06T10:45:00Z'),
      }),
    ).toBe('10:15–10:45 UTC');
  });
});
