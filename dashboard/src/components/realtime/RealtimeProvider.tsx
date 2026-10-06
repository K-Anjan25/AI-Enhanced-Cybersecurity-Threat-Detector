/**
 * The app shell's single connection, and the pub/sub hook that fans it out.
 *
 * architecture.md §10: "A single WebSocket connection at the app shell, fanned
 * out through a pub/sub hook." Both halves of that sentence are structural here:
 *
 *   * **One connection.** `AlertStreamClient` is created once, in a ref, and
 *     started once on mount. A provider per screen would open a socket per
 *     screen, and the hub's per-subscriber buffer is not free — the reason the
 *     rule exists is that N screens watching the stream should be one
 *     subscription, not N.
 *   * **Fanned out.** Subscribers register a callback and frames are dispatched
 *     to them directly; nothing subscribes by mounting a component per alert.
 *
 * The React state here is exactly the three things a render depends on: the
 * connection state, the words that explain it, and the moment of the last frame
 * (§8.1's "last update 2 m ago"). Alerts themselves are not state — they are
 * dispatched to whoever asked for them, and screens re-read the API (`useAlertSync`)
 * rather than accumulating a second copy of the alert list in the browser.
 *
 * The provider is optional by design: `useOptionalRealtime` returns `null` outside
 * it, so a component that *can* show live state renders a sensible default in a
 * test or a story that never mounted a socket, instead of throwing. Screens that
 * opt into live updates do so through hooks that no-op when there is no provider.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { AlertStreamClient, type SocketFactory, type StreamOptions } from '../../api/realtime';
import { onSessionTokenChange } from '../../api/session';
import { useDocumentVisible } from '../hooks/polling';
import type { AlertFrame, RealtimeFrame, RealtimeState } from '../../lib/realtime';

/** What a subscriber passes to `useAlertFeed`. */
export interface FeedOptions {
  /**
   * How long to coalesce a burst into one call, in milliseconds.
   *
   * A reconnect replays everything the server still holds, and a page that was
   * closed for an hour can arrive as one frame per alert. A consumer whose job is
   * "re-read the window" needs that to be one read, not fifty. Zero — the default
   * — delivers each alert as it arrives, which is what a live list wants.
   */
  coalesceMs?: number;
}

type AlertListener = (frames: AlertFrame[]) => void;

