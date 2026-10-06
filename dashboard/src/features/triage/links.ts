/**
 * The triage screen's addresses.
 *
 * A deep link to an alert must carry the partition key as well as the id: the
 * detail is addressed by `(id, created_at)` (D-030), so `/alerts/42` alone cannot
 * be answered — the same id exists in every partition. Encoding it in the URL is
 * what makes a link an analyst pastes into a ticket open the *same* alert next
 * month.
 *
 * `encodeURIComponent` because `created_at` is an ISO instant whose `+00:00`
 * offset would otherwise arrive as a space — the exact bug that made the first
 * version of T-404's own tests ask for a timestamp the API could not parse.
 */
import type { AlertRow } from '../../api/alerts';

/** The list route. */
export const ALERTS_PATH = '/alerts';

/** The detail route for one alert, partition key included. */
export function alertHref(row: Pick<AlertRow, 'id' | 'created_at'>): string {
  return `${ALERTS_PATH}/${String(row.id)}?created_at=${encodeURIComponent(row.created_at)}`;
}

/** The detail route from a raw id and key, for callers without a row. */
export function alertHrefFor(alertId: number, createdAt: string): string {
  return `${ALERTS_PATH}/${String(alertId)}?created_at=${encodeURIComponent(createdAt)}`;
}

/**
 * Every pair of adjacent rows in queue order, for "next alert".
 *
 * Kept here rather than in the page so the rule — *next* means the next row the
 * analyst can see, and the last row has no next — is a pure function with a test.
 */
export function nextHref(rows: readonly AlertRow[], currentId: number | null): string | null {
  if (currentId === null) return rows.length === 0 ? null : alertHref(rows[0]!);
  const index = rows.findIndex((row) => row.id === currentId);
  if (index === -1) return rows.length === 0 ? null : alertHref(rows[0]!);
  const next = rows[index + 1];
  return next === undefined ? null : alertHref(next);
}
