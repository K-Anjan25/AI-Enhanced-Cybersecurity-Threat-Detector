/**
 * The hunt's results: an ordinary table, with the columns an analyst can switch.
 *
 * Built on `DataTable` (§6's rule that every table in the product is the same
 * primitive), which is also where the column picker comes from — the low-value
 * columns are `hiddenByDefault` and the picker in the toolbar brings them back. The
 * alert's own id links to the triage screen, addressed by both halves of its key
 * (D-030), because the most likely next act after finding an alert in a hunt is to
 * triage it.
 *
 * The severity cell is a `SeverityPill` carrying the level's own word: a hunt shows
 * what the correlator banded, and this build's model does not re-score old rows. An
 * unrecognised severity is printed as it arrived rather than coloured as something it
 * is not.
 */
import { Link } from 'react-router-dom';

import { DataTable, SeverityPill, type Column } from '../../../components/ui';
import { alertHrefFor } from '../../../lib/routes';
import type { HuntRow } from '../view';

export interface ResultsTableProps {
  rows: readonly HuntRow[];
  /** Rendered in place of the table's own empty state — the console's executed query. */
  empty: React.ReactNode;
}

export function ResultsTable({ rows, empty }: ResultsTableProps) {
  const columns: Column<HuntRow>[] = [
    {
      id: 'severity',
      header: 'Severity',
      sortValue: (row) => row.severityLabel,
      cell: (row) =>
        row.severity === 'unrecognised' ? (
          <span className="text-caption text-muted">unrecognised: {row.severityLabel}</span>
        ) : (
          <SeverityPill severity={row.severity} />
        ),
    },
    {
      id: 'family',
      header: 'Family',
      sortValue: (row) => row.family,
      cell: (row) => <span className="font-mono text-body-sm">{row.family}</span>,
    },
    {
      id: 'entity',
      header: 'Entity',
      sortValue: (row) => row.row.entity_id,
      cell: (row) => <span className="font-mono tabular-nums">{row.entity}</span>,
    },
    {
      id: 'score',
      header: 'Score',
      sortValue: (row) => row.row.score,
      cell: (row) => <span className="tabular-nums">{row.score}</span>,
    },
    {
      id: 'created',
      header: 'Created (UTC)',
      sortValue: (row) => row.row.created_at,
      cell: (row) => (
        <Link
          className="text-accent underline-offset-2 hover:underline"
          to={alertHrefFor(row.row.id, row.row.created_at)}
        >
          {row.created}
        </Link>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      sortValue: (row) => row.status,
      cell: (row) => <span className="text-muted">{row.status}</span>,
    },
    {
      id: 'occurrences',
      header: 'Occurrences',
      sortValue: (row) => row.row.occurrence_count,
      cell: (row) => <span className="tabular-nums">{row.occurrences}</span>,
    },
    {
      id: 'id',
      header: 'ID',
      sortValue: (row) => row.row.id,
      cell: (row) => <span className="font-mono tabular-nums">{row.id}</span>,
    },
    {
      id: 'first-seen',
      header: 'First seen (UTC)',
      hiddenByDefault: true,
      cell: (row) => <span className="tabular-nums">{row.firstSeen}</span>,
    },
    {
      id: 'last-seen',
      header: 'Last seen (UTC)',
      hiddenByDefault: true,
      cell: (row) => <span className="tabular-nums">{row.lastSeen}</span>,
    },
    {
      id: 'trace',
      header: 'Trace',
      hiddenByDefault: true,
      cell: (row) => <span className="font-mono text-caption">{row.trace}</span>,
    },
  ];

  return (
    <DataTable
      caption="Alerts matching this hunt"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      rowLabel={(row) => `${row.severityLabel} ${row.family} on entity ${row.entity}`}
      empty={empty}
    />
  );
}
