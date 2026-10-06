/**
 * Audit log — design.md §4.8: "append-only, filterable, exportable, visibly
 * non-editable (no edit affordance anywhere)" (FR-42, R-37).
 *
 * The panel is a reader: no control here writes, and the sentence above the table says
 * so, because "where is the edit button" is the question a reader of an audit screen
 * asks first. The window is bounded because the route bounds it (R-34), and it is
 * stated on screen so an empty table is never mistaken for a quiet system.
 *
 * The export is generated from the rows on screen (`auditCsv`), so what leaves the
 * browser is what was read — a second query would be a claim about the trail that
 * nobody had in front of them. The download itself is the hunt console's mechanism
 * (T-408): a Blob URL and a synthetic anchor, revoked immediately.
 *
 * One structural note, because it is a bug this panel had: the three states are
 * rendered *inside* the body rather than through the card's own `state` prop. Every
 * keystroke in a filter is a new query key, and a card that swapped its children for a
 * skeleton on `isPending` would unmount the filter fields mid-typing — the first
 * character would land and the rest would go to a detached input. The filters stay
 * mounted, and R-29 is met by the body's own loading, empty and error renderings.
 */
import { useMemo, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  DataTable,
  ErrorState,
  Skeleton,
  type Column,
} from '../../../components/ui';
import { FILTER_MARK } from '../../../lib/keyboard';
import {
  AUDIT_ACTION_CHOICES,
  DEFAULT_AUDIT_HOURS,
  auditCsv,
  auditNote,
  auditRows,
  type AuditRow,
} from '../audit';
import { useAudit } from '../hooks';

const PAGE_SIZE = 50;

