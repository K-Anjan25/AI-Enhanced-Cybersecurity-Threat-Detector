/**
 * The traffic explorer's wiring, driven through a provider the way the page mounts it
 * (T-418).
 *
 * Four things live here that the page cannot reach: the `enabled` gates (the page passes
 * `true`, so nothing on screen would notice if a hook ignored it), the push subscription
 * (a pushed alert must re-read the *traffic* window, not only the triage queue), the fact
 * that an unbrushed screen makes **one** request rather than two, and the request the
 * hook actually builds — the filters and the bucket width are query parameters, and a
 * hook that dropped one would still render.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { RealtimeProvider } from '../../components/realtime/RealtimeProvider';
import { jsonResponse, stubFetch, testQueryClient } from '../../test/query';
import { fakeClock, fakeSockets, settle } from '../../test/socket';
import { rangeOf, useTrafficBrush, useTrafficWindow } from './hooks';
import type { FlowAggregate } from '../../api/flows';
import { DEFAULT_FILTERS, type TrafficFilters } from './view';

const FLOWS_PATH = '/api/v1/flows';

const READY = {
  type: 'ready',
  epoch: 'e-1',
  latest: 0,
  oldest_available: null,
  resync_required: false,
  after: null,
  heartbeat_seconds: 15,
};

function aggregate(flows: number): FlowAggregate {
  const now = Date.now();
  return {
    window: {
      start: new Date(now - 3_600_000).toISOString(),
      end: new Date(now).toISOString(),
      hours: 1,
    },
    bucket_minutes: 1,
    source: 'rollup',
    filters: { protocol: null, direction: null },
    series: [
      {
        start: new Date(now - 3_600_000).toISOString(),
        flows,
        bytes: flows * 100,
        packets: flows,
        alerts: 0,
        score: null,
      },
    ],
    entities: [],
    edges: [],
    totals: {
      flows,
      bytes: flows * 100,
      packets: flows,
      nodes: 0,
      edges: 0,
      nodes_capped: false,
      edges_capped: false,
      untracked_address_flows: 0,
      untracked_pair_flows: 0,
    },
    caveats: [],
  };
}

/** A probe that mounts both hooks and shows what each one read. */
function Probe({
  enabled,
  brush,
  filters,
}: {
  enabled: boolean;
  brush: { from: number; to: number } | null;
  filters?: TrafficFilters;
}) {
  const range = rangeOf('24h');
  const chosen = filters ?? DEFAULT_FILTERS;
  const window = useTrafficWindow(range, chosen, enabled);
  const brushed = useTrafficBrush(range, chosen, brush, enabled);
  return (
    <p>
      window: {window.data === undefined ? 'loading' : String(window.data.totals.flows)} / brushed:{' '}
      {brushed.data === undefined ? 'loading' : String(brushed.data.totals.flows)}
    </p>
  );
}

function renderProbe(
  options: {
    enabled?: boolean;
    brush?: { from: number; to: number } | null;
    filters?: TrafficFilters;
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
          <Probe
            enabled={options.enabled ?? true}
            brush={options.brush ?? null}
            filters={options.filters ?? DEFAULT_FILTERS}
          />
        </RealtimeProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...utils, sockets, clock };
}

function stubFlows(flows: number) {
  return stubFetch([{ match: FLOWS_PATH, respond: () => jsonResponse(aggregate(flows)) }]);
}

