/**
 * The triage screen's three calls.
 *
 *   * **`GET /api/v1/alerts`** — the queue. One bounded page, never a walk: the
 *     queue is the newest alerts in a fixed window, and a screen that pages
 *     through an unbounded backlog before it can show anything is a screen that
 *     never shows anything (R-34).
 *   * **`GET /api/v1/alerts/{id}?created_at=…`** — the four zones, one round trip.
 *     The `created_at` is not optional: D-030 makes `(id, created_at)` the key of
 *     the row, so a lookup without it would address whatever different alert
 *     happens to share the id in the month the server guesses.
 *   * **`POST /api/v1/alerts/{id}/verdict`** — the analyst's decision. The body
 *     carries the partition key for the same reason.
 */
import { alertDetailPath, alertListPath, alertVerdictPath, type AlertPage } from '../../api/alerts';
import { getJson, postJson } from '../../api/client';
import type { AlertDetail, VerdictOutcome } from './types';
import type { VerdictName } from './verdicts';

/** How many alerts a queue page holds. One page, so this is also the cap shown. */
export const QUEUE_LIMIT = 100;

/** How far back the queue looks. */
export const QUEUE_WINDOW_HOURS = 24;

/** The queue's window in milliseconds, for the callers that build one. */
export const QUEUE_WINDOW_MS = QUEUE_WINDOW_HOURS * 3_600_000;

export interface QueueRequest {
  start: Date;
  end: Date;
  limit?: number | undefined;
  cursor?: string | undefined;
  signal?: AbortSignal | undefined;
}

/** One page of the queue, newest first. */
export async function fetchQueue(request: QueueRequest): Promise<AlertPage> {
  return getJson<AlertPage>(
    alertListPath({
      start: request.start,
      end: request.end,
      order: 'desc',
      limit: request.limit ?? QUEUE_LIMIT,
      cursor: request.cursor,
    }),
    { signal: request.signal },
  );
}

export interface DetailRequest {
  alertId: number;
  /** The alert's `created_at`, which addresses its partition (D-030). */
  createdAt: string;
  signal?: AbortSignal | undefined;
}

/** Everything design.md §4.3's four zones render. */
export async function fetchAlertDetail(request: DetailRequest): Promise<AlertDetail> {
  return getJson<AlertDetail>(alertDetailPath(request.alertId, request.createdAt), {
    signal: request.signal,
  });
}

export interface VerdictRequest {
  alertId: number;
  createdAt: string;
  verdict: VerdictName;
  note?: string | undefined;
}

/** Record a verdict. The answer distinguishes a write from a repeat. */
export async function recordVerdict(request: VerdictRequest): Promise<VerdictOutcome> {
  return postJson<VerdictOutcome>(alertVerdictPath(request.alertId), {
    created_at: request.createdAt,
    verdict: request.verdict,
    ...(request.note === undefined ? {} : { note: request.note }),
  });
}
