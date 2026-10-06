/**
 * The entity table (design.md §4.4: "entity table (host / user / service) with alert
 * counts, sortable").
 *
 * Two deviations, both deliberate and both visible on screen:
 *
 *   * **The entity is an id.** The alert API returns `entity_id` and no host or user
 *     value, so this table cannot print one; the gap is T-416's (the aggregation
 *     endpoint that also names entities), and it is named in the column header rather
 *     than left to look like a number that happens to be an id.
 *   * **It is built on `DataTable`**, not on a `<table>` written here: §6 says the
 *     primitives are the only approved building blocks, and the virtualised, sortable,
 *     sticky-header behaviour the analyst expects from every other table in the
 *     product comes from using the same one (R-22, R-27).
 */
import { Badge, DataTable, SeverityPill, type Column } from '../../../components/ui';
import { formatCount, formatSince } from '../../../lib/format';
import type { EntityRow } from '../aggregate';

export interface EntityTableProps {
  entities: readonly EntityRow[];
  pinnedEntityId: number | null;
  onPin: (entityId: number) => void;
  /** A clock for the "last seen" column, so ages tick with the rest of the screen. */
  now?: number;
}

export function EntityTable({
  entities,
  pinnedEntityId,
  onPin,
  now = Date.now(),
}: EntityTableProps) {
  const columns: readonly Column<EntityRow>[] = [
    {
      id: 'entity',
      header: 'Entity (id)',
      cell: (row) => (
        <button
          type="button"
          onClick={() => onPin(row.entityId)}
          aria-pressed={pinnedEntityId === row.entityId}
          className="rounded-input text-left text-ink hover:text-accent"
        >
          {row.entityId}
          {pinnedEntityId === row.entityId ? ' · pinned' : ''}
        </button>
      ),
      sortValue: (row) => row.entityId,
    },
    {
      id: 'records',
      header: 'Records',
      cell: (row) => <span className="tabular-nums">{formatCount(row.records)}</span>,
      sortValue: (row) => row.records,
    },
    {
      id: 'alerts',
      header: 'Alerts',
      cell: (row) => <span className="tabular-nums">{formatCount(row.alerts)}</span>,
      sortValue: (row) => row.alerts,
    },
    {
      id: 'severity',
      header: 'Peak severity',
      cell: (row) =>
        row.peakSeverity === null ? (
          <Badge tone="neutral">unrecognised</Badge>
        ) : (
          <SeverityPill severity={row.peakSeverity} />
        ),
      sortValue: (row) => row.peakSeverity ?? 'zz-unrecognised',
    },
    {
      id: 'families',
      header: 'Families',
      cell: (row) => row.families.join(', '),
      sortValue: (row) => row.families.join(','),
    },
    {
      id: 'status',
      header: 'Open',
      cell: (row) => (row.hasOpen ? 'yes' : 'no'),
      sortValue: (row) => (row.hasOpen ? 1 : 0),
      hiddenByDefault: true,
    },
    {
      id: 'last-seen',
      header: 'Last seen',
      cell: (row) => formatSince(row.lastSeen, now),
      sortValue: (row) => Date.parse(row.lastSeen),
    },
  ];

  return (
    <DataTable
      caption="Entities in the brushed window, by alerted record volume"
      columns={columns}
      rows={entities}
      rowKey={(row) => String(row.entityId)}
      height={320}
      empty={
        <p className="text-body-sm text-muted">
          No entities in this selection. Widen the brush, or lower the record threshold.
        </p>
      }
    />
  );
}
