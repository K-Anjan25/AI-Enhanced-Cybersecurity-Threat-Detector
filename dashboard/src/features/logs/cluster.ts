/**
 * The log tail's vocabulary: levels, keys, counts and windows.
 *
 * Everything here is pure, so the screen's claims about a log line can be tested
 * without rendering one. Three of them are decisions rather than formatting:
 *
 *   * **A level is not a severity.** `log@1`'s five levels map onto the severity
 *     palette so a reader's eye can find the worst rows — but the label stays the
 *     level's own word, because "critical" in this column means a line said
 *     `critical`, not that a model scored anything (design.md §4.5's anomaly colour
 *     has no source in this build at all: no log model is served here). `levelTone`
 *     picks the hue, `levelLabel` names the thing.
 *   * **A cluster key is shown, not the message.** An untemplated cluster's key is a
 *     digest (R-58), so the row can be addressed and linked without a log line
 *     travelling in a URL. The row still shows a sample message, because that is
 *     what the analyst is reading for.
 *   * **`×10,000` is the count's own presentation.** design.md §4.5 writes the
 *     collapse exactly that way, and a bare `10000` does not read as "identical
 *     lines collapsed into one row".
 */
import type { BadgeTone } from '../../components/ui';
import { formatCount } from '../../lib/format';
import { LOG_LEVELS, type LogCluster, type LogLevel, type LogSource } from '../../api/logs';

/** Levels ordered least severe first, from the wire vocabulary's own list. */
export { LOG_LEVELS };

/** Which severity hue carries each level. `debug` is off the severity scale. */
const LEVEL_TONES: Record<LogLevel, BadgeTone> = {
  debug: 'neutral',
  info: 'info',
  warning: 'medium',
  error: 'high',
  critical: 'critical',
};

/** Levels a reader should look at first: these get the row's rail (design.md §4.5). */
const NOTABLE: readonly LogLevel[] = ['error', 'critical'];

/** Whether a level warrants the highlight. A level, not a model's verdict. */
export function isNotable(level: LogLevel): boolean {
  return NOTABLE.includes(level);
}

/** The severity hue for one level. */
export function levelTone(level: LogLevel): BadgeTone {
  return LEVEL_TONES[level];
}

/** The level's own word, for the label: the chip names the level, not a severity. */
export function levelLabel(level: LogLevel): string {
  return level;
}

/** Where a level sits, least severe first, for ordering and for "worst". */
export function levelRank(level: LogLevel): number {
  return LOG_LEVELS.indexOf(level);
}

/** Narrow an arbitrary string from the API to a level. */
export function isLogLevel(value: string): value is LogLevel {
  return (LOG_LEVELS as readonly string[]).includes(value);
}

/** The worst level among a cluster's lines, falling back to the field the API sent. */
export function worstLevel(cluster: LogCluster): LogLevel {
  return isLogLevel(cluster.worst_level) ? cluster.worst_level : 'info';
}

/** A count the way the collapse is written: `×10,000`. */
export function countLabel(count: number): string {
  return `×${formatCount(count)}`;
}

/** The levels a cluster holds, most severe first: `2 critical, 1 info`. */
export function levelsLabel(cluster: LogCluster): string {
  const entries = LOG_LEVELS.filter((level) => (cluster.levels[level] ?? 0) > 0).reverse();
  return entries.map((level) => `${formatCount(cluster.levels[level] ?? 0)} ${level}`).join(', ');
}

/** What a row is called when there is no template id: its digest, shortened. */
export function templateLabel(cluster: LogCluster): string {
  const template = (cluster.template_id ?? '').trim();
  if (template !== '') return template;
  return `${cluster.key.slice(0, 16)}…`;
}

/** The instants a read covers. Half-open, `[start, end)`, like every other window. */
export interface LogWindow {
  start: Date;
  end: Date;
}

