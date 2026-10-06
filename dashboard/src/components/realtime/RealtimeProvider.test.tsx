/**
 * The realtime layer's end-to-end behaviour, through the shell an analyst sees.
 *
 * What is faked here is the boundary and nothing above it: a socket the test
 * drives by hand, a clock it moves, and `fetch`. Everything between — the client's
 * state machine, the provider, the pub/sub fan-out, React Query's cache and the
 * shell's banner — is the real code, so the assertions are on rendered output
 * rather than on whether a mock was called.
 *
 * The labels are queried as text rather than by role because an indicator and a
 * banner are both live regions (they are supposed to be: one is the state, the
 * other is what the state means), so `getByRole('status')` would be ambiguous —
 * and the words are the thing the analyst reads anyway.
 */
import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getJson } from '../../api/client';
import { resetSessionForTests, setSessionToken } from '../../api/session';
import { AppShell } from '../layout/AppShell';
import { expectAccessible } from '../../test/axe';
import { jsonResponse, stubFetch, testQueryClient } from '../../test/query';
import { fakeClock, fakeSockets, settle } from '../../test/socket';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { RealtimeProvider, useAlertFeed } from './RealtimeProvider';
import { useAlertSync } from './useAlertSync';

const QUEUE_PATH = '/api/v1/alerts';
const NOTIFICATIONS_PATH = '/api/v1/alerts/notifications';

const READY = {
  type: 'ready',
  epoch: 'e-1',
  latest: 0,
  oldest_available: null,
  resync_required: false,
  after: null,
  heartbeat_seconds: 15,
};

function row(id: number) {
  return {
    id,
    created_at: '2026-10-06T10:00:00Z',
    entity_id: 3,
    family: 'exfiltration',
    severity: 'high',
    score: 0.9,
    status: 'open',
    first_seen: '2026-10-06T09:59:00Z',
    last_seen: '2026-10-06T10:00:00Z',
    occurrence_count: 1,
    trace_id: 'abc',
  };
}

const alertFrame = (sequence: number) => ({ type: 'alert', sequence, alert: row(sequence) });

/**
 * A screen that reads alerts the way the triage queue does: a React Query read of
 * the alert window, live updates through `useAlertSync`, and a pub/sub subscriber
 * that records what the stream pushed.
 */
function AlertList() {
  useAlertSync([['queue']]);
  const query = useQuery({
    queryKey: ['queue'],
    queryFn: async () => {
      const page = await getJson<{ items: { id: number }[] }>(QUEUE_PATH);
      return page.items.map((item) => item.id);
    },
  });
  const [pushed, setPushed] = useState<number[]>([]);
  useAlertFeed((frames) =>
    setPushed((previous) => [...previous, ...frames.map((f) => f.alert.id)]),
  );

  return (
    <>
      <p>queue: {query.data === undefined ? 'loading' : query.data.join(',')}</p>
      <p>pushed: {pushed.join(',') || 'none'}</p>
    </>
  );
}

function renderShell(options: { pollIntervalMs?: number } = {}) {
  const sockets = fakeSockets();
  const clock = fakeClock();
  const utils = render(
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>
        <RealtimeProvider
          socketFactory={sockets.factory}
          options={{ clock, random: () => 0, pollIntervalMs: options.pollIntervalMs ?? 15_000 }}
        >
          <MemoryRouter>
            <AppShell>
              <AlertList />
            </AppShell>
          </MemoryRouter>
        </RealtimeProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...utils, sockets, clock };
}

/**
 * A fetch stub for the two alert endpoints, with the queue's answer pluggable.
 *
 * `polls` records the cursor every fallback request asked to resume from, which is
 * how the tests assert on what the client *sent* rather than on what it meant to.
 */
function stubAlertEndpoints(
  queue: () => number[],
  notifications: () => { sequence: number; alert: unknown }[] = () => [],
) {
  const polls: (string | null)[] = [];
  const seen = stubFetch([
    {
      match: NOTIFICATIONS_PATH,
      respond: (request) => {
        polls.push(new URL(request.url).searchParams.get('after'));
        const items = notifications();
        return jsonResponse({
          items,
          oldest_available: 1,
          latest: items.at(-1)?.sequence ?? null,
          resync_required: false,
          epoch: 'e-1',
        });
      },
    },
    {
      match: QUEUE_PATH,
      respond: () =>
        jsonResponse({ items: queue().map(row), next_cursor: null, limit: 100, order: 'desc' }),
    },
  ]);
  return { seen, polls };
}

afterEach(() => {
  // The visibility test shadows jsdom's own getter; drop the shadow so the next
  // file's tests see a visible document.
  delete (document as unknown as Record<string, unknown>)['visibilityState'];
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetSessionForTests();
});

