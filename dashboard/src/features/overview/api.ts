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
import type { AlertPage, AlertRow } from '../../api/alerts';
import { getJson, getText } from '../../api/client';
import type { MetricsSnapshot } from './pipeline';
import { parseExposition } from '../../lib/prometheus';

export type { AlertPage, AlertRow };

// The bounded window walk moved to `src/api/alerts.ts` when the traffic explorer
// needed it too (T-406): a feature may not import another feature, and two copies of
// a page-walk that stops at a cap is two places for the cap to disagree. Re-exported
// here because this module is where the overview reads it from.
export {
  fetchAlertWindow,
  MAX_PAGES,
  PAGE_SIZE,
  type AlertWindow,
  type WindowRequest,
} from '../../api/alerts';

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
