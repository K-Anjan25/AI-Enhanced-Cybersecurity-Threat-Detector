/**
 * The alert stream client: one connection, three transports, and the rules for
 * when each one is in charge.
 *
 * This is the only place in the dashboard that constructs a `WebSocket` (R-23:
 * all network access goes through a typed client in `src/api/`), and it is the
 * only place that knows the difference between "the socket is down" and "the
 * session is over". Everything above it — the provider, the shell's indicator,
 * the pub/sub hook — sees two things: frames, and a state.
 *
 * The behaviour it implements, in the order it matters:
 *
 *   1. **Open, and keep the position.** The socket resumes from the last sequence
 *      a subscriber actually received, so an alert published during the outage
 *      arrives after it, from the server's own buffer.
 *   2. **While it is down, poll.** Every 15 s (architecture.md §14), using the
 *      same cursor, so the position keeps advancing with no socket at all — and
 *      the polling answer is turned into the *same frames* the socket sends, so
 *      nothing above this file can tell which transport delivered an alert.
 *   3. **Back off, with jitter.** Attempts grow 500 ms → 30 s and never arrive in
 *      lockstep with every other dashboard.
 *   4. **Stop on a refusal.** 4401/4403 are not transient; the client waits for a
 *      credential (`src/api/session.ts` broadcasts one) rather than hammering a
 *      server that has already said no. Polling continues in that state, because
 *      "the socket cannot authenticate" is not the same claim as "the API
 *      cannot", and a banner over the last known numbers beats an empty screen.
 *   5. **Pause when nobody is looking.** design.md §4.1 pauses refreshes in a
 *      hidden tab; the fallback poll is a refresh, so it pauses with the rest. The
 *      socket stays open — it is the server pushing, and a tab that is hidden now
 *      may be the one an analyst returns to.
 *
 * `AlertStreamClient` is deliberately not a React component: it takes a socket
 * factory, a clock and a frame sink, so its whole state machine is exercised by a
 * node-speed test with no DOM and no wall clock.
 */
import { getJson } from './client';
import { sessionToken } from './session';
import {
  backoffDelay,
  closeDetail,
  closeVerdict,
  cursorOf,
  FALLBACK_POLL_MS,
  framesFromNotifications,
  parseFrame,
  socketUrl,
  CONNECT_TIMEOUT_MS,
  type AlertFrame,
  type RealtimeFrame,
  type RealtimeState,
} from '../lib/realtime';

/** The socket's path. Same origin as the page; the dev server proxies `/api`. */
export const STREAM_PATH = '/api/v1/alerts/ws';

/** The polling fallback's path (T-310's REST transport, and the resync target). */
export const NOTIFICATIONS_PATH = '/api/v1/alerts/notifications';

/** The subprotocol a browser uses to carry its bearer token (T-310). */
export const BEARER_PROTOCOL = 'aegis.bearer';

/** The subset of `WebSocket` this client uses, so a test can implement it. */
export interface SocketLike {
  readyState: number;
  close(code?: number, reason?: string): void;
  onopen: ((event: unknown) => void) | null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
}

export interface SocketFactory {
  (url: string, protocols: string[]): SocketLike;
}

/** A timer source, so a test can drive the clock instead of waiting for it. */
export interface Clock {
  setTimeout(handler: () => void, ms: number): number;
  clearTimeout(handle: number): void;
}

/**
 * One alert plus its stream position, as `AlertNotificationOut` defines it.
 *
 * Named rather than written inline in `NotificationsPayload.items`, so the wire
 * contract check can see it: an inline literal is invisible to a field-by-field
 * comparison, which is exactly how the erasure report's `preserved` rows drifted
 * (`{store}` where the server sends `{name}`) without anything noticing.
 */
export interface AlertNotification {
  sequence: number;
  alert: AlertFrame['alert'];
}

/** The polling answer, as `app/schemas/stream.py` defines it. */
export interface NotificationsPayload {
  items: AlertNotification[];
  oldest_available: number | null;
  latest: number | null;
  resync_required: boolean;
  epoch: string;
}

