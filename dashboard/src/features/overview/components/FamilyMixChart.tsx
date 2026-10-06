/**
 * Threat family mix — horizontal bars, sorted descending, counts at the bar end
 * (design.md §4.1, §7).
 *
 * §7 also says the count is labelled *at the bar end*, which is why the bars carry
 * Chart.js' datalabels plugin rather than relying on a tooltip: a tooltip is a
 * hover, and a number you have to hover for is not a labelled number.
 *
 * The sort happens once, in `familyMixConfig`, and the table alternative renders
 * the same array — so the chart and the table can never disagree about the order.
 */
import { useMemo, useState } from 'react';

import { Badge, Button, Card, type Severity } from '../../../components/ui';
import { familyMixConfig, type FamilyBar } from '../charts';
import { type ChartPalette } from '../palette';
import { ChartCanvas } from './ChartCanvas';

export interface FamilyMixChartProps {
  families: readonly FamilyBar[];
  /** Peak severity per family. A family with no rated severity is absent, and the
   * table shows the neutral chip rather than inventing a band. */
  peaks: Readonly<Record<string, Severity>>;
  windowLabel: string;
  /** Just the range, for the empty sentence. */
  rangeLabel: string;
  palette: ChartPalette;
  reducedMotion: boolean;
  state: 'ready' | 'loading' | 'empty' | 'error';
  onRetry?: (() => void) | undefined;
}

export function FamilyMixChart({
  families,
  peaks,
  windowLabel,
  rangeLabel,
  palette,
  reducedMotion,
  state,
  onRetry,
}: FamilyMixChartProps) {
  const [asTable, setAsTable] = useState(false);
  const config = useMemo(
    () => familyMixConfig(families, palette, { reducedMotion }),
    [families, palette, reducedMotion],
  );
  const sorted = useMemo(
    () => [...families].sort((a, b) => b.count - a.count || a.family.localeCompare(b.family)),
    [families],
  );

  return (
    <Card
      title="Threat family mix"
      state={state}
      loadingLines={5}
      actions={
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={asTable}
          aria-controls="family-mix-table"
          onClick={() => setAsTable((open) => !open)}
        >
          {asTable ? 'View as chart' : 'View as table'}
        </Button>
      }
      empty={{
        title: `No families in the ${rangeLabel}.`,
        description: 'No alert named a family in this window.',
      }}
      {...(onRetry === undefined
        ? {}
        : {
            error: {
              message: 'The family mix could not be loaded',
              detail: 'It reads the same alert window as the tiles.',
              action: <Button onClick={onRetry}>Retry</Button>,
            },
          })}
    >
      <p className="mb-2 text-caption text-muted">{windowLabel}</p>
      {asTable ? (
        <table id="family-mix-table" className="w-full border-collapse text-body-sm">
          <caption className="sr-only">Threat family mix, {windowLabel}, as a table</caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className="py-2 pr-4 font-semibold">
                Family
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Alerts
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Peak severity
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((family) => (
              <tr key={family.family} className="border-b border-line/50">
                <th scope="row" className="py-1 pr-4 text-left font-normal text-ink">
                  {family.family}
                </th>
                <td className="py-1 pr-4 tabular-nums text-ink">{family.count}</td>
                <td className="py-1 pr-4">
                  <Badge tone={peaks[family.family] ?? 'neutral'}>
                    {peaks[family.family] ?? 'unrated'}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ChartCanvas
          config={config}
          label={`Threat family mix, ${windowLabel}: horizontal bars of alert counts. The same numbers are available as a table.`}
        />
      )}
    </Card>
  );
}
