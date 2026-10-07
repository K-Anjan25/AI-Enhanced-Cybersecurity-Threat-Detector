/**
 * API keys — design.md §4.8: "secret shown exactly once, in a field that cannot be
 * re-rendered; only the prefix is stored" (FR-44, T-313, D-042).
 *
 * The one-time rule is implemented as a *lifetime*, not as a flag somebody has to
 * remember to clear. `IssuedKey.expiresWith` holds the value of the counter that was
 * current when the create response arrived; `secretIsLive` compares it against the
 * same counter now. Closing the dialog increments the counter, so the secret becomes
 * unreachable — there is no code path that could show it again, because the number it
 * needs no longer exists. A test asserts the gone case by rendering the closed state.
 *
 * Everything else on the panel is the design's list: the prefix (the public half), the
 * scopes, who issued it, when it was last used and whether it has been revoked.
 * Revoking is a `ConfirmDialog` because it is a destructive act on a live credential —
 * but it is *not* a delete, and the row stays: the record of a credential having
 * existed is the point.
 */
import { useState } from 'react';
import { Copy } from 'lucide-react';

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  Modal,
  useToast,
  type Column,
} from '../../../components/ui';
import { keyRefusalMessage, useIssueKey, useKeys, useRevokeKey, useScopes } from '../hooks';
import {
  SECRET_ONCE_NOTE,
  creationReadiness,
  issuedKey,
  keyRows,
  keySummary,
  scopeChoices,
  type IssuedKey,
  type KeyRow,
} from '../keys';
import { secretIsLive } from '../secrets';

