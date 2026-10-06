/**
 * The realtime layer's pure half: the frame vocabulary, the resume cursor, the
 * reconnect schedule and the URL a socket is opened on.
 *
 * architecture.md §10 asks for "a single WebSocket connection at the app shell,
 * fanned out through a pub/sub hook. Auto-reconnect with exponential backoff and
 * a visible `disconnected` banner", and §14 gives the failure behaviour: "UI
 * falls back to REST polling at 15 s; banner shown". Every one of those is a rule
 * about *decisions*, not about a socket, so they live here where a node test can
 * pin them down:
 *
 *   * **The fallback speaks the socket's vocabulary.** `GET /alerts/notifications`
 *     returns notifications and a cursor — the same facts a `ready` frame carries
 *     — so polling is turned into `ready` + `alert` frames here. A subscriber
 *     cannot tell which transport delivered an alert except by the state the
 *     shell shows, which is the point: two code paths for the same alert is two
 *     places for a bug to hide.
 *   * **A refusal is terminal; a broken pipe is not.** `4401`/`4403` mean the
 *     credential was rejected — retrying is a login form, not a backoff — so the
 *     client stops and says so. Everything else backs off and keeps trying.
 *   * **The cursor is the resume position, and it is the last sequence a
 *     subscriber actually received.** `after` on reconnect is what makes "no
 *     alert is lost across the switch" true rather than aspirational.
 *
 * Frame sizes are bounded by the server (one alert per frame, and the hub's
 * buffer bounded), so nothing here reads an unbounded stream.
 */

/** The frames the alert stream carries, as `app/schemas/stream.py` defines them. */
export interface ReadyFrame {
  type: 'ready';
  /** The publishing process's stream identity. A change means cursors are void. */
  epoch: string;
  /** The newest sequence published, or `null` when nothing has been. */
  latest: number | null;
  oldest_available: number | null;
  /** True when the cursor predated the retained window, so the gap is incomplete. */
  resync_required: boolean;
  after: number | null;
  heartbeat_seconds: number;
}

export interface AlertFrame {
  type: 'alert';
  sequence: number;
  alert: {
    id: number;
    created_at: string;
    entity_id: number;
    family: string;
    severity: string;
    score: number;
    status: string;
    first_seen: string;
    last_seen: string;
    occurrence_count: number;
    trace_id: string | null;
  };
}

export interface HeartbeatFrame {
  type: 'heartbeat';
  at: string;
}

export interface DroppedFrame {
  type: 'dropped';
  reason: string;
  after: number | null;
}

export type RealtimeFrame = ReadyFrame | AlertFrame | HeartbeatFrame | DroppedFrame;

/** The connection states a screen can be in, in the order they can occur. */
export type RealtimeState = 'connecting' | 'live' | 'polling' | 'refused';

/**
 * How often the fallback polls while the socket is down.
 *
 * architecture.md §14: "Dashboard WebSocket drops → UI falls back to REST polling
 * at 15 s". The same cadence the overview's charts use, so a screen that has lost
 * the socket is not *twice* as chatty as one that has not.
 */
export const FALLBACK_POLL_MS = 15_000;

/** How long an opening socket may take before it is treated as a failure. */
export const CONNECT_TIMEOUT_MS = 8_000;

/** The backoff's first step, and its ceiling. */
export const BACKOFF_BASE_MS = 500;
export const BACKOFF_MAX_MS = 30_000;

/**
 * How long a live socket may say nothing before it is presumed dead.
 *
 * Derived from the heartbeat the server advertised rather than fixed here: the
 * server beats every `heartbeat_seconds`, so three missed beats is a dead
 * channel, and a deployment that changes its cadence does not have to remember to
 * change this.
 */
export function silenceTimeoutMs(heartbeatSeconds: number): number {
  return Math.max(3 * heartbeatSeconds, 1) * 1_000;
}

/**
 * The delay before reconnect attempt `attempt` (0-based).
 *
 * Exponential with **equal jitter**: half the window is fixed, half is random, so
 * a thousand dashboards reconnecting after a deploy do not arrive together, and a
 * single one still retries within a predictable bound. `random` is injected so the
 * schedule is testable instead of merely plausible.
 */
