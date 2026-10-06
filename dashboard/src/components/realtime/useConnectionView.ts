/**
 * The words the shell shows about the connection.
 *
 * Everything a screen has to say about the stream is derived here, once: the
 * indicator's three states, §8.1's stale age ("if live data stops arriving, show
 * `last update 2 m ago` in the header, rather than silently showing old numbers"),
 * and the banner's two sentences. The alternative — the shell deciding and the
 * banner deciding — is how a header ends up saying "Live" under a banner saying
 * the stream is down.
 *
 * Derived rather than stored, because an age is a function of the clock: it has to
 * keep ticking while the screen is stale. A frozen age looks exactly like a live
 * screen that has not changed.
 */
import { useMemo } from 'react';

import { useNow } from '../hooks/polling';
import { useOptionalRealtime } from './RealtimeProvider';
import {
  connectionStateOf,
  FALLBACK_POLL_MS,
  stalenessLabel,
  type ShellConnectionState,
} from '../../lib/realtime';

export interface ConnectionView {
  /** What the header indicator shows. */
  state: ShellConnectionState;
  /** What it says beside the label: the age of the last frame, when not live. */
  detail: string | undefined;
  /** The banner, or `null` when there is nothing to announce. */
  banner: { message: string; explanation: string } | null;
  /** The banner's Retry action, when one is offered. */
  retryNow: (() => void) | undefined;
}

/**
 * Build the shell's connection view.
 *
 * `override` exists for the presentational shell: a test or a story can say
 * "pretend the stream is down" without a socket, and gets the same banner an
 * outage would produce.
 */
export function useConnectionView(override?: ShellConnectionState): ConnectionView {
  const realtime = useOptionalRealtime();
  const state: ShellConnectionState = override ?? connectionStateOf(realtime?.state ?? 'live');

  // The clock only ticks while the screen is stale: a live header has nothing to
  // age, and re-rendering the whole shell every second to say "Live" is a cost
  // paid for no information.
  const now = useNow(1_000, state !== 'live');
  const lastUpdateAt = realtime?.lastUpdateAt ?? null;

  return useMemo<ConnectionView>(() => {
    const age = stalenessLabel(lastUpdateAt, now);
    const seconds = FALLBACK_POLL_MS / 1_000;

    if (state === 'live') {
      return { state, detail: undefined, banner: null, retryNow: undefined };
    }

    if (state === 'degraded') {
      return {
        state,
        detail: realtime === null ? undefined : age,
        banner: {
          message: 'Connecting to the live alert stream',
          explanation: 'Retrying automatically; the screen keeps showing the last data it read.',
        },
        retryNow: realtime?.retryNow,
      };
    }

    // Two different failures, one treatment, and the banner says which: a refused
    // handshake will not be fixed by waiting (the credential is the problem), and
    // the fallback is still running either way.
    const why = realtime?.detail ?? 'The live channel is not available';
    return {
      state,
      detail: realtime === null ? undefined : age,
      banner: {
        message: 'Live updates are off',
        explanation: `${why}. Showing the API's data and polling every ${String(seconds)} s.`,
      },
      retryNow: realtime?.retryNow,
    };
  }, [state, now, lastUpdateAt, realtime]);
}
