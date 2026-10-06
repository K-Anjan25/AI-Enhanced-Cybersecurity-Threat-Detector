import { describe, expect, it } from 'vitest';

import {
  ALERTS_EXPORT_PATH,
  alertDetailPath,
  alertExportBody,
  alertListPath,
  alertVerdictPath,
} from './alerts';

describe('alert paths', () => {
  it('carries a bounded window on the list, because R-34 requires one', () => {
    const path = alertListPath({
      start: new Date('2026-03-15T09:00:00Z'),
      end: new Date('2026-03-15T10:00:00Z'),
    });
    const params = new URLSearchParams(path.split('?')[1]);

    expect(path.startsWith('/api/v1/alerts?')).toBe(true);
    expect(params.get('start')).toBe('2026-03-15T09:00:00.000Z');
    expect(params.get('end')).toBe('2026-03-15T10:00:00.000Z');
  });

  it('drops filters that were not asked for rather than sending them empty', () => {
    const path = alertListPath({ start: 'a', end: 'b', limit: 100 });

    expect(path).toBe('/api/v1/alerts?start=a&end=b&limit=100');
  });

  it('percent-encodes the partition key, so an offset survives the query string', () => {
    // The bug this pins down: in a raw query string `+00:00` decodes as a space,
    // and the API then refuses a timestamp that looked perfectly valid here.
    const path = alertDetailPath(42, '2026-03-15T10:00:00+00:00');

    expect(path.startsWith('/api/v1/alerts/42?')).toBe(true);
    expect(path).toContain('%2B00%3A00');
    expect(
      decodeURIComponent(new URLSearchParams(path.split('?')[1]).get('created_at') ?? ''),
    ).toBe('2026-03-15T10:00:00+00:00');
  });

  it('addresses the verdict write without the key, which the body carries', () => {
    expect(alertVerdictPath(7)).toBe('/api/v1/alerts/7/verdict');
  });
});

describe('the alert batch export', () => {
  it('sends the queue\u2019s filter as wire names, and the format it was asked for', () => {
    const body = alertExportBody(
      {
        start: new Date('2026-10-05T10:00:00Z'),
        end: new Date('2026-10-06T10:00:00Z'),
        severity: 'high,critical',
        status: 'open',
        family: 'exfiltration',
        entityId: 7,
        minScore: 0.5,
        order: 'desc',
        limit: 100,
      },
      'pdf',
    );

    expect(body).toEqual({
      start: '2026-10-05T10:00:00.000Z',
      end: '2026-10-06T10:00:00.000Z',
      severity: 'high,critical',
      status: 'open',
      family: 'exfiltration',
      entity_id: 7,
      min_score: 0.5,
      order: 'desc',
      limit: 100,
      format: 'pdf',
    });
  });

  it('omits the filters the caller did not set rather than sending them empty', () => {
    const body = alertExportBody({ start: 'a', end: 'b' }, 'csv');

    expect(body).toEqual({ start: 'a', end: 'b', format: 'csv' });
  });

  it('cannot express a cursor, because the API refuses one', () => {
    // A cursor would let a caller export a page nobody saw, and the audit row would
    // then describe a read that never happened (T-415's schema types it `None`).
    const body = alertExportBody({ start: 'a', end: 'b', cursor: 'next' }, 'csv');

    expect('cursor' in body).toBe(false);
  });

  it('names the export route the same way both halves of the API do', () => {
    expect(ALERTS_EXPORT_PATH).toBe('/api/v1/alerts/export');
  });
});
