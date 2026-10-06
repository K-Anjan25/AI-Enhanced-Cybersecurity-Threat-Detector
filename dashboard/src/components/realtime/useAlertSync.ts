/**
 * Live updates for a screen that holds server state in React Query.
 *
 * The rule this hook exists to implement is one sentence: **a pushed alert is a
 * reason to re-read, not a second copy of the data.** The browser already has a
 * cache, a window and a cursor for alerts; the moment a stream also *writes* rows
 * into component state there are two lists that can disagree, and the one on
 * screen is the one nobody can trace. So a frame — from the socket, from a
 * replay, or from the 15 s REST fallback — invalidates the caller's queries and
 * the API stays the single source of truth (architecture.md §10: "No detection
 * logic in the browser"; R-24: server state is React Query's).
 *
 * Three occasions, and each is a different fact:
 *
 *   * **An alert arrived** — live or polled, possibly a burst after a reconnect.
 *     Coalesced: a replay of fifty alerts is one re-read, not fifty.
 *   * **A resync was required** — the server's buffer no longer held the whole
 *     gap, so the frames alone are not the full story and the window must be
 *     re-read even if nothing arrived.
 *   * **The connection came back** — we may have missed frames while it was gone
 *     (a backoff, a closed tab), and re-reading costs one request.
 *
 * The caller names its own query keys. That is why this takes `roots` rather than
 * knowing them: a shared component may not reach into a feature, and a shared
 * hook that hard-coded `['triage', 'queue']` would be exactly that reach, spelled
 * differently.
 */
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useDocumentVisible } from '../hooks/polling';
import { useAlertFeed, useOptionalRealtime } from './RealtimeProvider';

/** A query-key root, as React Query matches them: a prefix of the full key. */
export type QueryRoot = readonly unknown[];

export function useAlertSync(roots: readonly QueryRoot[]): void {
  const realtime = useOptionalRealtime();
  const queryClient = useQueryClient();
  const visible = useDocumentVisible();

  // A counter rather than a boolean: every cause is a separate reason to re-read,
  // and two causes that arrive together must still be two counts, because React
  // only re-renders when the value changes.
  const [pending, setPending] = useState(0);
  const previousState = useRef(realtime?.state ?? 'live');
  const previousResync = useRef(realtime?.resyncCount ?? 0);

  useAlertFeed(() => setPending((count) => count + 1), { coalesceMs: 250 });

  const state = realtime?.state ?? 'live';
  const resyncCount = realtime?.resyncCount ?? 0;

  // A connection that has just become live again may have missed frames while it
  // was away; there is no way to know from here, so the cheap answer is to re-read.
  useEffect(() => {
    if (previousState.current !== 'live' && state === 'live') setPending((count) => count + 1);
    previousState.current = state;
  }, [state]);

  useEffect(() => {
    if (resyncCount > previousResync.current) setPending((count) => count + 1);
    previousResync.current = resyncCount;
  }, [resyncCount]);

  useEffect(() => {
    // §4.1's pause applies here too: a hidden tab that is being streamed to has no
    // business refetching, and the count is kept rather than dropped so the read
    // happens the moment somebody looks again.
    if (pending === 0 || !visible) return;
    setPending(0);
    for (const root of roots) {
      void queryClient.invalidateQueries({ queryKey: root });
    }
  }, [pending, visible, roots, queryClient]);
}
