/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';

import {
  formatAge,
  formatCount,
  formatInstant,
  formatMilliseconds,
  formatPercent,
  formatRate,
  formatSince,
  formatStamp,
} from './format';

describe('formatAge', () => {
  it('says "just now" for a value that would round to zero', () => {
    // "0 s ago" reads as broken; the first band has to be a phrase.
    expect(formatAge(0)).toBe('just now');
    expect(formatAge(9.7)).toBe('just now');
  });

  it('names its unit in each band', () => {
    expect(formatAge(10)).toBe('10 s ago');
    expect(formatAge(59)).toBe('59 s ago');
    expect(formatAge(60)).toBe('1 m ago');
    expect(formatAge(3_599)).toBe('59 m ago');
    expect(formatAge(3_600)).toBe('1 h ago');
    expect(formatAge(7_200)).toBe('2 h ago');
    expect(formatAge(7_500)).toBe('2 h 5 m ago');
    expect(formatAge(86_400)).toBe('1 d ago');
    expect(formatAge(3 * 86_400)).toBe('3 d ago');
  });

  it('never renders a negative age when the clocks disagree', () => {
    // The clamp has to be asserted past a band boundary: at -5 s the "just now"
    // rule hides it, and at -60 s an unclamped value would print "-1 m ago".
    expect(formatAge(-5)).toBe('just now');
    expect(formatAge(-60)).toBe('just now');
    expect(formatAge(-86_400)).toBe('just now');
  });

  it('survives a duration that is not a number', () => {
    expect(formatAge(Number.NaN)).toBe('just now');
  });
});

describe('formatCount', () => {
  it('groups digits', () => {
    expect(formatCount(1_204)).toBe('1,204');
    expect(formatCount(0)).toBe('0');
  });

  it('shows a dash for a value that is not a number', () => {
    expect(formatCount(Number.NaN)).toBe('—');
  });
});

describe('formatRate', () => {
  it('carries its unit', () => {
    expect(formatRate(1_204, 'flows')).toBe('1,204 flows/s');
  });
});

describe('formatMilliseconds', () => {
  it('stays in milliseconds below a second, the unit the budgets use', () => {
    expect(formatMilliseconds(412.4)).toBe('412 ms');
  });

  it('switches to seconds above one', () => {
    expect(formatMilliseconds(1_000)).toBe('1.00 s');
    expect(formatMilliseconds(2_500)).toBe('2.50 s');
  });

  it('shows a dash when there is no measurement', () => {
    expect(formatMilliseconds(Number.NaN)).toBe('—');
  });
});

describe('formatPercent', () => {
  it('renders a proportion as whole percent', () => {
    expect(formatPercent(0.5)).toBe('50%');
    expect(formatPercent(0.987)).toBe('99%');
  });

  it('shows a dash for a value that is not a number', () => {
    expect(formatPercent(Number.POSITIVE_INFINITY)).toBe('—');
  });
});

describe('instant formats', () => {
  it('renders a time in UTC with its zone marked', () => {
    // Pinned to UTC on purpose: the same instant has to read the same in the API's
    // logs, in another analyst's browser and in this test.
    expect(formatInstant('2026-03-15T14:02:11Z')).toBe('14:02:11Z');
    expect(formatInstant('2026-03-15T14:02:11+02:00')).toBe('12:02:11Z');
  });

  it('renders a full instant for dates that are not today', () => {
    expect(formatStamp('2026-04-14T10:00:00Z')).toBe('14 Apr 2026, 10:00:00Z');
  });

  it('states an unreadable instant instead of printing an invalid date', () => {
    // 'Invalid Date' on screen is a bug the operator cannot distinguish from data.
    expect(formatInstant('not a date')).toBe('unknown time');
    expect(formatStamp('')).toBe('unknown time');
    expect(formatSince('not a date', Date.now())).toBe('unknown age');
  });

  it("ages an instant against the caller's clock", () => {
    const now = Date.parse('2026-03-15T10:05:00Z');
    expect(formatSince('2026-03-15T10:04:50Z', now)).toBe('10 s ago');
  });
});
