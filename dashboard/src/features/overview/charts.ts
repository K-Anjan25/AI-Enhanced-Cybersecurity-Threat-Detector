/**
 * Chart.js configuration, built as plain data.
 *
 * The charts live behind canvas, which a test cannot read and a screen reader
 * cannot see, so everything that could be *wrong* about them is decided here, in
 * functions that return a configuration object, and asserted in a node test: the
 * series order, the stacked flag, "y-axis starts at 0 — never truncate a count
 * axis" (§7), the axis titles carrying their units, and the label at the end of
 * each bar.
 *
 * **Colours are resolved from the theme, not written here.** A chart drawn with a
 * literal would keep its dark-theme hue in the light theme, and §5's tokens are
 * the only place a colour is allowed to exist (R-27). Each dataset names the CSS
 * variable it wants; `resolvePalette` reads the computed value at draw time.
 */
import type { ChartConfiguration } from 'chart.js';

import type { Severity } from '../../components/ui/severity';

/** The severity palette as CSS variables (design.md §5.1). */
export const SEVERITY_VARIABLES: Record<Severity, string> = {
  critical: '--severity-critical',
  high: '--severity-high',
  medium: '--severity-medium',
  low: '--severity-low',
  info: '--severity-info',
  benign: '--severity-benign',
};

/** Chart text and grid, from the same tokens the rest of the UI uses. */
export const CHART_VARIABLES = {
  text: '--color-text-muted',
  grid: '--color-border',
} as const;

/**
 * How long a chart's own transition lasts.
 *
 * design.md §8.2 publishes 200 ms for panels, so the chart uses the panel
 * duration rather than a number of its own — and the chart test asserts this
 * matches `--duration-panel` in `src/index.css`.
 */
export const CHART_ANIMATION_MS = 200;

/**
 * The severity hues plus the two neutrals the axes and legends use.
 *
 * Structural, so `ChartPalette` — which also carries the text and grid colours a
 * chart needs for its ticks and labels — satisfies it without a cast.
 */
export interface SeverityColours extends Record<Severity, string> {
  muted: string;
  grid: string;
}

/** One x-axis label with its per-severity counts. */
export interface SeverityPoint {
  label: string;
  counts: Partial<Record<Severity, number>>;
}

/** Which severities a series actually shows, most serious first. */
export function seriesOrder(
  points: readonly SeverityPoint[],
  order: readonly Severity[],
): Severity[] {
  return order.filter((severity) => points.some((point) => (point.counts[severity] ?? 0) > 0));
}

/**
 * A stacked area chart of alert volume by severity.
 *
 * `stacked` on both axes is what makes the areas add up to the total; `beginAtZero`
 * is §7's rule for a count axis, and it is set on the *stacked* scale so no series
 * can be drawn against a truncated one.
 */
export function severityAreaConfig(
  points: readonly SeverityPoint[],
  colours: SeverityColours,
  options: { reducedMotion: boolean },
): ChartConfiguration<'line'> {
  const order: Severity[] = ['critical', 'high', 'medium', 'low', 'info', 'benign'];
  const shown = seriesOrder(points, order);

  return {
    type: 'line',
    data: {
      labels: points.map((point) => point.label),
      datasets: shown.map((severity) => ({
        label: severity,
        data: points.map((point) => point.counts[severity] ?? 0),
        borderColor: colours[severity],
        backgroundColor: colours[severity],
        fill: true,
        // Straight segments: an alert count is a count per interval, and a curve
        // between two intervals implies values the data never had.
        tension: 0,
        pointRadius: 0,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: options.reducedMotion ? false : { duration: CHART_ANIMATION_MS },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          stacked: true,
          title: { display: true, text: 'time (local)' },
          ticks: { color: colours.muted },
          grid: { color: colours.grid },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          title: { display: true, text: 'alerts' },
          ticks: { color: colours.muted },
          grid: { color: colours.grid },
        },
      },
      plugins: {
        legend: { labels: { color: colours.muted } },
        tooltip: { enabled: true },
      },
    },
  };
}

/** One family bar. */
export interface FamilyBar {
  family: string;
  count: number;
}

/**
 * The threat family mix: horizontal bars, sorted descending, counts at the bar end.
 *
 * The sort is applied here rather than left to the caller so the chart and the
 * table alternative cannot disagree about the order.
 */
export function familyMixConfig(
  families: readonly FamilyBar[],
  colours: SeverityColours,
  options: { reducedMotion: boolean },
): ChartConfiguration<'bar'> {
  const sorted = [...families].sort(
    (a, b) => b.count - a.count || a.family.localeCompare(b.family),
  );

  return {
    type: 'bar',
    data: {
      labels: sorted.map((family) => family.family),
      datasets: [
        {
          label: 'alerts',
          data: sorted.map((family) => family.count),
          backgroundColor: colours.medium,
          borderWidth: 0,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: options.reducedMotion ? false : { duration: CHART_ANIMATION_MS },
      // A count axis starts at zero: a bar chart that truncates its axis
      // exaggerates every difference on it (§7).
      scales: {
        x: {
          beginAtZero: true,
          title: { display: true, text: 'alerts' },
          ticks: { color: colours.muted, precision: 0 },
          grid: { color: colours.grid },
        },
        y: {
          title: { display: true, text: 'family' },
          ticks: { color: colours.muted },
          grid: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        // §7: "counts labelled at bar end".
        datalabels: {
          anchor: 'end',
          align: 'end',
          color: colours.muted,
          formatter: (value: number): string => String(value),
        },
      },
    },
  };
}
