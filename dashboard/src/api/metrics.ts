/**
 * The Prometheus scrape, in the shared client layer.
 *
 * `/metrics` is the backend's own exposition — the same document Prometheus
 * scrapes — and it is unauthenticated by decision (D-050) and content-free, only
 * counts and gauges. The overview's pipeline strip was its first reader (T-403);
 * the drift screen is its second (T-409), and a feature may not import another
 * feature (rules.md, `scripts/check_frontend_boundaries.py`), so the fetch and the
 * snapshot shape live here rather than in `features/overview`.
 *
 * One copy of the path and one copy of "what a snapshot is" is the point: two
 * readers that disagreed about either would show two different pictures of one
 * scrape, and the second one would be wrong.
 */
import { getText } from './client';
import { parseExposition, type Sample } from '../lib/prometheus';

/** Same-origin: the dev server proxies `/metrics` (vite.config.ts). */
export const METRICS_PATH = '/metrics';

export interface MetricsSnapshot {
  /** When the scrape was read, in epoch milliseconds. */
  at: number;
  samples: readonly Sample[];
}

/** Read `/metrics` as a parsed snapshot stamped with the time it arrived. */
export async function fetchMetrics(signal?: AbortSignal): Promise<MetricsSnapshot> {
  const text = await getText(METRICS_PATH, { signal });
  return { at: Date.now(), samples: parseExposition(text) };
}