describe('the shell and the live stream', () => {
  it('says live only once the server has confirmed the subscription', async () => {
    stubAlertEndpoints(() => []);
    const { sockets } = renderShell();
    await screen.findByText(/queue:/);

    expect(screen.getByText('Degraded')).toBeInTheDocument();
    expect(screen.getByText('Connecting to the live alert stream')).toBeInTheDocument();

    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });

    await waitFor(() => expect(screen.getByText('Live')).toBeInTheDocument());
    expect(screen.queryByText('Live updates are off')).not.toBeInTheDocument();
  });

  it('shows the banner and falls back to polling when the connection is killed', async () => {
    const { seen } = stubAlertEndpoints(() => []);
    const { sockets, clock } = renderShell();
    await screen.findByText(/queue:/);
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });
    await screen.findByText('Live');
    const polls = () =>
      seen.filter((request) => new URL(request.url).pathname === NOTIFICATIONS_PATH).length;
    const before = polls();

    // The socket dies. This is the acceptance criterion: a visible banner, and REST
    // polling standing in for the stream.
    act(() => {
      sockets.last().serverClose(1006);
    });

    expect(await screen.findByText('Live updates are off')).toBeInTheDocument();
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
    expect(screen.getByText(/polling every 15 s/)).toBeInTheDocument();

    await settle();
    expect(polls()).toBeGreaterThan(before);

    // And it keeps polling at the documented cadence while the socket is down.
    await act(async () => {
      clock.advance(15_000);
      await settle();
    });
    expect(polls()).toBeGreaterThan(before + 1);
  });

  it('explains a refused credential, and still polls', async () => {
    stubAlertEndpoints(() => []);
    const { sockets } = renderShell();
    await screen.findByText(/queue:/);

    act(() => {
      sockets.last().open();
      sockets.last().serverClose(4401);
    });

    expect(await screen.findByText('Live updates are off')).toBeInTheDocument();
    expect(screen.getByText(/session is not authenticated/)).toBeInTheDocument();
  });

  it('replays missed alerts across a reconnect, without waiting for an interval', async () => {
    // The server's table: alerts 1 and 2 exist, and 3 is published mid-outage.
    let published = [1, 2];
    const { polls } = stubAlertEndpoints(
      () => published,
      () => [{ sequence: 3, alert: row(3) }],
    );
    const { sockets } = renderShell();

    await screen.findByText('queue: 1,2');
    act(() => {
      sockets.last().open();
      sockets.last().emit({ ...READY, latest: 2 });
      sockets.last().emit(alertFrame(1));
      sockets.last().emit(alertFrame(2));
    });
    await waitFor(() => expect(screen.getByText('pushed: 1,2')).toBeInTheDocument());

    // The socket dies with the client's cursor at 2, and alert 3 is published.
    published = [1, 2, 3];
    act(() => {
      sockets.last().serverClose(1006);
    });

    // The fallback resumes from the position the socket left off at, which is what
    // makes the screen whole again rather than merely restarting the poll.
    await waitFor(() => expect(screen.getByText('queue: 1,2,3')).toBeInTheDocument());
    expect(polls).toContain('2');
    expect(screen.getByText('pushed: 1,2,3')).toBeInTheDocument();
  });

  it('re-reads the window when the server says the gap was incomplete', async () => {
    stubAlertEndpoints(() => [1, 2]);
    const { sockets } = renderShell();
    await screen.findByText('queue: 1,2');
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });

    // A resync: the buffer no longer holds the whole gap, so the frames alone are
    // not the story and the window has to be read again.
    stubAlertEndpoints(() => [1, 4]);
    act(() => {
      sockets.last().emit({
        ...READY,
        after: 1,
        latest: 4,
        oldest_available: 3,
        resync_required: true,
      });
    });

    await waitFor(() => expect(screen.getByText('queue: 1,4')).toBeInTheDocument());
  });

  it('reconnects on demand from the banner, without waiting out the backoff', async () => {
    stubAlertEndpoints(() => []);
    const { sockets, clock } = renderShell();
    await screen.findByText(/queue:/);
    act(() => {
      sockets.last().open();
      sockets.last().serverClose(1006);
    });
    await screen.findByText('Live updates are off');
    expect(sockets.sockets).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'Reconnect now' }));

    expect(sockets.sockets).toHaveLength(2);
    expect(new URL(sockets.last().url).pathname).toBe('/api/v1/alerts/ws');
    // The abandoned backoff timer must not open a third socket behind it.
    clock.advance(1_000);
    expect(sockets.sockets).toHaveLength(2);
  });

  it('reopens a refused stream when a credential appears', async () => {
    stubAlertEndpoints(() => []);
    const { sockets } = renderShell();
    await screen.findByText(/queue:/);
    act(() => {
      sockets.last().open();
      sockets.last().serverClose(4401);
    });
    await screen.findByText('Live updates are off');

    act(() => {
      setSessionToken('t-fresh');
    });

    expect(sockets.sockets).toHaveLength(2);
    expect(sockets.last().protocols).toContain('aegis.bearer.t-fresh');
  });

  it('re-reads the window when the connection comes back, even with no frames', async () => {
    let queue = [1, 2];
    stubAlertEndpoints(() => queue);
    const { sockets, clock } = renderShell();
    await screen.findByText('queue: 1,2');
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });
    await screen.findByText('Live');

    // The socket dies and the fallback finds nothing new; meanwhile the window
    // moved on (an alert judged elsewhere, a row that fell out of it) and the
    // screen has no way to know.
    act(() => {
      sockets.last().serverClose(1006);
    });
    await screen.findByText('Live updates are off');
    queue = [1, 2, 9];
    await act(async () => {
      clock.advance(250);
      await settle();
    });

    // A connection that has just become live may have missed frames while it was
    // away, so the window is read again rather than assumed current.
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });

    await waitFor(() => expect(screen.getByText('queue: 1,2,9')).toBeInTheDocument());
  });

  it('does not poll while the tab is hidden, and polls at once when it is shown', async () => {
    const { seen } = stubAlertEndpoints(() => []);
    const { sockets, clock } = renderShell();
    await screen.findByText(/queue:/);

    const hide = (state: 'hidden' | 'visible') => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
    };

    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });
    await screen.findByText('Live');
    hide('hidden');

    // §4.1: a refresh nobody can see is a refresh nobody asked for. The socket
    // dies while the tab is in the background, and no poll is issued at all.
    act(() => {
      sockets.last().serverClose(1006);
    });
    await screen.findByText('Live updates are off');
    const polls = () =>
      seen.filter((request) => new URL(request.url).pathname === NOTIFICATIONS_PATH).length;
    expect(polls()).toBe(0);
    await act(async () => {
      clock.advance(60_000);
      await settle();
    });
    expect(polls()).toBe(0);

    hide('visible');
    expect(polls()).toBe(1);
  });

  it('defers a live refresh until the tab is visible again', async () => {
    let queue = [1];
    const { seen } = stubAlertEndpoints(() => queue);
    const { sockets } = renderShell();
    await screen.findByText('queue: 1');
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });
    await screen.findByText('Live');

    const setVisibility = (state: 'hidden' | 'visible') => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'));
      });
    };
    const reads = () =>
      seen.filter((request) => new URL(request.url).pathname === QUEUE_PATH).length;

    setVisibility('hidden');
    const before = reads();
    queue = [1, 2];

    // An alert arrives while nobody is looking. It is remembered rather than
    // acted on: §4.1 pauses refreshes in a hidden tab, and a read nobody can see
    // is a read nobody asked for.
    act(() => {
      sockets.last().emit(alertFrame(2));
    });
    await settle();
    expect(reads()).toBe(before);
    expect(screen.queryByText('queue: 1,2')).not.toBeInTheDocument();

    // The moment somebody looks, the read happens.
    setVisibility('visible');
    await waitFor(() => expect(screen.getByText('queue: 1,2')).toBeInTheDocument());
  });

  it('has no serious accessibility violations with the banner showing', async () => {
    stubAlertEndpoints(() => []);
    const { sockets, container } = renderShell();
    await screen.findByText(/queue:/);
    act(() => {
      sockets.last().open();
      sockets.last().serverClose(1006);
    });
    await screen.findByText('Live updates are off');

    await expectAccessible(container as HTMLElement);
  });
});

