/**
 * The alert API's wire shapes and paths, in one place.
 *
 * Two features read alerts — the overview aggregates them (T-403) and the triage
 * screen lists and opens them (T-404) — and a feature may not import another
 * feature, so the shapes they share live here, in the `api` layer beside the
 * typed client. This is the *only* copy of `AlertRow`: two structurally identical
 * interfaces would drift the first time the API changed a field name, and nothing
 * would fail until a screen showed `undefined`.
 *
 * The path builders live here for the same reason. A URL that appears in two
 * places is a URL that can be changed in one of them, and `GET /api/v1/alerts`
 * has three things about it that are rules rather than formatting:
 *
 *   * **`start` and `end` are mandatory** (R-34 forbids scanning a partitioned
 *     table without a bounded window), so no builder here can produce a list path
 *     without them.
 *   * **The detail is addressed by `(id, created_at)`** (D-030). An id alone is
 *     ambiguous across partitions, so the builder cannot be called without the
 *     partition key.
 *   * **Nothing absolute.** Paths are relative to the dashboard's own origin;
 *     `src/api/client.ts` is what turns them into URLs (R-23).
 */
import { query } from './client';

/** One alert as `GET /api/v1/alerts` returns it (T-305's `AlertRow`). */
export interface AlertRow {
  id: number;
  created_at: string;
  entity_id: number;
  family: string;
  severity: string;
  score: number;
  status: string;
  first_seen: string;
  last_seen: string;
  occurrence_count: number;
  trace_id: string | null;
}

/** One page of alerts, as `GET /api/v1/alerts` returns it. */
export interface AlertPage {
  items: AlertRow[];
  next_cursor: string | null;
  limit: number;
  order: 'asc' | 'desc';
}

export interface AlertListParams {
  /** Inclusive lower bound of the window (R-34). */
  start: Date | string;
  /** Exclusive upper bound of the window (R-34). */
  end: Date | string;
  severity?: string | undefined;
  status?: string | undefined;
  family?: string | undefined;
  entityId?: number | undefined;
  minScore?: number | undefined;
  order?: 'asc' | 'desc' | undefined;
  limit?: number | undefined;
  cursor?: string | undefined;
}

/** The ISO form the API's parsers accept, whichever form the caller passed. */
function instant(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : value;
}

/** `GET /api/v1/alerts` — one bounded page of alerts. */
export function alertListPath(params: AlertListParams): string {
  return `/api/v1/alerts${query({
    start: instant(params.start),
    end: instant(params.end),
    severity: params.severity,
    status: params.status,
    family: params.family,
    entity_id: params.entityId,
    min_score: params.minScore,
    order: params.order,
    limit: params.limit,
    cursor: params.cursor,
  })}`;
}

/** `GET /api/v1/alerts/{id}` — one alert, addressed by both halves of its key. */
export function alertDetailPath(alertId: number, createdAt: Date | string): string {
  return `/api/v1/alerts/${String(alertId)}${query({ created_at: instant(createdAt) })}`;
}

/** `POST /api/v1/alerts/{id}/verdict` — where an analyst's decision is written. */
export function alertVerdictPath(alertId: number): string {
  return `/api/v1/alerts/${String(alertId)}/verdict`;
}
