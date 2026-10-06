/**
 * The log tail's data wiring, driven through a provider the way the page mounts it.
 *
 * Three things live here that a page test cannot see sharply: that a live tail is
 * re-read on its own 2 s cadence, that the previous window stays on screen while the
 * next one is in flight (a tail that blanked twice a second would read as a broken
 * feed), and that opening nothing reads no raw lines — the expansion is a *look*, and
 * its absence is asserted as a request that was never made.
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { jsonResponse, stubFetch, testQueryClient } from '../../test/query';
import { LOG_TAIL_REFRESH_MS, useLogLines, useLogTail } from './hooks';
import { tailWindow, type LogWindow } from './cluster';
import type { LogTail } from './api';

const NOW = Date.parse('2026-10-06T10:05:00Z');

function tail(count: number): LogTail {
  return {
    start: '2026-10-06T10:00:00Z',
    end: '2026-10-06T10:05:00Z',
    clusters: [
      {
        key: 't-1',
        template_id: 't-1',
        count,
        first_seen: '2026-10-06T10:00:00Z',
        last_seen: '2026-10-06T10:04:59Z',
        worst_level: 'error',
        levels: { error: count },
        hosts: ['web-1'],
        services: ['api'],
        sample_message: 'connection refused',
        parameters: {},
      },
    ],
    lines_seen: count,
    clusters_seen: 1,
    clusters_truncated: false,
    retained_from: '2026-10-06T10:00:00Z',
    retained_to: '2026-10-06T10:04:59Z',
    retained_lines: count,
    dropped_lines: 0,
    caveats: ['not a store', 'Nothing matched these filters'],
  };
}

const WINDOW: LogWindow = tailWindow(NOW, 300_000);

/** A probe that mounts the hook and prints what it currently holds. */
function TailProbe({ enabled, window = WINDOW }: { enabled: boolean; window?: LogWindow }) {
  const query = useLogTail(window, { level: 'all' }, enabled);
  const count = query.data?.clusters[0]?.count;
  return <p>count: {count === undefined ? 'loading' : String(count)}</p>;
}

function LinesProbe({ clusterKey }: { clusterKey: string | null }) {
  const query = useLogLines(WINDOW, clusterKey, true);
  return <p>lines: {query.data === undefined ? 'none' : String(query.data.lines.length)}</p>;
}

function renderProbe(ui: React.ReactElement) {
  return render(
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>{ui}</QueryClientProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('useLogTail', () => {
  it('re-reads a live tail on its own cadence rather than a chart’s', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    let reads = 0;
    const requests = stubFetch([
      {
        match: '/api/v1/logs',
        respond: () => {
          reads += 1;
          return jsonResponse(tail(reads));
        },
      },
    ]);
    renderProbe(<TailProbe enabled />);
    await screen.findByText('count: 1');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(LOG_TAIL_REFRESH_MS + 500);
    });

    // A tail's subject is the last few seconds; 15 s would show it from the wrong end.
    expect(reads).toBeGreaterThanOrEqual(2);
    expect(requests.length).toBeGreaterThanOrEqual(2);
  });

  it('reads nothing at all while it is disabled, and picks up when it is enabled', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    const requests = stubFetch([{ match: '/api/v1/logs', respond: () => jsonResponse(tail(7)) }]);
    const view = renderProbe(<TailProbe enabled={false} />);
    await screen.findByText('count: loading');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(LOG_TAIL_REFRESH_MS * 3);
    });

    // Paused is not "read and hidden": a frozen view that is still fetching is a view
    // that jumps the moment it resumes.
    expect(requests).toHaveLength(0);

    view.rerender(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <TailProbe enabled />
        </QueryClientProvider>
      </ThemeProvider>,
    );
    await waitFor(() => expect(requests.length).toBeGreaterThan(0));
  });

  it('keeps the previous window on screen while the next one is being read', async () => {
    // The subject is a *new window*: a same-key refetch keeps its data by default, so
    // only a moved window shows what `keepPreviousData` is for.
    let answered = 0;
    stubFetch([
      {
        match: '/api/v1/logs',
        respond: () => {
          answered += 1;
          return answered === 1
            ? jsonResponse(tail(11))
            : new Promise<Response>(() => {
                /* never answers: the next window's read is hanging */
              });
        },
      },
    ]);
    const view = renderProbe(<TailProbe enabled />);
    await screen.findByText('count: 11');

    const moved = tailWindow(NOW + 60_000, 300_000);
    view.rerender(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <TailProbe enabled window={moved} />
        </QueryClientProvider>
      </ThemeProvider>,
    );

    // Without `keepPreviousData` the panel would blank every time the window moved,
    // which reads as a broken feed rather than a live one.
    expect(answered).toBe(2);
    expect(screen.getByText('count: 11')).toBeInTheDocument();
  });
});

describe('useLogLines', () => {
  it('reads no raw lines while no cluster is open', async () => {
    const requests = stubFetch([
      {
        match: '/api/v1/logs/lines',
        respond: () =>
          jsonResponse({
            start: '2026-10-06T10:00:00Z',
            end: '2026-10-06T10:05:00Z',
            key: null,
            lines: [],
            lines_seen: 0,
            lines_truncated: false,
            retained_from: null,
            retained_to: null,
            retained_lines: 0,
            dropped_lines: 0,
            caveats: [],
          }),
      },
    ]);
    const view = renderProbe(<LinesProbe clusterKey={null} />);
    await screen.findByText('lines: none');

    // An unkeyed read would answer "every line in the window" — a much larger read
    // than the panel was asked for, fired by merely arriving at the screen.
    expect(requests).toHaveLength(0);

    view.rerender(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <LinesProbe clusterKey="t-1" />
        </QueryClientProvider>
      </ThemeProvider>,
    );
    await waitFor(() => expect(requests.length).toBe(1));
    expect(new URL(requests[0]?.url ?? '').searchParams.get('key')).toBe('t-1');
  });
});
