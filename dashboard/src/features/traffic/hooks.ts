/**
 * The traffic explorer's data wiring.
 *
 * Three decisions, each borrowed from a screen that already made it, because two
 * screens answering "when do we re-read?" differently is a bug waiting for a
 * reviewer to notice:
 *
 *   * **A 15 s poll while the tab is visible** (design.md §4.1's chart cadence,
 *     the same `CHART_REFRESH_MS` the overview uses) and nothing at all in a hidden
 *     tab.
 *   * **Pushed alerts re-read the window** (T-405): the traffic view is derived from
 *     the alert stream's own data, so a frame invalidates this query too — including
 *     the frames the REST fallback delivers once the socket is down.
 *   * **`placeholderData` keeps the previous window on screen** while the next one
 *     loads, so a 15 s refresh does not blank the series and re-lay the graph — the
 *     flicker that makes a dashboard feel broken (T-403's reason, unchanged).
 *
 * The brush, the filters and the pin are **not** query keys: they are view state, and
 * a brush that refetched would turn a drag into a request per pixel. They are applied
 * to the rows the query already returned, in `view.ts`.
 */
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { useDocumentVisible } from '../../components/hooks/polling';
import { useAlertSync } from '../../components/realtime/useAlertSync';
import { fetchTrafficWindow, type AlertWindow } from './api';
import type { TrafficFilters } from './view';

/** design.md §4.1's chart cadence — the same 15 s the overview polls at. */
export const TRAFFIC_REFRESH_MS = 15_000;

/** The range options the page offers. */
export type TrafficRangeKey = '1h' | '24h' | '7d';

export interface TrafficRange {
  key: TrafficRangeKey;
  label: string;
  spanMs: number;
}

export const TRAFFIC_RANGES: readonly TrafficRange[] = [
  { key: '1h', label: 'Last 1 h', spanMs: 3_600_000 },
  { key: '24h', label: 'Last 24 h', spanMs: 86_400_000 },
  { key: '7d', label: 'Last 7 d', spanMs: 604_800_000 },
];

export function rangeOf(key: TrafficRangeKey): TrafficRange {
  return TRAFFIC_RANGES.find((range) => range.key === key) ?? (TRAFFIC_RANGES[1] as TrafficRange);
}

const TRAFFIC_ROOTS = [['traffic', 'window']] as const;

/** The window, refreshed while the tab is visible and on every pushed alert. */
export function useTrafficWindow(
  range: TrafficRange,
  severity: TrafficFilters['severity'],
  enabled = true,
): UseQueryResult<AlertWindow, Error> {
  useAlertSync(TRAFFIC_ROOTS);
  return useQuery({
    queryKey: ['traffic', 'window', range.key, severity],
    queryFn: ({ signal }) =>
      fetchTrafficWindow({
        start: new Date(Date.now() - range.spanMs),
        end: new Date(),
        severity,
        signal,
      }),
    refetchInterval: enabled ? TRAFFIC_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/** Whether the screen should be polling at all. Re-exported for the page. */
export function useTrafficVisible(): boolean {
  return useDocumentVisible();
}
