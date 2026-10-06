/**
 * The tail's controls: pause, the window, and the level filter.
 *
 * Pause is a **button with `aria-pressed`**, not a checkbox, because it changes what
 * the screen is doing rather than recording a preference — and it says, in words,
 * what pausing did: the view is frozen from a named instant. A paused tail that kept
 * reading would jump the moment it resumed, which is the behaviour the task's
 * acceptance criterion exists to forbid.
 *
 * The window is capped at the tail's own retention by construction: the options are
 * 1, 5 and 15 minutes and the API refuses anything wider than the retention (T-407's
 * 900 s default), so the picker cannot offer a span the server would reject.
 */
import { Button } from '../../../components/ui';
import { LOG_LEVELS, type LogLevel } from '../api';
import { TAIL_SPANS, type TailSpan } from '../cluster';
import type { LogFilters } from '../hooks';

export interface TailControlsProps {
  paused: boolean;
  pausedAt: Date | null;
  onPause: (paused: boolean) => void;
  span: TailSpan;
  onSpan: (key: TailSpan['key']) => void;
  filters: LogFilters;
  onFilters: (filters: LogFilters) => void;
  /** The window actually being read, in words. */
  windowLabel: string;
}

export function TailControls({
  paused,
  pausedAt,
  onPause,
  span,
  onSpan,
  filters,
  onFilters,
  windowLabel,
}: TailControlsProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <Button
        variant={paused ? 'primary' : 'secondary'}
        size="sm"
        aria-pressed={paused}
        onClick={() => onPause(!paused)}
      >
        {paused ? 'Resume tail' : 'Pause tail'}
      </Button>

      <p className="text-caption text-muted">
        {paused
          ? `Paused${pausedAt === null ? '' : ` at ${pausedAt.toISOString().slice(11, 19)}Z`} — the window below is frozen and nothing is being read.`
          : `Live · ${windowLabel}`}
      </p>

      <div className="flex items-center gap-2">
        <label className="text-caption text-muted" htmlFor="log-span">
          Window
        </label>
        <select
          id="log-span"
          value={span.key}
          onChange={(event) => onSpan(event.target.value as TailSpan['key'])}
          className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
        >
          {TAIL_SPANS.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-caption text-muted" htmlFor="log-level">
          Level
        </label>
        <select
          id="log-level"
          value={filters.level}
          onChange={(event) =>
            onFilters({ ...filters, level: event.target.value as LogLevel | 'all' })
          }
          className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
        >
          <option value="all">All levels</option>
          {LOG_LEVELS.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
