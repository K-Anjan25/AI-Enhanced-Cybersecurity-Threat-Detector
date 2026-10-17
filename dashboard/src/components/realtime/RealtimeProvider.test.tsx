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
import { useState } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getJson } from '../../api/client';
import { resetSessionForTests } from '../../api/session';
import { AppShell } from '../layout/AppShell';
import { jsonResponse, stubFetch, testQueryClient } from '../../test/query';
import { fakeClock, fakeSockets } from '../../test/socket';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { RealtimeProvider, useAlertFeed } from './RealtimeProvider';
import { useAlertSync } from './useAlertSync';

/**
 * The shell now renders the palette's search control, which opens a dialog this
 * file does not test: it is a stub here so the shell can be rendered without the
 * command provider.
 */
const openPalette = vi.fn();

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
            <AppShell onOpenPalette={openPalette} onSignOut={() => undefined}>
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
});
