/**
 * @vitest-environment node
 */
/**
 * The chart configurations, asserted as data.
 *
 * A canvas cannot be asserted on in any useful way — it is pixels — so the parts
 * that can be *wrong* about a chart are decided in `charts.ts` and checked here:
 * the series order, the stacking, §7's "y-axis starts at 0 — never truncate a count
 * axis", the axis titles that carry the units, the descending family order, and the
 * animation duration design.md §8.2 publishes. The colours are checked to be token
 * references rather than values, which is R-27's rule applied to a canvas.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import {
  CHART_ANIMATION_MS,
  CHART_VARIABLES,
  familyMixConfig,
  SEVERITY_VARIABLES,
  seriesOrder,
  severityAreaConfig,
  type SeverityPoint,
} from './charts';
import { readPalette } from './palette';

const css = readFileSync(fileURLToPath(new URL('../../index.css', import.meta.url)), 'utf8');

const COLOURS = {
  critical: 'rgb(1, 1, 1)',
  high: 'rgb(2, 2, 2)',
  medium: 'rgb(3, 3, 3)',
  low: 'rgb(4, 4, 4)',
  info: 'rgb(5, 5, 5)',
  benign: 'rgb(6, 6, 6)',
  muted: 'rgb(7, 7, 7)',
  grid: 'rgb(8, 8, 8)',
};

const POINTS: SeverityPoint[] = [
  { label: '00:00', counts: { high: 2, medium: 1 } },
  { label: '01:00', counts: { critical: 1, high: 3 } },
];

describe('seriesOrder', () => {
  it('shows only the severities with data, most serious first', () => {
    expect(seriesOrder(POINTS, ['critical', 'high', 'medium', 'low', 'info', 'benign'])).toEqual([
      'critical',
      'high',
      'medium',
    ]);
  });

  it('is empty when no severity has data', () => {
    expect(seriesOrder([{ label: '00:00', counts: {} }], ['critical'])).toEqual([]);
  });
});

/** The scale shape this suite asserts on, out of Chart.js' union of all scales. */
interface ScaleLike {
  stacked?: boolean;
  beginAtZero?: boolean;
  title?: { text?: string };
}

function scale(config: { options?: unknown }, axis: 'x' | 'y'): ScaleLike {
  const options = config.options as { scales?: Record<string, ScaleLike> } | undefined;
  const found = options?.scales?.[axis];
  expect(found, `the ${axis} scale is configured`).toBeDefined();
  return found as ScaleLike;
}

describe('severityAreaConfig', () => {
  const config = severityAreaConfig(POINTS, COLOURS, { reducedMotion: false });

  it('is a line chart with one dataset per severity present', () => {
    expect(config.type).toBe('line');
    expect(config.data.datasets.map((dataset) => dataset.label)).toEqual([
      'critical',
      'high',
      'medium',
    ]);
  });

  it('pads a severity that is absent in some buckets with zeroes', () => {
    // The datasets must be the same length as the labels, or Chart.js draws the
    // series against the wrong intervals.
    for (const dataset of config.data.datasets) {
      expect(dataset.data).toHaveLength(POINTS.length);
    }
    expect(config.data.datasets[0]?.data).toEqual([0, 1]);
    expect(config.data.datasets[2]?.data).toEqual([1, 0]);
  });

  it('stacks both axes, so the areas add up to the total', () => {
    expect(scale(config, 'x').stacked).toBe(true);
    expect(scale(config, 'y').stacked).toBe(true);
  });

  it('starts the count axis at zero (§7) and labels both axes with units', () => {
    expect(scale(config, 'y').beginAtZero).toBe(true);
    expect(scale(config, 'y').title?.text).toBe('alerts');
    expect(scale(config, 'x').title?.text).toBe('time (local)');
  });

  it('uses the colours it is given, one per severity', () => {
    expect(config.data.datasets[0]?.borderColor).toBe(COLOURS.critical);
    expect(config.data.datasets[1]?.borderColor).toBe(COLOURS.high);
  });

  it('draws straight segments, not a curve through invented values', () => {
    expect(config.data.datasets.every((dataset) => dataset.tension === 0)).toBe(true);
  });

  it('honours prefers-reduced-motion', () => {
    const still = severityAreaConfig(POINTS, COLOURS, { reducedMotion: true });

    expect(still.options?.animation).toBe(false);
    expect(config.options?.animation).toEqual({ duration: CHART_ANIMATION_MS });
  });
});

describe('familyMixConfig', () => {
  const families = [
    { family: 'Brute force', count: 31 },
    { family: 'DDoS', count: 41 },
    { family: 'Recon', count: 41 },
  ];
  const config = familyMixConfig(families, COLOURS, { reducedMotion: false });

  it('is a horizontal bar chart, sorted descending', () => {
    expect(config.type).toBe('bar');
    expect(config.options?.indexAxis).toBe('y');
    expect(config.data.labels).toEqual(['DDoS', 'Recon', 'Brute force']);
    expect(config.data.datasets[0]?.data).toEqual([41, 41, 31]);
  });

  it('does not mutate the caller’s array', () => {
    const input = [...families];

    familyMixConfig(input, COLOURS, { reducedMotion: false });

    expect(input.map((family) => family.family)).toEqual(['Brute force', 'DDoS', 'Recon']);
  });

  it('starts the count axis at zero and labels it', () => {
    expect(scale(config, 'x').beginAtZero).toBe(true);
    expect(scale(config, 'x').title?.text).toBe('alerts');
    expect(scale(config, 'y').title?.text).toBe('family');
  });

  it('labels the count at the bar end (§7)', () => {
    const datalabels = config.options?.plugins?.datalabels as
      { anchor?: string; align?: string; formatter?: (value: number) => string } | undefined;

    expect(datalabels?.anchor).toBe('end');
    expect(datalabels?.align).toBe('end');
    expect(datalabels?.formatter?.(41)).toBe('41');
  });

  it('drops the legend, because there is one series and the axis names it', () => {
    expect(config.options?.plugins?.legend?.display).toBe(false);
  });
});

describe('the colours come from the token layer', () => {
  it('names a CSS variable for every severity', () => {
    expect(Object.keys(SEVERITY_VARIABLES).sort()).toEqual([
      'benign',
      'critical',
      'high',
      'info',
      'low',
      'medium',
    ]);
  });

  it('names variables the stylesheet actually declares', () => {
    for (const variable of [
      ...Object.values(SEVERITY_VARIABLES),
      ...Object.values(CHART_VARIABLES),
    ]) {
      expect(css, `${variable} is declared`).toContain(`${variable}:`);
    }
  });

  it('resolves to nothing rather than a literal when no stylesheet is applied', () => {
    // jsdom in a node test has the CSS import stubbed out. A transparent chart is
    // honest; an invented fallback hue would put colour outside the token layer.
    const palette = readPalette();

    expect(palette.critical).toBe('transparent');
    expect(palette.muted).toBe('transparent');
  });

  it('animates for the panel duration §8.2 publishes, not a number of its own', () => {
    expect(css).toContain(`--duration-panel: ${String(CHART_ANIMATION_MS)}ms;`);
  });
});
