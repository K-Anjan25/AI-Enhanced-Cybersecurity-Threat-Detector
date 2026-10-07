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
 * The address `delta` rows away from the open alert, for "next alert" and for
 * `j`/`k` (T-411).
 *
 * Kept here rather than in the page so the rule is a pure function with a test:
 *
 *   * **The step is the queue's, not a list widget's.** `j` opens the next alert —
 *     the same thing the "Next alert" link does — because the analyst is reading the
 *     detail and wants the next one, not to move focus inside a list beside it.
 *   * **Nothing selected means the top.** `j` on `/alerts` opens the first row; `k`
 *     has nowhere to go and does nothing, which is better than opening the last row
 *     of a queue the analyst has not looked at.
 *   * **The ends are the ends.** No wrap: re-opening the alert at the top of a
 *     queue is the one moment an analyst is definitely not looking, and T-411's
 *     reference promises "the next or previous alert", not a carousel.
 */
export function stepHref(
  rows: readonly AlertRow[],
  currentId: number | null,
  delta: number,
): string | null {
  const first = rows[0];
  if (first === undefined) return null;
  const index = currentId === null ? -1 : rows.findIndex((row) => row.id === currentId);
  if (index === -1) return delta > 0 ? alertHref(first) : null;
  const target = rows[index + delta];
  return target === undefined ? null : alertHref(target);
}

/** The next row the analyst can see: `stepHref` one forward. */
export function nextHref(rows: readonly AlertRow[], currentId: number | null): string | null {
  return stepHref(rows, currentId, 1);
}