export function AuditPanel() {
  const [hours, setHours] = useState(DEFAULT_AUDIT_HOURS);
  const [action, setAction] = useState('');
  const [actor, setActor] = useState('');
  const [target, setTarget] = useState('');
  const [before, setBefore] = useState<number | null>(null);

  // The window is derived from one instant, held in state: recomputing `now` on every
  // render would change the query key on every render and refetch forever.
  const [anchor, setAnchor] = useState(() => new Date());
  const { start, end } = useMemo(() => {
    const upper = anchor;
    const lower = new Date(upper.getTime() - hours * 3_600_000);
    return { start: lower, end: upper };
  }, [anchor, hours]);

  const audit = useAudit({
    start,
    end,
    ...(action === '' ? {} : { action }),
    ...(actor.trim() === '' ? {} : { actor: actor.trim() }),
    ...(target.trim() === '' ? {} : { targetId: target.trim() }),
    ...(before === null ? {} : { before }),
    limit: PAGE_SIZE,
  });

  const rows = auditRows(audit.data?.items);
  const nextBefore = audit.data?.next_before ?? null;

  const columns: readonly Column<AuditRow>[] = [
    {
      id: 'at',
      header: 'When',
      sortValue: (row) => row.at,
      cell: (row) => <span className="text-body-sm">{row.at}</span>,
    },
    {
      id: 'actor',
      header: 'Actor',
      sortValue: (row) => row.actor,
      cell: (row) => row.actor,
    },
    {
      id: 'action',
      header: 'Action',
      sortValue: (row) => row.action,
      cell: (row) => <code className="font-mono text-body-sm">{row.action}</code>,
    },
    {
      id: 'target',
      header: 'Target',
      sortValue: (row) => row.target,
      cell: (row) => <code className="font-mono text-body-sm">{row.target}</code>,
    },
    {
      id: 'detail',
      header: 'Context',
      sortValue: (row) => row.detail,
      cell: (row) => <span className="font-mono text-body-sm text-muted">{row.detail}</span>,
    },
    {
      id: 'ip',
      header: 'Source IP',
      sortValue: (row) => row.ip,
      cell: (row) => <span className="font-mono text-body-sm">{row.ip}</span>,
      hiddenByDefault: true,
    },
    {
      id: 'id',
      header: 'Trail id',
      sortValue: (row) => row.id,
      cell: (row) => <span className="font-mono text-body-sm">{row.id}</span>,
      hiddenByDefault: true,
    },
  ];

  const download = (): void => {
    const url = URL.createObjectURL(new Blob([auditCsv(rows)], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'aegis-audit.csv';
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <Card
      title="Audit log"
      actions={
        <div className="flex items-center gap-2">
          <label className="text-body-sm text-muted" htmlFor="audit-hours">
            Window
          </label>
          <select
            id="audit-hours"
            className="rounded-control border border-line bg-base px-2 py-1 text-body-sm"
            value={hours}
            onChange={(event) => {
              setHours(Number(event.target.value));
              setBefore(null);
              setAnchor(new Date());
            }}
          >
            <option value={1}>last hour</option>
            <option value={24}>last 24 hours</option>
            <option value={168}>last 7 days</option>
          </select>
          <Button size="sm" variant="secondary" disabled={rows.length === 0} onClick={download}>
            Export CSV
          </Button>
          <Button
            size="sm"
            variant="secondary"
            loading={audit.isFetching}
            onClick={() => {
              setBefore(null);
              setAnchor(new Date());
            }}
          >
            Reload
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-body-sm">
            Action
            <select
              className="rounded-control border border-line bg-base px-2 py-1 text-body-sm"
              value={action}
              onChange={(event) => {
                setAction(event.target.value);
                setBefore(null);
              }}
            >
              {AUDIT_ACTION_CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-body-sm">
            Actor
            <input
              {...FILTER_MARK}
              value={actor}
              onChange={(event) => {
                setActor(event.target.value);
                setBefore(null);
              }}
              className="w-full rounded-control border border-line bg-base px-2 py-1 text-body"
              placeholder="who did it"
            />
          </label>
          <label className="flex flex-col gap-1 text-body-sm">
            Target id
            <input
              value={target}
              onChange={(event) => {
                setTarget(event.target.value);
                setBefore(null);
              }}
              className="w-full rounded-control border border-line bg-base px-2 py-1 text-body"
              placeholder="the row it touched"
            />
          </label>
        </div>
        {audit.isError ? (
          <ErrorState
            message="The audit trail could not be read"
            detail={
              'Nothing is shown rather than an empty table: an audit screen that rendered a failed read as "no actions" would be reporting the opposite of what it knows.'
            }
            action={
              <Button
                onClick={() => {
                  setAnchor(new Date());
                }}
              >
                Retry
              </Button>
            }
            retrying={audit.isFetching}
          />
        ) : null}
        {audit.isPending || audit.isError ? (
          <Skeleton lines={6} label="Audit trail is loading" />
        ) : null}
        {audit.isPending || audit.isError ? null : (
          <p className="text-body-sm text-muted" data-testid="audit-note">
            {auditNote(rows.length, nextBefore !== null)}
          </p>
        )}
        {audit.isSuccess && nextBefore !== null ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setBefore(nextBefore);
            }}
          >
            Older entries in this window
          </Button>
        ) : null}
        {audit.isPending || audit.isError ? null : (
          <DataTable
            caption="Recorded actions, newest first"
            columns={columns}
            rows={rows}
            rowKey={(row) => String(row.id)}
            rowLabel={(row) => `${row.action} at ${row.at}`}
            height={420}
            empty={
              <p className="text-body" data-testid="audit-empty">
                No recorded action falls in this window with these filters. That is an answer about
                the filters as much as about the system: widen the window before concluding nothing
                happened.
              </p>
            }
          />
        )}
        <p className="text-body-sm text-muted">
          <Badge tone="neutral">read-only</Badge> There is no edit or delete affordance on this
          screen, in any role: the trail is append-only at the store and the API has no route that
          would change a row of it.
        </p>
      </div>
    </Card>
  );
}
