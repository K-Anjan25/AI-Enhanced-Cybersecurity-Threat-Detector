import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AlertStreamClient, BEARER_PROTOCOL, NOTIFICATIONS_PATH, STREAM_PATH } from './realtime';
import { resetSessionForTests, setSessionToken } from './session';
import { jsonResponse, stubFetch } from '../test/query';
import { fakeClock, fakeSockets, settle } from '../test/socket';
import type { RealtimeFrame, RealtimeState } from '../lib/realtime';

const ALERT = (id: number) => ({
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
});

const READY = {
  type: 'ready',
  epoch: 'e-1',
  latest: 0,
  oldest_available: null,
  resync_required: false,
  after: null,
  heartbeat_seconds: 15,
};

function notifications(items: { sequence: number; alert: ReturnType<typeof ALERT> }[], extra = {}) {
  return {
    items,
    oldest_available: 1,
    latest: items.at(-1)?.sequence ?? null,
    resync_required: false,
    epoch: 'e-1',
    ...extra,
  };
}

function build(options: Partial<ConstructorParameters<typeof AlertStreamClient>[0]> = {}) {
  const sockets = fakeSockets();
  const clock = fakeClock();
  const frames: RealtimeFrame[] = [];
  const states: { state: RealtimeState; detail: string | null }[] = [];
  const client = new AlertStreamClient({
    socketFactory: sockets.factory,
    clock,
    random: () => 0,
    onFrame: (frame) => frames.push(frame),
    onState: (state, detail) => states.push({ state, detail }),
    ...options,
  });
  return { client, sockets, clock, frames, states };
}

function currentState(states: { state: RealtimeState }[]): RealtimeState | undefined {
  return states.at(-1)?.state;
}

/** The notification sequences the client handed to its subscriber, in order. */
function sequences(frames: RealtimeFrame[]): number[] {
  return frames.flatMap((frame) => (frame.type === 'alert' ? [frame.sequence] : []));
}

beforeEach(() => {
  resetSessionForTests();
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetSessionForTests();
});

