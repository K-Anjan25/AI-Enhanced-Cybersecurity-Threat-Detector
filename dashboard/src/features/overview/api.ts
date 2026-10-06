/**
 * The overview page's data sources.
 *
 * Four of them, and each one is a documented decision rather than a convenience:
 *
 *   * **`GET /api/v1/alerts`** (T-305) is the only alert source. Its `start`/`end`
 *     are mandatory because R-34 forbids an unbounded scan of a partitioned table,
 *     so every call here carries the window the operator selected. The row shape
 *     and the path are imported from `src/api/alerts.ts`: the triage screen reads
 *     the same endpoint (T-404), and two copies of a wire field name is one copy
 *     too many.
 *   * **Paging is explicit and bounded.** There is no aggregate endpoint yet (that
 *     gap is filed as T-416), so the overview counts rows client-side — and once
 *     the page cap is reached it reports `complete: false` rather than presenting
 *     a partial count as a total (design.md §8.1).
 *   * **`/metrics`** is where the pipeline strip gets its numbers: the same
 *     exposition Prometheus scrapes, parsed in `src/lib/prometheus.ts`. It is
 *     unauthenticated by decision (D-050) and carries no content, only counts.
 *   * **`/readyz`** answers the one question metrics cannot: whether a dependency
 *     the process needs is currently refused.
 */
import { alertListPath, type AlertPage, type AlertRow } from '../../api/alerts';
import { getJson, getText } from '../../api/client';
import type { MetricsSnapshot } from './pipeline';
import { parseExposition } from '../../lib/prometheus';

export type { AlertPage, AlertRow };

/** The largest page the API will serve (T-305's `MAX_PAGE_SIZE`). */
export const PAGE_SIZE = 1_000;

/**
 * How many pages the overview will walk before it stops.
 *
 * Five thousand alerts in a window is far past the point where the overview is
 * the right instrument — that is what the alert list and the hunt console are
 * for. The cap is what keeps a 7-day window from turning into an unbounded crawl;
 * hitting it is reported, not hidden.
 */
export const MAX_PAGES = 5;

export interface AlertWindow {
  rows: AlertRow[];
  /** False when the page cap stopped the walk and rows remain unread. */
  complete: boolean;
  pagesFetched: number;
  /**
   * The window actually read.
   *
   * Carried with the rows rather than recomputed at render time: the page buckets
   * its series against these bounds, and a window recomputed from a later `now`
   * would put a bucket boundary at a time no query ever asked for — bars that drift
   * left as the clock advances.
   */
  start: Date;
  end: Date;
}

export interface WindowRequest {
  start: Date;
  end: Date;
  signal?: AbortSignal | undefined;
  maxPages?: number;
}

/** Walk one page at a time until the window is exhausted or the cap is reached. */
export async function fetchAlertWindow(request: WindowRequest): Promise<AlertWindow> {
  const { start, end, signal, maxPages = MAX_PAGES } = request;
  const rows: AlertRow[] = [];
  let cursor: string | null = null;
  let pagesFetched = 0;

  while (pagesFetched < maxPages) {
    const path: string = alertListPath({
      start,
      end,
      limit: PAGE_SIZE,
      cursor: cursor ?? undefined,
    });
    const page: AlertPage = await getJson<AlertPage>(path, { signal });
    rows.push(...page.items);
    pagesFetched += 1;
    cursor = page.next_cursor;
    if (cursor === null) return { rows, complete: true, pagesFetched, start, end };
  }

  return { rows, complete: false, pagesFetched, start, end };
}

/** One dependency probe from `/readyz` (T-301/T-317's shape). */
export interface ProbeCheck {
  name: string;
  status: 'ok' | 'degraded' | 'unavailable';
  detail: string;
}

export interface Readiness {
  status: 'ready' | 'not_ready';
  service: string;
  version: string;
  checks: ProbeCheck[];
}

/**
 * Read the readiness probes.
 *
 * A 503 is a valid answer here, not an error: `/readyz` serves "not ready" with a
 * body naming the dependency that is down, and throwing that away would leave the
 * strip able to say *something* is wrong but not *what*.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  return getJson<Readiness>('/readyz', { signal, okStatuses: [503] });
}

/** Read `/metrics` as a parsed snapshot stamped with the time it arrived. */
export async function fetchMetrics(signal?: AbortSignal): Promise<MetricsSnapshot> {
  const text = await getText('/metrics', { signal });
  return { at: Date.now(), samples: parseExposition(text) };
}
