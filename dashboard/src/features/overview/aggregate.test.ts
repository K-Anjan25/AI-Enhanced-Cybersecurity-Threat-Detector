/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';

import {
  countBySeverity,
  countOpen,
  delta,
  familyMix,
  peakSeverity,
  severitySeries,
  topEntities,
} from './aggregate';
import type { AlertRow } from './api';

const WINDOW_START = new Date('2026-10-06T00:00:00Z');
const WINDOW_END = new Date('2026-10-07T00:00:00Z');

function row(overrides: Partial<AlertRow> = {}): AlertRow {
  return {
    id: 1,
    created_at: '2026-10-06T12:00:00Z',
    entity_id: 7,
    family: 'Reconnaissance',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: '2026-10-06T11:00:00Z',
    last_seen: '2026-10-06T12:00:00Z',
    occurrence_count: 3,
    trace_id: null,
    ...overrides,
  };
}

describe('countBySeverity', () => {
  it('counts every palette severity and starts from zero', () => {
    const tally = countBySeverity([row({ severity: 'critical' }), row({ severity: 'benign' })]);

    expect(tally.critical).toBe(1);
    expect(tally.benign).toBe(1);
    expect(tally.high).toBe(0);
    expect(Object.keys(tally).sort()).toEqual(
      ['benign', 'critical', 'high', 'info', 'low', 'medium', 'unrecognised'].sort(),
    );
  });

  it('counts a severity it does not know instead of dropping the row', () => {
    // The column is a checked enum (T-321), but a count that silently skips a
    // value would not add up to the rows the API sent.
    const tally = countBySeverity([row({ severity: 'catastrophic' }), row({ severity: 'high' })]);

    expect(tally.unrecognised).toBe(1);
    expect(tally.high).toBe(1);
    expect(Object.values(tally).reduce((sum, value) => sum + value, 0)).toBe(2);
  });
});

describe('countOpen and peakSeverity', () => {
  it('counts only open alerts', () => {
    expect(
      countOpen([row({ status: 'open' }), row({ status: 'resolved' }), row({ status: 'open' })]),
    ).toBe(2);
  });

  it('reports the most serious severity present', () => {
    expect(peakSeverity([row({ severity: 'low' }), row({ severity: 'critical' })])).toBe(
      'critical',
    );
    expect(peakSeverity([])).toBeNull();
    // An unrecognised severity is not a band, so it cannot be the peak.
    expect(peakSeverity([row({ severity: 'catastrophic' })])).toBeNull();
  });
});

describe('severitySeries', () => {
  it('tiles the window exactly, with the last bucket ending at the window end', () => {
    const series = severitySeries([], { start: WINDOW_START, end: WINDOW_END, buckets: 24 });

    expect(series).toHaveLength(24);
    expect(series[0]?.start).toEqual(WINDOW_START);
    expect(series.at(-1)?.end).toEqual(WINDOW_END);
    // Contiguous: no gap and no overlap.
    for (let index = 1; index < series.length; index += 1) {
      expect(series[index]?.start).toEqual(series[index - 1]?.end);
    }
  });

  it('puts each row in its bucket, and every row in some bucket', () => {
    const rows = [
      row({ created_at: '2026-10-06T00:30:00Z', severity: 'high' }),
      row({ created_at: '2026-10-06T12:00:00Z', severity: 'critical' }),
      // A hair past the end: clamped into the last bucket rather than dropped, so
      // the series total still equals the row count.
      row({ created_at: '2026-10-07T00:00:01Z', severity: 'low' }),
    ];
    const series = severitySeries(rows, { start: WINDOW_START, end: WINDOW_END, buckets: 24 });

    expect(series[0]?.counts.high).toBe(1);
    expect(series[12]?.counts.critical).toBe(1);
    expect(series.at(-1)?.counts.low).toBe(1);
    expect(series.reduce((total, bucket) => total + bucket.total, 0)).toBe(3);
  });

  it('skips a row whose timestamp cannot be read', () => {
    const series = severitySeries([row({ created_at: 'not a date' })], {
      start: WINDOW_START,
      end: WINDOW_END,
      buckets: 4,
    });

    expect(series.reduce((total, bucket) => total + bucket.total, 0)).toBe(0);
  });

  it('refuses a window that is empty or inverted', () => {
    expect(() => severitySeries([], { start: WINDOW_END, end: WINDOW_START, buckets: 4 })).toThrow(
      RangeError,
    );
    expect(() =>
      severitySeries([], { start: WINDOW_START, end: WINDOW_START, buckets: 4 }),
    ).toThrow(RangeError);
    expect(() => severitySeries([], { start: WINDOW_START, end: WINDOW_END, buckets: 0 })).toThrow(
      RangeError,
    );
  });
});

describe('topEntities', () => {
  it('ranks by alert count, then by peak severity', () => {
    const rows = [
      row({ entity_id: 1, severity: 'low' }),
      row({ entity_id: 1, severity: 'low' }),
      row({ entity_id: 2, severity: 'critical' }),
      row({ entity_id: 2, severity: 'critical' }),
      row({ entity_id: 3, severity: 'critical' }),
    ];

    const ranked = topEntities(rows, 5);

    // Entity 2 leads entity 1: both have two alerts, and the tie breaks toward the
    // more serious peak. Entity 3 has one alert, so it is last.
    expect(ranked.map((entity) => entity.entityId)).toEqual([2, 1, 3]);
    expect(ranked[0]).toMatchObject({ alerts: 2, peak: 'critical' });
    expect(ranked[1]).toMatchObject({ alerts: 2, peak: 'low' });
  });

  it('breaks a complete tie by id, so two refreshes agree', () => {
    const rows = [row({ entity_id: 9 }), row({ entity_id: 4 })];

    expect(topEntities(rows, 5).map((entity) => entity.entityId)).toEqual([4, 9]);
  });

  it('sums occurrences as well as alerts', () => {
    const sum = topEntities([row({ occurrence_count: 4 }), row({ occurrence_count: 6 })], 5);

    expect(sum[0]?.occurrences).toBe(10);
  });

  it('applies the limit', () => {
    const rows = [1, 2, 3, 4].map((entityId) => row({ entity_id: entityId }));

    expect(topEntities(rows, 2)).toHaveLength(2);
  });
});

describe('familyMix', () => {
  it('counts and sorts descending, with the peak severity per family', () => {
    const rows = [
      row({ family: 'DDoS', severity: 'high' }),
      row({ family: 'Brute force', severity: 'medium' }),
      row({ family: 'DDoS', severity: 'critical' }),
    ];

    const mix = familyMix(rows);

    expect(mix.map((family) => family.family)).toEqual(['DDoS', 'Brute force']);
    expect(mix[0]).toMatchObject({ count: 2, peak: 'critical' });
  });

  it('keeps an unnamed family, because the counts have to add up', () => {
    const mix = familyMix([row({ family: '  ' })]);

    expect(mix[0]?.family).toBe('(unnamed)');
  });

  it('breaks a tie by name', () => {
    const mix = familyMix([row({ family: 'Zeta' }), row({ family: 'Alpha' })]);

    expect(mix.map((family) => family.family)).toEqual(['Alpha', 'Zeta']);
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