export function backoffDelay(
  attempt: number,
  random: () => number = Math.random,
  options: { baseMs?: number; maxMs?: number } = {},
): number {
  const base = options.baseMs ?? BACKOFF_BASE_MS;
  const max = options.maxMs ?? BACKOFF_MAX_MS;
  const safeAttempt = Number.isFinite(attempt) ? Math.max(0, Math.floor(attempt)) : 0;
  const window = Math.min(base * 2 ** safeAttempt, max);
  const half = window / 2;
  return Math.round(half + Math.max(0, Math.min(1, random())) * half);
}

/**
 * The `ws:`/`wss:` URL for a same-origin path.
 *
 * The browser must never call the backend directly (T-403's rule for `/api`), so
 * the path is relative and the origin comes from the page. `http:` becomes `ws:`
 * and `https:` becomes `wss:` — a page served over TLS opening a clear-text socket
 * is blocked by every browser, and a URL that cannot be opened is better refused
 * here where the reason is nameable.
 */
export function socketUrl(
  path: string,
  params: Record<string, string | number | undefined>,
  location: { protocol: string; host: string },
): string {
  if (!path.startsWith('/')) {
    throw new Error('socket paths must be absolute paths on this origin');
  }
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return `${protocol}//${location.host}${path}${query === '' ? '' : `?${query}`}`;
}

/** Whether a raw frame is a JSON object we can read a `type` off. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isAlertRow(value: unknown): value is AlertFrame['alert'] {
  if (!isRecord(value)) return false;
  return (
    typeof value['id'] === 'number' &&
    typeof value['created_at'] === 'string' &&
    typeof value['entity_id'] === 'number' &&
    typeof value['family'] === 'string' &&
    typeof value['severity'] === 'string' &&
    typeof value['score'] === 'number'
  );
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * Decode one frame, or `null` when it is not one this build understands.
 *
 * Returning `null` rather than throwing is the whole reason this is a function: a
 * frame from a *newer* server, a truncated payload, or a text message the socket
 * was not expecting must not tear down a working connection. The unknown frame is
 * dropped and the stream continues — the alternative is a dashboard that goes
 * dark because it met a field it had not heard of.
 */
export function parseFrame(raw: unknown): RealtimeFrame | null {
  if (!isRecord(raw)) return null;
  const type = raw['type'];
  if (type === 'alert') {
    const sequence = numberOrNull(raw['sequence']);
    if (sequence === null || !isAlertRow(raw['alert'])) return null;
    return { type: 'alert', sequence, alert: raw['alert'] };
  }
  if (type === 'ready') {
    const heartbeat = numberOrNull(raw['heartbeat_seconds']);
    return {
      type: 'ready',
      epoch: typeof raw['epoch'] === 'string' ? raw['epoch'] : '',
      latest: numberOrNull(raw['latest']),
      oldest_available: numberOrNull(raw['oldest_available']),
      resync_required: raw['resync_required'] === true,
      after: numberOrNull(raw['after']),
      heartbeat_seconds: heartbeat === null || heartbeat <= 0 ? 15 : heartbeat,
    };
  }
  if (type === 'heartbeat') {
    return { type: 'heartbeat', at: typeof raw['at'] === 'string' ? raw['at'] : '' };
  }
  if (type === 'dropped') {
    return {
      type: 'dropped',
      reason: typeof raw['reason'] === 'string' ? raw['reason'] : 'dropped',
      after: numberOrNull(raw['after']),
    };
  }
  return null;
}

/**
 * Turn one polling answer into the frames the socket would have sent.
 *
 * The fallback is not a smaller feature: it carries the same `resync_required`
 * and the same sequences, in the same order, so a subscriber's cursor advances
 * identically whichever transport it is on. That is what makes the switch
 * invisible to everything above this function.
 */