describe('AlertStreamClient', () => {
  it('opens a same-origin socket with no cursor until one exists', () => {
    const { client, sockets } = build();

    client.start();

    expect(sockets.sockets).toHaveLength(1);
    expect(sockets.last().url).toBe(`ws://localhost:3000${STREAM_PATH}`);
  });

  it('carries the session token as a subprotocol, and offers the bare prefix too', () => {
    setSessionToken('t-abc');
    const { client, sockets } = build();

    client.start();

    // The server echoes `aegis.bearer`; a browser refuses a handshake whose
    // selected protocol it did not offer, so both must be on the wire.
    expect(sockets.last().protocols).toEqual([BEARER_PROTOCOL, 'aegis.bearer.t-abc']);
  });

  it('opens without a credential when there is no session, and says so', () => {
    const { client, sockets, states } = build();
    client.start();
    sockets.last().open();

    expect(sockets.last().protocols).toEqual([]);

    // The server refuses an unauthenticated handshake with 4401.
    sockets.last().serverClose(4401);

    expect(currentState(states)).toBe('refused');
    expect(states.at(-1)?.detail).toBe('The session is not authenticated');
  });

  it('goes live on the ready frame, not on the socket opening', () => {
    const { client, sockets, states } = build();

    client.start();
    sockets.last().open();

    expect(currentState(states)).toBe('connecting');

    sockets.last().emit(READY);

    expect(currentState(states)).toBe('live');
    expect(states.at(-1)?.detail).toBeNull();
  });

  it('falls back to REST polling the moment the socket dies', async () => {
    const seen = stubFetch([
      {
        match: NOTIFICATIONS_PATH,
        respond: () => jsonResponse(notifications([{ sequence: 1, alert: ALERT(1) }])),
      },
    ]);
    const { client, sockets, states, frames } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit(READY);
    sockets.last().serverClose(1006);
    await settle();

    expect(currentState(states)).toBe('polling');
    expect(states.at(-1)?.detail).toBe('The connection closed (1006)');
    expect(seen).toHaveLength(1);
    expect(new URL(seen[0]!.url).pathname).toBe(NOTIFICATIONS_PATH);
    expect(sequences(frames)).toEqual([1]);
  });

  it('polls with the same cursor, so the position advances with no socket at all', async () => {
    const seen = stubFetch([
      {
        match: NOTIFICATIONS_PATH,
        respond: (request) =>
          new URL(request.url).searchParams.get('after') === '5'
            ? jsonResponse(notifications([{ sequence: 6, alert: ALERT(6) }], { latest: 6 }))
            : jsonResponse(notifications([])),
      },
    ]);
    const { client, sockets, frames, clock } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit({ ...READY, latest: 5 });
    sockets.last().emit({ type: 'alert', sequence: 5, alert: ALERT(5) });
    sockets.last().serverClose(1006);
    await settle();
    clock.advance(15_000);
    await settle();

    // Each poll resumes from where the last one left the position, which is how
    // the fallback stays equivalent to the socket rather than a second timeline.
    expect(seen.map((request) => new URL(request.url).searchParams.get('after'))).toEqual([
      '5',
      '6',
    ]);
    expect(sequences(frames)).toEqual([5, 6]);
  });

  it('sends the session token on the polling fallback too', async () => {
    const seen = stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) },
    ]);
    setSessionToken('t-poll');
    const { client, sockets } = build();

    client.start();
    sockets.last().open();
    sockets.last().serverClose(1006);
    await settle();

    expect(seen[0]!.headers.get('authorization')).toBe('Bearer t-poll');
  });

  it('replays what was missed: the sequence across the switch is unbroken', async () => {
    // This is T-405's acceptance criterion, in the shape T-310 established for the
    // server: publish a known sequence, break the connection in the middle, and
    // assert the union across the switch *is* that sequence. The weak version — a
    // frame sent before the kill arrived — passes against a client that drops
    // everything after it.
    stubFetch([
      {
        match: NOTIFICATIONS_PATH,
        respond: () =>
          jsonResponse(notifications([{ sequence: 3, alert: ALERT(3) }], { latest: 3 })),
      },
    ]);
    const { client, sockets, clock, frames, states } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit({ ...READY, latest: 2 });
    sockets.last().emit({ type: 'alert', sequence: 1, alert: ALERT(1) });
    sockets.last().emit({ type: 'alert', sequence: 2, alert: ALERT(2) });

    // The socket dies mid-stream; alert 3 is published while the client is down and
    // arrives over the fallback.
    sockets.last().serverClose(1006);
    await settle();
    expect(sequences(frames)).toEqual([1, 2, 3]);

    // Reconnect: the resume cursor is the last sequence the subscriber received.
    clock.advance(1_000);
    expect(sockets.sockets).toHaveLength(2);
    expect(new URL(sockets.last().url).searchParams.get('after')).toBe('3');
    expect(currentState(states)).toBe('connecting');

    // The server replays everything after the cursor, which is exactly the window
    // the client missed plus what it had already seen excluded.
    sockets.last().open();
    sockets.last().emit({ ...READY, latest: 6, after: 3, oldest_available: 1 });
    for (const id of [4, 5, 6]) {
      sockets.last().emit({ type: 'alert', sequence: id, alert: ALERT(id) });
    }

    expect(sequences(frames)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(new Set(sequences(frames)).size).toBe(6);
    expect(currentState(states)).toBe('live');
  });

  it('backs off exponentially with jitter, and stops trying to reconnect while live', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build({ random: () => 1 });

    client.start();
    sockets.last().open();
    sockets.last().serverClose(1006);
    await settle();

    // Attempt 0 waits the full first window (jitter at its maximum here).
    clock.advance(499);
    expect(sockets.sockets).toHaveLength(1);
    clock.advance(1);
    expect(sockets.sockets).toHaveLength(2);
    sockets.last().serverClose(1006);

    // Attempt 1 waits twice as long.
    clock.advance(999);
    expect(sockets.sockets).toHaveLength(2);
    clock.advance(1);
    expect(sockets.sockets).toHaveLength(3);
    sockets.last().open();
    sockets.last().emit(READY);

    // A working stream stops the retries, and the fallback's timer with them.
    // (Under the 45 s silence window: a stream that says nothing at all is
    // *supposed* to be abandoned, which is what the heartbeat test pins.)
    clock.advance(30_000);
    sockets.last().emit({ type: 'heartbeat', at: '2026-10-06T10:00:30Z' });
    clock.advance(30_000);
    expect(sockets.sockets).toHaveLength(3);
  });

  it('resets the backoff after a stream has been live', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build({ random: () => 0 });

    client.start();
    sockets.last().open();
    sockets.last().serverClose(1006);
    await settle();
    clock.advance(250);
    sockets.last().serverClose(1006);
    await settle();
    clock.advance(500);
    expect(sockets.sockets).toHaveLength(3);

    // Third socket works for a while, then dies: the next attempt is back at the
    // base delay rather than continuing to grow from a failure that is over.
    sockets.last().open();
    sockets.last().emit(READY);
    sockets.last().serverClose(1006);
    await settle();
    clock.advance(249);
    expect(sockets.sockets).toHaveLength(3);
    clock.advance(1);
    expect(sockets.sockets).toHaveLength(4);
  });

  it('gives up on a refused credential, and keeps the screen fed by polling', async () => {
    const seen = stubFetch([
      {
        match: NOTIFICATIONS_PATH,
        respond: () => jsonResponse(notifications([{ sequence: 1, alert: ALERT(1) }])),
      },
    ]);
    const { client, sockets, clock, states, frames } = build();

    client.start();
    sockets.last().open();
    sockets.last().serverClose(4403);
    await settle();

    expect(currentState(states)).toBe('refused');
    // Ten minutes of waiting opens no further socket: the fix is a credential, not
    // patience. The fallback keeps the numbers moving in the meantime.
    for (let tick = 0; tick < 3; tick += 1) {
      clock.advance(15_000);
      await settle();
    }
    expect(sockets.sockets).toHaveLength(1);
    expect(sequences(frames)).toEqual([1, 1, 1, 1]);
    expect(seen).toHaveLength(4);
  });

  it('reopens the socket when a credential appears', () => {
    const { client, sockets, states } = build();

    client.start();
    sockets.last().open();
    sockets.last().serverClose(4401);
    expect(currentState(states)).toBe('refused');

    setSessionToken('t-fresh');
    client.onTokenChanged();

    expect(sockets.sockets).toHaveLength(2);
    expect(sockets.last().protocols).toEqual([BEARER_PROTOCOL, 'aegis.bearer.t-fresh']);
  });

  it('treats a slow-reader drop as a resume, not a failure', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build({ random: () => 0 });

    client.start();
    sockets.last().open();
    sockets.last().emit({ ...READY, latest: 2 });
    sockets.last().emit({ type: 'alert', sequence: 2, alert: ALERT(2) });
    // The server drops a slow consumer with 1013 and its resume cursor.
    sockets.last().serverClose(1013);
    await settle();

    // A drop is not a failure: the next attempt is the first one, 250 ms away (the
    // base window at full jitter), not the grown window of a broken connection.
    clock.advance(249);
    expect(sockets.sockets).toHaveLength(1);
    clock.advance(1);
    expect(sockets.sockets).toHaveLength(2);
    expect(new URL(sockets.last().url).searchParams.get('after')).toBe('2');

    // And a second drop in a row still starts from the base — otherwise a busy
    // stream would walk the delay up to its ceiling one drop at a time.
    sockets.last().serverClose(1013);
    await settle();
    clock.advance(250);
    expect(sockets.sockets).toHaveLength(3);
  });

  it('honours the server\u2019s resume cursor when it is ahead of ours', async () => {
    // A dropped slow reader is told where to resume from, which is what makes the
    // drop survivable rather than lossy: the server's position can be ahead of what
    // this client has managed to apply (frames still in flight when the drop
    // arrives), and taking it is what closes the gap.
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build({ random: () => 0 });

    client.start();
    sockets.last().open();
    sockets.last().emit({ ...READY, latest: 2 });
    sockets.last().emit({ type: 'alert', sequence: 2, alert: ALERT(2) });
    sockets.last().emit({ type: 'dropped', reason: 'slow reader', after: 5 });
    sockets.last().serverClose(1013);
    await settle();

    clock.advance(250);

    expect(new URL(sockets.last().url).searchParams.get('after')).toBe('5');
  });

  it('stops the fallback the moment the stream comes back', async () => {
    const seen = stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) },
    ]);
    const { client, sockets, clock } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit(READY);
    sockets.last().serverClose(1006);
    await settle();
    expect(seen).toHaveLength(1);

    // A reconnect succeeds and the subscription is confirmed.
    clock.advance(250);
    sockets.last().open();
    sockets.last().emit(READY);
    expect(client.currentState).toBe('live');

    // A screen that both streams *and* polls is paying twice for the same alerts.
    for (let beat = 0; beat < 4; beat += 1) {
      clock.advance(15_000);
      sockets.last().emit({ type: 'heartbeat', at: '2026-10-06T10:00:00Z' });
      await settle();
    }
    expect(seen).toHaveLength(1);
  });

  it('abandons a socket that has gone quiet for three heartbeats', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock, states } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit({ ...READY, heartbeat_seconds: 2 });

    clock.advance(5_999);
    expect(states.at(-1)?.detail).not.toBe('The stream went quiet');

    clock.advance(1);

    // A TCP connection that is open while the peer is gone is the failure a
    // heartbeat exists to catch: nothing else would ever report it.
    expect(states.at(-1)?.detail).toBe('The stream went quiet');
    expect(currentState(states)).toBe('polling');
  });

  it('never polls while the stream is carrying alerts, and heartbeats keep it alive', async () => {
    const seen = stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) },
    ]);
    const { client, sockets, clock } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit(READY);

    // A minute of heartbeats. Each one re-arms the watchdog: without that, the
    // first one would fire 45 s after the last *data* frame and a healthy stream
    // would be torn down for being quiet on a channel it is beating on.
    for (let beat = 0; beat < 4; beat += 1) {
      clock.advance(15_000);
      sockets.last().emit({ type: 'heartbeat', at: '2026-10-06T10:00:00Z' });
      await settle();
    }

    expect(seen).toHaveLength(0);
    expect(sockets.sockets).toHaveLength(1);
    expect(client.currentState).toBe('live');
  });

  it('abandons a socket that never finishes opening', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock, states } = build();

    client.start();
    // The handshake hangs: nothing opens, nothing closes, nothing arrives.
    clock.advance(7_999);
    expect(client.currentState).toBe('connecting');

    clock.advance(1);

    expect(currentState(states)).toBe('polling');
    expect(states.at(-1)?.detail).toBe('The live channel did not open in time');
    clock.advance(250);
    expect(sockets.sockets).toHaveLength(2);
  });

  it('keeps a live stream alive across frames it does not understand', () => {
    const { client, sockets, states, frames } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit(READY);
    sockets.last().emit('{ this is not json');
    sockets.last().emit({ type: 'future-frame' });
    sockets.last().emit([1, 2, 3]);

    expect(currentState(states)).toBe('live');
    expect(sockets.sockets).toHaveLength(1);
    expect(sequences(frames)).toEqual([]);
  });

  it('retries on demand rather than waiting out the backoff', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build({ random: () => 1 });

    client.start();
    sockets.last().open();
    sockets.last().serverClose(1006);
    await settle();
    clock.advance(100);
    expect(sockets.sockets).toHaveLength(1);

    client.retryNow();

    expect(sockets.sockets).toHaveLength(2);
    // The abandoned timer must not fire a third socket later.
    clock.advance(1_000);
    expect(sockets.sockets).toHaveLength(2);
  });

  it('pauses the fallback while nobody is looking, and polls at once when they look', async () => {
    const seen = stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) },
    ]);
    const { client, sockets, clock } = build();

    client.start();
    sockets.last().open();
    sockets.last().emit(READY);
    sockets.last().emit({ type: 'alert', sequence: 1, alert: ALERT(1) });

    // The tab is hidden, and then the socket dies: no poll is issued at all while
    // nobody could see the answer.
    client.setPaused(true);
    sockets.last().serverClose(1006);
    clock.advance(30_000);
    await settle();
    expect(seen).toHaveLength(0);

    // Somebody looks again: the poll happens at once rather than in 15 s.
    client.setPaused(false);
    await settle();
    expect(seen).toHaveLength(1);
  });

  it('stops everything when the screen is done with the stream', async () => {
    stubFetch([{ match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) }]);
    const { client, sockets, clock } = build();

    client.start();
    sockets.last().open();
    client.stop();

    expect(sockets.last().closes).toEqual([1000]);
    clock.advance(120_000);
    await settle();
    expect(sockets.sockets).toHaveLength(1);
    expect(clock.pending()).toBe(0);
  });

  it('polls instead of throwing when the socket cannot even be constructed', async () => {
    const seen = stubFetch([
      { match: NOTIFICATIONS_PATH, respond: () => jsonResponse(notifications([])) },
    ]);
    const { client, clock, states } = build({
      socketFactory: () => {
        throw new Error('blocked by a content security policy');
      },
    });

    client.start();
    await settle();

    expect(currentState(states)).toBe('polling');
    expect(seen).toHaveLength(1);
    // And it keeps trying: a blocked socket is often a policy that a reload fixes.
    clock.advance(1_000);
  });
});
