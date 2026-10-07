/**
 * The traffic view model (T-418).
 *
 * What this file holds to account:
 *
 *   * **The series is the whole window's, always.** The chart is the axis the analyst
 *     brushes, so it is built from the unbrushed aggregate even while the panels below
 *     describe the brushed one — a series drawn from its own selection could never be
 *     re-brushed.
 *   * **The panels are the read's own counts.** Addresses and relationships come from
 *     the aggregate for the window on screen, so a brushed window's table is the
 *     server's top-N for that window rather than a slice of a wider one.
 *   * **The controls narrow, the pin widens.** `minFlows` and `openAlertsOnly` remove
 *     rows and report how many; a pin keeps its neighbours in view *and* survives the
 *     controls that would have hidden it.
 *   * **The caveats are the source's, verbatim.** The screen renders the server's
 *     sentences as they arrive, adding only the client-side facts (which sub-window the
 *     numbers describe, what the matrix did not draw).
 */
import { describe, expect, it } from 'vitest';

import { buildTrafficView, DEFAULT_FILTERS } from './view';
import type { FlowAggregate, FlowBucket, FlowEntity } from '../../api/flows';

const START = Date.parse('2026-10-06T10:00:00Z');
const MINUTE = 60_000;

function bucket(index: number, flows: number): FlowBucket {
  return {
    start: new Date(START + index * 5 * MINUTE).toISOString(),
    flows,
    bytes: flows * 100,
    packets: flows,
    alerts: 0,
    score: null,
  };
}

function entity(overrides: Partial<FlowEntity> & { ip: string }): FlowEntity {
  return {
    flows: 10,
    bytes: 1_000,
    packets: 10,
    inbound: 0,
    outbound: 10,
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
      end: new Date(START + 60 * MINUTE).toISOString(),
      hours: 1,
    },
    bucket_minutes: 5,
    source: 'rollup',
    filters: { protocol: null, direction: null },
    series: [bucket(0, 4), bucket(1, 8), bucket(2, 0), bucket(3, 2)],
    entities: [entity({ ip: '10.0.0.1' }), entity({ ip: '10.0.0.2', flows: 5 })],
    edges: [{ source: '10.0.0.1', target: '10.0.0.2', flows: 4, bytes: 400 }],
    totals: {
      flows: 14,
      bytes: 1_400,
      packets: 14,
      nodes: 2,
      edges: 1,
      nodes_capped: false,
      edges_capped: false,
      untracked_address_flows: 0,
      untracked_pair_flows: 0,
    },
    caveats: ['These numbers are counted from the flow store.'],
    ...overrides,
  };
}

function view(overrides: Partial<Parameters<typeof buildTrafficView>[0]> = {}) {
  const panels = overrides.panels ?? aggregate();
  return buildTrafficView({
    aggregate: overrides.aggregate ?? aggregate(),
    panels,
    brush: overrides.brush ?? null,
    filters: overrides.filters ?? DEFAULT_FILTERS,
    pinnedId: overrides.pinnedId ?? null,
  });
}

describe('the series and the panels', () => {
  it('draws the series from the whole window even when the panels are brushed', () => {
    const brushed = aggregate({ series: [bucket(1, 8)] });

    const model = view({
      panels: brushed,
      brush: { from: START + 5 * MINUTE, to: START + 10 * MINUTE },
    });

    expect(model.series.map((point) => point.flows)).toEqual([4, 8, 0, 2]);
  });

  it('takes the addresses from the aggregate the read produced', () => {
    const model = view();

    expect(model.nodes.map((node) => node.id)).toEqual(['10.0.0.1', '10.0.0.2']);
  });

  it('takes the relationships from the read, weighted by records', () => {
    const model = view();

    expect(model.edges).toEqual([{ source: '10.0.0.1', target: '10.0.0.2', flows: 4, bytes: 400 }]);
  });

  it('does not re-sort the read model’s ranking', () => {
    // The API orders addresses busiest first with its own tie-breaks; a second sort here
    // would be a second answer to the same question.
    const model = view({
      panels: aggregate({
        entities: [entity({ ip: '10.0.0.9', flows: 3 }), entity({ ip: '10.0.0.8', flows: 5 })],
      }),
    });

    expect(model.nodes.map((node) => node.id)).toEqual(['10.0.0.9', '10.0.0.8']);
  });
});