describe('the stale age in the header', () => {
  it('shows last update 2 m ago when nothing arrives at all', async () => {
    // design.md §8.1: "If live data stops arriving, show `last update 2 m ago` in
    // the header rather than silently showing old numbers." Nothing here reaches
    // the API — the socket never answers and the fallback's request fails — which
    // is exactly the outage the state exists for.
    vi.useFakeTimers();
    stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse({ detail: 'unavailable' }, 503) },
      {
        match: QUEUE_PATH,
        respond: () => jsonResponse({ items: [], next_cursor: null, limit: 100, order: 'desc' }),
      },
    ]);
    const sockets = fakeSockets();
    render(
      <ThemeProvider>
        <QueryClientProvider client={testQueryClient()}>
          <RealtimeProvider socketFactory={sockets.factory} options={{ random: () => 0 }}>
            <MemoryRouter>
              <AppShell>
                <AlertList />
              </AppShell>
            </MemoryRouter>
          </RealtimeProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    );

    // One frame, so there is a moment for the age to be measured from.
    act(() => {
      sockets.last().open();
      sockets.last().emit(READY);
    });
    expect(screen.getByText('Live')).toBeInTheDocument();

    // Two minutes with nothing arriving at all. Advanced in steps, because React
    // has to render between them for the age to keep ticking — which is what the
    // wall clock does on its own, and what the stale state exists for.
    for (let step = 0; step < 8; step += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000);
      });
    }

    expect(screen.getByText('Disconnected')).toBeInTheDocument();
    expect(screen.getByText(/last update 2 m ago/)).toBeInTheDocument();
  });
});
