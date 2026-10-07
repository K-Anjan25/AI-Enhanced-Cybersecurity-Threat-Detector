/**
 * Users and roles — design.md §4.8: "role changes confirmed + audited; last own admin
 * cannot demote"; R-53.
 *
 * The panel renders the server's rule rather than restating it. `active_admins` is the
 * number the 409 is decided by, so the mark on the row and the refusal it explains come
 * from one authority. Two consequences shape the markup:
 *
 *   * **The last admin still gets a control.** Disabling it and saying nothing would
 *     hide the rule; the row carries the sentence, the save button is available, and
 *     the server's refusal is what the operator reads when they try (the 409 maps to a
 *     sentence in `hooks.ts`). Trying and being told is how the rule is learned.
 *   * **A change that changes nothing is reported as a no-op.** `changed: false` means
 *     nothing was written and nothing was audited (D-038), and the panel says exactly
 *     that instead of congratulating itself.
 *
 * design.md §4.8 also asks for role changes to be *confirmed*, so saving goes through a
 * `ConfirmDialog` naming the account and both roles. The confirmation is not decoration:
 * the change is audited under the operator's own name, and "which way round did I set
 * it" is worth one more sentence before an append-only record of it exists.
 */
import { useState } from 'react';

import { Badge, Button, Card, ConfirmDialog, DataTable, type Column } from '../../../components/ui';
import { roleRefusalMessage, useChangeRole, useRoles, useUsers } from '../hooks';
import { roleChangeRequired, roleChoices, userRows, userSummary, type UserRow } from '../users';
import type { RoleChange } from '../../../api/admin';

