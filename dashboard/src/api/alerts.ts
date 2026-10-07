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
import { getJson, postExport, query, type ExportDocument } from './client';

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

/**
 * `POST /api/v1/alerts/export` — the queue's batch, as CSV or as a PDF report.
 *
 * A POST for the reason the hunt export is one (T-408, D-065): it writes an audit
 * row, and a route that writes one is a change by the same rule the ingest routes
 * are. The body is the *filter definition*, so the file's rows are the rows the
 * queue showed -- the acceptance criterion of T-415 is exactly that agreement, and
 * the only way to keep it is to send the same query the queue sent.
 */
export const ALERTS_EXPORT_PATH = '/api/v1/alerts/export';

/** The two shapes FR-23 asks for. The value is the wire name *and* the suffix. */
export type AlertExportFormat = 'csv' | 'pdf';

/** The JSON body the export route takes: the alert query plus the format. */
export interface AlertExportBody {
  start: string;
  end: string;
  severity?: string;
  status?: string;
  family?: string;
  entity_id?: number;
  min_score?: number;
  order?: 'asc' | 'desc';
  limit?: number;
  format: AlertExportFormat;
}

/**
 * The queue's filter, as the export's body.
 *
 * Field names are the *wire* names (`entity_id`, `min_score`), and the cursor is
 * deliberately absent: the API refuses one, because an export mirrors the first
 * page of the query the analyst ran.
 */
export function alertExportBody(
  params: AlertListParams,
  format: AlertExportFormat,
): AlertExportBody {
  const body: AlertExportBody = {
    start: instant(params.start),
    end: instant(params.end),
    format,
  };
  if (params.severity !== undefined) body.severity = params.severity;
  if (params.status !== undefined) body.status = params.status;
  if (params.family !== undefined) body.family = params.family;
  if (params.entityId !== undefined) body.entity_id = params.entityId;
  if (params.minScore !== undefined) body.min_score = params.minScore;
  if (params.order !== undefined) body.order = params.order;
  if (params.limit !== undefined) body.limit = params.limit;
  return body;
}

/** Export the alert batch matching a queue filter, in one of FR-23's two shapes. */
export async function exportAlerts(
  params: AlertListParams,
  format: AlertExportFormat,
  options: { signal?: AbortSignal | undefined } = {},
): Promise<ExportDocument> {
  const accept = format === 'pdf' ? 'application/pdf' : 'text/csv';
  return postExport(ALERTS_EXPORT_PATH, alertExportBody(params, format), accept, options);
}

/** `POST /api/v1/alerts/{id}/verdict` — where an analyst's decision is written. */
export function alertVerdictPath(alertId: number): string {
  return `/api/v1/alerts/${String(alertId)}/verdict`;
}

/**
 * `GET /api/v1/alerts` — one bounded page, with whichever filters the caller set.
 *
 * The primitive the window walk below is built from, and what the hunt console reads
 * (T-408): a hunt is one page by definition, because its answer is a question about
 * a window rather than a crawl of one. The `limit` is the caller's, so the console
 * can cap what an export will contain.
 */
export async function fetchAlertPage(
  params: AlertListParams,
  options: { signal?: AbortSignal | undefined } = {},
): Promise<AlertPage> {
  return getJson<AlertPage>(alertListPath(params), options);
}

/** The largest page the API will serve (T-305's `MAX_PAGE_SIZE`). */
export const PAGE_SIZE = 1_000;

/**
 * How many pages a screen walks before it stops.
 *
 * Five thousand alerts in a window is far past the point where a single screen is
 * the right instrument — that is what the alert list and the hunt console are for.
 * The cap is what keeps a 7-day window from becoming an unbounded crawl; hitting it
 * is reported, never hidden.
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
   * Carried with the rows rather than recomputed at render time: a screen buckets
   * its series against these bounds, and a window recomputed from a later `now`
   * would put a bucket boundary at a time no query ever asked for — bars that drift
   * as the clock advances.
   */
  start: Date;
  end: Date;
}

export interface WindowRequest {
  /** Inclusive lower bound (R-34). */
  start: Date;
  /** Exclusive upper bound (R-34). */
  end: Date;
  signal?: AbortSignal | undefined;
  maxPages?: number;
  /** Narrow the read server-side; the brush never widens a query. */
  severity?: string | undefined;
}

/** Walk one page at a time until the window is exhausted or the cap is reached. */
export async function fetchAlertWindow(request: WindowRequest): Promise<AlertWindow> {
  const { start, end, signal, maxPages = MAX_PAGES, severity } = request;
  const rows: AlertRow[] = [];
  let cursor: string | null = null;
  let pagesFetched = 0;

  while (pagesFetched < maxPages) {
    const page: AlertPage = await fetchAlertPage(
      {
        start,
        end,
        severity,
        limit: PAGE_SIZE,
        cursor: cursor ?? undefined,
      },
      { signal },
    );
    rows.push(...page.items);
    pagesFetched += 1;
    cursor = page.next_cursor;
    if (cursor === null) return { rows, complete: true, pagesFetched, start, end };
  }

  return { rows, complete: false, pagesFetched, start, end };
}
