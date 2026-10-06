/**
 * The hunt's derived model, in the states the screen can be in.
 *
 * The state that matters most is `empty`: §4.6's acceptance criterion is that an
 * empty result renders the executed query and the time range, and the assertion here
 * is on the sentence that reaches the analyst — a description that named neither
 * would be the "quiet network" conclusion this screen exists to prevent. `idle` is
 * asserted too, because "nothing searched yet" and "nothing matched" must never be
 * the same screen.
 */
import { describe, expect, it } from 'vitest';

import type { AlertPage, AlertRow } from '../../api/alerts';
import { parseHuntQuery } from './query';
import { buildHuntView, huntSpanLabel, huntWindowLabel } from './view';

const START = Date.parse('2026-10-06T09:00:00Z');
const WINDOW = { start: new Date(START), end: new Date(START + 3_600_000) };

function row(overrides: Partial<AlertRow> & { id: number }): AlertRow {
  return {
    created_at: new Date(START + 60_000).toISOString(),
    entity_id: 7,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8123,
    status: 'open',
    first_seen: new Date(START).toISOString(),
    last_seen: new Date(START + 3_000_000).toISOString(),
    occurrence_count: 1_234,
    trace_id: 'trace-abc',
    ...overrides,
  };
}

function page(items: AlertRow[], next: string | null = null): AlertPage {
  return { items, next_cursor: next, limit: 100, order: 'desc' };
}

const PARSE = parseHuntQuery('severity:high family:exfiltration');

describe('buildHuntView', () => {
  it('is idle before anything has been run — not empty, which is a different answer', () => {
    const view = buildHuntView({ page: undefined, parse: null, window: null, failed: false });

    expect(view.state).toBe('idle');
    expect(view.rows).toEqual([]);
    expect(view.executed).toBeNull();
    expect(view.windowLabel).toBeNull();
    expect(view.emptyReason).toBeNull();
  });

  it('is loading once a run is in flight, with the window it is reading already known', () => {
    const view = buildHuntView({ page: undefined, parse: PARSE, window: WINDOW, failed: false });

    expect(view.state).toBe('loading');
    expect(view.executed).toBe('severity:high family:exfiltration order:desc limit:100');
    expect(view.windowLabel).toContain('06 Oct 2026, 09:00:00Z');
  });

  it('shows the rows it read, and reports the window it read them from', () => {
    const view = buildHuntView({
      page: page([row({ id: 1 }), row({ id: 2, severity: 'low' })]),
      parse: PARSE,
      window: WINDOW,
      failed: false,
    });

    expect(view.state).toBe('rows');
    expect(view.rows.map((entry) => entry.id)).toEqual(['1', '2']);
    expect(view.rowCount).toBe(2);
    expect(view.truncated).toBe(false);
    expect(view.emptyReason).toBeNull();
    expect(view.rows[0]?.score).toBe('0.8123');
    expect(view.rows[0]?.occurrences).toBe('1,234');
  });

  it('renders the executed query and the time range when nothing matched (§4.6)', () => {
    const view = buildHuntView({ page: page([]), parse: PARSE, window: WINDOW, failed: false });

    expect(view.state).toBe('empty');
    expect(view.emptyReason).toContain('severity:high family:exfiltration order:desc limit:100');
    expect(view.emptyReason).toContain('06 Oct 2026, 09:00:00Z');
    expect(view.emptyReason).toContain('06 Oct 2026, 10:00:00Z');
    // And it says what the emptiness is *not* a statement about.
    expect(view.emptyReason).toContain('not a statement about the network');
  });

  it('says when the read stopped at the cap rather than presenting a page as a window', () => {
    const view = buildHuntView({
      page: page([row({ id: 1 })], 'cursor-2'),
      parse: PARSE,
      window: WINDOW,
      failed: false,
    });

    expect(view.truncated).toBe(true);
  });

  it('shows nothing rather than a stale page when the read failed', () => {
    const view = buildHuntView({
      page: page([row({ id: 1 })]),
      parse: PARSE,
      window: WINDOW,
      failed: true,
    });

    expect(view.state).toBe('error');
    expect(view.rows).toEqual([]);
    expect(view.emptyReason).toBe('The read failed, so nothing is shown rather than a stale page.');
    // The echo survives the failure: what was searched is still what was searched.
    expect(view.executed).not.toBeNull();
  });

  it('prints an unrecognised severity as it arrived instead of colouring it', () => {
    const view = buildHuntView({
      page: page([row({ id: 1, severity: 'urgent' })]),
      parse: PARSE,
      window: WINDOW,
      failed: false,
    });

    expect(view.rows[0]?.severity).toBe('unrecognised');
    expect(view.rows[0]?.severityLabel).toBe('urgent');
  });

  it('shows an absent trace as a dash rather than a blank cell', () => {
    const view = buildHuntView({
      page: page([row({ id: 1, trace_id: null })]),
      parse: PARSE,
      window: WINDOW,
      failed: false,
    });

    expect(view.rows[0]?.trace).toBe('—');
  });
});

describe('the window in words', () => {
  it('names both ends and the span, so a screenshot is self-describing', () => {
    expect(huntWindowLabel(WINDOW)).toBe(
      '06 Oct 2026, 09:00:00Z–06 Oct 2026, 10:00:00Z · last 1 h',
    );
  });

  it('counts a day in days, not in twenty-four hours', () => {
    expect(huntSpanLabel(24 * 3_600_000)).toBe('last 24 h');
    expect(huntSpanLabel(48 * 3_600_000)).toBe('last 2 days');
    expect(huntSpanLabel(7 * 24 * 3_600_000)).toBe('last 7 days');
  });
});