export function UsersPanel() {
  const users = useUsers();
  const roles = useRoles();
  const change = useChangeRole();
  const [chosen, setChosen] = useState<Record<number, string>>({});
  // The last answer, kept until the next change: a no-op has to be *stated*, because
  // a request that wrote nothing must not look like one that wrote something (D-038).
  const [answered, setAnswered] = useState<RoleChange | null>(null);
  // The change waiting for confirmation: the row, and the role picked for it.
  const [confirming, setConfirming] = useState<{ row: UserRow; role: string } | null>(null);

  const rows = userRows(users.data);
  const choices = roleChoices(roles.data?.items);
  const summary = userSummary(users.data);
  const refusal = roleRefusalMessage(change.error);

  const pick = (id: number, role: string): void => {
    setChosen((current) => ({ ...current, [id]: role }));
  };

  const save = (row: UserRow, role: string): void => {
    change.mutate(
      { userId: row.id, role },
      {
        onSuccess: (result) => {
          setChosen((current) => {
            const next = { ...current };
            delete next[row.id];
            return next;
          });
          setAnswered(result);
        },
      },
    );
  };

  const columns: readonly Column<UserRow>[] = [
    {
      id: 'email',
      header: 'Account',
      sortValue: (row) => row.email,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.email}</span>
          {row.lastActiveAdmin ? (
            // Neutral, not a severity: "the only way in" is a state, not a level on
            // the severity scale, and colouring it like one would put an alert's
            // palette on a governance fact (NFR-09, §5.3).
            <span>
              <Badge tone="neutral">Last active admin</Badge>
            </span>
          ) : null}
          {row.disabled ? (
            <span className="text-body-sm text-muted">
              Disabled {row.disabledAt}: it cannot sign in, and it does not count towards the admin
              floor.
            </span>
          ) : null}
        </span>
      ),
    },
    {
      id: 'role',
      header: 'Role',
      sortValue: (row) => row.role,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.roleLabel}</span>
          {row.demotionRefusal === null ? null : (
            <span className="text-body-sm text-muted">{row.demotionRefusal}</span>
          )}
        </span>
      ),
    },
    {
      id: 'change',
      header: 'Change role to',
      cell: (row) => (
        <span className="flex items-center gap-2">
          <label className="sr-only" htmlFor={`role-${String(row.id)}`}>
            {`New role for ${row.email}`}
          </label>
          <select
            id={`role-${String(row.id)}`}
            className="rounded-control border border-line bg-base px-2 py-1 text-body-sm"
            value={chosen[row.id] ?? row.role}
            onChange={(event) => {
              pick(row.id, event.target.value);
            }}
          >
            {choices.map((choice) => (
              <option key={choice.role} value={choice.role}>
                {choice.label}
              </option>
            ))}
          </select>
          {/* The label names the row: a column of identical "Save" buttons is
              ambiguous to a screen reader, which announces the button and not the
              row it sits in (R-26). */}
          <Button
            size="sm"
            variant="secondary"
            aria-label={`Save the new role for ${row.email}`}
            loading={change.isPending && change.variables?.userId === row.id}
            disabled={!roleChangeRequired(row.role, chosen[row.id] ?? row.role)}
            onClick={() => {
              setConfirming({ row, role: chosen[row.id] ?? row.role });
            }}
          >
            Save
          </Button>
        </span>
      ),
    },
    {
      id: 'created',
      header: 'Created',
      sortValue: (row) => row.createdAt,
      cell: (row) => row.createdAt,
      hiddenByDefault: true,
    },
  ];

  return (
    <Card
      title="Users and roles"
      actions={
        <Button
          size="sm"
          variant="secondary"
          loading={users.isFetching}
          onClick={() => {
            void users.refetch();
          }}
        >
          Reload
        </Button>
      }
      state={users.isPending ? 'loading' : users.isError ? 'error' : 'ready'}
      loadingLines={4}
      error={{
        message: 'The user directory could not be read',
        detail:
          'Nothing is listed rather than a stale roster: a role change offered against an account list this screen cannot vouch for would be a privilege change made blind.',
      }}
    >
      <div className="flex flex-col gap-3">
        <p className="text-body-sm text-muted">{summary.note}</p>
        {summary.stranded ? (
          <p className="text-body-sm text-severityText-critical" role="status">
            No active admin: every action on this screen will be refused until one exists.
          </p>
        ) : null}
        {refusal === null ? null : (
          <p className="text-body-sm text-severityText-critical" role="alert">
            {refusal}
          </p>
        )}
        {answered === null || answered.changed ? null : (
          <p className="text-body-sm text-muted">
            {`Nothing changed: that account already holds the ${answered.applied} role, so no audit
            row was written (D-038).`}
          </p>
        )}
        {answered === null || !answered.changed ? null : (
          <p className="text-body-sm text-muted">
            {`Account set to ${answered.applied} at ${answered.at} by ${answered.actor}. The change
            is in the audit trail.`}
          </p>
        )}
        <DataTable
          caption="Users, their roles and the role control"
          columns={columns}
          rows={rows}
          rowKey={(row) => String(row.id)}
          rowLabel={(row) => row.email}
          height={280}
          empty={
            <p className="text-body">
              The directory is empty. This build starts with no bootstrap account (D-047): the
              directory is populated by the deployment, not by the dashboard.
            </p>
          }
        />
      </div>

      <ConfirmDialog
        open={confirming !== null}
        title="Confirm the role change"
        message={
          confirming === null
            ? ''
            : `${confirming.row.email} goes from ${confirming.row.role} to ${confirming.role}. The change is recorded in the audit trail against your account, and the account's access changes on its next request.`
        }
        confirmLabel="Change the role"
        onClose={() => {
          setConfirming(null);
        }}
        onConfirm={() => {
          if (confirming === null) return;
          const { row, role } = confirming;
          save(row, role);
          setConfirming(null);
        }}
      />
    </Card>
  );
}

/** The role matrix: R-53's four roles and what each may do, from the server. */
export function RolesPanel() {
  const roles = useRoles();
  const choices = roleChoices(roles.data?.items);
  return (
    <Card
      title="What each role may do"
      state={roles.isPending ? 'loading' : roles.isError ? 'error' : 'ready'}
      loadingLines={5}
      error={{ message: 'The role matrix could not be read' }}
    >
      <ul className="flex flex-col gap-2" data-testid="role-matrix">
        {choices.map((choice) => (
          <li key={choice.role} className="flex flex-col gap-1">
            <span className="text-body">{choice.label}</span>
            <span className="text-body-sm text-muted">
              {choice.capabilities.length === 0
                ? 'No capabilities. It can read its own session and nothing else.'
                : choice.describes}
            </span>
            <span className="font-mono text-body-sm text-muted">
              {choice.capabilities.join(', ')}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