function reads(seen: Request[], path = FLOWS_PATH): Request[] {
  return seen.filter((request) => new URL(request.url).pathname === path);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useTrafficWindow', () => {
  it('reads the window and reports its flow total', async () => {
    stubFlows(12);
    renderProbe();

    expect(await screen.findByText(/window: 12/)).toBeInTheDocument();
  });

  it('asks for the flow endpoint with the window and the bucket width', async () => {
    const seen = stubFlows(1);
    renderProbe({ filters: { ...DEFAULT_FILTERS, protocol: 'udp', direction: 'inbound' } });

    await screen.findByText(/window: 1/);
    const url = new URL((reads(seen)[0] as Request).url);

    expect(url.pathname).toBe(FLOWS_PATH);
    expect(url.searchParams.get('protocol')).toBe('udp');
    expect(url.searchParams.get('direction')).toBe('inbound');
    // 24 h over a 15-minute bucket: the series' resolution is the screen's choice, and
    // a hook that dropped it would silently get the endpoint's default.
    expect(url.searchParams.get('bucket_minutes')).toBe('15');
    expect(url.searchParams.get('start')).not.toBeNull();
    expect(url.searchParams.get('end')).not.toBeNull();
  });

  it('omits a filter set to "all"', async () => {
    const seen = stubFlows(1);
    renderProbe();

    await screen.findByText(/window: 1/);
    const url = new URL((reads(seen)[0] as Request).url);

    expect(url.searchParams.has('protocol')).toBe(false);
    expect(url.searchParams.has('direction')).toBe(false);
  });

  it('does not poll when the screen says polling is off', async () => {
    vi.useFakeTimers();
    try {
      const seen = stubFlows(1);
      renderProbe({ enabled: false });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });
      expect(reads(seen)).toHaveLength(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });

      // `enabled: false` is a screen that has nothing to keep fresh — a hidden tab, or a
      // range picker mid-change. The read already made is the whole workload.
      expect(reads(seen)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('re-reads the window when a pushed alert arrives', async () => {
    // The score overlay and the alert counts come from the alert side, so a frame is a
    // reason to re-read *this* window — including a frame the REST fallback delivered
    // while the socket was down.
    const seen = stubFlows(1);
    const { sockets } = renderProbe();
    await screen.findByText(/window: 1/);
    const before = reads(seen).length;

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

    await waitFor(() => expect(reads(seen).length).toBeGreaterThan(before));
  });

  it('re-reads the window when the connection comes back', async () => {
    const seen = stubFlows(1);
    const { sockets, clock } = renderProbe();
    await screen.findByText(/window: 1/);
    const before = reads(seen).length;

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

    await waitFor(() => expect(reads(seen).length).toBeGreaterThan(before));
  });
});

describe('useTrafficBrush', () => {
  const brush = { from: Date.now() - 600_000, to: Date.now() };

  it('reads nothing while there is no brush', async () => {
    // An unbrushed screen pays one request, not two: the brushed query is disabled, and
    // "disabled" is one word that could be forgotten without anything failing loudly.
    vi.useFakeTimers();
    try {
      const seen = stubFlows(3);
      renderProbe({ brush: null });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });

      expect(reads(seen)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reads the brushed window as its own request', async () => {
    const seen = stubFlows(4);
    renderProbe({ brush });

    await screen.findByText(/brushed: 4/);
    const brushed = reads(seen).find((request) => {
      const url = new URL(request.url);
      return url.searchParams.get('start') === new Date(brush.from).toISOString();
    });

    expect(brushed).toBeDefined();
    expect(new URL((brushed as Request).url).searchParams.get('end')).toBe(
      new Date(brush.to).toISOString(),
    );
  });

  it('asks for the brushed window with the same filters as the series', async () => {
    const seen = stubFlows(2);
    renderProbe({ brush, filters: { ...DEFAULT_FILTERS, protocol: 'icmp' } });

    await screen.findByText(/brushed: 2/);
    for (const request of reads(seen)) {
      expect(new URL(request.url).searchParams.get('protocol')).toBe('icmp');
    }
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
    // `useAlertSync` invalidates `['traffic', 'window']`; a key change here would leave
    // the screen immune to pushed alerts without anything failing loudly.
    const seen = stubFlows(1);
    const client = testQueryClient();
    render(
      <ThemeProvider>
        <QueryClientProvider client={client}>
          <RealtimeProvider socketFactory={fakeSockets().factory} options={{ random: () => 0 }}>
            <Probe enabled brush={null} />
          </RealtimeProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    );
    await screen.findByText(/window: 1/);
    const before = seen.length;

    await client.invalidateQueries({ queryKey: ['traffic', 'window'] });

    await waitFor(() => expect(seen.length).toBeGreaterThan(before));
  });

  it('gives each filter combination its own cache entry', async () => {
    // Two filter states are two windows: a shared key would show the previous filter's
    // numbers under the new filter's label.
    const client = testQueryClient();
    stubFlows(5);
    render(
      <ThemeProvider>
        <QueryClientProvider client={client}>
          <RealtimeProvider socketFactory={fakeSockets().factory} options={{ random: () => 0 }}>
            <Probe enabled brush={null} filters={{ ...DEFAULT_FILTERS, protocol: 'tcp' }} />
          </RealtimeProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    );
    await screen.findByText(/window: 5/);

    const keys = client
      .getQueryCache()
      .getAll()
      .map((query) => JSON.stringify(query.queryKey));

    expect(keys.some((key) => key.includes('tcp'))).toBe(true);
  });
});
