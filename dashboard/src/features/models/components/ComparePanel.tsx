/**
 * Version comparison (design.md §4.7).
 *
 * "Two models side by side, delta per metric" is what this panel does. The separate
 * per-version metrics read also carries the recorded eval@2 confusion matrix and score
 * histogram; older or missing artifacts remain visibly unavailable rather than being
 * reverse-engineered from scalar values. Both visual panels show their exact source.
 *
 * A delta is computed only where both sides have the metric: differencing a value
 * against a missing one would be arithmetic on a hole, and the row renders "not
 * comparable" so the absence is visible rather than a zero that reads as "no change".
 */
import { useMemo, useState } from 'react';

import { Card, DataTable, type Column } from '../../../components/ui';
import { useModelMetrics } from '../hooks';
import { compareVersions, type ComparisonCell, type VersionRow } from '../versions';
import { ComparisonEvidence } from './ComparisonEvidence';
import { ScoreHistogramComparison } from './ScoreHistogramComparison';

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

  // The version listing stays small; the per-version endpoint is the authority for
  // metrics and carries evaluation details from the immutable report when available.
  const leftFetch = useModelMetrics(leftId, left !== null);
  const rightFetch = useModelMetrics(rightId, right !== null);
  const leftMetrics = leftFetch.data ?? null;
  const rightMetrics = rightFetch.data ?? null;

  const comparison = useMemo(
    () => compareVersions(leftMetrics, rightMetrics),
    [leftMetrics, rightMetrics],
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
          <div className="grid gap-4 border-t border-line p-4 xl:grid-cols-2">
            <ComparisonEvidence
              side="A"
              modelId={left?.id ?? null}
              evaluation={leftMetrics?.evaluation ?? null}
              loading={left !== null && leftFetch.isFetching}
              error={leftFetch.error ?? null}
            />
            <ComparisonEvidence
              side="B"
              modelId={right?.id ?? null}
              evaluation={rightMetrics?.evaluation ?? null}
              loading={right !== null && rightFetch.isFetching}
              error={rightFetch.error ?? null}
            />
          </div>
          <ScoreHistogramComparison
            left={{
              modelId: left?.id ?? null,
              histogram: leftMetrics?.evaluation?.score_histogram ?? null,
              threshold: leftMetrics?.evaluation?.confusion.threshold ?? null,
              loading: left !== null && leftFetch.isFetching,
              error: leftFetch.error ?? null,
            }}
            right={{
              modelId: right?.id ?? null,
              histogram: rightMetrics?.evaluation?.score_histogram ?? null,
              threshold: rightMetrics?.evaluation?.confusion.threshold ?? null,
              loading: right !== null && rightFetch.isFetching,
              error: rightFetch.error ?? null,
            }}
          />
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
