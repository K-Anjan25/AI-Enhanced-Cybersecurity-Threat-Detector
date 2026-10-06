/**
 * The drift screen's derived model: PSI per feature, against FR-32's threshold (T-409).
 *
 * The numbers are not fetched from a JSON endpoint, because there is not one: PSI is
 * computed by `ml-service` (T-211) and published as the gauge `aegis_drift_psi{feature}`,
 * exactly as architecture.md §14 names it. The screen therefore reads the Prometheus
 * scrape through `src/api/metrics.ts` — the same document and the same reader the
 * overview's pipeline strip uses (D-060), so the drift page and a Grafana panel cannot
 * disagree about what "PSI" is.
 *
 * Three rules are encoded here:
 *
 *   * **The threshold is one number, and it is not re-declared.** FR-32 fixes it at
 *     0.25; `ml-service/aegis_ml/scoring/drift.py` holds `PSI_DRIFT_THRESHOLD = 0.25`
 *     and decides `drifted = psi > threshold`. The comparison here is *strictly
 *     greater* for that reason, and a test reads both the Python constant and
 *     architecture.md's alert rule and fails if either moves without this file.
 *   * **The threshold is drawn on the same scale as the bars.** A mark at a fixed
 *     pixel offset would stop meaning anything the moment a feature drifted past the
 *     axis top, and PSI has no upper bound — the UNSW→CIC measurement reaches 26.7
 *     (D-025). So the domain is chosen from the data and the mark's position is
 *     computed from it.
 *   * **No series is a fact, not an empty chart.** The gauge is published by the
 *     drift job, and this deployment has nothing that observes it in the process
 *     serving `/metrics` (filed as T-421). When the scrape carries no
 *     `aegis_drift_psi`, the screen says exactly that instead of drawing an axis
 *     with nothing on it — "no news" and "not measured" must not look the same.
 */
import type { Sample } from '../../lib/prometheus';

/** The gauge architecture.md §14 fixes. */
export const DRIFT_METRIC = 'aegis_drift_psi';

/** FR-32's threshold. Mirrors `PSI_DRIFT_THRESHOLD`; a test pins the two together. */
export const DRIFT_THRESHOLD = 0.25;

/** The label the gauge carries the feature name in. */
export const DRIFT_FEATURE_LABEL = 'feature';

export interface DriftBar {
  feature: string;
  value: number;
  /** `value > DRIFT_THRESHOLD`, the same rule `measure_drift` applies. */
  drifting: boolean;
  /** The value as it renders. PSI is unbounded, so it renders wide when it is. */
  valueText: string;
  /** The bar's width as a fraction of the domain, clamped to `[0, 1]`. */
  fraction: number;
  /** Where the threshold sits on the same domain, as a fraction. */
  thresholdFraction: number;
}

export interface DriftView {
  bars: DriftBar[];
  /** The domain top the bars and the threshold are drawn against. */
  domainMax: number;
  /** Where FR-32's threshold sits on that domain, as a fraction in `[0, 1]`. */
  thresholdFraction: number;
  /** How many features are over the threshold. */
  drifting: number;
  /** What to render when there are no bars: why, and what has to happen. */
  absentNote: string | null;
  /** True when the scrape carried no drift series at all. */
  absent: boolean;
}

/** PSI at the precision the drift report prints (four decimals, as T-211 does). */
export function formatPsi(value: number): string {
  return value.toFixed(4);
}

/**
 * The domain top: a round number at or above the largest reading.
 *
 * Rounded up to 1, 2 or 5 times a power of ten so the axis reads in round units, and
 * floored at `1` so the 0.25 mark is never compressed into the first few pixels by a
 * vocabulary of small readings. A reading above the top cannot happen — the top is
 * derived from the readings — but `Math.max` keeps it true if a caller passes a
 * domain it computed elsewhere.
 */
export function driftDomainMax(values: readonly number[]): number {
  const largest = Math.max(0, ...values);
  const target = Math.max(largest, 1);
  const magnitude = 10 ** Math.floor(Math.log10(target));
  for (const step of [1, 2, 5, 10]) {
    const candidate = step * magnitude;
    if (candidate >= target) return candidate;
  }
  return 10 * magnitude;
}

/** Read the gauge's samples into bars. Unknown labels are skipped, never guessed. */
export function driftBars(samples: readonly Sample[]): DriftBar[] {
  const readings: { feature: string; value: number }[] = [];
  for (const sample of samples) {
    if (sample.name !== DRIFT_METRIC) continue;
    const feature = sample.labels[DRIFT_FEATURE_LABEL];
    if (feature === undefined || feature === '') continue;
    readings.push({ feature, value: sample.value });
  }
  // Worst first: the screen exists to answer "what moved", and a stable feature at
  // the top of a long list is a feature nobody reads.
  readings.sort((left, right) =>
    left.value === right.value
      ? left.feature.localeCompare(right.feature)
      : right.value - left.value,
  );
  const domainMax = driftDomainMax(readings.map((reading) => reading.value));
  const thresholdFraction = DRIFT_THRESHOLD / domainMax;
  return readings.map((reading) => ({
    feature: reading.feature,
    value: reading.value,
    drifting: reading.value > DRIFT_THRESHOLD,
    valueText: formatPsi(reading.value),
    fraction: Math.min(1, Math.max(0, reading.value / domainMax)),
    thresholdFraction,
  }));
}

/** What the screen says when the scrape carries no drift series. */
export const DRIFT_ABSENT_NOTE =
  'No aegis_drift_psi series is in this scrape, so no PSI has been measured here. The ' +
  'drift job (T-211) publishes the gauge into the process that computes it, and nothing ' +
  'in the process serving /metrics observes it yet (T-421). The bars below are drawn ' +
  'against FR-32’s 0.25 threshold and will fill in as soon as a reading arrives.';

/** Build the view: bars, the domain, the count over threshold, and the absence note. */
export function driftView(samples: readonly Sample[]): DriftView {
  const bars = driftBars(samples);
  const values = bars.map((bar) => bar.value);
  const domainMax = driftDomainMax(values);
  return {
    bars,
    domainMax,
    thresholdFraction: DRIFT_THRESHOLD / domainMax,
    drifting: bars.filter((bar) => bar.drifting).length,
    absentNote: bars.length === 0 ? DRIFT_ABSENT_NOTE : null,
    absent: bars.length === 0,
  };
}

/**
 * The glyph and word a drifting feature carries.
 *
 * A badge rather than colour alone: R-27's contrast rules and NFR-10's non-colour
 * encoding both require the state to survive a monochrome screenshot, and the design
 * asks for the words "retrain recommended".
 */
export const RETRAIN_BADGE = 'retrain recommended';
