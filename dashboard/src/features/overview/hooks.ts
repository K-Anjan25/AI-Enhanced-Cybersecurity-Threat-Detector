/**
 * The overview's data wiring: what is polled, how often, and when it stops.
 *
 * Two rules from design.md §4.1 are implemented here rather than in the panels,
 * because both are properties of the *polling*, not of a rendering:
 *
 *   * **"Auto-refresh 5 s for KPI tiles; charts refresh 15 s."** The tiles and the
 *     chart read the same alert window, so polling it at both cadences would fetch
 *     the same pages twice for no new information. The window therefore polls at
 *     the chart's cadence and the 5 s cadence belongs to the metrics scrape, which
 *     is one small text document — the pipeline's numbers are what changes fast
 *     enough for 5 s to matter. The deviation is recorded in D-060.
 *   * **"Both pause when the tab is hidden."** `refetchInterval` is `false` while
 *     the document is hidden, so a dashboard left open overnight is not a client
 *     hammering the API from a background tab.
 */
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import {
  fetchAlertWindow,
  fetchMetrics,
  fetchReadiness,
  type AlertWindow,
  type Readiness,
} from './api';
import type { MetricsSnapshot } from './pipeline';

/** design.md §4.1's KPI cadence. */
export const KPI_REFRESH_MS = 5_000;

/** design.md §4.1's chart cadence. */
export const CHART_REFRESH_MS = 15_000;

export type RangeKey = '1h' | '24h' | '7d';

export interface RangeSpec {
  key: RangeKey;
  /** What the operator sees in the selector. */
  label: string;
  spanMs: number;
  /** How many buckets the series is divided into. */
  buckets: number;
}

/**
 * The three windows. The bucket counts are chosen so each bucket is a round
 * interval (5 min, 1 h, 6 h) — a chart whose columns are 37 minutes wide is a chart
 * nobody can read a time off.
 */
export const RANGES: readonly RangeSpec[] = [
  { key: '1h', label: 'Last 1 h', spanMs: 3_600_000, buckets: 12 },
  { key: '24h', label: 'Last 24 h', spanMs: 86_400_000, buckets: 24 },
  { key: '7d', label: 'Last 7 d', spanMs: 604_800_000, buckets: 28 },
];

export function rangeSpec(key: RangeKey): RangeSpec {
  const spec = RANGES.find((candidate) => candidate.key === key);
  if (spec === undefined) throw new RangeError(`unknown range ${key}`);
  return spec;
}

/** Whether the tab is visible, for pausing the polls. */
export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');

  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  return visible;
}

/**
 * A clock that ticks, for the "last update" age.
 *
 * Without it the age would be computed once and then freeze — the exact failure
 * §8.1's stale state exists to prevent, since a frozen age looks like a live
 * screen that simply has not changed.
 */
export function useNow(intervalMs = 1_000, enabled = true): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!enabled) return undefined;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, enabled]);

  return now;
}

/** The previous value of something, for differencing two samples. */
export function usePrevious<T>(value: T | undefined): T | undefined {
  const previous = useRef<T | undefined>(undefined);
  const current = useRef<T | undefined>(undefined);

  useEffect(() => {
    if (value !== current.current) {
      previous.current = current.current;
      current.current = value;
    }
  }, [value]);

  return previous.current;
}

/** Whether the operator asked for less motion (§8.2). */
export function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)';
  const [reduced, setReduced] = useState(
    () => typeof window.matchMedia === 'function' && window.matchMedia(query).matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

/**
 * The alert window the page aggregates.
 *
 * `placeholderData` keeps the previous window on screen while the next one loads,
 * so a 15 s poll does not blank the chart and re-lay it out — the flicker that
 * makes a dashboard feel broken.
 */
export function useAlertWindow(
  range: RangeSpec,
  enabled: boolean,
): UseQueryResult<AlertWindow, Error> {
  return useQuery({
    queryKey: ['overview', 'alerts', range.key],
    queryFn: ({ signal }) =>
      fetchAlertWindow({
        start: new Date(Date.now() - range.spanMs),
        end: new Date(),
        signal,
      }),
    refetchInterval: enabled ? CHART_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/** The metrics scrape the pipeline strip reads. */
export function useMetrics(enabled: boolean): UseQueryResult<MetricsSnapshot, Error> {
  return useQuery({
    queryKey: ['overview', 'metrics'],
    queryFn: ({ signal }) => fetchMetrics(signal),
    refetchInterval: enabled ? KPI_REFRESH_MS : false,
  });
}

/** The readiness probes. */
export function useReadiness(enabled: boolean): UseQueryResult<Readiness, Error> {
  return useQuery({
    queryKey: ['overview', 'readiness'],
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: enabled ? CHART_REFRESH_MS : false,
  });
}
