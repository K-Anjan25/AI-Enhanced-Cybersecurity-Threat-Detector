/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';

import { emptyTally } from './aggregate';
import { CHART_REFRESH_MS } from './hooks';
import {
  bucketLabel,
  connectionState,
  kpiTiles,
  panelState,
  STALE_AFTER_MS,
  staleness,
} from './view';

describe('panelState', () => {
  it('is loading until the query resolves', () => {
    expect(panelState('pending', 0)).toBe('loading');
  });

  it('names a failure rather than showing a blank panel', () => {
    expect(panelState('error', 0)).toBe('error');
  });

  it('calls a window with no rows empty, which is an answer', () => {
    expect(panelState('success', 0)).toBe('empty');
    expect(panelState('success', 3)).toBe('ready');
  });
});

describe('staleness', () => {
  it('is not stale before the threshold', () => {
    const age = staleness(1_000, 1_000 + STALE_AFTER_MS - 1);

    expect(age.stale).toBe(false);
    expect(age.label).toBe('last update 29 s ago');
  });

  it('is stale past the threshold, which is two missed chart polls', () => {
    const age = staleness(0, STALE_AFTER_MS + 1);

    expect(age.stale).toBe(true);
    expect(age.ageSeconds).toBeGreaterThan(30);
  });

  it('says there is no data rather than reporting a zero age', () => {
    // "0 s ago" for a screen that has never loaded is the lie §8.1 is about.
    const age = staleness(null, 5_000);

    expect(age.ageSeconds).toBeNull();
    expect(age.label).toBe('no data yet');
    expect(age.stale).toBe(false);
  });

  it('thresholds at two refreshes', () => {
    expect(STALE_AFTER_MS).toBe(2 * CHART_REFRESH_MS);
  });
});

describe('connectionState', () => {
  it('is live when the alerts and metrics both answered recently', () => {
    expect(connectionState({ alertsFailed: false, metricsFailed: false, stale: false })).toBe(
      'live',
    );
  });

  it('is disconnected when a request failed — the console stopped hearing from the server', () => {
    expect(connectionState({ alertsFailed: true, metricsFailed: false, stale: false })).toBe(
      'disconnected',
    );
    expect(connectionState({ alertsFailed: false, metricsFailed: true, stale: false })).toBe(
      'disconnected',
    );
  });

  it('is degraded when the last answer was real but old', () => {
    expect(connectionState({ alertsFailed: false, metricsFailed: false, stale: true })).toBe(
      'degraded',
    );
  });
});

describe('bucketLabel', () => {
  it('stays local and fixed-width within a day', () => {
    expect(bucketLabel(new Date(2026, 9, 6, 9, 5), 86_400_000)).toBe('09:05');
  });

  it('adds the date for a window longer than a day', () => {
    expect(bucketLabel(new Date(2026, 9, 6, 9, 5), 604_800_000)).toBe('Oct 6 09:05');
  });
});

describe('kpiTiles', () => {
  const tiles = kpiTiles(emptyTally(), 0, 'Last 24 h');

  it('is the five tiles §4.1 draws, in reading order', () => {
    expect(tiles.map((tile) => tile.label)).toEqual([
      'Critical',
      'High',
      'Medium',
      'Open alerts',
      'Mean time to verdict',
    ]);
  });

  it('shows no mean when the window has no verdict to measure', () => {
    // §4.1 draws "41 s" here. T-416 gave the tile a source; a window with no
    // recorded verdict still has no mean, and "0 s" would claim instant triage.
    const verdict = tiles.at(-1);

    expect(verdict?.value).toBeNull();
    expect(verdict?.caption).toContain('no verdict recorded in this window');
    expect(verdict?.caption).toContain('≤ 60 s');
  });

  it('shows the mean with the number of verdicts it covers', () => {
    // A mean of one verdict is not a trend, so the count travels with the figure.
    const verdict = kpiTiles(emptyTally(), 0, 'Last 24 h', {
      meanSeconds: 47.42,
      measured: 4,
    }).at(-1);

    expect(verdict?.value).toBe(47);
    expect(verdict?.unit).toBe('s');
    expect(verdict?.caption).toBe('4 verdicts measured · target ≤ 60 s');
  });

  it('says "verdict", singular, when the mean covers exactly one', () => {
    const verdict = kpiTiles(emptyTally(), 0, 'Last 24 h', {
      meanSeconds: 12,
      measured: 1,
    }).at(-1);

    expect(verdict?.caption).toBe('1 verdict measured · target ≤ 60 s');
  });

  it('carries the window as the caption of every counted tile', () => {
    for (const tile of tiles.slice(0, 4)) expect(tile.caption).toBe('Last 24 h');
  });
});