export interface StreamOptions {
  /** Injected in tests; defaults to `window.WebSocket`. */
  socketFactory?: SocketFactory;
  /** Injected in tests; defaults to the browser's timers. */
  clock?: Clock;
  /** The token provider; defaults to the session store. */
  token?: () => string | null;
  /** The polling cadence; defaults to architecture.md §14's 15 s. */
  pollIntervalMs?: number;
  /** Jitter source for the backoff, so the schedule is deterministic in tests. */
  random?: () => number;
  /** Where frames go. */
  onFrame: (frame: RealtimeFrame) => void;
  /** Where state changes go, with a human-readable detail for the banner. */
  onState: (state: RealtimeState, detail: string | null) => void;
}

const OPEN = 1;

function browserClock(): Clock {
  return {
    setTimeout: (handler, ms) => window.setTimeout(handler, ms),
    clearTimeout: (handle) => {
      window.clearTimeout(handle);
    },
  };
}

function defaultFactory(url: string, protocols: string[]): SocketLike {
  return new WebSocket(url, protocols) as unknown as SocketLike;
}

export class AlertStreamClient {
  private readonly options: StreamOptions;
  private readonly clock: Clock;
  private readonly random: () => number;
  private readonly factory: SocketFactory;
  private readonly token: () => string | null;
  private readonly pollIntervalMs: number;

  private socket: SocketLike | null = null;
  private state: RealtimeState = 'connecting';
  private cursor: number | null = null;
  private heartbeatSeconds = 15;
  private attempt = 0;
  private running = false;
  private polling = false;
  private paused = false;
  private pollTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private silenceTimer: number | null = null;
  private connectTimer: number | null = null;

  constructor(options: StreamOptions) {
    this.options = options;
    this.clock = options.clock ?? browserClock();
    this.random = options.random ?? Math.random;
    this.factory = options.socketFactory ?? defaultFactory;
    this.token = options.token ?? sessionToken;
    this.pollIntervalMs = options.pollIntervalMs ?? FALLBACK_POLL_MS;
  }

  /** The state the shell renders. */
  get currentState(): RealtimeState {
    return this.state;
  }

  /** The resume position: the last sequence delivered to a subscriber. */
  get currentCursor(): number | null {
    return this.cursor;
  }

  /** Begin: open a socket and, if it does not hold, fall back to polling. */
  start(): void {
    if (this.running) return;
    this.running = true;
    this.setState('connecting', 'Opening the live channel');
    this.open();
  }

  /** Stop for good: no reconnect, no polling, no socket. */
  stop(): void {
    this.running = false;
    this.clearTimers();
    const socket = this.socket;
    this.socket = null;
    if (socket !== null) {
      // Detach before closing: a close handler that runs during `stop()` would
      // schedule a reconnect for a client that was just shut down, which is how a
      // page that navigated away keeps a server's subscription alive.
      socket.onclose = null;
      socket.onerror = null;
      socket.onmessage = null;
      socket.onopen = null;
      try {
        socket.close(1000);
      } catch {
        // A socket that cannot be closed is already gone.
      }
    }
  }

  /**
   * React to a credential appearing, rotating or being cleared.
   *
   * A terminal refusal is the one state a credential can fix, so a change clears
   * it and starts over; anything else keeps the schedule it already had.
   */
  onTokenChanged(): void {
    if (!this.running) return;
    this.attempt = 0;
    if (this.state === 'refused') {
      this.setState('connecting', 'Opening the live channel');
      this.open();
    }
  }

  /**
   * Try again now, ignoring whatever is left of the backoff.
   *
   * The banner offers this because a backoff is a policy about *unattended*
   * retries: an analyst who has just fixed something (signed in, restarted the
   * API) should not have to wait out a 30 s ceiling to find out whether it
   * worked.
   */
  retryNow(): void {
    if (!this.running || this.state === 'live') return;
    this.attempt = 0;
    this.clearTimeout('reconnectTimer');
    this.setState('connecting', 'Reconnecting');
    this.open();
  }

