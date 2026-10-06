/**
 * ScoreMeter — design.md §6: "score meter is a 0–1 bar with the band threshold
 * marked".
 *
 * Three things the bar has to get right:
 *
 *   1. **The scale is 0–1**, the score column's own scale (R-38 stores it as
 *      `numeric(5,4)`), so the meter never rescales a score and a score is never
 *      shown on a made-up 0–100.
 *   2. **The threshold is marked and named.** A bar without its threshold cannot be
 *      read: 0.71 is alarming at a 0.6 band and unremarkable at 0.9. The tick is a
 *      position, and the accessible value says in words which side of it the score
 *      falls on — a tick alone would be colour-and-position-only encoding.
 *   3. **It clamps rather than crashes.** A value a hair outside [0, 1] is a
 *      rounding artefact from the pipeline, not an analyst's problem; a bar pinned
 *      to its end still tells the truth. A value that is not a number at all is a
 *      caller bug and throws.
 */
import { type Severity } from './severity';

/** The score is a probability: 0 to 1 inclusive. */
const MIN = 0;
const MAX = 1;

/** Bands are named, not numbered, so the meter cannot imply a scale it lacks. */
export type ScoreBand = 'below' | 'at-or-above';

export interface ScoreMeterProps {
  /** The model score, 0–1. Out-of-range values are clamped; non-finite throws. */
  score: number;
  /** The active threshold the score is compared against, 0–1. */
  threshold?: number | undefined;
  /** What is being scored, e.g. "Lateral movement attempt". Names the meter. */
  label: string;
  /** The band the meter is coloured by. Defaults to the accent. */
  tone?: Severity | 'accent';
}

const TONE_FILL: Record<Severity | 'accent', string> = {
  critical: 'bg-severity-critical',
  high: 'bg-severity-high',
  medium: 'bg-severity-medium',
  low: 'bg-severity-low',
  info: 'bg-severity-info',
  benign: 'bg-severity-benign',
  accent: 'bg-accent',
};

function clamp(value: number, what: string): number {
  if (!Number.isFinite(value)) {
    throw new RangeError(`${what} must be a number, got ${String(value)}`);
  }
  return Math.min(MAX, Math.max(MIN, value));
}

/** Whether the score reaches its band. Exported so a caller cannot disagree. */
export function scoreBand(score: number, threshold: number): ScoreBand {
  return score >= threshold ? 'at-or-above' : 'below';
}

/** Two decimals: the precision the score column stores, and no more. */
function fixed(value: number): string {
  return value.toFixed(2);
}

export function ScoreMeter({ score, threshold, label, tone = 'accent' }: ScoreMeterProps) {
  const value = clamp(score, 'score');
  const band = threshold === undefined ? undefined : clamp(threshold, 'threshold');
  const banded = band === undefined ? undefined : scoreBand(value, band);

  // What a screen reader hears: the number, the threshold, and the comparison in
  // words. The visual tick is decoration on top of this, not a substitute.
  const valueText =
    banded === undefined
      ? `${fixed(value)} of 1`
      : `${fixed(value)} of 1, ${banded === 'at-or-above' ? 'at or above' : 'below'} the ` +
        `${fixed(band as number)} threshold`;

  return (
    <div className="flex items-center gap-2">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        aria-valuenow={value}
        aria-valuetext={valueText}
        className="relative h-row-compact w-full overflow-hidden rounded-input border border-line bg-surface"
      >
        <div
          className={`h-full ${TONE_FILL[tone]}`}
          // A width is a value, not a token: it is the score itself. The clamp
          // above keeps it inside the track.
          style={{ width: `${value * 100}%` }}
        />
        {banded === undefined ? null : (
          <div
            aria-hidden="true"
            className="absolute inset-y-0 w-1 bg-ink"
            // The threshold's position on the same 0–1 scale.
            style={{ left: `${(band as number) * 100}%` }}
          />
        )}
      </div>
      <span className="text-caption tabular-nums text-ink">{fixed(value)}</span>
    </div>
  );
}
