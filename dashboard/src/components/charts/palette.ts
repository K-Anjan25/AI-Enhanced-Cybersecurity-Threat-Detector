/**
 * Reading the theme's colours for a chart — canvas or SVG.
 *
 * Chart.js wants colour strings, and an SVG needs them too; design.md §5 wants
 * every colour to come from a token. So the chart asks the *document* for the value of the variables it uses
 * (`--severity-critical`, …) rather than carrying any of them itself, and the
 * theme switch keeps working without the chart knowing what a theme is.
 *
 * The subtlety is **when** the read happens. `ThemeProvider` writes `data-theme`
 * on `<html>` in a passive effect, and React runs effects children-first, so a
 * child that re-read the computed styles on a theme change would read the theme
 * that is one paint behind. Rather than guess at ordering, this hook watches the
 * attribute itself and re-reads when it actually changes: whatever sets the
 * attribute, the chart follows.
 *
 * It lives in the components layer because two features read it — the overview's
 * Chart.js panels (T-403) and the traffic explorer's SVG series and graph (T-406) —
 * and a feature may not import another feature. It is not in `lib` because it is
 * React.
 */
import { useEffect, useState } from 'react';

import type { Severity } from '../ui/severity';

/** The CSS variable each severity hue is published under (design.md §5.3). */
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

export interface ChartPalette extends Record<Severity, string> {
  muted: string;
  grid: string;
}

/**
 * A CSS colour that is valid when no stylesheet is loaded.
 *
 * Reached only outside a styled document — jsdom in a node test, or a page whose
 * stylesheet failed to load — and it is deliberately a *valid* colour so that a
 * canvas draw is never handed something it cannot parse. It is not a fallback
 * palette: inventing hues here would put colour outside the token layer.
 */
const UNSTYLED = 'transparent';

function readVariable(name: string): string {
  if (typeof window === 'undefined' || typeof window.getComputedStyle !== 'function') {
    return UNSTYLED;
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value === '' ? UNSTYLED : value;
}

/** The palette as the document currently defines it. */
export function readPalette(): ChartPalette {
  const palette = {
    muted: readVariable(CHART_VARIABLES.text),
    grid: readVariable(CHART_VARIABLES.grid),
  } as ChartPalette;
  for (const [severity, variable] of Object.entries(SEVERITY_VARIABLES)) {
    palette[severity as Severity] = readVariable(variable);
  }
  return palette;
}

/** Increments whenever `data-theme` changes, whoever changed it. */
export function useThemeRevision(): number {
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return undefined;
    const observer = new MutationObserver(() => setRevision((value) => value + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => observer.disconnect();
  }, []);

  return revision;
}

/** The palette, kept in step with the applied theme. */
export function useChartPalette(): ChartPalette {
  const revision = useThemeRevision();
  const [palette, setPalette] = useState<ChartPalette>(readPalette);

  useEffect(() => {
    setPalette(readPalette());
  }, [revision]);

  return palette;
}
