/**
 * The version table (design.md §4.7, FR-30).
 *
 * A row is a version; the columns are what the design asks for — id, kind, status,
 * manifest, who promoted it and when. Two rules are rendered rather than implied:
 *
 *   * **A version that cannot be promoted says why, in the row.** A disabled button
 *     with no explanation teaches an operator nothing; the reason is visible text
 *     (`promotionRefusal`), so R-63's manifest rule and R-68's terminal `retired`
 *     are learned from the table instead of from a 409.
 *   * **The id is shortened on screen and complete in the accessible name.** The full
 *     64-character content address appears in the cell's `title` and in the button's
 *     label, because the promotion modal asks the operator to type it: a screen that
 *     hid the id behind an abbreviation and then demanded it would be a puzzle.
 */
import { Badge, Button, DataTable, type Column } from '../../../components/ui';
import type { VersionRow } from '../versions';

export interface VersionTableProps {
  rows: readonly VersionRow[];
  /** Open the promotion modal for this version. */
  onPromote: (row: VersionRow) => void;
}

export function VersionTable({ rows, onPromote }: VersionTableProps) {
  const columns: readonly Column<VersionRow>[] = [
    {
      id: 'model_id',
      header: 'Version',
      sortValue: (row) => row.id,
      cell: (row) => (
        <code className="font-mono text-body-sm" title={`${row.id} (content address, R-68)`}>
          {row.shortId}
        </code>
      ),
    },
    {
      id: 'kind',
      header: 'Kind',
      sortValue: (row) => row.kind,
      cell: (row) => row.kindLabel,
    },
    {
      id: 'status',
      header: 'Status',
      sortValue: (row) => row.status,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <Badge tone={row.statusTone}>{row.statusLabel}</Badge>
          {/*
            The badge is a word; the sentence is what makes it mean something. Only
            the serving version gets one, and it is the fact an operator needs before
            promoting anything — which model is answering requests right now.
          */}
          {row.servingNote === null ? null : (
            <span className="text-body-sm text-muted">{row.servingNote}</span>
          )}
        </span>
      ),
    },
    {
      id: 'manifest',
      header: 'Training manifest',
      sortValue: (row) => row.manifestLabel,
      cell: (row) => (
        <span className={row.version.manifest_present ? 'text-muted' : 'text-severityText-high'}>
          {row.manifestLabel}
        </span>
      ),
    },
    {
      id: 'promoted_by',
      header: 'Promoted by',
      sortValue: (row) => row.promotedBy,
      cell: (row) => row.promotedBy,
    },
    {
      id: 'promoted_at',
      header: 'Promoted at',
      sortValue: (row) => row.promotedAt,
      cell: (row) => <span className="text-muted">{row.promotedAt}</span>,
    },
    {
      id: 'action',
      header: 'Promotion',
      cell: (row) =>
        row.promotable ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              onPromote(row);
            }}
            aria-label={`Promote ${row.id}`}
          >
            Promote…
          </Button>
        ) : (
          <span className="text-body-sm text-muted">{row.promotableReason}</span>
        ),
    },
  ];

  return (
    <DataTable
      caption="Registered model versions"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      rowLabel={(row) => `${row.kindLabel} model ${row.id}`}
    />
  );
}
