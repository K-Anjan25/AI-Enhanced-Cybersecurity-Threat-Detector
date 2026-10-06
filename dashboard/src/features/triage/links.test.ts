import { describe, expect, it } from 'vitest';

import { alertHref, alertHrefFor, nextHref } from './links';
import { alertRow } from './fixtures';

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
