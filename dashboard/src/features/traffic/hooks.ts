/**
 * The traffic explorer's data wiring (T-418).
 *
 * Two queries, because the screen now has two windows when a brush is set — and the
 * reason is the one the whole feature changed for:
 *
 *   * **`useTrafficWindow`** reads the selected range and draws the series. It is also
 *     the query behind the panels when no brush is set.
 *   * **`useTrafficBrush`** reads the *brushed* sub-window and is what the table and the
 *     graph describe once the analyst draws a selection. It is disabled with no brush,
 *     so an unbrushed screen makes one request rather than two.
 *
 * Why re-read instead of filtering in the browser: the API returns the window's **top**
 * addresses and relationships. Narrowing that list to a sub-window would leave out the
 * addresses the sub-window's own top-N should have contained, so "brushing filters
 * everything below" would be false in exactly the case it matters. A read per committed
 * brush is one request per *selection*, not per pixel of a drag — the brush is view
 * state until it is committed, and the drag itself never queries.
 *
 * The rest is borrowed from a screen that already made the decision, because two screens
 * answering "when do we re-read?" differently is a bug waiting for a reviewer:
 *
 *   * **A 15 s poll while the tab is visible** (design.md §4.1's chart cadence, the same
 *     `CHART_REFRESH_MS` the overview uses) and nothing at all in a hidden tab.
 *   * **Pushed alerts re-read both windows** (T-405): the score overlay and the alert
 *     counts come from the alert side, so an alert frame invalidates these queries too —
 *     including the frames the REST fallback delivers once the socket is down.
 *   * **`placeholderData` keeps the previous window on screen** while the next one loads,
 *     so a 15 s refresh does not blank the series and re-lay the graph — the flicker that
 *     makes a dashboard feel broken (T-403's reason, unchanged). A brushed read keeps the
 *     unbrushed one on screen for the same reason: the selection the analyst just drew
 *     should not blink.
 */
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query';

import { useDocumentVisible } from '../../components/hooks/polling';
import { useAlertSync } from '../../components/realtime/useAlertSync';
import type { FlowAggregate } from '../../api/flows';
import { fetchTrafficWindow, type TrafficRequest } from './api';
import { BUCKET_MINUTES, type TrafficFilters } from './view';

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

/**
 * The query roots a pushed alert re-reads: **both** windows.
 *
 * The panels describe the brushed window when there is one, and their alert counts,
 * severities and peak score come from the alert side — the same reason the series
 * carries a score overlay. A single root was enough while the brush filtered a list
 * in the browser; since T-418 the brushed window is read from the server like the
 * series, and a frame for a new alert left the table and the graph showing the
 * previous counts until their own poll came round.
 */
const TRAFFIC_ROOTS = [
  ['traffic', 'window'],
  ['traffic', 'brush'],
] as const;

/**
 * The request for one window, from the range, the controls and the clock.
 *
 * Exported because both queries build theirs from the same rule, and a second copy of
 * "which filters are read-level" is a copy that can disagree: `protocol` and `direction`
 * narrow the read (the read model filters by dimension), while the thresholds below are
 * applied to what came back.
 */
export function trafficRequest(
  range: TrafficRange,
  filters: TrafficFilters,
  now: number = Date.now(),
): TrafficRequest {
  return {
    start: new Date(now - range.spanMs),
    end: new Date(now),
    bucketMinutes: BUCKET_MINUTES[range.key],
    protocol: filters.protocol === 'all' ? undefined : filters.protocol,
    direction: filters.direction === 'all' ? undefined : filters.direction,
  };
}

/** The window, refreshed while the tab is visible and on every pushed alert. */
export function useTrafficWindow(
  range: TrafficRange,
  filters: TrafficFilters,
  enabled = true,
): UseQueryResult<FlowAggregate, Error> {
  useAlertSync(TRAFFIC_ROOTS);
  return useQuery({
    queryKey: ['traffic', 'window', range.key, filters.protocol, filters.direction],
    queryFn: ({ signal }) => fetchTrafficWindow({ ...trafficRequest(range, filters), signal }),
    refetchInterval: enabled ? TRAFFIC_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/**
 * The brushed window: what the table and the graph describe once a selection is drawn.
 *
 * `enabled` is false with no brush, so an unbrushed screen pays nothing for this hook.
 * `from`/`to` are in the key, so dragging the selection to a new range is a new read —
 * including narrowing it to one bucket, which is how the analyst asks "what was
 * happening in that five minutes".
 */
export function useTrafficBrush(
  range: TrafficRange,
  filters: TrafficFilters,
  brush: { from: number; to: number } | null,
  enabled = true,
): UseQueryResult<FlowAggregate, Error> {
  return useQuery({
    queryKey: [
      'traffic',
      'brush',
      range.key,
      filters.protocol,
      filters.direction,
      brush?.from ?? 0,
      brush?.to ?? 0,
    ],
    queryFn: ({ signal }) =>
      fetchTrafficWindow({
        ...trafficRequest(range, filters),
        start: new Date(brush?.from ?? 0),
        end: new Date(brush?.to ?? 0),
        signal,
      }),
    enabled: enabled && brush !== null,
    refetchInterval: enabled && brush !== null ? TRAFFIC_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/** Whether the screen should be polling at all. Re-exported for the page. */
export function useTrafficVisible(): boolean {
  return useDocumentVisible();
}
