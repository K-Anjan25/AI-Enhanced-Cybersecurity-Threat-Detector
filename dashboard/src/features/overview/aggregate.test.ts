/**
 * @vitest-environment node
 */
/**
 * The overview's arithmetic, against the wire shape T-416 serves.
 *
 * These are mappings, not counts, so the tests are about the two ways a mapping
 * can lose a row: a band the client's palette does not know, and a total the bands
 * do not add up to. Both must land in `unrecognised` rather than vanish, or the
 * tiles and the chart stop agreeing with the window they describe.
 */
import { describe, expect, it } from 'vitest';

import {
  delta,
  emptyTally,
  entitiesFromOverview,
  familiesFromOverview,
  seriesFromOverview,
  tallyFromOverview,
} from './aggregate';
import type { OverviewEntity, OverviewFamily, OverviewTotals } from './api';

function totals(overrides: Partial<OverviewTotals> = {}): OverviewTotals {
  return {
    alerts: 0,
    open: 0,
    by_severity: {},
    unrecognised_severity: 0,
    verdicts: {},
    unrecorded: 0,
    verdicts_measured: 0,
    mean_time_to_verdict_seconds: null,
    ...overrides,
  };
}

function entity(overrides: Partial<OverviewEntity> = {}): OverviewEntity {
  return {
    entity_id: 7,
    kind: 'host',
    value: 'web-01.corp',
    named: true,
    alerts: 3,
    occurrences: 9,
    open: 1,
    worst_severity: 'critical',
    max_score: 0.97,
    last_seen: '2026-10-06T11:30:00Z',
    ...overrides,
  };
}

describe('tallyFromOverview', () => {
  it('zero-fills every band the palette draws', () => {
    const tally = tallyFromOverview(totals({ alerts: 2, by_severity: { high: 2 } }));

    expect(tally).toEqual({ ...emptyTally(), high: 2 });
    expect(Object.keys(tally).sort()).toEqual(
      ['benign', 'critical', 'high', 'info', 'low', 'medium', 'unrecognised'].sort(),
    );
  });

  it('counts a band the palette does not know as unrecognised', () => {
    // The API's column is a checked enum (T-321) and the palette is the client's
    // own list; if they ever disagree the tile must still add up to the window.
    const tally = tallyFromOverview(
      totals({ alerts: 5, by_severity: { high: 3, apocalyptic: 2 }, unrecognised_severity: 0 }),
    );

    expect(tally.high).toBe(3);
    expect(tally.unrecognised).toBe(2);
    expect(Object.values(tally).reduce((sum, value) => sum + value, 0)).toBe(5);
  });

  it('trusts the window total over the bands it can see', () => {
    // A band map that covers three of four rows leaves the fourth unrecognised
    // rather than silently shrinking the tile.
    const tally = tallyFromOverview(totals({ alerts: 4, by_severity: { high: 3 } }));

    expect(tally.unrecognised).toBe(1);
  });

  it('does not double-count the server’s own unrecognised figure', () => {
    const tally = tallyFromOverview(
      totals({ alerts: 4, by_severity: { high: 1 }, unrecognised_severity: 3 }),
    );

    expect(tally.high).toBe(1);
    expect(tally.unrecognised).toBe(3);
  });
});

describe('seriesFromOverview', () => {
  it('maps buckets to instants and tallies, oldest first', () => {
    const points = seriesFromOverview([
      {
        start: '2026-10-06T10:00:00Z',
        total: 3,
        by_severity: { critical: 1, high: 2 },
      },
      { start: '2026-10-06T11:00:00Z', total: 1, by_severity: { low: 1 } },
    ]);

    expect(points.map((point) => point.start.toISOString())).toEqual([
      '2026-10-06T10:00:00.000Z',
      '2026-10-06T11:00:00.000Z',
    ]);
    expect(points[0]?.counts.critical).toBe(1);
    expect(points[0]?.counts.high).toBe(2);
    expect(points[0]?.total).toBe(3);
    expect(points[1]?.counts.low).toBe(1);
  });

  it('makes each bucket add up to its own total, unknown bands included', () => {
    const points = seriesFromOverview([
      { start: '2026-10-06T10:00:00Z', total: 3, by_severity: { high: 2, weird: 1 } },
    ]);

    const counts = points[0]?.counts;
    expect(counts?.unrecognised).toBe(1);
    expect(Object.values(counts ?? {}).reduce((sum, value) => sum + value, 0)).toBe(3);
    // A bucket counts every row it was given, and the total says so.
    expect(points[0]?.total).toBe(3);
  });

  it('keeps the buckets the server sent rather than inventing its own', () => {
    // The window's width and bucketing are the server's (T-416); the client maps,
    // it does not re-bucket. An empty series is an empty series, not 24 zeroes.
    expect(seriesFromOverview([])).toEqual([]);
  });
});

describe('entitiesFromOverview', () => {
  it('carries the kind and the value, so a row is named', () => {
    const [row] = entitiesFromOverview([entity()]);

    expect(row).toMatchObject({
      entityId: 7,
      named: true,
      kind: 'host',
      value: 'web-01.corp',
      alerts: 3,
      occurrences: 9,
      peak: 'critical',
    });
  });

  it('keeps an id the registry could not name, as an unnamed row', () => {
    const [row] = entitiesFromOverview([entity({ kind: null, value: null, named: false })]);

    expect(row?.named).toBe(false);
    expect(row?.kind).toBeNull();
    expect(row?.value).toBeNull();
    // The counts are unaffected by the missing name: the alerts were still there.
    expect(row?.alerts).toBe(3);
  });

  it('renders no pill for a band the palette does not know', () => {
    const [row] = entitiesFromOverview([entity({ worst_severity: 'apocalyptic' })]);

    expect(row?.peak).toBeNull();
  });

  it('keeps the order the server ranked', () => {
    // The server ranks by alert count with a total tie-break; a client that
    // re-sorted would be a second opinion about the one thing a top-N cannot have.
    const rows = entitiesFromOverview([entity({ entity_id: 9 }), entity({ entity_id: 3 })]);

    expect(rows.map((row) => row.entityId)).toEqual([9, 3]);
  });
});

describe('familiesFromOverview', () => {
  it('maps the server’s counts and keeps the unnamed row', () => {
    const families: OverviewFamily[] = [
      { family: 'Reconnaissance', alerts: 4, worst_severity: 'high' },
      { family: '(unnamed)', alerts: 1, worst_severity: 'low' },
    ];

    expect(familiesFromOverview(families)).toEqual([
      { family: 'Reconnaissance', count: 4, peak: 'high' },
      { family: '(unnamed)', count: 1, peak: 'low' },
    ]);
  });

  it('drops a peak the palette cannot label without dropping the bar', () => {
    const rows = familiesFromOverview([
      { family: 'Exfiltration', alerts: 2, worst_severity: 'apocalyptic' },
    ]);

    expect(rows).toEqual([{ family: 'Exfiltration', count: 2, peak: null }]);
  });
});

describe('delta', () => {
  it('reports the change when both windows were read completely', () => {
    expect(delta(12, 9, true)).toEqual({ previous: 9, change: 3 });
  });

  it('reports nothing when either window was partial', () => {
    // A delta against a truncated window is a confident, wrong arrow.
    expect(delta(12, 9, false)).toBeNull();
  });

  it('reports nothing without a previous window', () => {
    expect(delta(12, null, true)).toBeNull();
  });
});
