/**
 * The tail's vocabulary, asserted on the values a screen shows.
 *
 * The claims worth pinning are the ones a reader acts on: which levels get the rail,
 * that a level is named by its own word rather than a severity, that ten thousand
 * lines read as `×10,000`, and that a window crossing midnight cannot be mistaken for
 * an inverted one.
 */
import { describe, expect, it } from 'vitest';

import {
  LOG_LEVELS,
  countLabel,
  isLogLevel,
  isNotable,
  levelRank,
  levelTone,
  levelsLabel,
  spanOf,
  tailWindow,
  templateLabel,
  windowLabel,
  worstLevel,
  TAIL_SPANS,
} from './cluster';
import type { LogCluster } from './api';

function cluster(overrides: Partial<LogCluster> = {}): LogCluster {
  return {
    key: 't-1',
    template_id: 't-1',
    count: 1,
    first_seen: '2026-10-06T10:00:00Z',
    last_seen: '2026-10-06T10:00:00Z',
    worst_level: 'info',
    levels: { info: 1 },
    hosts: ['web-1'],
    services: ['api'],
    sample_message: 'connection refused',
    parameters: {},
    ...overrides,
  };
}

describe('levels', () => {
  it('walks the wire vocabulary in severity order', () => {
    expect(LOG_LEVELS).toEqual(['debug', 'info', 'warning', 'error', 'critical']);
    expect(levelRank('debug')).toBeLessThan(levelRank('critical'));
  });

  it('puts the rail on error and critical only', () => {
    // Warning is a level a reader may want to see; error is a level a reader should
    // not miss. Marking everything notable marks nothing.
    expect(isNotable('critical')).toBe(true);
    expect(isNotable('error')).toBe(true);
    expect(isNotable('warning')).toBe(false);
    expect(isNotable('info')).toBe(false);
    expect(isNotable('debug')).toBe(false);
  });

  it('colours a level with the severity palette without renaming it', () => {
    expect(levelTone('critical')).toBe('critical');
    expect(levelTone('error')).toBe('high');
    expect(levelTone('warning')).toBe('medium');
    expect(levelTone('info')).toBe('info');
    // Debug is off the severity scale: neutral, because it is not a severity.
    expect(levelTone('debug')).toBe('neutral');
  });

  it('narrows an arbitrary string, so an unknown level cannot reach a chip', () => {
    expect(isLogLevel('error')).toBe(true);
    expect(isLogLevel('catastrophic')).toBe(false);
  });

  it('falls back to info when the API sends a level it does not know', () => {
    expect(worstLevel(cluster({ worst_level: 'critical' }))).toBe('critical');
    expect(worstLevel(cluster({ worst_level: 'nonsense' as never }))).toBe('info');
  });
});

describe('counts', () => {
  it('writes the collapse the way design.md §4.5 writes it', () => {
    expect(countLabel(10_000)).toBe('×10,000');
    expect(countLabel(1)).toBe('×1');
  });

  it('lists the levels most severe first, skipping the ones with no lines', () => {
    expect(levelsLabel(cluster({ levels: { info: 3, critical: 2, debug: 1 } }))).toBe(
      '2 critical, 3 info, 1 debug',
    );
    expect(levelsLabel(cluster({ levels: {} }))).toBe('');
  });
});

describe('templateLabel', () => {
  it('names a templated cluster by its template id', () => {
    expect(templateLabel(cluster({ template_id: 'drain-42' }))).toBe('drain-42');
  });

  it('shortens a digest, so an untemplated row is addressable and readable', () => {
    const digest = cluster({ template_id: null, key: 'message:9f2c1ab34def' });

    expect(templateLabel(digest)).toBe('message:9f2c1ab3…');
  });

  it('treats an empty template id as absent rather than as a name', () => {
    expect(templateLabel(cluster({ template_id: '  ', key: 'message:aaaa' }))).toBe(
      'message:aaaa…',
    );
  });
});

describe('tailWindow', () => {
  it('is half-open and ends at the clock', () => {
    const window = tailWindow(Date.parse('2026-10-06T10:05:00Z'), 300_000);

    expect(window.end.toISOString()).toBe('2026-10-06T10:05:00.000Z');
    expect(window.start.toISOString()).toBe('2026-10-06T10:00:00.000Z');
    expect(window.end.getTime() - window.start.getTime()).toBe(300_000);
  });

  it('offers only spans the tail retains', () => {
    expect(TAIL_SPANS.map((span) => span.spanMs)).toEqual([60_000, 300_000, 900_000]);
    expect(spanOf('15m').spanMs).toBe(900_000);
    expect(spanOf('nonsense' as never).key).toBe('5m');
  });
});

describe('windowLabel', () => {
  it('shows a time of day when both ends are the same day', () => {
    const label = windowLabel(new Date('2026-10-06T10:00:00Z'), new Date('2026-10-06T10:05:00Z'));

    expect(label).toBe('10:00:00–10:05:00 UTC');
  });

  it('shows the date when the span crosses midnight', () => {
    // "23:59–00:01" on its own reads as an inverted window, which is exactly the
    // misreading a tail running overnight would invite.
    const label = windowLabel(new Date('2026-10-06T23:59:00Z'), new Date('2026-10-07T00:01:00Z'));

    expect(label).toBe('06 Oct 23:59:00 → 07 Oct 00:01:00 UTC');
  });
});
