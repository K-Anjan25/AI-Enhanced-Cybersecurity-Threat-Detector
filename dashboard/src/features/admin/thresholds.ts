/**
 * The threshold panel's derived model (T-410, design.md §4.8, FR-18/R-69).
 *
 * design.md §4.8 asks for four things per threshold — the current value, its source,
 * who last changed it and when — and one thing before saving: *a preview of how many
 * alerts the new value would have produced over the last 7 days*. The preview is the
 * part worth encoding carefully, because a preview is a claim about the past:
 *
 *   * **The number is the server's, and it arrives with its window.** `ThresholdImpact`
 *     carries `window_start`/`window_end` and `alerts_read`, so the panel can print
 *     "of the 412 alerts recorded between X and Y" rather than a bare count that
 *     invites being read as a forecast.
 *   * **The unit is alerts, not events.** A row stands for a case and its
 *     `occurrence_count` says how many occurrences went into it — the correlator
 *     groups before it bands (T-308), so the panel says so.
 *   * **`complete: false` is not a total.** When the walk hit its page cap the
 *     counts are a floor, and the sentence says "at least".
 *
 * The band table is built from the *stored* rows plus FR-13's documented defaults,
 * which is exactly what the server's `defaults` map is for: a band with no row is
 * governed by the default, so the panel shows it as `default` rather than as absent.
 */
import { formatStamp } from '../../lib/format';
import type { Threshold, ThresholdImpact, ThresholdList } from '../../api/admin';

/** FR-13's bands, worst first, which is the order the correlator bands in. */
export const BANDS: readonly string[] = ['critical', 'high', 'medium', 'low'];

/** `info` has no lower bound to move: everything below `low` is `info`. */
export const BAND_WITHOUT_BOUND = 'info';

/** design.md §4.8's three source names, as a value and a label. */
export const SOURCE_DEFAULT = 'default';
export const SOURCE_CALIBRATED = 'calibrated';
export const SOURCE_MANUAL = 'manual';

export interface BandRow {
  band: string;
  label: string;
  /** The lower bound in force, from a row or from FR-13's default. */
  value: number;
  /** `default`, `calibrated` or `manual`. */
  source: string;
  sourceLabel: string;
  /** Who last moved it, or the sentence for a value nobody moved here. */
  changedBy: string;
  updatedAt: string;
  /** True when a row exists, i.e. this is a value the deployment moved. */
  moved: boolean;
}

const BAND_LABELS: Readonly<Record<string, string>> = {
  critical: 'Critical (≥)',
  high: 'High (≥)',
  medium: 'Medium (≥)',
  low: 'Low (≥)',
};

const SOURCE_TEXT: Readonly<Record<string, string>> = {
  default: 'FR-13 documented default',
  calibrated: 'Fitted by the recalibration job (T-322)',
  manual: 'Set by hand',
};

/** The value at the precision a band edge is quoted at. */
export function formatThreshold(value: number): string {
  return value.toFixed(2);
}

/**
 * The four bands with the value in force for each, per family.
 *
 * A family with no row at all still gets four rows, all `default`: returning
 * nothing would make "this family has never been recalibrated" look like "this
 * family has no thresholds", and the two are opposite facts.
 */
export function bandRows(list: ThresholdList | undefined, family: string): BandRow[] {
  if (list === undefined) return [];
  return BANDS.map((band) => {
    const stored: Threshold | undefined = list.items.find(
      (row) => row.family === family && row.band === band,
    );
    const fallback = list.defaults[band] ?? 0;
    const source = stored === undefined ? SOURCE_DEFAULT : stored.source_label || stored.source;
    return {
      band,
      label: BAND_LABELS[band] ?? band,
      value: stored?.value ?? fallback,
      source: source === 'recalculation' ? SOURCE_CALIBRATED : source,
      sourceLabel: SOURCE_TEXT[source] ?? source,
      changedBy:
        stored === undefined
          ? 'not changed on this deployment'
          : (stored.changed_by ?? 'not recorded in the trail'),
      updatedAt: stored === undefined ? '' : formatStamp(stored.updated_at),
      moved: stored !== undefined,
    };
  });
}

/** The families the deployment has moved a threshold for, alphabetical. */
export function knownFamilies(list: ThresholdList | undefined): string[] {
  const families = new Set<string>();
  for (const row of list?.items ?? []) families.add(row.family);
  return [...families].sort();
}

/**
 * What the preview says, as sentences with the numbers already in them.
 *
 * Returned as data rather than as JSX so the same sentences are asserted in the
 * model tests and rendered by the panel — a component that composed its own
 * wording would be a second place for "at least" to be forgotten.
 */
export interface PreviewReading {
  /** The headline: what the proposed value would have produced. */
  headline: string;
  /** What changes from the value in force. */
  change: string;
  /** The window and the unit, which the number is meaningless without. */
  basis: string;
  /** Anything the numbers cannot support, stated rather than implied. */
  caveat: string | null;
}

export function readPreview(impact: ThresholdImpact): PreviewReading {
  const fired = impact.would_fire;
  const floor = impact.complete ? '' : 'at least ';
  const change = raisedText(impact) ?? loweredText(impact) ?? 'The value in force is unchanged.';
  return {
    headline: `${floor}${String(fired)} of the ${String(impact.alerts_read)} recorded alerts would have been banded ${impact.band} or worse.`,
    change,
    basis:
      `Counted over ${formatStamp(impact.window_start)} → ${formatStamp(impact.window_end)}, ` +
      `one per alert row rather than per occurrence: the correlator groups repeats into a case before it bands one (T-308).`,
    caveat: impact.complete
      ? null
      : 'The walk stopped at its page cap, so these are floored counts rather than totals: the window holds more traffic than one read returns.',
  };
}

function raisedText(impact: ThresholdImpact): string | null {
  if (impact.proposed <= impact.current) return null;
  return `Raising ${impact.band} from ${formatThreshold(impact.current)} to ${formatThreshold(impact.proposed)}: ${String(impact.would_stop_firing)} alerts would no longer reach it.`;
}

function loweredText(impact: ThresholdImpact): string | null {
  if (impact.proposed >= impact.current) return null;
  return `Lowering ${impact.band} from ${formatThreshold(impact.current)} to ${formatThreshold(impact.proposed)}: ${String(impact.would_start_firing)} alerts would reach it that do not today.`;
}

/** Whether a proposed value may be sent: a proportion, and a real change. */
export function setReadiness(
  proposed: number | null,
  current: number,
): { ready: boolean; reason: string | null } {
  if (proposed === null) return { ready: false, reason: 'Enter a value to preview.' };
  if (!Number.isFinite(proposed)) {
    return { ready: false, reason: 'A threshold is a number between 0 and 1.' };
  }
  if (proposed <= 0 || proposed >= 1) {
    return { ready: false, reason: 'A threshold is strictly between 0 and 1.' };
  }
  if (proposed === current) {
    return { ready: false, reason: 'This is the value already in force.' };
  }
  return { ready: true, reason: null };
}
