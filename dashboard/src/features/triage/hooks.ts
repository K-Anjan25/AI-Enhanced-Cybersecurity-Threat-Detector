/**
 * The triage screen's data wiring.
 *
 * Three things here are decisions rather than plumbing:
 *
 *   * **The queue and the detail both refresh, and both stop when the tab is
 *     hidden.** An analyst's screen is a live queue: an alert that arrived a minute
 *     ago should appear, and a verdict someone else recorded should show up in the
 *     bar. §4.1's "pause when the tab is hidden" applies for the same reason it
 *     does on the overview — a background tab is not an operator.
 *   * **The keyboard verdict is a mutation with a settled answer.** After it
 *     resolves, both the detail and the queue are invalidated: the bar has to show
 *     the new verdict, and the row in the list has to stop looking unjudged. A
 *     mutation that only updated local state would leave the two disagreeing.
 *   * **A pushed alert is a reason to re-read, not a second list.** Both the queue
 *     and the open detail subscribe to the stream (T-405) and invalidate on a
 *     frame, so an alert that arrives over the socket — or over the 15 s REST
 *     fallback once the socket is down — appears without waiting for the next
 *     interval, and there is still exactly one copy of the data (the cache).
 *   * **`unchanged` is not an error.** The API answers `unchanged` when the same
 *     analyst re-sends the verdict already current, and the screen says so rather
 *     than claiming a write that did not happen.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useCallback, useEffect, useMemo } from 'react';

import { useDocumentVisible } from '../../components/hooks/polling';
import { useAlertSync } from '../../components/realtime/useAlertSync';
import { ApiError } from '../../api/client';
import { fetchAlertDetail, fetchQueue, recordVerdict, QUEUE_LIMIT, QUEUE_WINDOW_MS } from './api';
import type { AlertDetail } from './types';
import type { VerdictName } from './verdicts';
import type { AlertPage } from '../../api/alerts';

/** The triage screen's cadence. A queue is not a chart; 15 s is fast enough. */
export const TRIAGE_REFRESH_MS = 15_000;

/** The queue keys, so a mutation can invalidate exactly what it changed. */
export const queueKey = ['triage', 'queue'] as const;

export function detailKey(alertId: number, createdAt: string) {
  return ['triage', 'detail', alertId, createdAt] as const;
}

// Module-level constants, not literals at the call site: `useAlertSync` takes its
// roots as a dependency, and a fresh array every render would re-run its effect
// for no reason on every render.
const QUEUE_ROOTS = [queueKey] as const;

/** The newest alerts in the window, refreshed while the tab is visible. */
export function useQueue(enabled = true): UseQueryResult<AlertPage, Error> {
  useAlertSync(QUEUE_ROOTS);
  return useQuery({
    queryKey: queueKey,
    queryFn: ({ signal }) =>
      fetchQueue({
        start: new Date(Date.now() - QUEUE_WINDOW_MS),
        end: new Date(),
        limit: QUEUE_LIMIT,
        signal,
      }),
    refetchInterval: enabled ? TRIAGE_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/**
 * One alert's detail.
 *
 * `enabled` is false until a route names an alert *and* its partition key: without
 * `created_at` there is no row to ask for, and a query that fired anyway would be a
 * 400 the screen had to explain away.
 */
export function useAlertDetail(
  alertId: number | null,
  createdAt: string | null,
  enabled = true,
): UseQueryResult<AlertDetail, Error> {
  // The root is this alert's own key, so a frame for *any* alert re-reads the open
  // detail only when the screen is showing something related — and since the
  // detail includes the family's history and the window around it, a neighbour's
  // alert frequently is related.
  const roots = useMemo<readonly (readonly unknown[])[]>(
    () => [[...detailKey(alertId ?? 0, createdAt ?? '')]],
    [alertId, createdAt],
  );
  useAlertSync(roots);
  return useQuery({
    queryKey: detailKey(alertId ?? 0, createdAt ?? ''),
    queryFn: ({ signal }) => {
      if (alertId === null || createdAt === null) {
        throw new Error('an alert detail needs both halves of its key');
      }
      return fetchAlertDetail({ alertId, createdAt, signal });
    },
    enabled: enabled && alertId !== null && createdAt !== null,
    refetchInterval: enabled ? TRIAGE_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

export interface VerdictSelection {
  alertId: number;
  createdAt: string;
  verdict: VerdictName;
}

/**
 * What the analyst's keypress produced, for the live region to announce.
 */
export function verdictOutcomeMessage(outcome: {
  action: 'recorded' | 'unchanged';
  record: { verdict: string };
  superseded: { verdict: string } | null;
}): string {
  const label = outcome.record.verdict.replace(/_/g, ' ');
  if (outcome.action === 'unchanged') return `${label} was already the current verdict.`;
  return outcome.superseded === null
    ? `Verdict recorded: ${label}.`
    : `Verdict recorded: ${label}, superseding ${outcome.superseded.verdict.replace(/_/g, ' ')}.`;
}

/** The message a failed verdict write may put on screen (R-58: no URL, no body). */
export function verdictFailureMessage(error: unknown): string {
  if (error instanceof ApiError && error.failure === 'status' && error.status === 403) {
    return 'Your role may not record verdicts.';
  }
  if (error instanceof ApiError && error.failure === 'timeout') {
    return 'The verdict was not recorded: the request timed out.';
  }
  return 'The verdict was not recorded: the service could not be reached.';
}

/** Record a verdict, then refetch the detail and the queue that it changed. */
export function useRecordVerdict(): UseMutationResult<
  Awaited<ReturnType<typeof recordVerdict>>,
  Error,
  VerdictSelection
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (selection: VerdictSelection) =>
      recordVerdict({
        alertId: selection.alertId,
        createdAt: selection.createdAt,
        verdict: selection.verdict,
      }),
    onSuccess: async (_outcome, selection) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: detailKey(selection.alertId, selection.createdAt) }),
        client.invalidateQueries({ queryKey: queueKey }),
      ]);
    },
  });
}

/** Whether the triage screen should be polling at all. */
export function useTriageVisible(): boolean {
  return useDocumentVisible();
}

/**
 * The `1`/`2`/`3` shortcuts.
 *
 * Three rules, and each one is the difference between a shortcut and a bug:
 *
 *   * **A repeat is ignored.** Holding a key must not write the same verdict
 *     dozens of times; the API would answer `unchanged` for the repeat, but the
 *     audit trail and the analyst's trust are better served by not asking.
 *   * **A modified keystroke is not a shortcut.** Cmd-1, Ctrl-1 and Alt-1 belong to
 *     the browser and the OS.
 *   * **Typing is not a verdict.** A keypress that lands in an input, a textarea,
 *     a select or a contenteditable region is that control's, not this screen's —
 *     this is the bug that makes a shortcut dangerous once a note field exists.
 */
export function useVerdictShortcuts(
  onVerdict: (verdict: VerdictName) => void,
  enabled: boolean,
  resolve: (key: string) => VerdictName | null,
): void {
  const handler = useCallback(
    (event: KeyboardEvent) => {
      if (!enabled || event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest('input, textarea, select, [contenteditable]')
      ) {
        return;
      }
      const verdict = resolve(event.key);
      if (verdict === null) return;
      event.preventDefault();
      onVerdict(verdict);
    },
    [enabled, onVerdict, resolve],
  );

  useEffect(() => {
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handler]);
}