  /**
   * Pause or resume the fallback poll (design.md §4.1).
   *
   * Resuming polls immediately: the point of the pause is that nobody was
   * watching, not that the screen should be stale for another interval once
   * somebody is.
   */
  setPaused(paused: boolean): void {
    if (this.paused === paused) return;
    this.paused = paused;
    if (paused) {
      this.polling = false;
      this.clearTimeout('pollTimer');
      return;
    }
    // Not gated on there being no socket: a socket that is reconnecting has not
    // proved it can carry alerts, and the fallback is what makes the screen
    // correct in the meantime.
    if (this.running && this.state !== 'live') this.startPolling();
  }

  private setState(state: RealtimeState, detail: string | null): void {
    this.state = state;
    this.options.onState(state, detail);
  }

  private clearTimers(): void {
    this.clearTimeout('pollTimer');
    this.clearTimeout('reconnectTimer');
    this.clearTimeout('silenceTimer');
    this.clearTimeout('connectTimer');
  }

  private clearTimeout(
    key: 'pollTimer' | 'reconnectTimer' | 'silenceTimer' | 'connectTimer',
  ): void {
    const handle = this[key];
    if (handle !== null) {
      this.clock.clearTimeout(handle);
      this[key] = null;
    }
  }

  private protocols(): string[] {
    const token = this.token();
    if (token === null || token === '') return [];
    // Both are offered: the server echoes the bare prefix (a WebSocket handshake
    // fails when the server selects a protocol the client did not offer), and the
    // token rides in the offered one. A header, so it is as private as any other.
    return [BEARER_PROTOCOL, `${BEARER_PROTOCOL}.${token}`];
  }

  /** Emit a frame and take the bookkeeping it implies, whatever carried it. */
  private emit(frame: RealtimeFrame): void {
    this.options.onFrame(frame);
    if (frame.type === 'alert') {
      this.cursor = cursorOf([frame], this.cursor);
      return;
    }
    if (frame.type === 'ready') {
      this.heartbeatSeconds = frame.heartbeat_seconds;
      return;
    }
    if (frame.type === 'dropped' && frame.after !== null) {
      // The server dropped this subscriber and says where to resume: taking its
      // position is what stops the next connection from re-delivering what the
      // socket already sent.
      this.cursor = this.cursor === null ? frame.after : Math.max(this.cursor, frame.after);
    }
  }

  private open(): void {
    if (!this.running) return;
    const url = socketUrl(STREAM_PATH, { after: this.cursor ?? undefined }, window.location);

    let socket: SocketLike;
    try {
      socket = this.factory(url, this.protocols());
    } catch {
      // A constructor that throws (a blocked mixed-content upgrade, a hostile
      // Content-Security-Policy) is a transport failure like any other: poll and
      // back off rather than leaving the screen claiming to be live.
      this.scheduleReconnect('The live channel could not be opened');
      return;
    }
    this.socket = socket;

    this.connectTimer = this.clock.setTimeout(() => {
      this.connectTimer = null;
      if (this.socket !== socket || socket.readyState === OPEN) return;
      this.abandon(socket, 'The live channel did not open in time');
    }, CONNECT_TIMEOUT_MS);

    socket.onopen = () => {
      this.clearTimeout('connectTimer');
      // Not yet `live`: the server's `ready` frame is what says the subscription
      // exists and where the cursor stands. Claiming live before the handshake
      // completed is the classic dashboard lie.
      this.setState('connecting', 'Waiting for the stream to confirm');
    };

    socket.onmessage = (event) => {
      const frame = this.decode(event.data);
      if (frame === null) return;
      this.emit(frame);
      // Armed *after* the frame is applied, not before: a `ready` frame carries
      // the server's own heartbeat interval, and arming first would watch the
      // socket for the *previous* interval — 45 s by default against a deployment
      // that happens to beat every two.
      this.armSilenceTimer();
      if (frame.type === 'ready') {
        // The subscription is real: this is the moment the screen may say live,
        // and the moment the fallback stops — a screen that both streams and
        // polls is paying twice for the same alerts.
        this.attempt = 0;
        this.stopPolling();
        this.setState('live', null);
      }
      if (frame.type === 'dropped') this.attempt = 0;
    };

    socket.onerror = () => {
      // Nothing to read here: a socket's fate is decided by the close that always
      // follows an error, and a message built from an error event would be a
      // message built from nothing.
    };

    socket.onclose = (event) => {
      const code = typeof event?.code === 'number' ? event.code : 1006;
      this.socket = null;
      this.clearTimeout('connectTimer');
      this.clearTimeout('silenceTimer');
      // A slow-reader drop is the server's doing, not a sign the client is
      // failing, so the next attempt starts from the base delay. Nothing else
      // resets here: a socket that had gone `live` already reset when its `ready`
      // frame arrived, and re-testing it here would be a condition that can never
      // be true at this point.
      if (code === 1013) this.attempt = 0;
      const verdict = closeVerdict(code);
      if (verdict === 'terminal') {
        this.setState('refused', closeDetail(code));
        this.startPolling();
        return;
      }
      this.scheduleReconnect(closeDetail(code));
    };
  }

