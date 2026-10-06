/**
 * The thresholds model (T-410, design.md §4.8, FR-13/FR-18).
 *
 * The preview is the part §4.8 asks for by name — *a preview of how many alerts the new
 * value would have produced over the last 7 days* — and the claims worth testing are
 * about what the sentences commit to: the window, the unit (alerts, not occurrences),
 * and the "at least" when the walk stopped at its page cap. A preview that rendered
 * `412` for a floored count would be a number the operator would act on and that the
 * server never claimed.
 */
import { describe, expect, it } from 'vitest';

import type { Threshold, ThresholdImpact, ThresholdList } from '../../api/admin';
import {
  BAND_WITHOUT_BOUND,
  SOURCE_CALIBRATED,
  SOURCE_DEFAULT,
  SOURCE_MANUAL,
  bandRows,
  formatThreshold,
  knownFamilies,
  readPreview,
  setReadiness,
} from './thresholds';

function row(over: Partial<Threshold> = {}): Threshold {
  return {
    tenant_id: 't1',
    family: 'flow',
    band: 'high',
    value: 0.72,
    source: 'recalculation',
    source_label: 'calibrated',
    updated_at: '2026-10-01T00:00:00Z',
    changed_by: 'ops@example.test',
    ...over,
  };
}

function listing(items: Threshold[], defaults: Record<string, number>): ThresholdList {
  return { tenant_id: 't1', defaults, items };
}

const FR13 = { critical: 0.9, high: 0.7, medium: 0.4, low: 0.2 };

describe('bandRows', () => {
  it('returns four rows for a family with no stored row, all default', () => {
    // A family nobody has moved is not a family without thresholds: returning no
    // rows would make "never recalibrated" look like "nothing is banded".
    const rows = bandRows(listing([], FR13), 'flow');
    expect(rows.map((r) => r.band)).toEqual(['critical', 'high', 'medium', 'low']);
    expect(rows.every((r) => r.source === SOURCE_DEFAULT)).toBe(true);
    expect(rows.every((r) => !r.moved)).toBe(true);
    expect(rows[1]?.value).toBe(0.7);
    expect(rows[1]?.changedBy).toBe('not changed on this deployment');
  });

  it('prefers the stored row to the default and keeps its provenance', () => {
    const rows = bandRows(listing([row()], FR13), 'flow');
    expect(rows[1]?.value).toBe(0.72);
    expect(rows[1]?.source).toBe(SOURCE_CALIBRATED);
    expect(rows[1]?.moved).toBe(true);
    expect(rows[1]?.changedBy).toBe('ops@example.test');
    expect(rows[0]?.value).toBe(0.9);
    expect(rows[0]?.source).toBe(SOURCE_DEFAULT);
  });

  it('maps the stored source to §4.8’s vocabulary', () => {
    const calibrated = bandRows(listing([row()], FR13), 'flow')[1];
    expect(calibrated?.sourceLabel).toBe('Fitted by the recalibration job (T-322)');
    const manual = bandRows(
      listing([row({ source: 'manual', source_label: 'manual' })], FR13),
      'flow',
    )[1];
    expect(manual?.source).toBe(SOURCE_MANUAL);
    expect(manual?.sourceLabel).toBe('Set by hand');
  });

  it('reads a handed-back source it does not know as itself', () => {
    const rows = bandRows(listing([row({ source_label: 'imported' })], FR13), 'flow');
    expect(rows[1]?.source).toBe('imported');
    expect(rows[1]?.sourceLabel).toBe('imported');
  });

  it('marks a value moved with no trail entry as unrecorded rather than guessing', () => {
    const rows = bandRows(listing([row({ changed_by: null })], FR13), 'flow');
    expect(rows[1]?.changedBy).toBe('not recorded in the trail');
  });

  it('ignores another family’s rows', () => {
    const rows = bandRows(listing([row({ family: 'log', value: 0.99 })], FR13), 'flow');
    expect(rows[1]?.value).toBe(0.7);
  });

  it('is empty for an unread listing', () => {
    expect(bandRows(undefined, 'flow')).toEqual([]);
  });
});

