/**
 * The traffic window's wiring, driven through a provider the way the page mounts it.
 *
 * Two things live here that the page cannot reach: the `enabled` gate (the page always
 * passes `true`, so nothing on screen would notice if the hook ignored it) and the
 * push subscription (a pushed alert must re-read the *traffic* window, not only the
 * triage queue). Both are asserted on what the hook caused — a request that was or was
 * not made — rather than on a mock being called.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { RealtimeProvider } from '../../components/realtime/RealtimeProvider';
import { jsonResponse, stubFetch, testQueryClient } from '../../test/query';
import { fakeClock, fakeSockets, settle } from '../../test/socket';
import { rangeOf, useTrafficWindow } from './hooks';

const QUEUE_PATH = '/api/v1/alerts';

const READY = {
  type: 'ready',
  epoch: 'e-1',
  latest: 0,
  oldest_available: null,
  resync_required: false,
  after: null,
  heartbeat_seconds: 15,
};

/** A probe that mounts the hook and shows how many rows it read. */
function Probe({ enabled }: { enabled: boolean }) {
  const query = useTrafficWindow(rangeOf('24h'), 'all', enabled);
  return <p>rows: {query.data === undefined ? 'loading' : String(query.data.rows.length)}</p>;
}

function renderProbe(
  options: {
    enabled?: boolean;
    sockets?: ReturnType<typeof fakeSockets>;
    clock?: ReturnType<typeof fakeClock>;
  } = {},
) {
  const sockets = options.sockets ?? fakeSockets();
  const clock = options.clock ?? fakeClock();
  const utils = render(
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>
        <RealtimeProvider socketFactory={sockets.factory} options={{ clock, random: () => 0 }}>
          <Probe enabled={options.enabled ?? true} />
        </RealtimeProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...utils, sockets, clock };
}

function stubWindow(rows: number) {
  return stubFetch([
    {
      match: QUEUE_PATH,
      respond: () =>
        jsonResponse({
          items: Array.from({ length: rows }, (_unused, index) => ({
            id: index + 1,
            created_at: new Date(Date.now() - 60_000).toISOString(),
            entity_id: index + 1,
            family: 'exfiltration',
            severity: 'high',
            score: 0.8,
            status: 'open',
            first_seen: new Date(Date.now() - 120_000).toISOString(),
            last_seen: new Date(Date.now() - 60_000).toISOString(),
            occurrence_count: 3,
            trace_id: null,
          })),
          next_cursor: null,
          limit: 1_000,
          order: 'desc',
        }),
    },
  ]);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useTrafficWindow', () => {
  it('reads the window and reports its rows', async () => {
    stubWindow(2);
    renderProbe();

    expect(await screen.findByText('rows: 2')).toBeInTheDocument();
  });

  it('does not poll when the screen says polling is off', async () => {
    vi.useFakeTimers();
    try {
      const seen = stubWindow(1);
      renderProbe({ enabled: false });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });
      const reads = () =>
        seen.filter((request) => new URL(request.url).pathname === QUEUE_PATH).length;
      expect(reads()).toBe(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });

      // `enabled: false` is a screen that has nothing to keep fresh — a hidden tab,
      // or a range picker mid-change. The read already made is the whole workload.
      expect(reads()).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('re-reads the window when a pushed alert arrives', async () => {
    // The traffic view is derived from the alert stream's own data, so a frame is a
    // reason to re-read *this* window — including a frame the REST fallback delivered
    // while the socket was down.
    const seen = stubWindow(1);
    const { sockets } = renderProbe();
    await screen.findByText('rows: 1');
    const before = seen.filter((request) => new URL(request.url).pathname === QUEUE_PATH).length;

    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
      sockets.last().emit({
        type: 'alert',
        sequence: 1,
        alert: {
          id: 9,
          created_at: new Date(Date.now() - 30_000).toISOString(),
          entity_id: 9,
          family: 'scan',
          severity: 'critical',
          score: 0.95,
          status: 'open',
          first_seen: new Date(Date.now() - 60_000).toISOString(),
          last_seen: new Date(Date.now() - 30_000).toISOString(),
          occurrence_count: 1,
          trace_id: null,
        },
      });
    });
    await settle();

    // The invalidation is coalesced, so give the microtask queue a turn before the
    // refetch is asserted.
    await waitFor(() => {
      const after = seen.filter((request) => new URL(request.url).pathname === QUEUE_PATH).length;
      expect(after).toBeGreaterThan(before);
    });
  });

  it('re-reads the window when the connection comes back', async () => {
    const seen = stubWindow(1);
    const { sockets, clock } = renderProbe();
    await screen.findByText('rows: 1');
    const reads = () =>
      seen.filter((request) => new URL(request.url).pathname === QUEUE_PATH).length;
    const before = reads();

    act(() => {
      sockets.last().open();
      sockets.last().serverClose(1006);
    });
    await settle();
    await act(async () => {
      clock.advance(1_000);
      await settle();
    });
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });

    await waitFor(() => expect(reads()).toBeGreaterThan(before));
  });
});

describe('rangeOf', () => {
  it('maps every key to its own span', () => {
    expect(rangeOf('1h').spanMs).toBe(3_600_000);
    expect(rangeOf('24h').spanMs).toBe(86_400_000);
    expect(rangeOf('7d').spanMs).toBe(604_800_000);
  });
});

describe('the traffic query keys', () => {
  it('is addressable by the stream invalidation root', async () => {
    // `useAlertSync` invalidates `['traffic', 'window']`; a key change here would
    // leave the screen immune to pushed alerts without anything failing loudly.
    const seen = stubWindow(1);
    const client = testQueryClient();
    render(
      <ThemeProvider>
        <QueryClientProvider client={client}>
          <RealtimeProvider socketFactory={fakeSockets().factory} options={{ random: () => 0 }}>
            <Probe enabled />
          </RealtimeProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    );
    await screen.findByText('rows: 1');
    const before = seen.length;

    await client.invalidateQueries({ queryKey: ['traffic', 'window'] });

    await waitFor(() => expect(seen.length).toBeGreaterThan(before));
  });
});
