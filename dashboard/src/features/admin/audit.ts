/**
 * The audit panel's derived model (T-410, FR-42, design.md §4.8).
 *
 * design.md §4.8 asks for a trail that is *append-only, filterable, exportable and
 * visibly non-editable: no edit affordance anywhere*. Three of those are properties
 * of this file:
 *
 *   * **Non-editable by construction.** Nothing here produces a mutation, and
 *     `auditRows` maps the server's record into a row whose fields are all read-only
 *     text. There is no `onEdit`, no `onDelete` and no editable column: the absence
 *     is the affordance, and the panel states it so an operator is not left
 *     wondering where the edit button went.
 *   * **Filterable, with the filters the route takes.** So the filter set is exactly
 *     `AuditQuery`'s fields — an action, an actor, a target, and a window — and a
 *     filter the route cannot apply is not offered.
 *   * **Exportable as CSV, generated from what is on screen.** Rows that were
 *     displayed, not a second query: an export that could disagree with the table
 *     would be a claim about the trail that nobody checked. The export is therefore
 *     a formatting function (`auditCsv`), and its escaping is this file's job.
 *
 * The window is bounded because the route bounds it (R-34): the panel defaults to the
 * last 24 hours and says the span, so a reader never mistakes "no rows" for "no
 * actions" when they have simply filtered to a quiet hour.
 */
import { formatStamp } from '../../lib/format';
import type { AuditEntry } from '../../api/admin';

/** The default window, in hours. The route's own maximum span is the limit. */
export const DEFAULT_AUDIT_HOURS = 24;

export interface AuditRow {
  id: number;
  actor: string;
  action: string;
  target: string;
  /** The thin context the writing route supplied, as text. */
  detail: string;
  /** The source address, or the sentence for a recorded absence. */
  ip: string;
  at: string;
}

/**
 * One entry as a row.
 *
 * `detail` is flattened into `key=value` pairs rather than shown as JSON: the
 * records are thin by design (counts and identifiers), and a `dict` rendered raw on
 * a line reads as noise. Sorted keys, so the same detail always reads the same way.
 */
export function auditRows(entries: readonly AuditEntry[] | undefined): AuditRow[] {
  return (entries ?? []).map((entry) => ({
    id: entry.id,
    actor: entry.actor,
    action: entry.action,
    target: `${entry.target_type}:${entry.target_id}`,
    detail: formatDetail(entry.detail),
    ip: entry.ip ?? 'not recorded',
    at: formatStamp(entry.at),
  }));
}

export function formatDetail(detail: Record<string, unknown>): string {
  const keys = Object.keys(detail).sort();
  if (keys.length === 0) return '—';
  return keys
    .map((key) => {
      const value = detail[key];
      const text = Array.isArray(value) ? value.join('|') : String(value);
      return `${key}=${text}`;
    })
    .join(' ');
}

/** The sentence under the table: what the window is, and what cannot be done here. */
export function auditNote(rowCount: number, hasMore: boolean): string {
  const read = `${String(rowCount)} ${rowCount === 1 ? 'entry' : 'entries'} in this window, newest first.`;
  const more = hasMore
    ? ' The page cap was reached: older entries in the window are behind "Older" — they were not dropped.'
    : ' This window is fully read.';
  return `${read}${more} The trail is append-only: it has no edit or delete anywhere, in any role (R-37).`;
}

/**
 * The rows as a CSV document.
 *
 * The escaping follows RFC 4180: a field containing a comma, a quote or a newline is
 * quoted, and a quote inside it is doubled. A detail value is operator-supplied text
 * (an email address, a partition name), so this is not theoretical — an unescaped
 * comma would shift every later column by one and the export would be a lie about
 * which actor did what.
 */
export function auditCsv(rows: readonly AuditRow[]): string {
  const header = ['id', 'at', 'actor', 'action', 'target', 'detail', 'ip'];
  const lines = [header.join(',')];
  for (const row of rows) {
    lines.push(
      [String(row.id), row.at, row.actor, row.action, row.target, row.detail, row.ip]
        .map(csvField)
        .join(','),
    );
  }
  return `${lines.join('\n')}\n`;
}

/** One field, quoted only when it has to be. */
export function csvField(value: string): string {
  if (/[",\n\r]/.test(value)) return `"${value.replaceAll('"', '""')}"`;
  return value;
}

/** The actions this build records, as filter choices. */
export const AUDIT_ACTION_CHOICES: readonly { value: string; label: string }[] = [
  { value: '', label: 'Any action' },
  { value: 'ingest.flows', label: 'Flows ingested' },
  { value: 'ingest.logs', label: 'Logs ingested' },
  { value: 'alert.verdict', label: 'Verdict recorded' },
  { value: 'webhook.create', label: 'Webhook created' },
  { value: 'webhook.delete', label: 'Webhook deleted' },
  { value: 'key.create', label: 'API key issued' },
  { value: 'key.revoke', label: 'API key revoked' },
  { value: 'retention.apply', label: 'Retention run' },
  { value: 'privacy.erasure', label: 'Subject erased' },
  { value: 'model.promote', label: 'Model promoted' },
  { value: 'model.rollback', label: 'Model rolled back' },
  { value: 'threshold.recalibrate', label: 'Threshold recalibrated' },
  { value: 'threshold.set', label: 'Threshold set by hand' },
  { value: 'user.role', label: 'User role changed' },
  { value: 'hunt.export', label: 'Data exported' },
];
