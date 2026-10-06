/**
 * A fake WebSocket and a fake clock for the realtime layer's tests.
 *
 * The realtime client takes both as options precisely so this file can exist: the
 * alternative is a test that waits 30 s for a backoff and a jsdom `WebSocket` that
 * cannot be told to die at a chosen moment. Nothing here is a mock of the client's
 * *logic* — the sockets and timers are the boundary, and everything above them is
 * the real code.
 *
 * A fake socket records what it was asked for (URL, subprotocols) and lets a test
 * play the server: `open()`, `emit(frame)`, `serverClose(code)`.
 */
import { vi } from 'vitest';

import type { Clock, SocketFactory } from '../api/realtime';

/** A socket a test drives by hand. */
export interface FakeSocket {
  readonly url: string;
  readonly protocols: string[];
  /** Every close code this socket was closed with. */
  readonly closes: (number | undefined)[];
  /** True once a close has been requested, by either side. */
  closed: boolean;
  readyState: number;
  onopen: ((event: unknown) => void) | null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  close(code?: number, reason?: string): void;
  /** The server accepted the handshake. */
  open(): void;
  /** The server sent a frame (an object is serialised like the real transport). */
  emit(frame: unknown): void;
  /** The server closed the connection. */
  serverClose(code: number, reason?: string): void;
  /** The server failed the handshake with an error, then a close. */
  error(): void;
}

export interface FakeSocketFactory {
  factory: SocketFactory;
  /** Every socket opened, in order. */
  sockets: FakeSocket[];
  /** The most recent socket, or a thrown error naming the test's mistake. */
  last(): FakeSocket;
}

export function fakeSockets(): FakeSocketFactory {
  const sockets: FakeSocket[] = [];
  const factory: SocketFactory = (url, protocols) => {
    const socket: FakeSocket = {
      url,
      protocols: [...protocols],
      closes: [],
      closed: false,
      readyState: 0,
      onopen: null,
      onclose: null,
      onerror: null,
      onmessage: null,
      close(code) {
        this.closes.push(code);
        this.closed = true;
        this.readyState = 3;
      },
      open() {
        this.readyState = 1;
        this.onopen?.({});
      },
      emit(frame) {
        this.onmessage?.({ data: typeof frame === 'string' ? frame : JSON.stringify(frame) });
      },
      serverClose(code, reason) {
        this.readyState = 3;
        this.closed = true;
        // `reason` is only present when a test gives one: with
        // exactOptionalPropertyTypes an explicit `undefined` is not the same as an
        // absent property, and the real close event omits it.
        this.onclose?.(reason === undefined ? { code } : { code, reason });
      },
      error() {
        this.onerror?.({});
      },
    };
    sockets.push(socket);
    return socket;
  };
  return {
    factory,
    sockets,
    last: () => {
      const socket = sockets.at(-1);
      if (socket === undefined) throw new Error('no socket was opened');
      return socket;
    },
  };
}

/** A clock whose time only moves when a test moves it. */
export interface FakeClock extends Clock {
  /** Move time forward, running every timer that comes due (in order). */
  advance(ms: number): void;
  /** How many timers are outstanding, so a test can assert nothing was scheduled. */
  pending(): number;
}

export function fakeClock(): FakeClock {
  let now = 0;
  let nextId = 1;
  const timers = new Map<number, { due: number; handler: () => void }>();

  return {
    setTimeout(handler, ms) {
      const id = nextId;
      nextId += 1;
      timers.set(id, { due: now + Math.max(0, ms), handler });
      return id;
    },
    clearTimeout(handle) {
      timers.delete(handle);
    },
    advance(ms) {
      const target = now + ms;
      // A timer may schedule another one that is also already due; the loop runs
      // until time stops moving, with a bound so a self-rescheduling handler is a
      // test failure rather than a hang.
      for (let guard = 0; guard < 1_000; guard += 1) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.due <= target)
          .sort(([, left], [, right]) => left.due - right.due || 0);
        const next = due[0];
        if (next === undefined) break;
        const [id, timer] = next;
        timers.delete(id);
        now = timer.due;
        timer.handler();
      }
      now = Math.max(now, target);
    },
    pending() {
      return timers.size;
    },
  };
}

/**
 * Let pending promise callbacks run.
 *
 * The client's fallback poll awaits a fetch; a fake clock advancing into that poll
 * has to give the microtask queue a turn before the frames appear.
 */
export async function settle(): Promise<void> {
  for (let i = 0; i < 4; i += 1) await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

/** Silence an expected console error so a test's output stays readable. */
export function silenceConsole(): void {
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
}
