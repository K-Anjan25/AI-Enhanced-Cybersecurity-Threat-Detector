/**
 * Connectors — design.md §3's `/admin/connectors`: the endpoints a deployment sends
 * alerts to, their signing secrets and the outcome of each delivery attempt (FR-21,
 * T-422).
 *
 * The one-time rule is implemented as a *lifetime*, not as a flag somebody has to
 * remember to clear, and it is the same mechanism the keys panel uses
 * (`secrets.ts`): a create response is stamped with the value of this dialog's open
 * counter, and `secretIsLive` compares that stamp against the counter now. Closing
 * the dialog passes `null`, so the secret becomes unreachable — there is no code path
 * that could show it again, because the number it needs no longer exists. A test
 * asserts the gone case by rendering the closed-and-reopened dialog.
 *
 * Everything else on the panel is what an operator needs to answer "are alerts leaving
 * the building, and are they landing?":
 *
 *   * the registered endpoints, with the floor each one receives at, and a *Test*
 *     action per row that makes one real signed attempt rather than a bespoke probe;
 *   * the attempts themselves — endpoint, outcome, retry count, HTTP status and the
 *     short reason code — newest first, in the same card as the sentence that says how
 *     much of the history the window holds;
 *   * the server's own caveats, rendered as written. A deployment with no outbound
 *     transport says exactly that instead of showing an empty table that would read as
 *     a quiet network (R-29, R-70).
 *
 * Removing an endpoint is a `ConfirmDialog`: it is a destructive act on configuration
 * that alerts are currently flowing to. The attempts already made keep their rows —
 * the record of what left the building is not something a delete unsends.
 */
import { useState } from 'react';
import { Copy } from 'lucide-react';

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  Modal,
  useToast,
  type Column,
} from '../../../components/ui';
import {
  connectorRefusalMessage,
  useCreateWebhook,
  useDeleteWebhook,
  useDeliveries,
  useTestWebhook,
  useWebhooks,
} from '../hooks';
import {
  SECRET_ONCE_NOTE,
  caveatText,
  connectorRows,
  connectorSummary,
  creationReadiness,
  deliveryRows,
  deliverySummary,
  floorChoices,
  floorLabel,
  issuedConnector,
  type ConnectorRow,
  type DeliveryRow,
  type IssuedConnector,
} from '../connectors';
import { secretIsLive } from '../secrets';