export function KeysPanel() {
  const keys = useKeys();
  const scopes = useScopes();
  const issue = useIssueKey();
  const revoke = useRevokeKey();
  const toast = useToast();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [revoking, setRevoking] = useState<KeyRow | null>(null);
  // The counter that gives a secret its lifetime. Bumping it is what closes the
  // window on a secret that has been shown.
  const [token, setToken] = useState(0);
  const [secret, setSecret] = useState<IssuedKey | null>(null);

  const rows = keyRows(keys.data?.items);
  const summary = keySummary(keys.data?.items);
  const choices = scopeChoices(scopes.data?.items);
  const readiness = creationReadiness(name, picked);
  const live = secretIsLive(secret, open ? token : null);

  const begin = (): void => {
    setName('');
    setPicked([]);
    issue.reset();
    // Bumping the counter is what revokes any secret from a previous rendering, and
    // it is the *only* thing that has to happen: there is no `setSecret(null)` to
    // forget, because the capture's own lifetime is what decides whether it renders.
    setToken((current) => current + 1);
    setOpen(true);
  };

  const close = (): void => {
    setOpen(false);
    // No counter bump here, deliberately: `live` is `secretIsLive(secret, open ?
    // token : null)`, so closing alone already makes the capture unreachable, and a
    // second mechanism would be a second thing to keep working. The bump lives on the
    // *open* edge, which is the one that decides whether a reopened dialog could show
    // a previous key.
    issue.reset();
  };

  const submit = (): void => {
    if (!readiness.ready) return;
    issue.mutate(
      { name: name.trim(), scopes: picked },
      {
        onSuccess: (result) => {
          setSecret(issuedKey(result, token));
          setPicked([]);
          setName('');
        },
      },
    );
  };

  const copy = (): void => {
    if (!live || secret === null) return;
    void navigator.clipboard.writeText(secret.secret).then(
      () => {
        toast('success', 'The key is on your clipboard. It will not be shown again.');
      },
      () => {
        toast(
          'warning',
          'Clipboard access was refused. Select the field and copy it before closing.',
        );
      },
    );
  };

  const columns: readonly Column<KeyRow>[] = [
    {
      id: 'name',
      header: 'Name',
      sortValue: (row) => row.name,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.name}</span>
          <code
            className="font-mono text-body-sm text-muted"
            title="The public half: it discloses nothing the key does not contain"
          >
            {row.prefix}
          </code>
        </span>
      ),
    },
    {
      id: 'scopes',
      header: 'Scopes',
      sortValue: (row) => row.scopesText,
      cell: (row) => <span className="font-mono text-body-sm">{row.scopesText}</span>,
    },
    {
      id: 'owner',
      header: 'Issued by',
      sortValue: (row) => row.owner,
      cell: (row) => row.owner,
    },
    {
      id: 'last_used',
      header: 'Last used',
      sortValue: (row) => row.lastUsedAt,
      cell: (row) => row.lastUsedAt,
    },
    {
      id: 'state',
      header: 'State',
      sortValue: (row) => (row.revoked ? 1 : 0),
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <Badge tone="neutral">{row.revoked ? 'Revoked' : 'Live'}</Badge>
          {row.revoked ? <span className="text-body-sm text-muted">{row.revokedAt}</span> : null}
        </span>
      ),
    },
    {
      id: 'actions',
      header: 'Revoke',
      cell: (row) =>
        row.revoked ? (
          <span className="text-body-sm text-muted">Already revoked</span>
        ) : (
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              setRevoking(row);
            }}
          >
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <Card
      title="API keys"
      actions={
        <Button size="sm" onClick={begin}>
          Issue a key
        </Button>
      }
      state={keys.isPending ? 'loading' : keys.isError ? 'error' : 'ready'}
      loadingLines={4}
      error={{ message: 'The key list could not be read' }}
    >
      <div className="flex flex-col gap-3">
        <p className="text-body-sm text-muted" data-testid="key-summary">
          {summary.note}
        </p>
        {keyRefusalMessage(revoke.error, 'revoke') === null ? null : (
          <p className="text-body-sm text-severityText-critical" role="alert">
            {keyRefusalMessage(revoke.error, 'revoke')}
          </p>
        )}
        <DataTable
          caption="Issued API keys"
          columns={columns}
          rows={rows}
          rowKey={(row) => String(row.id)}
          rowLabel={(row) => row.name}
          height={280}
          empty={
            <p className="text-body">
              No keys have been issued. A key is how a collector authenticates (FR-44); issuing one
              is the only way to obtain a credential, and it is shown once.
            </p>
          }
        />
      </div>

      <Modal
        open={open}
        title="Issue an API key"
        onClose={close}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              {live ? 'Done, I have stored it' : 'Cancel'}
            </Button>
            {live ? null : (
              <Button loading={issue.isPending} disabled={!readiness.ready} onClick={submit}>
                Issue
              </Button>
            )}
          </div>
        }
      >
        {live && secret !== null ? (
          <div className="flex flex-col gap-3">
            <p className="text-body-sm text-muted">{SECRET_ONCE_NOTE}</p>
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor="issued-secret">
                The new key
              </label>
              <input
                id="issued-secret"
                // Read-only and *not* a controlled input: an operator selects and
                // copies it. It is re-rendered only while `live`, which is the same
                // predicate that decides whether this block exists at all.
                readOnly
                value={secret.secret}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 font-mono text-body-sm"
                onFocus={(event) => {
                  event.currentTarget.select();
                }}
              />
              <Button variant="secondary" size="sm" onClick={copy} aria-label="Copy the key">
                <Copy aria-hidden="true" className="size-icon-sm" />
              </Button>
            </div>
            <dl className="grid grid-cols-2 gap-1 text-body-sm">
              <dt className="text-muted">Name</dt>
              <dd>{secret.name}</dd>
              <dt className="text-muted">Prefix</dt>
              <dd className="font-mono">{secret.prefix}</dd>
              <dt className="text-muted">Scopes</dt>
              <dd className="font-mono">{secret.scopes.join(', ')}</dd>
              <dt className="text-muted">Issued</dt>
              <dd>{secret.createdAt}</dd>
            </dl>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {keyRefusalMessage(issue.error, 'issue') === null ? null : (
              <p className="text-body-sm text-severityText-critical" role="alert">
                {keyRefusalMessage(issue.error, 'issue')}
              </p>
            )}
            <label className="flex flex-col gap-1 text-body-sm">
              Name
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                className="rounded-control border border-line bg-base px-2 py-1 text-body"
                placeholder="collector-hyderabad-01"
              />
            </label>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-body-sm text-muted">
                Scopes — at least one, and an empty set is refused rather than read as
                &ldquo;everything&rdquo;.
              </legend>
              {choices.length === 0 ? (
                <p className="text-body-sm text-muted">
                  The scope list could not be read, so no key can be issued from here. A key without
                  a scope is not a credential this screen will create.
                </p>
              ) : null}
              {/* The label is the scope's name and nothing else, so the control's
                  accessible name is exactly the scope (R-26); what it grants is
                  described beside it, where it reads as a sentence rather than as
                  part of the checkbox's name. */}
              {choices.map((choice) => (
                <div key={choice.name} className="flex flex-col gap-1">
                  <label
                    htmlFor={`scope-${choice.name}`}
                    className="flex items-center gap-2 text-body-sm"
                  >
                    <input
                      id={`scope-${choice.name}`}
                      type="checkbox"
                      checked={picked.includes(choice.name)}
                      onChange={(event) => {
                        setPicked((current) =>
                          event.target.checked
                            ? [...current, choice.name]
                            : current.filter((scope) => scope !== choice.name),
                        );
                      }}
                    />
                    <span className="font-mono">{choice.name}</span>
                  </label>
                  <span className="ps-6 text-body-sm text-muted">{choice.describes}</span>
                </div>
              ))}
            </fieldset>
            {readiness.reason === null ? null : (
              <p className="text-body-sm text-muted">{readiness.reason}</p>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={revoking !== null}
        title={`Revoke ${revoking?.name ?? ''}?`}
        message="The key stops working on its next request. Its row stays, because the record of a credential having existed is what an audit reads."
        confirmLabel="Revoke the key"
        onConfirm={() => {
          if (revoking === null) return;
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              toast('success', `${revoking.name} is revoked.`);
              setRevoking(null);
            },
          });
        }}
        onClose={() => {
          setRevoking(null);
        }}
      />
    </Card>
  );
}
