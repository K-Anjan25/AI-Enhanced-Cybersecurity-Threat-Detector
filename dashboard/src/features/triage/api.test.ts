/**
 * The triage screen's three calls, asserted on the requests they make.
 *
 * `fetch` is the boundary stubbed here, as in the overview's data tests: the real
 * client, the real path builders and the real serialisation all run, so what these
 * tests read is the request a browser would send.
 */
import { describe, expect, it } from 'vitest';

import { jsonResponse, stubFetch } from '../../test/query';
import { fetchAlertDetail, fetchQueue, recordVerdict, QUEUE_LIMIT } from './api';
import { alertDetail } from './fixtures';

describe('the queue read', () => {
  it('asks for a bounded window, newest first, with the page size it documents', async () => {
    const requests = stubFetch([
      { match: '/api/v1/alerts', respond: () => jsonResponse({ items: [], next_cursor: null }) },
    ]);

    await fetchQueue({
      start: new Date('2026-03-15T09:00:00Z'),
      end: new Date('2026-03-15T10:00:00Z'),
    });

    const url = new URL(requests[0]?.url ?? '');
    expect(url.pathname).toBe('/api/v1/alerts');
    expect(url.searchParams.get('start')).toBe('2026-03-15T09:00:00.000Z');
    expect(url.searchParams.get('end')).toBe('2026-03-15T10:00:00.000Z');
    expect(url.searchParams.get('order')).toBe('desc');
    expect(url.searchParams.get('limit')).toBe(String(QUEUE_LIMIT));
  });
});

describe('the detail read', () => {
  it('addresses the alert by both halves of its key', async () => {
    const detail = alertDetail();
    const requests = stubFetch([{ match: '/api/v1/alerts/', respond: () => jsonResponse(detail) }]);

    const answer = await fetchAlertDetail({ alertId: 42, createdAt: '2026-03-15T10:00:00+00:00' });

    const url = new URL(requests[0]?.url ?? '');
    expect(url.pathname).toBe('/api/v1/alerts/42');
    expect(url.searchParams.get('created_at')).toBe('2026-03-15T10:00:00+00:00');
    expect(answer.alert.id).toBe(42);
  });
});

describe('the verdict write', () => {
  it('posts the verdict with the partition key the API needs to find the row', async () => {
    const requests = stubFetch([
      {
        match: '/api/v1/alerts/',
        respond: () => jsonResponse({ action: 'recorded', record: {}, superseded: null }),
      },
    ]);

    await recordVerdict({
      alertId: 42,
      createdAt: '2026-03-15T10:00:00Z',
      verdict: 'false_positive',
    });

    const request = requests[0];
    expect(new URL(request?.url ?? '').pathname).toBe('/api/v1/alerts/42/verdict');
    expect(request?.method).toBe('POST');
    await expect(request?.json()).resolves.toEqual({
      created_at: '2026-03-15T10:00:00Z',
      verdict: 'false_positive',
    });
  });
});
