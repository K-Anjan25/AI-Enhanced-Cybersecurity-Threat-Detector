/**
 * The log tail's data wiring, and the two rules that make it a *tail*.
 *
 *   * **A 2 s poll while the tail is live and the tab is visible.** A chart can wait
 *     15 s (design.md §4.1) because its subject is a trend; a tail cannot, because
 *     its subject is the last few seconds, and a stack trace that appears a quarter
 *     of a minute late is a stack trace read from the wrong end. The read is bounded
 *     on every axis — a window, a row limit, a retention — so the cadence costs one
 *     small request. A hidden tab polls nothing (a dashboard in a background tab
 *     must not keep hitting a service nobody is watching), and the screen says how
 *     old what it is showing is (§8.1's staleness rule).
 *   * **Paused means nothing is read.** Not "read and hidden": the acceptance
 *     criterion is that pause *freezes* the view, and a frozen view that is still
 *     fetching is a view that will jump the moment it is resumed. So the page freezes
 *     the window with it — the query key stops moving — and the poll is switched off
 *     (`enabled: false`), which is also why resume is instant: the read it does is
 *     for the new window, not a re-read of the old one.
 *
 * The raw lines behind a cluster are a *look*, not a stream: they are fetched when a
 * row is opened and never on an interval, so leaving a cluster open cannot turn into
 * a request per two seconds.
 */
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { fetchLogLines, fetchLogTail, type LogLevel, type LogLines, type LogTail } from './api';
import type { LogWindow } from './cluster';

/** How often a live tail is re-read, while it is live and the tab is visible. */
export const LOG_TAIL_REFRESH_MS = 2_000;

/**
 * How often a *wide* window is re-read (T-419).
 *
 * The 2 s cadence exists because a tail's subject is the last few seconds. A 24-hour
 * window's subject is a trend, and architecture.md §14's 15 s is what a trend view
 * asks for; re-reading a day of clusters every two seconds would spend fifteen times
 * the requests to make a chart that has not visibly moved. The threshold is the tail's
 * own retention: at or below it this is a tail, above it it is an investigation.
 */
export const LOG_WIDE_REFRESH_MS = 15_000;

/** The span at or below which the read is a tail rather than a trend: 15 minutes. */
export const TAIL_CADENCE_CEILING_MS = 900_000;

/** How often to re-read a read of this span. */
export function refreshMsFor(spanMs: number): number {
  return spanMs > TAIL_CADENCE_CEILING_MS ? LOG_WIDE_REFRESH_MS : LOG_TAIL_REFRESH_MS;
}

export interface LogFilters {
  /** `'all'` reads every level; the API takes no filter at all for that. */
  level: LogLevel | 'all';
}

/** The level to send, or `undefined` for "no filter" — never the string `all`. */
export function levelParam(level: LogFilters['level']): LogLevel | undefined {
  return level === 'all' ? undefined : level;
}

/**
 * The clusters in one window.
 *
 * `placeholderData` keeps the previous window on screen while the next one loads:
 * without it a tail would blank every two seconds, which reads as a broken feed
 * rather than a live one (T-403's reason, unchanged).
 */
export function useLogTail(
  window: LogWindow,
  filters: LogFilters,
  enabled = true,
  refreshMs: number = LOG_TAIL_REFRESH_MS,
): UseQueryResult<LogTail, Error> {
  return useQuery({
    queryKey: ['logs', 'tail', window.start.toISOString(), window.end.toISOString(), filters.level],
    queryFn: ({ signal }) =>
      fetchLogTail({
        start: window.start,
        end: window.end,
        level: levelParam(filters.level),
        signal,
      }),
    enabled,
    refetchInterval: enabled ? refreshMs : false,
    placeholderData: keepPreviousData,
  });
}

/** The raw lines behind one cluster, fetched only while a row is open. */
export function useLogLines(
  window: LogWindow,
  key: string | null,
  enabled = true,
): UseQueryResult<LogLines, Error> {
  return useQuery({
    queryKey: ['logs', 'lines', key, window.start.toISOString(), window.end.toISOString()],
    queryFn: ({ signal }) =>
      fetchLogLines({
        start: window.start,
        end: window.end,
        key: key ?? undefined,
        signal,
      }),
    enabled: enabled && key !== null,
  });
}
