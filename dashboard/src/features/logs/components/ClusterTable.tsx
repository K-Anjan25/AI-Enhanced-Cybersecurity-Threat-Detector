/**
 * The clustered tail: one row per template, with the count that replaces the lines.
 *
 * Two things here are design.md §4.5's, and one is a decision:
 *
 *   * The **count** is the row's headline (`×10,000`), because the whole point of the
 *     fold is that ten thousand identical lines are one thing to read.
 *   * The **rail** marks a cluster holding an error or critical line. §4.5 asks for
 *     the severity colour *and* a left border — colour alone would fail NFR-09 — so
 *     the level chip carries the same hue and the glyph the palette publishes. The
 *     rail is drawn inside the first cell: `DataTable` renders its rows as divs with
 *     no row-class hook, and adding one to a shared primitive for a single screen
 *     would be the tail wagging the component. A short vertical rule at the row's
 *     left edge reads the same way.
 *   * The **sample** is the newest line in the cluster, shown beside the template so
 *     a reader can tell two similar templates apart without opening either.
 */
import { useMemo } from 'react';

import { Badge, Button, DataTable, type Column } from '../../../components/ui';
import type { LogRow } from '../view';

export interface ClusterTableProps {
  rows: readonly LogRow[];
  /** The cluster whose raw lines are open below, so the button can say so. */
  openKey: string | null;
  onOpen: (key: string | null) => void;
  /** Rendered in place of the table's own empty state. */
  empty: React.ReactNode;
}

export function ClusterTable({ rows, openKey, onOpen, empty }: ClusterTableProps) {
  const columns = useMemo<Column<LogRow>[]>(() => {
    const level: Column<LogRow> = {
      id: 'level',
      header: 'Level',
      sortValue: (row) => row.level,
      cell: (row) => (
        <span className={row.notable ? 'border-l-4 border-l-severity-high pl-2' : 'pl-2'}>
          <Badge tone={row.tone}>{row.level}</Badge>
          {/* The rail is a second, non-colour affordance for the same fact; these are
              the words that make it a third, for a reader who sees neither. */}
          {row.notable ? <span className="sr-only"> (error or worse)</span> : null}
        </span>
      ),
    };
    const template: Column<LogRow> = {
      id: 'template',
      header: 'Template',
      sortValue: (row) => row.template,
      cell: (row) => (
        <span className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={openKey === row.key}
            aria-controls="log-raw-lines"
            onClick={() => onOpen(openKey === row.key ? null : row.key)}
          >
            {row.template}
          </Button>
          <span
            className="truncate font-mono text-caption text-muted"
            title={row.cluster.sample_message}
          >
            {row.cluster.sample_message}
          </span>
        </span>
      ),
    };
    return [
      level,
      template,
      {
        id: 'count',
        header: 'Lines',
        sortValue: (row) => row.cluster.count,
        cell: (row) => <span className="tabular-nums font-semibold">{row.count}</span>,
      },
      {
        id: 'levels',
        header: 'Levels',
        sortValue: (row) => row.levels,
        cell: (row) => <span className="text-muted">{row.levels}</span>,
      },
      {
        id: 'span',
        header: 'Span (UTC)',
        sortValue: (row) => row.cluster.first_seen,
        cell: (row) => <span className="tabular-nums">{row.span}</span>,
      },
      {
        id: 'hosts',
        header: 'Hosts',
        hiddenByDefault: true,
        cell: (row) => <span className="text-muted">{row.hosts}</span>,
      },
      {
        id: 'services',
        header: 'Services',
        hiddenByDefault: true,
        cell: (row) => <span className="text-muted">{row.services}</span>,
      },
    ];
  }, [onOpen, openKey]);

  return (
    <DataTable
      caption="Log clusters in the tail's window"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.key}
      rowLabel={(row) => `${row.template}, ${row.count} lines`}
      empty={empty}
    />
  );
}
