/**
 * The address table (design.md §4.4's "entity table … with alert counts, sortable").
 *
 * Two things changed with T-418, and both are visible on the screen:
 *
 *   * **The entity is an address.** The flow read model counts an entity by address —
 *     that is the key `flow@1` carries and the only key the traffic and the alert sides
 *     can be joined on — so the table names what the traffic names: `10.0.0.7`, not
 *     `entity_id 42`. Alerts whose entity value is *not* an address are counted in no
 *     row here, and the panel's caveats say why.
 *   * **The volume is traffic.** "Flows" and "Bytes" are ingested records and their
 *     bytes; "Alerts" is the alert-side join. A reader can tell which is which because
 *     they are separate columns with separate headers, not one number with one story.
 *
 * It is still built on `DataTable`: §6 says the primitives are the only approved
 * building blocks, and the virtualised, sortable, sticky-header behaviour the analyst
 * expects from every other table in the product comes from using the same one (R-22,
 * R-27).
 */
import { Badge, DataTable, SeverityPill, type Column } from '../../../components/ui';
import { formatBytes, formatCount, formatSince } from '../../../lib/format';
import type { TrafficNode } from '../aggregate';

export interface EntityTableProps {
  entities: readonly TrafficNode[];
  pinnedId: string | null;
  onPin: (id: string) => void;
  /** A clock for the "last seen" column, so ages tick with the rest of the screen. */
  now?: number;
}

export function EntityTable({ entities, pinnedId, onPin, now = Date.now() }: EntityTableProps) {
  const columns: readonly Column<TrafficNode>[] = [
    {
      id: 'address',
      header: 'Address',
      cell: (row) => (
        <button
          type="button"
          onClick={() => onPin(row.id)}
          aria-pressed={pinnedId === row.id}
          className="rounded-input text-left tabular-nums text-ink hover:text-accent"
        >
          {row.id}
          {pinnedId === row.id ? ' · pinned' : ''}
        </button>
      ),
      sortValue: (row) => row.id,
    },
    {
      id: 'flows',
      header: 'Flows',
      cell: (row) => <span className="tabular-nums">{formatCount(row.flows)}</span>,
      sortValue: (row) => row.flows,
    },
    {
      id: 'bytes',
      header: 'Bytes',
      cell: (row) => <span className="tabular-nums">{formatBytes(row.bytes)}</span>,
      sortValue: (row) => row.bytes,
    },
    {
      id: 'direction',
      header: 'In / out',
      cell: (row) => (
        <span className="tabular-nums">
          {formatCount(row.inbound)} / {formatCount(row.outbound)}
        </span>
      ),
      sortValue: (row) => row.outbound,
      hiddenByDefault: true,
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
        row.peakSeverity !== null ? (
          <SeverityPill severity={row.peakSeverity} />
        ) : row.alerts > 0 ? (
          // An alert exists but its band is not one this build knows: saying "no alert"
          // here would be wrong, and colouring it would be a severity the pipeline
          // never assigned.
          <Badge tone="neutral">unrecognised</Badge>
        ) : (
          <Badge tone="neutral">no alert</Badge>
        ),
      sortValue: (row) => row.peakSeverity ?? (row.alerts > 0 ? 'zz-unrecognised' : 'zz-no-alert'),
    },
    {
      id: 'score',
      header: 'Max score',
      cell: (row) =>
        row.maxScore === null ? (
          <span className="text-muted">—</span>
        ) : (
          <span className="tabular-nums">{row.maxScore.toFixed(2)}</span>
        ),
      sortValue: (row) => row.maxScore ?? -1,
      hiddenByDefault: true,
    },
    {
      id: 'open',
      header: 'Open alerts',
      cell: (row) => <span className="tabular-nums">{formatCount(row.openAlerts)}</span>,
      sortValue: (row) => row.openAlerts,
      hiddenByDefault: true,
    },
    {
      id: 'last-seen',
      header: 'Last seen',
      cell: (row) =>
        row.lastSeen === null ? (
          <span className="text-muted">—</span>
        ) : (
          formatSince(row.lastSeen, now)
        ),
      sortValue: (row) => (row.lastSeen === null ? 0 : Date.parse(row.lastSeen)),
    },
  ];

  return (
    <DataTable
      caption="Addresses in the window, by flow count"
      columns={columns}
      rows={entities}
      rowKey={(row) => row.id}
      height={320}
      empty={
        <p className="text-body-sm text-muted">
          No addresses in this selection. Widen the brush, or lower the flow threshold.
        </p>
      }
    />
  );
}
