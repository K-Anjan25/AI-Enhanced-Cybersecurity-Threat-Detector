/**
 * The overview's data wiring: what is polled, how often, and when it stops.
 *
 * Two rules from design.md §4.1 are implemented here rather than in the panels,
 * because both are properties of the *polling*, not of a rendering:
 *
 *   * **"Auto-refresh 5 s for KPI tiles; charts refresh 15 s."** The tiles and the
 *     chart read the same window, so polling the aggregate at both cadences would
 *     ask the server the same question twice for no new information. The aggregate
 *     therefore polls at the chart's cadence and the 5 s cadence belongs to the
 *     metrics scrape, which is one small text document — the pipeline's numbers are
 *     what changes fast enough for 5 s to matter. The deviation is recorded in
 *     D-060, and T-416 kept it: one request now answers the tiles *and* the chart.
 *   * **A pushed alert refreshes the window, and the window still polls.** T-405's
 *     stream invalidates the aggregate when a frame arrives — including the frames
 *     the 15 s REST fallback delivers once the socket is down — so the chart is
 *     never a whole interval behind an alert the header already knew about. The polls stay: a stream can be down for reasons the browser cannot
 *     see, and a screen must not go stale because a socket looks open.
 *   * **"Both pause when the tab is hidden."** `refetchInterval` is `false` while
 *     the document is hidden, so a dashboard left open overnight is not a client
 *     hammering the API from a background tab.
 */
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { fetchMetrics } from '../../api/metrics';
import { fetchOverview, fetchReadiness, type Overview, type Readiness } from './api';
import { useAlertSync } from '../../components/realtime/useAlertSync';
import type { MetricsSnapshot } from './pipeline';

// The polling hooks are shared with the triage screen (T-404), so they live in the
// components layer; re-exported here because this is where the overview reads them.
export { useDocumentVisible, useNow } from '../../components/hooks/polling';

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
  /** The width the API should bucket the series at, in whole minutes. */
  bucketMinutes: number;
}

/**
 * The three windows. The bucket counts are chosen so each bucket is a round
 * interval (5 min, 1 h, 6 h) — a chart whose columns are 37 minutes wide is a chart
 * nobody can read a time off.
 */
export const RANGES: readonly RangeSpec[] = [
  { key: '1h', label: 'Last 1 h', spanMs: 3_600_000, buckets: 12, bucketMinutes: 5 },
  { key: '24h', label: 'Last 24 h', spanMs: 86_400_000, buckets: 24, bucketMinutes: 60 },
  { key: '7d', label: 'Last 7 d', spanMs: 604_800_000, buckets: 28, bucketMinutes: 360 },
];

/**
 * How many entities the overview asks for: the five design.md §4.1 draws.
 *
 * A cap on a list, never on a count -- the response says whether the window held
 * more than this (`entities_capped`), and the panel says so when it did.
 */
export const ENTITY_LIMIT = 5;

export function rangeSpec(key: RangeKey): RangeSpec {
  const spec = RANGES.find((candidate) => candidate.key === key);
  if (spec === undefined) throw new RangeError(`unknown range ${key}`);
  return spec;
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

const AGGREGATE_ROOTS = [['overview', 'aggregate']] as const;

/**
 * The window's aggregate: the tiles, the series, the entities and the mix.
 *
 * One request (T-416). The previous implementation walked pages of
 * `GET /api/v1/alerts` and counted them client-side, which is why the page used to
 * say "partial coverage" past the walk's cap and why three panels could disagree
 * about the same window. `placeholderData` still keeps the previous window on
 * screen while the next one loads, so a 15 s poll does not blank the chart and
 * re-lay it out — the flicker that makes a dashboard feel broken.
 */
export function useOverviewWindow(
  range: RangeSpec,
  enabled: boolean,
): UseQueryResult<Overview, Error> {
  // Pushed alerts refresh the aggregate (T-405). Only this query: the metrics
  // scrape and the readiness probes are about the pipeline, not about this data, so
  // a new alert is not a reason to re-scrape them.
  useAlertSync(AGGREGATE_ROOTS);
  return useQuery({
    queryKey: ['overview', 'aggregate', range.key],
    queryFn: ({ signal }) =>
      fetchOverview({
        start: new Date(Date.now() - range.spanMs),
        end: new Date(),
        bucketMinutes: range.bucketMinutes,
        entityLimit: ENTITY_LIMIT,
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
