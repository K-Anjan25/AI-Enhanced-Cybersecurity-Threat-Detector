import { describe, expect, it } from 'vitest';

import { alertHref, alertHrefFor, nextHref, stepHref } from './links';
import { alertRow } from './fixtures';

const AT = '2026-03-15T10:00:00.000Z';

function rows(ids: number[]) {
  return ids.map((id) => alertRow({ id, created_at: AT }));
}

describe('alert links', () => {
  it('carries the partition key, because an id alone addresses every month', () => {
    expect(alertHref(alertRow())).toBe('/alerts/42?created_at=2026-03-15T10%3A00%3A00Z');
  });

  it('escapes an offset so the key survives the query string', () => {
    expect(alertHrefFor(42, '2026-03-15T10:00:00+00:00')).toBe(
      '/alerts/42?created_at=2026-03-15T10%3A00%3A00%2B00%3A00',
    );
  });

  it('points at the next row in queue order', () => {
    const rows = [alertRow({ id: 1 }), alertRow({ id: 2 }), alertRow({ id: 3 })];

    expect(nextHref(rows, 1)).toBe(alertHref(rows[1]!));
    expect(nextHref(rows, 2)).toBe(alertHref(rows[2]!));
  });

  it('has no next on the last row, and says so by returning null', () => {
    const rows = [alertRow({ id: 1 }), alertRow({ id: 2 })];

    expect(nextHref(rows, 2)).toBeNull();
  });

  it('offers the first row when nothing is open yet', () => {
    const rows = [alertRow({ id: 1 }), alertRow({ id: 2 })];

    expect(nextHref(rows, null)).toBe(alertHref(rows[0]!));
    expect(nextHref([], null)).toBeNull();
  });

  it('falls back to the first row when the open alert is no longer in the queue', () => {
    // The queue is a 24 h window: an alert opened from a ticket this morning can
    // still be on screen long after it has fallen out of the list.
    const rows = [alertRow({ id: 1 }), alertRow({ id: 2 })];

    expect(nextHref(rows, 999)).toBe(alertHref(rows[0]!));
  });
});

/**
 * The step rule behind `j`/`k` (T-411).
 *
 * `nextHref` above is the same function one forward, so the forward cases are
 * pinned there; what is left is the half the keys added — walking *back* — and the
 * ends, which have to be ends rather than a carousel.
 */
describe('stepHref', () => {
  it('steps forward and backward between neighbouring rows', () => {
    expect(stepHref(rows([42, 41, 40]), 41, 1)).toBe(
      alertHref(alertRow({ id: 40, created_at: AT })),
    );
    expect(stepHref(rows([42, 41, 40]), 41, -1)).toBe(
      alertHref(alertRow({ id: 42, created_at: AT })),
    );
  });

  it('does nothing on a backward step with nothing selected', () => {
    // `k` on the bare queue has nowhere to go; opening the *last* row would start
    // the analyst at the bottom of a queue they have not looked at yet.
    expect(stepHref(rows([42, 41, 40]), null, -1)).toBeNull();
  });

  it('stops at the start of the queue instead of wrapping', () => {
    expect(stepHref(rows([42, 41, 40]), 42, -1)).toBeNull();
  });

  it('does not walk backward off an alert that is not in the visible queue', () => {
    // A deep link can open an alert outside the current window; forward has a real
    // destination (the top of the queue), backward does not.
    expect(stepHref(rows([42, 41]), 99, -1)).toBeNull();
  });

  it('has nowhere to step in an empty queue', () => {
    expect(stepHref([], null, 1)).toBeNull();
    expect(stepHref([], 42, -1)).toBeNull();
  });

  it('is what nextHref calls, so the link and the key cannot disagree', () => {
    const queue = rows([42, 41, 40]);

    expect(nextHref(queue, 42)).toBe(stepHref(queue, 42, 1));
    expect(nextHref(queue, 40)).toBe(stepHref(queue, 40, 1));
  });
});
