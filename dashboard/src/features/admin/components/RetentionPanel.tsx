/**
 * Retention — design.md §4.8: "the plan a run would execute, what a run did, and the
 * stores the policy cannot reach" (NFR-05, T-314).
 *
 * The panel shows the plan *before* the run, which is the whole point of the route
 * existing in two halves. The three lists beside the drop list are what stop the plan
 * reading as a clean bill of health — `missing`, `unevictable`, `external` — and each
 * gets a sentence in `retention.ts` rather than a bare code. Running is destructive, so
 * it goes through `ConfirmDialog`: the plan is a claim about the past, a run is a
 * change to it.
 *
 * Erasure sits here because it is the same policy's other half (NFR-05, R-37): a
 * subject is erased across every store and the ledger keeps a tombstone. The form
 * takes the identifier, which is the one place on this screen an operator types data
 * about a person — and it is not echoed back: the report renders the tombstone only.
 */
import { useState } from 'react';

import { Badge, Button, Card, ConfirmDialog, DataTable, type Column } from '../../../components/ui';
import { useEraseSubject, useRetention, useRunRetention, retentionRefusalMessage } from '../hooks';
import {
  partitionRows,
  readRetention,
  readRun,
  unevictableRows,
  type PartitionRow,
} from '../retention';

export function RetentionPanel() {
  const retention = useRetention();
  const run = useRunRetention();
  const erase = useEraseSubject();
  const [confirming, setConfirming] = useState(false);
  const [kind, setKind] = useState<'user' | 'entity'>('user');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');

  const plan = retention.data;
  const reading = readRetention(plan);
  const drops = partitionRows(plan?.drop);
  const unevictable = unevictableRows(plan?.unevictable);

  const columns: readonly Column<PartitionRow>[] = [
    {
      id: 'name',
      header: 'Partition',
      sortValue: (row) => row.name,
      cell: (row) => <code className="font-mono text-body-sm">{row.name}</code>,
    },
    { id: 'table', header: 'Table', sortValue: (row) => row.table, cell: (row) => row.table },
    { id: 'covers', header: 'Covers', sortValue: (row) => row.covers, cell: (row) => row.covers },
    {
      id: 'statement',
      header: 'Statement a run would execute',
      cell: (row) => <code className="font-mono text-body-sm text-muted">{row.statement}</code>,
      hiddenByDefault: true,
    },
  ];

  return (
    <Card
      title="Retention"
      {...(retention.isError
        ? {}
        : {
            actions: (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={retention.isFetching}
                  onClick={() => {
                    void retention.refetch();
                  }}
                >
                  Re-plan
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={plan === undefined || plan.drop.length === 0}
                  onClick={() => {
                    setConfirming(true);
                  }}
                >
                  Run retention
                </Button>
              </div>
            ),
          })}
      state={retention.isPending ? 'loading' : retention.isError ? 'error' : 'ready'}
      loadingLines={6}
      error={{
        message: 'The retention plan could not be read',
        detail:
          'A run is offered only from a plan this screen has read: dropping partitions on the strength of a failed read is the one way this screen could destroy data it never showed you.',
      }}
    >
      <div className="flex flex-col gap-3">
        <p className="text-body-sm text-muted">
          {reading.policy} Planned at {reading.plannedAt}.
        </p>
        <p className="text-body">
          {reading.drop} {reading.kept}
        </p>
        {reading.warnings.map((warning) => (
          <p key={warning} className="text-body-sm text-severityText-critical" role="status">
            {warning}
          </p>
        ))}
        {retentionRefusalMessage(run.error) === null ? null : (
          <p className="text-body-sm text-severityText-critical" role="alert">
            {retentionRefusalMessage(run.error)}
          </p>
        )}
        {run.isSuccess ? <p className="text-body-sm text-muted">{readRun(run.data)}</p> : null}
        <DataTable
          caption="Partitions a retention run would drop"
          columns={columns}
          rows={drops}
          rowKey={(row) => row.name}
          rowLabel={(row) => row.name}
          height={200}
          empty={
            <p className="text-body">
              Nothing is past its window. A run now would drop no partition and would still be
              recorded in the trail.
            </p>
          }
        />
        {unevictable.length === 0 ? null : (
          <div className="flex flex-col gap-1">
            <h3 className="text-h2">Storage a run cannot reach</h3>
            <ul className="flex flex-col gap-1">
              {unevictable.map((row) => (
                <li key={`${row.table}.${row.name}`} className="text-body-sm">
                  <code className="font-mono">{row.table}</code>
                  <span className="text-muted"> — {row.explains}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-col gap-2 rounded-card border border-line bg-surface p-3">
          <h3 className="text-h2">Erasure</h3>
          <p className="text-body-sm text-muted">
            Erases one subject across every store and records a tombstone in the ledger. The
            identifier is sent, never echoed: the report says the hash, not the person.
          </p>
          <div className="grid gap-2 md:grid-cols-4">
            <label className="flex flex-col gap-1 text-body-sm">
              Kind
              <select
                className="rounded-control border border-line bg-base px-2 py-1 text-body-sm"
                value={kind}
                onChange={(event) => {
                  setKind(event.target.value === 'entity' ? 'entity' : 'user');
                }}
              >
                <option value="user">user</option>
                <option value="entity">entity</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-body-sm">
              Identifier
              <input
                value={value}
                onChange={(event) => {
                  setValue(event.target.value);
                }}
                className="w-full rounded-control border border-line bg-base px-2 py-1 text-body"
              />
            </label>
            <label className="flex flex-col gap-1 text-body-sm">
              Reason (optional, recorded)
              <input
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
                className="w-full rounded-control border border-line bg-base px-2 py-1 text-body"
              />
            </label>
            <Button
              variant="danger"
              loading={erase.isPending}
              disabled={value.trim() === ''}
              onClick={() => {
                erase.mutate({ kind, value: value.trim(), reason: reason.trim() });
              }}
            >
              Erase
            </Button>
          </div>
          {erase.isError ? (
            <p className="text-body-sm text-severityText-critical" role="alert">
              The erasure could not be completed. The stores are not partial: the route reports what
              each one did, so check the trail before retrying.
            </p>
          ) : null}
          {erase.isSuccess ? (
            <p className="text-body-sm">
              Tombstone <code className="font-mono">{erase.data.tombstone}</code> at {erase.data.at}
              : {String(erase.data.affected)} row{erase.data.affected === 1 ? '' : 's'} across{' '}
              {String(erase.data.targets.length)} store{erase.data.targets.length === 1 ? '' : 's'}
              {erase.data.already_erased ? ', already erased once before' : ''}.{' '}
              {erase.data.preserved.length === 0
                ? 'Nothing was preserved.'
                : `Kept: ${erase.data.preserved.map((entry) => `${entry.store} (${entry.reason})`).join('; ')}.`}
            </p>
          ) : null}
          <p className="text-body-sm text-muted">
            <Badge tone="neutral">append-only</Badge> The ledger entry is not deletable, and neither
            is the audit row the erasure writes: erasing a person does not erase the fact that it
            was asked for.
          </p>
        </div>
      </div>

      <ConfirmDialog
        open={confirming}
        title="Run retention now?"
        message={`${String(drops.length)} partition${drops.length === 1 ? '' : 's'} would be dropped, and the rows they hold are gone: ${drops.map((row) => row.name).join(', ')}. The run is recorded in the audit trail.`}
        confirmLabel="Drop the partitions"
        onConfirm={() => {
          run.mutate(undefined, {
            onSuccess: () => {
              setConfirming(false);
            },
          });
        }}
        onClose={() => {
          setConfirming(false);
        }}
      />
    </Card>
  );
}
