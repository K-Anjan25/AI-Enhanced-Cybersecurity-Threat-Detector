/**
 * The hunt console's derived model: what a run means, in one place.
 *
 * design.md §4.6 ends with the sentence this module exists for: *"empty results
 * render the executed query and the time range so the analyst can see what was
 * actually searched."* An empty table is the single most misleading thing a search
 * screen can draw — it looks the same whether the query was wrong, the window was
 * wrong, or the window is genuinely quiet — so the echo is part of the model rather
 * than something a component remembers to render, and the state machine has an
 * `empty` case that cannot be reached without one.
 *
 * Everything a hunt cannot do is a note in the model (R-70, R-74): the fields this
 * build has no read model for, and the fact that the table shows the *newest* rows
 * of a window rather than all of them when the window holds more than the cap.
 */
import type { AlertPage, AlertRow } from '../../api/alerts';
import { formatCount, formatStamp } from '../../lib/format';
import type { Severity } from '../../components/ui/severity';
import { isSeverity } from '../../components/ui/severity';
import { describeHunt, type HuntParse, type HuntWindow } from './query';

export interface HuntRow {
  row: AlertRow;
  id: string;
  severity: Severity | 'unrecognised';
  /** The severity text the API sent, always shown even when it is unknown. */
  severityLabel: string;
  entity: string;
  family: string;
  score: string;
  status: string;
  occurrences: string;
  firstSeen: string;
  lastSeen: string;
  created: string;
  trace: string;
}

export interface HuntView {
  rows: HuntRow[];
  state: 'idle' | 'loading' | 'error' | 'empty' | 'rows';
  /** The executed query, canonical, always present — null only when nothing ran. */
  executed: string | null;
  /** The window that ran, in words. */
  windowLabel: string | null;
  /** The window's instants, for a caption that has to be exact. */
  window: HuntWindow | null;
  /** The API's row count for the window, and whether it stopped at the cap. */
  rowCount: number;
  truncated: boolean;
  /** Why nothing is on screen, in a sentence the analyst can act on. */
  emptyReason: string | null;
}

export interface HuntViewInput {
  page: AlertPage | undefined;
  /** The parse that was run, or null when nothing has been run yet. */
  parse: HuntParse | null;
  window: HuntWindow | null;
  failed: boolean;
}

/** The three most severe-ish shapes of "the API sent something unexpected". */
function severityOf(value: string): Severity | 'unrecognised' {
  return isSeverity(value) ? value : 'unrecognised';
}

function rowOf(row: AlertRow): HuntRow {
  return {
    row,
    id: String(row.id),
    severity: severityOf(row.severity),
    severityLabel: row.severity,
    entity: String(row.entity_id),
    family: row.family,
    score: row.score.toFixed(4),
    status: row.status,
    occurrences: formatCount(row.occurrence_count),
    firstSeen: formatStamp(row.first_seen),
    lastSeen: formatStamp(row.last_seen),
    created: formatStamp(row.created_at),
    trace: row.trace_id ?? '—',
  };
}

/**
 * A window in words: both ends with their *date*, and the span.
 *
 * A time of day would be ambiguous the moment the window is wider than a day, and
 * this console's windows run to ninety: an empty 7-day hunt whose echo read
 * "09:00:00Z–10:00:00Z" would be describing a window that does not exist.
 */
export function huntWindowLabel(window: HuntWindow): string {
  const start = formatStamp(window.start.toISOString());
  const end = formatStamp(window.end.toISOString());
  const spanMs = window.end.getTime() - window.start.getTime();
  return `${start}–${end} · ${huntSpanLabel(spanMs)}`;
}

/** A span in words: the two units this console offers, and a fallback. */
export function huntSpanLabel(spanMs: number): string {
  const hours = Math.round(spanMs / 3_600_000);
  if (hours < 24) return `last ${String(hours)} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'last 24 h' : `last ${String(days)} days`;
}

/**
 * Fold a response into what the page renders.
 *
 * `idle` is a state of its own: nothing has been run, which is not the same as a
 * run that matched nothing, and showing "no results" before the first search would
 * teach an analyst that the console is broken. `empty` can only be built from a
 * parse and a window, because the sentence it carries names both.
 */
export function buildHuntView(input: HuntViewInput): HuntView {
  const windowLabel = input.window === null ? null : huntWindowLabel(input.window);
  const executed = input.parse === null ? null : describeHunt(input.parse);

  if (input.failed) {
    return {
      rows: [],
      state: 'error',
      executed,
      windowLabel,
      window: input.window,
      rowCount: 0,
      truncated: false,
      emptyReason: 'The read failed, so nothing is shown rather than a stale page.',
    };
  }

  if (input.parse === null || input.window === null) {
    return {
      rows: [],
      state: 'idle',
      executed: null,
      windowLabel: null,
      window: null,
      rowCount: 0,
      truncated: false,
      emptyReason: null,
    };
  }

  if (input.page === undefined) {
    return {
      rows: [],
      state: 'loading',
      executed,
      windowLabel,
      window: input.window,
      rowCount: 0,
      truncated: false,
      emptyReason: null,
    };
  }

  const rows = input.page.items.map(rowOf);
  const truncated = input.page.next_cursor !== null;
  return {
    rows,
    state: rows.length === 0 ? 'empty' : 'rows',
    executed,
    windowLabel,
    window: input.window,
    rowCount: rows.length,
    truncated,
    emptyReason:
      rows.length === 0
        ? `No alert matched ${executed} between ${windowLabel ?? 'the chosen window'}. ` +
          'The window, the window’s dates or the filters are what removed them — an empty ' +
          'answer here is not a statement about the network.'
        : null,
  };
}

/** A row's label for the table's own accessibility: what it is, in words. */
export function rowLabel(row: HuntRow): string {
  return `${row.severityLabel} ${row.family} on entity ${row.entity}, score ${row.score}`;
}
