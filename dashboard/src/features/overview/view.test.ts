/**
 * @vitest-environment node
 */
import { describe, expect, it } from 'vitest';

import { emptyTally } from './aggregate';
import { bucketLabel, kpiTiles, panelState } from './view';

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
