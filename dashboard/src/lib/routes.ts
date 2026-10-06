/**
 * The dashboard's own addresses, for the links a screen hands out.
 *
 * A deep link to an alert must carry the partition key as well as the id: the detail
 * is addressed by `(id, created_at)` (D-030), so `/alerts/42` alone cannot be
 * answered — the same id exists in every partition. It lives in `lib` because two
 * features now link to an alert (the triage queue, T-404, and the hunt results,
 * T-408) and a feature may not import another feature; the alternative was a second
 * copy of the URL rule, which is how a link survives a route rename in one place and
 * breaks in the other.
 *
 * `encodeURIComponent` because `created_at` is an ISO instant whose `+00:00` offset
 * would otherwise arrive as a space — the exact bug that made the first version of
 * T-404's own tests ask for a timestamp the API could not parse.
 */

/** The alert list route. */
export const ALERTS_PATH = '/alerts';

/** The hunt console route. */
export const HUNT_PATH = '/hunt';

/**
 * The query parameter the hunt console reads.
 *
 * Exported with the href below so the writer and the reader share one spelling: a
 * link that says `?query=` to a screen that reads `q` is a link to a blank console,
 * and nothing would fail — it would just quietly search nothing.
 */
export const HUNT_QUERY_PARAM = 'q';

/**
 * The hunt console with a query to run, e.g. `/hunt?q=severity%3Ahigh`.
 *
 * A saved hunt is a query, not a window: the store keeps the text, so the deep link
 * carries the text and the console applies its own default window (T-408's own
 * decision, and the reason this encodes one parameter rather than two).
 */
export function huntHref(text: string): string {
  return `${HUNT_PATH}?${HUNT_QUERY_PARAM}=${encodeURIComponent(text)}`;
}

/** The detail route for one alert, partition key included. */
export function alertHref(row: { id: number; created_at: string }): string {
  return alertHrefFor(row.id, row.created_at);
}

/** The detail route from a raw id and key, for callers without a row. */
export function alertHrefFor(alertId: number, createdAt: string): string {
  return `${ALERTS_PATH}/${String(alertId)}?created_at=${encodeURIComponent(createdAt)}`;
}
