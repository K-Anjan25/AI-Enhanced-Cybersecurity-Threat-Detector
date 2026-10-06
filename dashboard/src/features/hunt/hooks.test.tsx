/**
 * The hunt's data wiring, driven through a provider the way the page mounts it.
 *
 * Three properties are asserted here that a page test would blur: that a hunt is read
 * exactly once and *not* polled (a console that re-ran on its own would move under an
 * analyst comparing rows), that the export posts the query as a document rather than
 * as query parameters, and that a refusal is turned into a sentence about the role
 * rather than a status code.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import {
  Providers,
  jsonResponse,
  stubFetch,
  testQueryClient,
  textResponse,
} from '../../test/query';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { csvRowCount, exportRefusalMessage, useHuntExport, useHuntSearch } from './hooks';
import type { AlertListParams } from '../../api/alerts';

const PARAMS: AlertListParams = {
  start: new Date('2026-10-05T10:00:00Z'),
  end: new Date('2026-10-06T10:00:00Z'),
  severity: 'high',
  limit: 100,
};

const EMPTY_PAGE = { items: [], next_cursor: null, limit: 100, order: 'desc' };

function SearchProbe({ params, enabled }: { params: AlertListParams | null; enabled: boolean }) {
  const query = useHuntSearch(params, enabled);
  return (
    <p>
      rows: {query.data === undefined ? 'loading' : String(query.data.items.length)} · fetches:{' '}
      {String(query.dataUpdatedAt === 0 ? 0 : 1)}
    </p>
  );
}

function ExportProbe({ params }: { params: AlertListParams }) {
  const mutation = useHuntExport();
  return (
    <div>
      <button
        type="button"
        onClick={() => {
          mutation.mutate(params);
        }}
      >
        Export
      </button>
      <p>rows: {mutation.data === undefined ? 'none' : String(mutation.data.rows)}</p>
      <p>error: {mutation.error === null ? 'none' : exportRefusalMessage(mutation.error)}</p>
    </div>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useHuntSearch', () => {
  it('reads the page the parameters describe, once, with the filters on the wire', async () => {
    const seen = stubFetch([
      {
        match: '/api/v1/alerts',
        respond: () => jsonResponse(EMPTY_PAGE),
      },
    ]);

    render(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <SearchProbe params={PARAMS} enabled />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/rows: 0/)).toBeInTheDocument();
    });

    const url = new URL(seen[0]?.url ?? '');
    expect(url.pathname).toBe('/api/v1/alerts');
    expect(url.searchParams.get('start')).toBe('2026-10-05T10:00:00.000Z');
    expect(url.searchParams.get('severity')).toBe('high');
    expect(url.searchParams.get('limit')).toBe('100');
    // The console does not walk pages: a hunt is one bounded read (§4.6).
    expect(url.searchParams.get('cursor')).toBeNull();
  });

  it('reads nothing while the hunt is switched off', async () => {
    const seen = stubFetch([{ match: '/api/v1/alerts', respond: () => jsonResponse(EMPTY_PAGE) }]);

    render(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <SearchProbe params={null} enabled={false} />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/rows: loading/)).toBeInTheDocument();
    });
    expect(seen).toEqual([]);
  });

  it('does not re-read on an interval — a hunt is a question, not a stream', async () => {
    vi.useFakeTimers();
    const seen = stubFetch([{ match: '/api/v1/alerts', respond: () => jsonResponse(EMPTY_PAGE) }]);

    render(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <SearchProbe params={PARAMS} enabled />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    await vi.advanceTimersByTimeAsync(60_000);
    expect(seen.length).toBeLessThanOrEqual(1);
    vi.useRealTimers();
  });
});

describe('useHuntExport', () => {
  it('posts the query as a document and counts the rows of the answer', async () => {
    const seen = stubFetch([
      {
        match: '/api/v1/hunt/export',
        respond: () =>
          textResponse(
            'id,created_at,entity_id\r\n1,2026-10-06T09:00:00Z,7\r\n2,2026-10-06T09:00:01Z,8\r\n',
          ),
      },
    ]);

    render(
      <Providers>
        <ExportProbe params={PARAMS} />
      </Providers>,
    );

    await screen.findByRole('button', { name: 'Export' }).then((button) => button.click());

    await waitFor(() => {
      expect(screen.getByText('rows: 2')).toBeInTheDocument();
    });

    const request = seen[0];
    expect(request?.method).toBe('POST');
    const body = (await request?.clone().json()) as Record<string, unknown>;
    expect(body).toEqual({
      start: '2026-10-05T10:00:00.000Z',
      end: '2026-10-06T10:00:00.000Z',
      severity: 'high',
      limit: 100,
    });
    // The API refuses a cursor in an export, so the body cannot carry one.
    expect(body).not.toHaveProperty('cursor');
  });

  it('turns a refusal into a sentence about the role, not a status code', async () => {
    stubFetch([
      {
        match: '/api/v1/hunt/export',
        respond: () => jsonResponse({ detail: 'role is not permitted' }, 403),
      },
    ]);

    render(
      <Providers>
        <ExportProbe params={PARAMS} />
      </Providers>,
    );

    await screen.findByRole('button', { name: 'Export' }).then((button) => button.click());

    await waitFor(() => {
      expect(screen.getByText(/needs the responder role/)).toBeInTheDocument();
    });
  });
});

describe('csvRowCount', () => {
  it('counts data rows, not the header or a trailing blank line', () => {
    expect(csvRowCount('a,b\r\n')).toBe(0);
    expect(csvRowCount('a,b\r\n1,2\r\n3,4\r\n')).toBe(2);
    expect(csvRowCount('a,b\n1,2')).toBe(1);
  });
});

describe('exportRefusalMessage', () => {
  it('is nothing at all when nothing failed', () => {
    expect(exportRefusalMessage(null)).toBeNull();
  });

  it('distinguishes an unauthenticated session from a refusal by role', () => {
    expect(exportRefusalMessage(new ApiError('status', 401, 'nope'))).toContain(
      'not authenticated',
    );
    expect(exportRefusalMessage(new ApiError('status', 403, 'nope'))).toContain('responder');
  });

  it('says nothing was written to the audit trail when the server refused', () => {
    // The audit entry is written after the document renders, so a refused export
    // leaves no row — and the analyst is told that rather than left to wonder.
    expect(exportRefusalMessage(new ApiError('status', 403, 'nope'))).toContain(
      'nothing was written',
    );
  });

  it('falls back to a plain sentence for anything else', () => {
    expect(exportRefusalMessage(new Error('boom'))).toBe(
      'The export could not be read. Nothing was downloaded.',
    );
  });
});
