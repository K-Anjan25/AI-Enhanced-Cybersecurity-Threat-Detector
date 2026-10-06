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
import { alertHref } from '../../lib/routes';

// The address itself moved to `lib/routes.ts` when the hunt console became the
// second feature to link to an alert (T-408). Re-exported here so this feature's
// callers and tests are unchanged.
export { ALERTS_PATH, alertHref, alertHrefFor } from '../../lib/routes';

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
