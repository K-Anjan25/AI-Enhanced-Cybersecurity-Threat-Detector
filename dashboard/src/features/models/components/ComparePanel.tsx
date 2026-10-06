/**
 * Version comparison (design.md §4.7).
 *
 * "Two models side by side, delta per metric" is what the read model can support, and
 * that is what this panel does. The design also asks for confusion matrices and
 * score-distribution histograms; FR-31's metrics are five scalars with provenance and
 * nothing in the API carries either, so the panel **says so** in `comparison.note`
 * instead of drawing a plausible-looking plot from numbers nobody measured. The gap is
 * filed as T-420.
 *
 * A delta is computed only where both sides have the metric: differencing a value
 * against a missing one would be arithmetic on a hole, and the row renders "not
 * comparable" so the absence is visible rather than a zero that reads as "no change".
 */
import { useMemo, useState } from 'react';

import { Card, DataTable, type Column } from '../../../components/ui';
import { useModelMetrics } from '../hooks';
import { compareVersions, type ComparisonCell, type VersionRow } from '../versions';

export interface ComparePanelProps {
  rows: readonly VersionRow[];
}

export function ComparePanel({ rows }: ComparePanelProps) {
  const active = rows.find((row) => row.status === 'active') ?? rows[0] ?? null;
  const other = rows.find((row) => row.id !== active?.id) ?? null;
  // The operator's explicit choice, or `null` for "whatever the table defaults to".
  // Kept as a choice rather than as an initial value because the rows arrive after the
  // first render: a state initialised from an empty list would pin both sides to
  // nothing and never recover.
  const [chosenLeft, setChosenLeft] = useState<string | null>(null);
  const [chosenRight, setChosenRight] = useState<string | null>(null);
  const leftId = chosenLeft ?? active?.id ?? null;
  const rightId = chosenRight ?? other?.id ?? null;

  const left = rows.find((row) => row.id === leftId) ?? null;
  const right = rows.find((row) => row.id === rightId) ?? null;

  // Fetch only what the listing did not carry: a version whose metrics came with the
  // list costs no request, and one without them costs exactly one.
  const leftFetch = useModelMetrics(leftId, left !== null && left.version.metrics === null);
  const rightFetch = useModelMetrics(rightId, right !== null && right.version.metrics === null);

  const comparison = useMemo(
    () =>
      compareVersions(
        left?.version.metrics ?? leftFetch.data ?? null,
        right?.version.metrics ?? rightFetch.data ?? null,
      ),
    [left, right, leftFetch.data, rightFetch.data],
  );

  const columns: readonly Column<ComparisonCell>[] = [
    { id: 'metric', header: 'Metric', sortValue: (cell) => cell.label, cell: (cell) => cell.label },
    {
      id: 'left',
      header: `A · ${left?.shortId ?? '—'}`,
      cell: (cell) => (cell.left === null ? 'not recorded' : cell.left.toFixed(4)),
    },
    {
      id: 'right',
      header: `B · ${right?.shortId ?? '—'}`,
      cell: (cell) => (cell.right === null ? 'not recorded' : cell.right.toFixed(4)),
    },
    {
      id: 'delta',
      header: 'Delta (B − A)',
      cell: (cell) => (
        <span className={cell.direction === 'unknown' ? 'text-muted' : 'font-mono tabular-nums'}>
          {cell.deltaText}
        </span>
      ),
    },
  ];

  const picker = (
    label: string,
    value: string | null,
    onChange: (id: string) => void,
    id: string,
  ): JSX.Element => (
    <label htmlFor={id} className="flex flex-col gap-1 text-caption text-muted">
      {label}
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => {
          onChange(event.currentTarget.value);
        }}
        className="h-8 rounded-input border border-line bg-base px-2 text-body-sm text-ink"
      >
        {rows.map((row) => (
          <option key={row.id} value={row.id}>
            {row.shortId} · {row.kindLabel} · {row.statusLabel}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <Card
      title="Version comparison"
      actions={
        <div className="flex items-end gap-3">
          {picker('Version A', left?.id ?? null, setChosenLeft, 'compare-left')}
          {picker('Version B', right?.id ?? null, setChosenRight, 'compare-right')}
        </div>
      }
    >
      {rows.length < 2 ? (
        <p className="p-4 text-body text-muted">
          A comparison needs two registered versions; this registry has{' '}
          {rows.length === 0 ? 'none' : 'one'}.
        </p>
      ) : (
        <>
          <DataTable
            caption="Metric comparison between two model versions"
            columns={columns}
            rows={comparison.cells}
            rowKey={(cell) => cell.name}
          />
          <p className="px-4 py-3 text-caption text-muted">{comparison.note}</p>
          {left !== null && right !== null && left.id === right.id ? (
            <p className="px-4 pb-3 text-caption text-muted">
              Both sides name the same version, so every delta is zero by construction.
            </p>
          ) : null}
        </>
      )}
    </Card>
  );
}
