/**
 * Alert volume by severity — the stacked area chart (design.md §4.1, §7).
 *
 * Chart.js draws it (D-007), and §9 requires a data-table alternative "toggled by
 * a 'view as table' control", so the table is a real, keyboard-reachable control
 * and not a visually-hidden afterthought: the numbers behind the chart are one
 * press away for anyone who cannot read the canvas — including a screen reader,
 * which gets nothing at all from the pixels.
 *
 * The chart is not brushable yet. §4.1 says it should be, and brushing is T-406's
 * task; the gap is recorded in D-060 rather than faked with a control that does
 * nothing.
 */
import { useMemo, useState } from 'react';

import { Button, Card } from '../../../components/ui';
import { SEVERITIES, SEVERITY_LABELS } from '../../../components/ui';
import { severityAreaConfig, type SeverityPoint } from '../charts';
import { type ChartPalette } from '../palette';
import { ChartCanvas } from './ChartCanvas';

export interface SeverityAreaChartProps {
  points: readonly SeverityPoint[];
  /** The window's description, for the panel's caption — "Last 24 h · 3 alerts read". */
  windowLabel: string;
  /** Just the range — "Last 24 h" — for the empty sentence. */
  rangeLabel: string;
  palette: ChartPalette;
  reducedMotion: boolean;
  state: 'ready' | 'loading' | 'empty' | 'error';
  onRetry?: (() => void) | undefined;
}

export function SeverityAreaChart({
  points,
  windowLabel,
  rangeLabel,
  palette,
  reducedMotion,
  state,
  onRetry,
}: SeverityAreaChartProps) {
  const [asTable, setAsTable] = useState(false);
  const config = useMemo(
    () => severityAreaConfig(points, palette, { reducedMotion }),
    [points, palette, reducedMotion],
  );

  const shown = SEVERITIES.filter((severity) =>
    points.some((point) => (point.counts[severity] ?? 0) > 0),
  );

  return (
    <Card
      title="Alert volume by severity"
      state={state}
      loadingLines={6}
      actions={
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={asTable}
          aria-controls="severity-area-table"
          onClick={() => setAsTable((open) => !open)}
        >
          {asTable ? 'View as chart' : 'View as table'}
        </Button>
      }
      empty={{
        title: `No alerts in the ${rangeLabel}.`,
        description: 'Widen the range to see activity.',
      }}
      {...(onRetry === undefined
        ? {}
        : {
            error: {
              message: 'Alert volume could not be loaded',
              detail: 'The alert window did not arrive; the tiles show the same failure.',
              action: <Button onClick={onRetry}>Retry</Button>,
            },
          })}
    >
      <p className="mb-2 text-caption text-muted">{windowLabel}</p>
      {asTable ? (
        <table id="severity-area-table" className="w-full border-collapse text-body-sm">
          <caption className="sr-only">Alert volume by severity, {windowLabel}, as a table</caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className="py-2 pr-4 font-semibold">
                Interval
              </th>
              {shown.map((severity) => (
                <th key={severity} scope="col" className="py-2 pr-4 font-semibold">
                  {SEVERITY_LABELS[severity]}
                </th>
              ))}
              <th scope="col" className="py-2 pr-4 font-semibold">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={point.label} className="border-b border-line/50">
                <th scope="row" className="py-1 pr-4 text-left font-normal text-muted">
                  {point.label}
                </th>
                {shown.map((severity) => (
                  <td key={severity} className="py-1 pr-4 tabular-nums text-ink">
                    {point.counts[severity] ?? 0}
                  </td>
                ))}
                <td
                  className="py-1 pr-4 tabular-nums text-ink"
                  data-testid={`total-${String(index)}`}
                >
                  {shown.reduce((total, severity) => total + (point.counts[severity] ?? 0), 0)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ChartCanvas
          config={config}
          label={`Alert volume by severity, ${windowLabel}: a stacked area chart. The same numbers are available as a table.`}
        />
      )}
    </Card>
  );
}
