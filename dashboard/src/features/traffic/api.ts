/**
 * The traffic explorer's one data source.
 *
 * `GET /api/v1/alerts` over a bounded window, walked page by page until the window
 * is exhausted or the shared cap is reached (T-305, R-34). There is no aggregate and
 * no flow endpoint to call: the aggregation happens in `aggregate.ts`, and the walk
 * reports `complete: false` when the cap stopped it rather than presenting a partial
 * window as the whole one (the rule D-060 recorded for the overview).
 *
 * The page size and the cap are the **shared** ones from `src/api/alerts.ts` — the
 * overview walks the same endpoint (T-403) and two copies of "how much will we read"
 * is two answers to a question an operator asks once.
 *
 * `severity` is passed to the API rather than applied after the read. That is not an
 * optimisation: with a cap on the walk, filtering client-side would search the first
 * 5,000 rows for a severity that may not appear in them, and a filter that silently
 * finds nothing is worse than one that takes an extra request.
 */
import { fetchAlertWindow, type AlertWindow } from '../../api/alerts';
import type { Severity } from '../../components/ui/severity';

export type { AlertWindow };

export interface TrafficRequest {
  /** Inclusive lower bound of the window (R-34). */
  start: Date;
  /** Exclusive upper bound of the window (R-34). */
  end: Date;
  /** `'all'` reads the window unfiltered; otherwise the API narrows it. */
  severity?: Severity | 'all' | undefined;
  signal?: AbortSignal | undefined;
}

/** Read the window the explorer aggregates. */
export async function fetchTrafficWindow(request: TrafficRequest): Promise<AlertWindow> {
  const severity =
    request.severity === undefined || request.severity === 'all' ? undefined : request.severity;
  return fetchAlertWindow({
    start: request.start,
    end: request.end,
    severity,
    signal: request.signal,
  });
}