describe('the controls', () => {
  it('hides addresses below the flow threshold and counts them', () => {
    const model = view({
      panels: aggregate({
        entities: [entity({ ip: '10.0.0.1', flows: 10 }), entity({ ip: '10.0.0.2', flows: 2 })],
      }),
      filters: { ...DEFAULT_FILTERS, minFlows: 5 },
    });

    expect(model.nodes.map((node) => node.id)).toEqual(['10.0.0.1']);
    expect(model.hiddenByControls).toBe(1);
  });

  it('keeps exactly the threshold value', () => {
    const model = view({ filters: { ...DEFAULT_FILTERS, minFlows: 10 } });

    expect(model.nodes.map((node) => node.id)).toEqual(['10.0.0.1']);
  });

  it('keeps only addresses with an open alert when asked', () => {
    const model = view({
      panels: aggregate({
        entities: [
          entity({ ip: '10.0.0.1', alerts: 3, open_alerts: 0 }),
          entity({ ip: '10.0.0.2', alerts: 1, open_alerts: 1 }),
        ],
      }),
      filters: { ...DEFAULT_FILTERS, openAlertsOnly: true },
    });

    expect(model.nodes.map((node) => node.id)).toEqual(['10.0.0.2']);
  });

  it('reports no hidden rows when nothing was hidden', () => {
    expect(view().hiddenByControls).toBe(0);
  });
});

describe('the pin', () => {
  const panels = aggregate({
    entities: [
      entity({ ip: '10.0.0.1', flows: 10 }),
      entity({ ip: '10.0.0.2', flows: 2 }),
      entity({ ip: '10.0.0.3', flows: 9 }),
    ],
    edges: [
      { source: '10.0.0.1', target: '10.0.0.2', flows: 2, bytes: 200 },
      { source: '10.0.0.3', target: '10.0.0.1', flows: 1, bytes: 100 },
    ],
  });

  it('promotes the pinned address and its neighbours to the front', () => {
    const model = view({ panels, pinnedId: '10.0.0.1' });

    expect(model.nodes.slice(0, 3).map((node) => node.id)).toEqual([
      '10.0.0.1',
      '10.0.0.2',
      '10.0.0.3',
    ]);
  });

  it('keeps a pinned address visible even when a control would hide it', () => {
    // The pin is a question ("what is this connected to?") and the answer must not be
    // an empty panel because the analyst's own threshold excluded the subject.
    const model = view({
      panels,
      pinnedId: '10.0.0.2',
      filters: { ...DEFAULT_FILTERS, minFlows: 5 },
    });

    expect(model.nodes.map((node) => node.id)).toContain('10.0.0.2');
  });

  it('promotes a neighbour the controls had hidden', () => {
    const model = view({
      panels,
      pinnedId: '10.0.0.1',
      filters: { ...DEFAULT_FILTERS, minFlows: 5 },
    });

    expect(model.nodes.map((node) => node.id)).toContain('10.0.0.2');
  });

  it('reports nothing pinned when the address is not in the read', () => {
    const model = view({ panels, pinnedId: '203.0.113.9' });

    expect(model.pinned).toBeNull();
  });

  it('exposes the pinned node for the table and the graph', () => {
    const model = view({ panels, pinnedId: '10.0.0.3' });

    expect(model.pinned?.id).toBe('10.0.0.3');
  });
});

describe('the caveats', () => {
  it('carries the source’s own sentences verbatim, first', () => {
    const caveats = ['These numbers are counted from the flow store.', 'A cap applies.'];

    const model = view({ panels: aggregate({ caveats }) });

    expect(model.notes.slice(0, 2)).toEqual(caveats);
  });

  it('says which sub-window the panels describe when a brush is set', () => {
    const model = view({ brush: { from: START + 5 * MINUTE, to: START + 35 * MINUTE } });

    expect(model.notes.join(' ')).toContain('10:05–10:35');
  });

  it('does not mention a brush when there is none', () => {
    expect(view().notes.join(' ')).not.toContain('brushed window');
  });

  it('says what the ranked matrix left undrawn', () => {
    // Past the node limit the graph becomes a matrix, and a matrix without the count of
    // what it is not drawing looks like the whole graph.
    const many = Array.from({ length: 2_001 }, (_unused, index) =>
      entity({ ip: `10.0.${String(index % 250)}.${String(Math.floor(index / 250))}` }),
    );
    const model = view({
      panels: aggregate({ entities: many }),
      aggregate: aggregate({ entities: many }),
    });

    expect(model.graph.mode).toBe('adjacency');
    expect(model.notes.join(' ')).toContain('most active of 2001 addresses');
  });

  it('keeps a source caveat even when the panel has no rows', () => {
    const model = view({
      panels: aggregate({ entities: [], edges: [], caveats: ['Nothing has been counted yet.'] }),
    });

    expect(model.notes).toContain('Nothing has been counted yet.');
  });
});