/**
 * The instants a live tail reads, given a clock and a span.
 *
 * The end is the clock rather than the last line seen: the screen asks for the
 * window it is showing and the API answers with what is in it, so a gap in the logs
 * shows as a gap instead of being silently skipped over.
 */
export function tailWindow(now: number, spanMs: number): LogWindow {
  return { start: new Date(now - spanMs), end: new Date(now) };
}

/**
 * The span options the page offers, which depend on what can answer (T-419).
 *
 * A tail can only answer within its retention, and the API refuses anything wider —
 * so a tail deployment is offered exactly the retained spans, and the picker cannot
 * offer a window the server would reject. A store is not bounded that way, so it also
 * offers an hour and a day: the same window that used to be unaskable becomes a read,
 * which is the acceptance criterion made visible on the screen rather than only in the
 * API.
 */
export interface TailSpan {
  key: '1m' | '5m' | '15m' | '1h' | '24h';
  label: string;
  spanMs: number;
}

/**
 * How wide each key is, in one table.
 *
 * The width is a fact about the key, not about who answers: a key the user picked is
 * the same window whether a store or a tail is reading it. Both span sets below are
 * built from this table, so a width cannot drift between the picker and the window
 * the page asks for.
 */
export const SPAN_MS: Record<TailSpan['key'], number> = {
  '1m': 60_000,
  '5m': 300_000,
  '15m': 900_000,
  '1h': 3_600_000,
  '24h': 86_400_000,
};

/** The spans a deployment with no log store can ask for: its retention, and no more. */
export const TAIL_SPANS: readonly TailSpan[] = [
  { key: '1m', label: 'Last minute', spanMs: SPAN_MS['1m'] },
  { key: '5m', label: 'Last 5 min', spanMs: SPAN_MS['5m'] },
  { key: '15m', label: 'Last 15 min', spanMs: SPAN_MS['15m'] },
];

/** The same, plus what a store can reach: the retention is no longer the ceiling. */
export const STORE_SPANS: readonly TailSpan[] = [
  ...TAIL_SPANS,
  { key: '1h', label: 'Last hour', spanMs: SPAN_MS['1h'] },
  { key: '24h', label: 'Last 24 h', spanMs: SPAN_MS['24h'] },
];

/**
 * The spans a picker should offer, given what answered.
 *
 * `undefined` is "the source is not known yet" -- the first paint, before any
 * response -- and it gets the *narrow* set. Offering an hour or a day before a store
 * has confirmed it is answering would put a control on screen that the next response
 * may prove dead; withholding them for one round trip costs a reload nothing. The
 * asymmetry is deliberate: a promise of what can be read is made only by a source
 * that has said it can read it.
 *
 * `spanOf` looks a key up in the same set, so the picker's value is always one of its
 * own options.
 */
export function spansFor(source: LogSource | undefined): readonly TailSpan[] {
  return source === 'store' ? STORE_SPANS : TAIL_SPANS;
}

/** One span by key, falling back to the five-minute default every source can read. */
export function spanOf(key: TailSpan['key'], source?: LogSource): TailSpan {
  const spans = spansFor(source);
  return spans.find((span) => span.key === key) ?? (spans[1] as TailSpan);
}

/**
 * A window in words, for a screen that must state what it is showing.
 *
 * A time alone is not enough once a span crosses midnight — `23:59–00:01` reads as
 * an inverted window — so the date is printed when the two ends fall on different
 * days.
 */
export function windowLabel(start: Date, end: Date): string {
  const time = (at: Date): string =>
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'UTC',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(at);
  const day = (at: Date): string =>
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'UTC',
      day: '2-digit',
      month: 'short',
    }).format(at);

  const sameDay =
    start.getUTCFullYear() === end.getUTCFullYear() &&
    start.getUTCMonth() === end.getUTCMonth() &&
    start.getUTCDate() === end.getUTCDate();

  return sameDay
    ? `${time(start)}–${time(end)} UTC`
    : `${day(start)} ${time(start)} → ${day(end)} ${time(end)} UTC`;
}