  private decode(data: unknown): RealtimeFrame | null {
    if (typeof data !== 'string') return null;
    try {
      return parseFrame(JSON.parse(data) as unknown);
    } catch {
      // A frame that is not JSON is not this client's to interpret; the stream
      // continues rather than dying on a message it did not expect.
      return null;
    }
  }

  /**
   * Re-arm the silence watchdog.
   *
   * Every frame counts, heartbeat included, and the window is derived from what
   * the server advertised: a socket that has said nothing for three beats is a
   * socket whose TCP connection is open and whose peer is gone.
   */
  private armSilenceTimer(): void {
    this.clearTimeout('silenceTimer');
    this.silenceTimer = this.clock.setTimeout(
      () => {
        this.silenceTimer = null;
        const socket = this.socket;
        if (socket === null) return;
        this.abandon(socket, 'The stream went quiet');
      },
      Math.max(3 * this.heartbeatSeconds, 1) * 1_000,
    );
  }

  /** Give up on a socket and start the fallback, as a transport loss. */
  private abandon(socket: SocketLike, detail: string): void {
    if (this.socket !== socket) return;
    this.socket = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;
    socket.onopen = null;
    try {
      socket.close();
    } catch {
      // Already gone.
    }
    this.clearTimeout('silenceTimer');
    this.clearTimeout('connectTimer');
    this.scheduleReconnect(detail);
  }

  private scheduleReconnect(detail: string): void {
    if (!this.running) return;
    this.setState('polling', detail);
    this.startPolling();
    if (this.reconnectTimer !== null) return;
    const delay = backoffDelay(this.attempt, this.random);
    this.attempt += 1;
    this.reconnectTimer = this.clock.setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.running) return;
      this.setState('connecting', 'Reconnecting');
      this.open();
    }, delay);
  }

  /**
   * Start the fallback, once.
   *
   * The first poll is immediate and then the cadence takes over: an analyst who
   * opens the screen while the socket is down should wait 15 s for *updates*, not
   * 15 s for any data at all. Polling stops the moment a `ready` frame proves the
   * socket is carrying alerts again, so a screen is never both streamed to and
   * polled at once.
   */
  private startPolling(): void {
    if (!this.running || this.polling || this.paused) return;
    this.polling = true;
    const schedule = () => {
      this.pollTimer = this.clock.setTimeout(() => {
        this.pollTimer = null;
        void this.poll().finally(() => {
          if (this.running && this.state !== 'live') schedule();
        });
      }, this.pollIntervalMs);
    };
    void this.poll().finally(() => {
      if (this.running && this.state !== 'live') schedule();
    });
  }

  private stopPolling(): void {
    this.polling = false;
    this.clearTimeout('pollTimer');
  }

  /** One fallback poll, emitting the frames the socket would have emitted. */
  private async poll(): Promise<void> {
    if (!this.running || !this.polling || this.paused) return;
    const after = this.cursor;
    try {
      const payload = await getJson<NotificationsPayload>(
        `${NOTIFICATIONS_PATH}${after === null ? '' : `?after=${String(after)}`}`,
      );
      if (!this.running || !this.polling) return;
      for (const frame of framesFromNotifications(payload, after)) this.emit(frame);
    } catch {
      // A failed poll is not a state change: the banner already says the socket
      // is down, and a second message per tick would be noise. Nothing is logged
      // here either (R-58 forbids a URL or a body reaching a log); the next tick
      // tries again.
    }
  }
}