export function framesFromNotifications(
  payload: {
    items: { sequence: number; alert: AlertFrame['alert'] }[];
    oldest_available: number | null;
    latest: number | null;
    resync_required: boolean;
    epoch: string;
  },
  after: number | null,
  heartbeatSeconds = 15,
): RealtimeFrame[] {
  const ready: ReadyFrame = {
    type: 'ready',
    epoch: payload.epoch,
    latest: payload.latest,
    oldest_available: payload.oldest_available,
    resync_required: payload.resync_required,
    after,
    heartbeat_seconds: heartbeatSeconds,
  };
  return [
    ready,
    ...payload.items.map((item): AlertFrame => ({
      type: 'alert',
      sequence: item.sequence,
      alert: item.alert,
    })),
  ];
}

/**
 * The cursor a set of frames leaves behind: the largest sequence seen.
 *
 * The *largest* rather than the last, because the transports are allowed to
 * deliver in order but this value is what a reconnect asks the server to resume
 * from, and a cursor that went backwards would replay — or worse, silently
 * re-deliver — alerts an analyst has already judged.
 */
export function cursorOf(
  frames: readonly RealtimeFrame[],
  after: number | null = null,
): number | null {
  let cursor = after;
  for (const frame of frames) {
    if (frame.type !== 'alert') continue;
    cursor = cursor === null ? frame.sequence : Math.max(cursor, frame.sequence);
  }
  return cursor;
}

/** What a close code means for the reconnect decision. */
export type CloseVerdict = 'terminal' | 'transient';

/** The app-specific close codes `stream.py` refuses a handshake with. */
export const CLOSE_UNAUTHENTICATED = 4401;
export const CLOSE_FORBIDDEN = 4403;

/**
 * Whether a close should end the connection for good.
 *
 * 4401 and 4403 are the server saying "not you" — no amount of waiting changes
 * that, so the client stops, shows the banner and waits for a credential. Every
 * other close, including 1013 ("try again later", which is what a dropped slow
 * consumer gets) is transient, and a clean 1000 is treated as transient too: the
 * server closing *without* a reason is exactly the case where a client's guess
 * must be "try again" rather than "give up".
 */
export function closeVerdict(code: number): CloseVerdict {
  return code === CLOSE_UNAUTHENTICATED || code === CLOSE_FORBIDDEN ? 'terminal' : 'transient';
}

/** A close code's reason, in words an operator can act on (R-58: no payload). */
export function closeDetail(code: number): string {
  if (code === CLOSE_UNAUTHENTICATED) return 'The session is not authenticated';
  if (code === CLOSE_FORBIDDEN) return 'This account may not read alerts';
  if (code === 1013) return 'The server dropped a slow reader';
  return `The connection closed (${String(code)})`;
}

/**
 * How the shell's three-state indicator reads a four-state client.
 *
 * The client needs `connecting` as a state of its own — an opening socket is not
 * the same claim as a broken one — while the indicator design.md §6 specifies
 * carries three states. The mapping is the honest one: opening is *degraded*
 * (nothing is lost yet), and both "the socket is down" and "the session was
 * refused" are *disconnected* (the banner carries the difference, because the
 * difference is what the analyst has to act on).
 */
export type ShellConnectionState = 'live' | 'degraded' | 'disconnected';

export function connectionStateOf(state: RealtimeState): ShellConnectionState {
  if (state === 'live') return 'live';
  if (state === 'connecting') return 'degraded';
  return 'disconnected';
}

/**
 * §8.1's stale treatment: `last update 2 m ago`.
 *
 * The age of the last frame from either transport — the last moment the server
 * spoke to this tab. Seconds until a minute, then minutes, then hours: a header
 * has room for one short phrase, and "last update 2 m ago" is what the design
 * asks for, not "last update 0.0333 h ago". A missing timestamp says `no update
 * yet` rather than inventing one, because a zero would read as "just now".
 */
export function stalenessLabel(lastUpdateAt: number | null, now: number): string {
  if (lastUpdateAt === null) return 'no update yet';
  const seconds = Math.max(0, Math.round((now - lastUpdateAt) / 1_000));
  if (seconds < 60) return `last update ${String(seconds)} s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `last update ${String(minutes)} m ago`;
  const hours = Math.round(minutes / 60);
  return `last update ${String(hours)} h ago`;
}
