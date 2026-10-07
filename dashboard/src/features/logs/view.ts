/**
 * The log explorer's derived model: one place that turns a tail response into rows.
 *
 * The rule the whole file exists to keep is the one `view.ts` keeps in the traffic
 * explorer and T-403 kept in the overview: **no number reaches a panel without the
 * sentence that qualifies it** (R-70, R-74). The caveats come from the API and are
 * carried through verbatim, so a panel cannot render a cluster count while dropping
 * the note that says where the lines came from and what that source cannot do —
 * whether that is a bounded in-process tail (T-407) or a store that outlives the
 * process but has no eviction yet (T-419). The screen adds
 * its own state lines — paused, hidden, stale — beside them rather than in place of
 * them, because "the view is frozen" and "the tail is not a store" are different
 * facts about the same screen.
 */
import type { LogCluster, LogLevel } from './api';
import {
  countLabel,
  isNotable,
  levelTone,
  levelsLabel,
  templateLabel,
  windowLabel,
  worstLevel,
  type LogWindow,
} from './cluster';
import { formatCount, formatInstant, formatStamp } from '../../lib/format';
import type { BadgeTone } from '../../components/ui';
import type { LogSource, LogTail } from './api';

/** One cluster, ready to render: the wire shape plus what the table's cells need. */
export interface LogRow {
  cluster: LogCluster;
  key: string;
  /** The template id, or a shortened digest when the lines carried none. */
  template: string;
  /** The collapse, as design.md §4.5 writes it: `×10,000`. */
  count: string;
  /** `2 critical, 1 info`, most severe first. */
  levels: string;
  /** The worst level's own word. A level, not a model's score. */
  level: LogLevel;
  tone: BadgeTone;
  /** Whether this row earns the rail: an error or critical line is in it. */
  notable: boolean;
  /** The instants the cluster spans, in UTC. */
  span: string;
  hosts: string;
  services: string;
}

/** What the page shows about the tail itself, not about any one cluster. */
export interface LogView {
  rows: LogRow[];
  window: LogWindow;
  windowLabel: string;
  linesSeen: number;
  clustersSeen: number;
  truncated: boolean;
  notableCount: number;
  /** The API's own caveats, in its own words, never rephrased. */
  caveats: string[];
  /** What the source holds right now, as a sentence. */
  retention: string;
  /** Which read model answered, or `null` before the first response (T-419). */
  source: LogSource | null;
  /**
   * One sentence naming the read model, so the screen never implies the other.
   *
   * `null` until a response arrives. It is deliberately not defaulted to the tail:
   * a loading screen that already says "read from this process's own tail" has named
   * a source it has not heard from, and on a store deployment that sentence is wrong
   * every time the page opens.
   */
  sourceLabel: string | null;
  /** The screen's state, so a panel has no empty-success path. */
  state: 'loading' | 'error' | 'empty' | 'rows';
  /** Why there is nothing to show, in the API's own words, when there is nothing. */
  emptyReason: string | null;
}

export interface LogViewInput {
  tail: LogTail | undefined;
  window: LogWindow;
  failed: boolean;
}

/** A list of names, collapsed once it stops being readable. */
function nameList(names: readonly string[], noun: string): string {
  if (names.length === 0) return '—';
  if (names.length <= 3) return names.join(', ');
  return `${String(names.length)} ${noun}`;
}

function rowOf(cluster: LogCluster): LogRow {
  const level = worstLevel(cluster);
  return {
    cluster,
    key: cluster.key,
    template: templateLabel(cluster),
    count: countLabel(cluster.count),
    levels: levelsLabel(cluster),
    level,
    tone: levelTone(level),
    notable: isNotable(level),
    span: `${formatInstant(cluster.first_seen)} → ${formatInstant(cluster.last_seen)}`,
    hosts: nameList(cluster.hosts, 'hosts'),
    services: nameList(cluster.services, 'services'),
  };
}

/**
 * Which read model answered, in a sentence (T-419).
 *
 * The API's caveats say it too, in more detail; this is the short form the header
 * uses, and it exists so the screen cannot read like a live tail when it is in fact
 * reading a store — which is the difference between "these lines are gone in fifteen
 * minutes" and "these lines survive a restart".
 */
const SOURCE_LABELS: Record<LogSource, string> = {
  store: 'Read from the log store.',
  tail: 'Read from this process’s own tail.',
};

/** The sentence about the source's own bounds: how much it holds, and what aged out. */
function retentionSentence(tail: LogTail): string {
  const parts = [`Holding ${formatCount(tail.retained_lines)} lines`];
  // A store cannot report evictions -- nothing evicts yet -- so the sentence omits the
  // clause rather than printing "0 aged out", which would be a claim it cannot make.
  if (tail.dropped_lines !== null) {
    parts.push(
      tail.dropped_lines > 0
        ? `${formatCount(tail.dropped_lines)} aged out`
        : 'nothing aged out yet',
    );
  }
  if (tail.retained_to !== null) parts.push(`newest ${formatStamp(tail.retained_to)}`);
  return `${parts.join(' · ')}.`;
}

/**
 * Fold a response into what the page renders.
 *
 * `loading` is the query's own state rather than "no rows yet", so a first paint
 * cannot show the empty state for a tail that has simply not answered; `empty` is a
 * response with no clusters, and the API's own caveats explain which kind of empty
 * it is (nothing accepted, aged out, outside the window, or filtered away).
 */
export function buildLogView(input: LogViewInput): LogView {
  const { tail, window: span } = input;

  if (input.failed) {
    return {
      rows: [],
      window: span,
      windowLabel: windowLabel(span.start, span.end),
      linesSeen: 0,
      clustersSeen: 0,
      truncated: false,
      notableCount: 0,
      caveats: [],
      retention: 'The logs could not be read.',
      source: null,
      sourceLabel: null,
      state: 'error',
      emptyReason: null,
    };
  }

  if (tail === undefined) {
    return {
      rows: [],
      window: span,
      windowLabel: windowLabel(span.start, span.end),
      linesSeen: 0,
      clustersSeen: 0,
      truncated: false,
      notableCount: 0,
      caveats: [],
      retention: 'Reading the logs…',
      source: null,
      sourceLabel: null,
      state: 'loading',
      emptyReason: null,
    };
  }

  const rows = tail.clusters.map(rowOf);
  return {
    rows,
    window: span,
    windowLabel: windowLabel(span.start, span.end),
    linesSeen: tail.lines_seen,
    clustersSeen: tail.clusters_seen,
    truncated: tail.clusters_truncated,
    notableCount: rows.filter((row) => row.notable).length,
    caveats: tail.caveats,
    retention: retentionSentence(tail),
    source: tail.source,
    sourceLabel: SOURCE_LABELS[tail.source],
    state: rows.length === 0 ? 'empty' : 'rows',
    // The API's second caveat is the specific one -- never accepted, aged out,
    // outside the window, or filtered away -- and it is the honest description of
    // an empty table (R-70). The first caveat is always the permanent one.
    emptyReason: rows.length === 0 ? (tail.caveats[1] ?? null) : null,
  };
}
