/**
 * @vitest-environment node
 */
/**
 * The drift model (T-409, FR-32).
 *
 * The threshold and the metric name are not this file's to invent, so the first two
 * tests read the specification's own copies of them: `ml-service`'s
 * `PSI_DRIFT_THRESHOLD` and `METRIC_NAME`, and architecture.md's alert rule. If either
 * moves, this suite fails before a screen can draw a threshold nobody published.
 *
 * The boundary cases are the point of the rest: `measure_drift` decides with
 * `value > threshold`, so exactly 0.25 is *not* drifting, and a screen that used `>=`
 * would mark a feature the backend considers stable. `driftDomainMax` and the
 * clamping are tested because the mark's position is the acceptance criterion — a
 * threshold drawn at a fixed fraction of the axis means something different on every
 * chart.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import type { Sample } from '../../lib/prometheus';
import {
  DRIFT_ABSENT_NOTE,
  DRIFT_FEATURE_LABEL,
  DRIFT_METRIC,
  DRIFT_THRESHOLD,
  RETRAIN_BADGE,
  driftBars,
  driftDomainMax,
  driftView,
  formatPsi,
} from './drift';

function psi(feature: string, value: number): Sample {
  return { name: DRIFT_METRIC, labels: { [DRIFT_FEATURE_LABEL]: feature }, value };
}

const driftSource = readFileSync(
  fileURLToPath(new URL('../../../../ml-service/aegis_ml/scoring/drift.py', import.meta.url)),
  'utf8',
);
const architecture = readFileSync(
  fileURLToPath(new URL('../../../../architecture.md', import.meta.url)),
  'utf8',
);
const design = readFileSync(
  fileURLToPath(new URL('../../../../design.md', import.meta.url)),
  'utf8',
);

describe('the specification’s numbers, not this file’s', () => {
  it('mirrors the ml-service threshold', () => {
    const match = /^PSI_DRIFT_THRESHOLD = ([\d.]+)$/m.exec(driftSource);
    expect(match, 'PSI_DRIFT_THRESHOLD is not a literal in drift.py').not.toBeNull();
    expect(Number(match?.[1])).toBe(DRIFT_THRESHOLD);
    expect(DRIFT_THRESHOLD).toBe(0.25);
  });

  it('mirrors the ml-service metric name and the architecture’s alert rule', () => {
    expect(driftSource).toContain(`METRIC_NAME = "${DRIFT_METRIC}"`);
    expect(architecture).toContain('aegis_drift_psi{feature}');
    expect(architecture).toContain('drift PSI > 0.25');
  });

  it('uses the same strict comparison the drift computation uses', () => {
    // `measure_drift` writes `drifted=value > threshold`. A client that used `>=`
    // would mark a feature the backend calls stable, so the operator would be told to
    // retrain on a boundary the pipeline does not act on.
    expect(driftSource).toContain('drifted=value > threshold');
    expect(driftBars([psi('state', 0.25)])[0]?.drifting).toBe(false);
    expect(driftBars([psi('state', 0.250001)])[0]?.drifting).toBe(true);
  });

  it('uses the badge wording the design publishes', () => {
    expect(design).toContain('retrain recommended');
    expect(RETRAIN_BADGE).toBe('retrain recommended');
  });
});

describe('driftDomainMax', () => {
  it('floors the domain at 1 so a small vocabulary cannot compress the mark', () => {
    expect(driftDomainMax([])).toBe(1);
    expect(driftDomainMax([0.05, 0.2])).toBe(1);
  });

  it('rounds up to a 1/2/5 step of a decade', () => {
    expect(driftDomainMax([1.2])).toBe(2);
    expect(driftDomainMax([3])).toBe(5);
    expect(driftDomainMax([7])).toBe(10);
    expect(driftDomainMax([26.667])).toBe(50);
  });
});

describe('driftBars', () => {
  it('keeps only the drift series and only labelled features', () => {
    const samples: Sample[] = [
      { name: 'aegis_alerts_created_total', labels: {}, value: 12 },
      { name: DRIFT_METRIC, labels: {}, value: 9 },
      psi('state', 0.4),
    ];
    expect(driftBars(samples).map((bar) => bar.feature)).toEqual(['state']);
  });

  it('orders the worst first, breaking ties on the feature name', () => {
    const bars = driftBars([psi('b', 0.5), psi('a', 0.5), psi('c', 0.9)]);
    expect(bars.map((bar) => bar.feature)).toEqual(['c', 'a', 'b']);
  });

  it('places the threshold on the same scale as the bars', () => {
    const bars = driftBars([psi('state', 3)]);
    expect(bars[0]?.fraction).toBeCloseTo(0.6, 10); // 3 of a domain rounded up to 5
    expect(bars[0]?.thresholdFraction).toBeCloseTo(0.05, 10); // 0.25 of the same 5
  });

  it('never lets a bar overflow its track', () => {
    const bars = driftBars([psi('state', 26.667)]);
    expect(bars[0]?.fraction).toBeLessThanOrEqual(1);
    expect(bars[0]?.valueText).toBe('26.6670');
  });

  it('formats PSI the way the report does', () => {
    expect(formatPsi(0.051082562)).toBe('0.0511');
  });
});

describe('driftView', () => {
  it('counts what is over the threshold and reports the domain once', () => {
    const view = driftView([psi('state', 26.667), psi('service', 3.9367), psi('fin', 0.01)]);
    expect(view.drifting).toBe(2);
    expect(view.domainMax).toBe(50);
    expect(view.thresholdFraction).toBeCloseTo(0.005, 10);
    expect(view.absent).toBe(false);
    expect(view.absentNote).toBeNull();
  });

  it('says which series is missing and what has to happen, rather than drawing an axis', () => {
    const view = driftView([{ name: 'aegis_alerts_created_total', labels: {}, value: 3 }]);
    expect(view.absent).toBe(true);
    expect(view.bars).toEqual([]);
    expect(view.absentNote).toBe(DRIFT_ABSENT_NOTE);
    expect(view.absentNote).toContain('aegis_drift_psi');
    expect(view.absentNote).toContain('T-421');
  });
});