export interface RealtimeContextValue {
  state: RealtimeState;
  /** Why the state is what it is, in words a banner can show. Null when live. */
  detail: string | null;
  /** When a frame last arrived, for §8.1's "last update 2 m ago". */
  lastUpdateAt: number | null;
  /**
   * How many `ready` frames have reported an incomplete gap.
   *
   * A counter rather than a boolean so a consumer can react to *each* one: two
   * resyncs in ten minutes are two windows that need re-reading, and a flag that
   * was already true would swallow the second.
   */
  resyncCount: number;
  /** Register a listener for alert frames. Returns the unsubscribe. */
  subscribeToAlerts: (listener: AlertListener) => () => void;
  /** The resume position: the last sequence dispatched to subscribers. */
  cursor: number | null;
  /** Ask the client to reconnect now, ignoring the backoff. */
  retryNow: () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export interface RealtimeProviderProps {
  children: ReactNode;
  /** Injections for tests; production passes nothing and gets the real things. */
  socketFactory?: SocketFactory | undefined;
  options?: Partial<Omit<StreamOptions, 'onFrame' | 'onState'>> | undefined;
}

export function RealtimeProvider({ children, socketFactory, options }: RealtimeProviderProps) {
  const [state, setState] = useState<RealtimeState>('connecting');
  const [detail, setDetail] = useState<string | null>(null);
  const [lastUpdateAt, setLastUpdateAt] = useState<number | null>(null);
  const [resyncCount, setResyncCount] = useState(0);
  const [cursor, setCursor] = useState<number | null>(null);
  const listeners = useRef(new Set<AlertListener>());

  // The client is created once, in a ref: it is not render output, and a client
  // recreated by a double render would be a second socket.
  const clientRef = useRef<AlertStreamClient | null>(null);
  if (clientRef.current === null) {
    clientRef.current = new AlertStreamClient({
      ...options,
      ...(socketFactory === undefined ? {} : { socketFactory }),
      onFrame: (frame: RealtimeFrame) => {
        setLastUpdateAt(Date.now());
        if (frame.type === 'ready' && frame.resync_required) setResyncCount((count) => count + 1);
        if (frame.type !== 'alert') return;
        for (const listener of listeners.current) listener([frame]);
      },
      onState: (next: RealtimeState, nextDetail: string | null) => {
        setState(next);
        setDetail(nextDetail);
        setCursor(clientRef.current?.currentCursor ?? null);
      },
    });
  }

  useEffect(() => {
    const client = clientRef.current;
    if (client === null) return undefined;
    client.start();
    const unsubscribe = onSessionTokenChange(() => {
      client.onTokenChanged();
    });
    return () => {
      unsubscribe();
      client.stop();
    };
  }, []);

  // §4.1: a refresh nobody can see is a refresh nobody asked for. The socket stays
  // open — the server pushes, so a hidden tab costs one idle connection, not a
  // request per interval — and only the fallback poll pauses.
  const visible = useDocumentVisible();
  useEffect(() => {
    clientRef.current?.setPaused(!visible);
  }, [visible]);

  const subscribeToAlerts = useCallback((listener: AlertListener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  const retryNow = useCallback(() => {
    clientRef.current?.retryNow();
  }, []);

  const value = useMemo<RealtimeContextValue>(
    () => ({ state, detail, lastUpdateAt, resyncCount, cursor, subscribeToAlerts, retryNow }),
    [state, detail, lastUpdateAt, resyncCount, cursor, subscribeToAlerts, retryNow],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

/**
 * The connection's state, or `null` when nothing mounted a provider.
 *
 * The null is the point: the shell and the alert screens are usable — and
 * testable — without a socket, and a component deciding how much to say about the
 * connection must be able to tell "no live layer here" from "live layer, live
 * connection". `useRealtime` is the strict version, for code that is only
 * meaningful with a connection.
 */
export function useOptionalRealtime(): RealtimeContextValue | null {
  return useContext(RealtimeContext);
}

/** The connection's state, for the shell's indicator and banner. */
export function useRealtime(): RealtimeContextValue {
  const value = useContext(RealtimeContext);
  if (value === null) {
    throw new Error('useRealtime must be used inside RealtimeProvider');
  }
  return value;
}

/**
 * Subscribe to pushed alerts.
 *
 * With `coalesceMs` set, a burst arrives as one call carrying every frame in the
 * burst, in order — the caller gets the alerts either way, so coalescing changes
 * how often it is woken, never what it is told.
 *
 * Outside a provider this does nothing at all. That is deliberate: a screen that
 * reads the API through React Query is *complete* without live updates, so a test
 * that mounts it alone must not have to build a socket to render it.
 *
 * The handler is held in a ref, so an inline arrow — which is every caller — does
 * not resubscribe on every render.
 */
export function useAlertFeed(
  handler: (frames: AlertFrame[]) => void,
  options: FeedOptions = {},
): void {
  const realtime = useOptionalRealtime();
  const subscribeToAlerts = realtime?.subscribeToAlerts;
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const coalesceMs = options.coalesceMs ?? 0;

  useEffect(() => {
    if (subscribeToAlerts === undefined) return undefined;
    let timer: number | null = null;
    let pending: AlertFrame[] = [];

    const listener: AlertListener = (frames) => {
      if (coalesceMs <= 0) {
        handlerRef.current(frames);
        return;
      }
      pending = [...pending, ...frames];
      if (timer !== null) return;
      timer = window.setTimeout(() => {
        timer = null;
        const batch = pending;
        pending = [];
        handlerRef.current(batch);
      }, coalesceMs);
    };

    const unsubscribe = subscribeToAlerts(listener);
    return () => {
      unsubscribe();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [subscribeToAlerts, coalesceMs]);
}
