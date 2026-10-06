/**
 * The fold from a tail response to rows, asserted on what a panel would render.
 *
 * The rule under test is the one the model exists for: a number never reaches a panel
 * without the API's own sentence about what the tail is — and an empty window arrives
 * with a reason rather than as a blank table.
 */
import { describe, expect, it } from 'vitest';

import { buildLogView } from './view';
import { tailWindow } from './cluster';
import type { LogCluster, LogTail } from './api';

const WINDOW = tailWindow(Date.parse('2026-10-06T10:05:00Z'), 300_000);

function cluster(overrides: Partial<LogCluster> = {}): LogCluster {
  return {
    key: 't-1',
    template_id: 't-1',
    count: 1,
    first_seen: '2026-10-06T10:00:00Z',
    last_seen: '2026-10-06T10:00:09Z',
    worst_level: 'info',
    levels: { info: 1 },
    hosts: ['web-1'],
    services: ['api'],
    sample_message: 'connection refused',
    parameters: {},
    ...overrides,
  };
}

function tail(overrides: Partial<LogTail> = {}): LogTail {
  return {
    start: '2026-10-06T10:00:00Z',
    end: '2026-10-06T10:05:00Z',
    clusters: [cluster()],
    lines_seen: 1,
    clusters_seen: 1,
    clusters_truncated: false,
    retained_from: '2026-10-06T10:00:00Z',
    retained_to: '2026-10-06T10:00:09Z',
    retained_lines: 1,
    dropped_lines: 0,
    caveats: ['the tail is not a store', 'nothing matched these filters'],
    ...overrides,
  };
}

describe('buildLogView', () => {
  it('is loading until a response arrives, never empty', () => {
    const view = buildLogView({ tail: undefined, window: WINDOW, failed: false });

    expect(view.state).toBe('loading');
    expect(view.rows).toEqual([]);
  });

  it('is an error when the read failed, with no rows invented', () => {
    const view = buildLogView({ tail: undefined, window: WINDOW, failed: true });

    expect(view.state).toBe('error');
    expect(view.retention).toBe('The tail could not be read.');
  });

  it('turns a cluster into the cells the table renders', () => {
    const view = buildLogView({
      tail: tail({
        clusters: [
          cluster({
            count: 10_000,
            worst_level: 'error',
            levels: { error: 2, info: 9_998 },
            hosts: ['web-1', 'web-2', 'web-3', 'web-4'],
            services: ['api', 'worker'],
            first_seen: '2026-10-06T10:00:00Z',
            last_seen: '2026-10-06T10:04:59Z',
          }),
        ],
        lines_seen: 10_000,
      }),
      window: WINDOW,
      failed: false,
    });

    const row = view.rows[0];
    expect(row?.count).toBe('×10,000');
    expect(row?.template).toBe('t-1');
    expect(row?.levels).toBe('2 error, 9,998 info');
    expect(row?.level).toBe('error');
    expect(row?.tone).toBe('high');
    expect(row?.notable).toBe(true);
    expect(row?.span).toBe('10:00:00Z → 10:04:59Z');
    // Four hosts collapse to a count rather than a list a cell cannot hold.
    expect(row?.hosts).toBe('4 hosts');
    expect(row?.services).toBe('api, worker');
  });

  it('counts the rows a reader should look at', () => {
    const view = buildLogView({
      tail: tail({
        clusters: [
          cluster({ key: 'a', template_id: 'a', worst_level: 'critical' }),
          cluster({ key: 'b', template_id: 'b', worst_level: 'warning' }),
          cluster({ key: 'c', template_id: 'c', worst_level: 'info' }),
        ],
      }),
      window: WINDOW,
      failed: false,
    });

    expect(view.notableCount).toBe(1);
    expect(view.state).toBe('rows');
  });

  it('carries the API’s caveats through verbatim', () => {
    const caveats = [
      'This tail holds the most recent 20,000 lines',
      'Nothing matched these filters',
    ];
    const view = buildLogView({ tail: tail({ caveats }), window: WINDOW, failed: false });

    // Verbatim, in order: a screen that reworded "not a store" would eventually word
    // it wrong, and the claim is about the deployment rather than the data.
    expect(view.caveats).toEqual(caveats);
  });

  it('says how much the tail holds, and whether anything aged out', () => {
    const view = buildLogView({
      tail: tail({ retained_lines: 12_000, dropped_lines: 3, retained_to: '2026-10-06T10:04:59Z' }),
      window: WINDOW,
      failed: false,
    });

    expect(view.retention).toBe(
      'Holding 12,000 lines · 3 aged out · newest 06 Oct 2026, 10:04:59Z.',
    );
  });

  it('says nothing has aged out rather than leaving the number out', () => {
    const view = buildLogView({ tail: tail({ dropped_lines: 0 }), window: WINDOW, failed: false });

    expect(view.retention).toContain('nothing aged out yet');
  });

  it('describes an empty window with the API’s own reason', () => {
    const view = buildLogView({
      tail: tail({
        clusters: [],
        lines_seen: 0,
        caveats: ['the tail is not a store', 'The tail is empty: 4,000 lines have aged out'],
      }),
      window: WINDOW,
      failed: false,
    });

    expect(view.state).toBe('empty');
    expect(view.emptyReason).toBe('The tail is empty: 4,000 lines have aged out');
  });

  it('has no empty reason when there are rows to show', () => {
    const view = buildLogView({ tail: tail(), window: WINDOW, failed: false });

    expect(view.emptyReason).toBeNull();
  });

  it('labels the window it was asked about, not the one it was given', () => {
    const view = buildLogView({
      tail: tail({ start: '2026-10-01T00:00:00Z', end: '2026-10-01T00:05:00Z' }),
      window: WINDOW,
      failed: false,
    });

    // The label describes the request; a response echoing a different window is a
    // server bug, and printing the server's window beside the client's rows would
    // hide it rather than show it.
    expect(view.windowLabel).toBe('10:00:00–10:05:00 UTC');
  });

  it('reports the API’s truncation rather than a row count', () => {
    const view = buildLogView({
      tail: tail({ clusters_seen: 900, clusters_truncated: true }),
      window: WINDOW,
      failed: false,
    });

    expect(view.truncated).toBe(true);
    expect(view.clustersSeen).toBe(900);
    expect(view.rows).toHaveLength(1);
  });
});
