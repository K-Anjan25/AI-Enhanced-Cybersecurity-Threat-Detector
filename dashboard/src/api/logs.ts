/**
 * The log tail API's wire shapes and paths, in one place.
 *
 * `GET /api/v1/logs` folds a window's log lines into clusters and
 * `GET /api/v1/logs/lines` returns the raw lines behind one of them (T-407). Both
 * live here, beside the alert shapes, for the reason that file records: a URL that
 * appears in two places is a URL that can be changed in one of them.
 *
 * Three things about these paths are rules rather than formatting:
 *
 *   * **`start` and `end` are mandatory** and the span is capped by the tail's
 *     retention (R-34). `LogParams` has no defaults for them, so no caller can
 *     produce a path that reads "the logs, as far as they go".
 *   * **`key` is a digest, never a message.** An untemplated line's cluster key is a
 *     hash of its message, so no log content ends up in a query string, in a proxy's
 *     access log or in a browser's history (R-58).
 *   * **Nothing absolute** (R-23): `src/api/client.ts` turns a path into a URL.
 */
import { getJson, query } from './client';

/** The levels `log@1` defines, least severe first. */
export const LOG_LEVELS = ['debug', 'info', 'warning', 'error', 'critical'] as const;

export type LogLevel = (typeof LOG_LEVELS)[number];

/** One raw log line, as `GET /api/v1/logs/lines` returns it. */
export interface LogLine {
  timestamp: string;
  host: string;
  service: string;
  level: LogLevel;
  message: string;
  template_id: string | null;
  parameters: Record<string, string>;
  key: string;
}

/** One cluster: the fold of identical lines, with what a reader needs about them. */
export interface LogCluster {
  key: string;
  template_id: string | null;
  count: number;
  first_seen: string;
  last_seen: string;
  worst_level: LogLevel;
  levels: Record<string, number>;
  hosts: string[];
  services: string[];
  sample_message: string;
  parameters: Record<string, string>;
}

/** The retention every read carries, so a screen cannot imply a complete log. */
export interface LogRetention {
  retained_from: string | null;
  retained_to: string | null;
  retained_lines: number;
  dropped_lines: number;
}

/** The clustered tail, as `GET /api/v1/logs` returns it. */
export interface LogTail extends LogRetention {
  start: string;
  end: string;
  clusters: LogCluster[];
  lines_seen: number;
  clusters_seen: number;
  clusters_truncated: boolean;
  caveats: string[];
}

/** The raw lines, as `GET /api/v1/logs/lines` returns it. */
export interface LogLines extends LogRetention {
  start: string;
  end: string;
  key: string | null;
  lines: LogLine[];
  lines_seen: number;
  lines_truncated: boolean;
  caveats: string[];
}

export interface LogParams {
  /** Inclusive lower bound of the window (R-34). */
  start: Date | string;
  /** Exclusive upper bound of the window (R-34). */
  end: Date | string;
  /** `undefined` reads every level. */
  level?: LogLevel | undefined;
  host?: string | undefined;
  service?: string | undefined;
  /** Restrict to one cluster — the value a row carries in its `key`. */
  key?: string | undefined;
  limit?: number | undefined;
  signal?: AbortSignal | undefined;
}

/** The path and query for one log read. Shared so the two reads cannot diverge. */
function logPath(base: string, params: LogParams): string {
  return `${base}${query({
    start: toInstant(params.start),
    end: toInstant(params.end),
    level: params.level,
    host: params.host,
    service: params.service,
    key: params.key,
    limit: params.limit,
  })}`;
}

/** An instant as the API takes it: ISO-8601, always with a timezone. */
function toInstant(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : value;
}

/** Read the clusters in one window. */
export async function fetchLogTail(params: LogParams): Promise<LogTail> {
  return getJson<LogTail>(logPath('/api/v1/logs', params), { signal: params.signal });
}

/** Read the raw lines behind one cluster (or one window, when `key` is omitted). */
export async function fetchLogLines(params: LogParams): Promise<LogLines> {
  return getJson<LogLines>(logPath('/api/v1/logs/lines', params), { signal: params.signal });
}