export function ConnectorsPanel() {
  const targets = useWebhooks();
  const deliveries = useDeliveries();
  const create = useCreateWebhook();
  const remove = useDeleteWebhook();
  const test = useTestWebhook();
  const toast = useToast();

  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [floor, setFloor] = useState('high');
  const [removing, setRemoving] = useState<ConnectorRow | null>(null);
  // The counter that gives a signing secret its lifetime. Bumping it is what closes
  // the window on a secret that has been shown.
  const [token, setToken] = useState(0);
  const [issued, setIssued] = useState<IssuedConnector | null>(null);

  const rows = connectorRows(targets.data?.items);
  const summary = connectorSummary(targets.data?.items);
  const attempts = deliveryRows(deliveries.data?.items, targets.data?.items);
  const attemptSummary = deliverySummary(deliveries.data);
  const caveats = caveatText(deliveries.data);
  const readiness = creationReadiness(
    url,
    rows.map((row) => row.url),
  );
  const live = secretIsLive(issued, open ? token : null);

  const begin = (): void => {
    setUrl('');
    setDescription('');
    setFloor('high');
    create.reset();
    // Bumping the counter is what revokes any secret from a previous rendering, and it
    // is the *only* thing that has to happen: there is no `setIssued(null)` to forget.
    setToken((current) => current + 1);
    setOpen(true);
  };

  const close = (): void => {
    setOpen(false);
    // No counter bump here, deliberately: `live` is `secretIsLive(issued, open ? token :
    // null)`, so closing alone already makes the capture unreachable, and a second
    // mechanism would be a second thing to keep working.
    create.reset();
  };

  const submit = (): void => {
    if (!readiness.ready) return;
    create.mutate(
      {
        url: url.trim(),
        ...(description.trim() === '' ? {} : { description: description.trim() }),
        severity_floor: floor,
      },
      {
        onSuccess: (result) => {
          setIssued(issuedConnector(result, token));
          setUrl('');
          setDescription('');
        },
      },
    );
  };

  const copy = (): void => {
    if (!live || issued === null) return;
    void navigator.clipboard.writeText(issued.secret).then(
      () => {
        toast('success', 'The signing secret is on your clipboard. It will not be shown again.');
      },
      () => {
        toast(
          'warning',
          'Clipboard access was refused. Select the field and copy it before closing.',
        );
      },
    );
  };

  const sendTest = (row: ConnectorRow): void => {
    test.mutate(row.id, {
      onSuccess: (record) => {
        toast(
          record.delivered ? 'success' : 'warning',
          record.delivered
            ? `${row.host} accepted the signed event (HTTP ${String(record.status ?? '')}).`
            : `${row.host} did not accept it: ${record.outcome.replace(/_/g, ' ')} (${record.reason}). The attempt is in the table below.`,
        );
      },
    });
  };

  const endpointColumns: readonly Column<ConnectorRow>[] = [
    {
      id: 'endpoint',
      header: 'Endpoint',
      sortValue: (row) => row.host,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.host}</span>
          <code className="font-mono text-body-sm text-muted">{row.url}</code>
          {row.description === '' ? null : (
            <span className="text-body-sm text-muted">{row.description}</span>
          )}
        </span>
      ),
    },
    {
      id: 'floor',
      header: 'Sends at or above',
      sortValue: (row) => row.severityFloor,
      cell: (row) => <Badge tone="neutral">{row.severityLabel}</Badge>,
    },
    {
      id: 'id',
      header: 'Id',
      sortValue: (row) => row.id,
      cell: (row) => <code className="font-mono text-body-sm">{row.id}</code>,
      hiddenByDefault: true,
    },
    {
      id: 'created',
      header: 'Registered',
      sortValue: (row) => row.createdAt,
      cell: (row) => row.createdAt,
      hiddenByDefault: true,
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: (row) => (
        <span className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            loading={test.isPending && test.variables === row.id}
            onClick={() => {
              sendTest(row);
            }}
          >
            Send a test event
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              setRemoving(row);
            }}
          >
            Remove
          </Button>
        </span>
      ),
    },
  ];

  const attemptColumns: readonly Column<DeliveryRow>[] = [
    {
      id: 'endpoint',
      header: 'Endpoint',
      sortValue: (row) => row.endpoint,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.endpoint}</span>
          <span className="text-body-sm text-muted">{row.endpointDetail}</span>
        </span>
      ),
    },
    {
      id: 'outcome',
      header: 'Outcome',
      sortValue: (row) => row.outcome,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <Badge tone={row.tone}>{row.outcomeLabel}</Badge>
          <span className="text-body-sm text-muted">{row.reason}</span>
        </span>
      ),
    },
    {
      id: 'attempts',
      header: 'Attempts',
      sortValue: (row) => row.attempts,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.attempts}</span>
          <span className="text-body-sm text-muted">{row.waited}</span>
        </span>
      ),
    },
    {
      id: 'status',
      header: 'HTTP',
      sortValue: (row) => row.status,
      cell: (row) => <span className="font-mono text-body-sm">{row.status}</span>,
    },
    {
      id: 'when',
      header: 'When',
      sortValue: (row) => row.at,
      cell: (row) => (
        <span className="flex flex-col gap-1">
          <span className="text-body">{row.age}</span>
          <span className="text-body-sm text-muted">{row.at}</span>
        </span>
      ),
    },
    {
      id: 'delivery',
      header: 'Delivery id',
      sortValue: (row) => row.deliveryId,
      cell: (row) => <code className="font-mono text-body-sm">{row.deliveryId}</code>,
      hiddenByDefault: true,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Card
        title="Endpoints"
        actions={
          <Button size="sm" onClick={begin}>
            Add an endpoint
          </Button>
        }
        state={targets.isPending ? 'loading' : targets.isError ? 'error' : 'ready'}
        loadingLines={4}
        error={{ message: 'The endpoint list could not be read' }}
      >
        <div className="flex flex-col gap-3">
          <p className="text-body-sm text-muted">{summary.note}</p>
          {connectorRefusalMessage(remove.error, 'delete') === null ? null : (
            <p className="text-body-sm text-severityText-critical" role="alert">
              {connectorRefusalMessage(remove.error, 'delete')}
            </p>
          )}
          {connectorRefusalMessage(test.error, 'test') === null ? null : (
            <p className="text-body-sm text-severityText-critical" role="alert">
              {connectorRefusalMessage(test.error, 'test')}
            </p>
          )}
          <DataTable
            caption="Outbound endpoints"
            columns={endpointColumns}
            rows={rows}
            rowKey={(row) => row.id}
            rowLabel={(row) => row.host}
            height={280}
            empty={
              <EmptyState
                title="No endpoints are registered"
                description="An alert leaves the deployment only through one of these. R-55 refuses a destination that is not allowlisted or that resolves into a private address, and names which when it does."
              />
            }
          />
        </div>
      </Card>

      <Card
        title="Delivery attempts"
        state={deliveries.isPending ? 'loading' : deliveries.isError ? 'error' : 'ready'}
        loadingLines={4}
        error={{ message: 'The delivery history could not be read' }}
      >
        <div className="flex flex-col gap-3">
          <p className="text-body-sm text-muted">{attemptSummary.note}</p>
          {/* The server's own sentences, as written (R-70): the window's limits are
              the store's to describe, and a screen that paraphrased them would be a
              second place for them to be wrong. */}
          {caveats.map((sentence) => (
            <p key={sentence} className="text-body-sm text-muted">
              {sentence}
            </p>
          ))}
          <DataTable
            caption="Recent delivery attempts"
            columns={attemptColumns}
            rows={attempts}
            rowKey={(row) => row.deliveryId}
            rowLabel={(row) => `${row.outcomeLabel} to ${row.endpoint}`}
            height={280}
            empty={
              <EmptyState
                title="No delivery has been attempted"
                description="A row appears here the moment an attempt is made — an alert that reached an endpoint, or a test send from the table above."
              />
            }
          />
        </div>
      </Card>

      <Modal
        open={open}
        title="Add an endpoint"
        onClose={close}
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>
              {live ? 'Done, I have stored it' : 'Cancel'}
            </Button>
            {live ? null : (
              <Button loading={create.isPending} disabled={!readiness.ready} onClick={submit}>
                Register
              </Button>
            )}
          </div>
        }
      >
        {live && issued !== null ? (
          <div className="flex flex-col gap-3">
            <p className="text-body-sm text-muted">{SECRET_ONCE_NOTE}</p>
            <div className="flex items-center gap-2">
              <label className="sr-only" htmlFor="issued-webhook-secret">
                The signing secret
              </label>
              <input
                id="issued-webhook-secret"
                // Read-only and *not* a controlled input: an operator selects and
                // copies it. It is re-rendered only while `live`, which is the same
                // predicate that decides whether this block exists at all.
                readOnly
                value={issued.secret}
                className="w-full rounded-control border border-line bg-surface px-2 py-1 font-mono text-body-sm"
                onFocus={(event) => {
                  event.currentTarget.select();
                }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={copy}
                aria-label="Copy the signing secret"
              >
                <Copy aria-hidden="true" className="size-icon-sm" />
              </Button>
            </div>
            <dl className="grid grid-cols-2 gap-1 text-body-sm">
              <dt className="text-muted">Endpoint</dt>
              <dd className="font-mono">{issued.url}</dd>
              <dt className="text-muted">Id</dt>
              <dd className="font-mono">{issued.id}</dd>
              <dt className="text-muted">Sends at or above</dt>
              <dd>{floorLabel(issued.severityFloor)}</dd>
              <dt className="text-muted">Registered</dt>
              <dd>{issued.createdAt}</dd>
            </dl>
            <p className="text-body-sm text-muted">
              The receiver verifies the signature with this secret, so send it to whoever operates
              the endpoint — it is not stored anywhere it can be read back.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {connectorRefusalMessage(create.error, 'create') === null ? null : (
              <p className="text-body-sm text-severityText-critical" role="alert">
                {connectorRefusalMessage(create.error, 'create')}
              </p>
            )}
            <label className="flex flex-col gap-1 text-body-sm">
              URL
              <input
                value={url}
                onChange={(event) => {
                  setUrl(event.target.value);
                }}
                className="rounded-control border border-line bg-base px-2 py-1 font-mono text-body"
                placeholder="https://hooks.example.com/aegis"
              />
            </label>
            <label className="flex flex-col gap-1 text-body-sm">
              Description — optional, and never the URL: it is what a reader recognises the endpoint
              by in a list.
              <input
                value={description}
                onChange={(event) => {
                  setDescription(event.target.value);
                }}
                className="rounded-control border border-line bg-base px-2 py-1 text-body"
                placeholder="SOC shift handover channel"
              />
            </label>
            <label className="flex flex-col gap-1 text-body-sm">
              Lowest severity delivered
              <select
                value={floor}
                onChange={(event) => {
                  setFloor(event.target.value);
                }}
                className="rounded-control border border-line bg-base px-2 py-1 text-body"
              >
                {floorChoices().map((choice) => (
                  <option key={choice} value={choice}>
                    {floorLabel(choice)}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-body-sm text-muted">
              FR-21 delivers `high` and `critical` by default; a lower floor sends more, and every
              alert at or above it is one signed POST, retried with backoff while the receiver
              answers with a retryable status.
            </p>
            {readiness.reason === null ? null : (
              <p className="text-body-sm text-muted">{readiness.reason}</p>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={removing !== null}
        title={`Remove ${removing?.host ?? ''}?`}
        message="Alerts stop being delivered to it immediately, and its signing secret is discarded with it. The attempts already made keep their rows, because the record of what left the building is not something a delete unsends."
        confirmLabel="Remove the endpoint"
        onConfirm={() => {
          if (removing === null) return;
          remove.mutate(removing.id, {
            onSuccess: () => {
              toast('success', `${removing.host} is no longer registered.`);
              setRemoving(null);
            },
          });
        }}
        onClose={() => {
          setRemoving(null);
        }}
      />
    </div>
  );
}