describe('knownFamilies', () => {
  it('lists the families with a moved threshold, alphabetically and once each', () => {
    const families = knownFamilies(
      listing([row({ family: 'log' }), row({ band: 'low' }), row({ family: 'auth' })], FR13),
    );
    expect(families).toEqual(['auth', 'flow', 'log']);
  });

  it('is empty when nothing has been moved', () => {
    expect(knownFamilies(listing([], FR13))).toEqual([]);
  });
});

describe('readPreview', () => {
  function impact(over: Partial<ThresholdImpact> = {}): ThresholdImpact {
    return {
      tenant_id: 't1',
      family: 'flow',
      band: 'high',
      proposed: 0.8,
      current: 0.7,
      current_source: 'manual',
      window_start: '2026-09-29T10:00:00Z',
      window_end: '2026-10-06T10:00:00Z',
      alerts_read: 412,
      would_fire: 98,
      would_stop_firing: 12,
      would_start_firing: 0,
      complete: true,
      ...over,
    };
  }

  it('gives the count with the window and the unit it was counted in', () => {
    const reading = readPreview(impact());
    expect(reading.headline).toContain('98 of the 412 recorded alerts');
    expect(reading.basis).toContain('one per alert row rather than per occurrence');
    expect(reading.basis).toContain('T-308');
    expect(reading.caveat).toBeNull();
  });

  it('says "at least" and explains itself when the walk hit its page cap', () => {
    const reading = readPreview(impact({ complete: false }));
    expect(reading.headline.startsWith('at least 98')).toBe(true);
    expect(reading.caveat).toContain('floored counts rather than totals');
  });

  it('describes a raise by what no longer reaches the band', () => {
    expect(readPreview(impact()).change).toBe(
      'Raising high from 0.70 to 0.80: 12 alerts would no longer reach it.',
    );
  });

  it('describes a lower by what newly reaches it', () => {
    const reading = readPreview(impact({ proposed: 0.6, would_start_firing: 31 }));
    expect(reading.change).toBe(
      'Lowering high from 0.70 to 0.60: 31 alerts would reach it that do not today.',
    );
  });

  it('says the value is unchanged when the proposal equals the value in force', () => {
    expect(readPreview(impact({ proposed: 0.7 })).change).toBe('The value in force is unchanged.');
  });
});

describe('setReadiness', () => {
  it('refuses a value outside (0, 1)', () => {
    expect(setReadiness(0, 0.7).reason).toContain('strictly between 0 and 1');
    expect(setReadiness(1, 0.7).reason).toContain('strictly between 0 and 1');
    expect(setReadiness(-0.1, 0.7).ready).toBe(false);
  });

  it('refuses the value already in force, so a no-op request is not sent', () => {
    expect(setReadiness(0.7, 0.7)).toEqual({
      ready: false,
      reason: 'This is the value already in force.',
    });
  });

  it('refuses a missing or non-numeric value', () => {
    expect(setReadiness(null, 0.7).reason).toBe('Enter a value to preview.');
    expect(setReadiness(Number.NaN, 0.7).reason).toContain('between 0 and 1');
  });

  it('accepts a real change', () => {
    expect(setReadiness(0.8, 0.7)).toEqual({ ready: true, reason: null });
  });
});

describe('the band vocabulary', () => {
  it('names the band with no lower bound, which cannot be set', () => {
    expect(BAND_WITHOUT_BOUND).toBe('info');
  });

  it('quotes a band edge at two decimals', () => {
    expect(formatThreshold(0.7)).toBe('0.70');
    expect(formatThreshold(0.726)).toBe('0.73');
    // 0.725 is stored as the double just *below* the half, so it rounds down. The
    // panel quotes the number in force rather than the one that was typed in.
    expect(formatThreshold(0.725)).toBe('0.72');
  });
});
