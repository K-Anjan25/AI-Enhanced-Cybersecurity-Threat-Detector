/**
 * The connectors panel (T-422, FR-21).
 *
 * *Issuing an endpoint shows its signing secret exactly once and the listing never
 * carries it* has two halves, and both are asserted by rendering rather than by reading
 * the model:
 *
 *   1. **Once, visibly.** Registering an endpoint puts the secret in the dialog, with
 *      the sentence that says it will not come back.
 *   2. **Not a second time.** Closing the dialog and reopening it must not show it
 *      again — the case a screenshot review would never catch, because the form looks
 *      identical whether the field holds a live secret or nothing. The reopened form is
 *      asserted empty of the secret, and the *listing* is asserted never to contain it
 *      either.
 *
 * *A delivery attempt's outcome is readable* is the other half of the criterion, and it
 * is read the way an operator reads it: the endpoint, the outcome and its short reason,
 * the attempt count with the time spent in backoff, the HTTP status and the age. The
 * records carry their target by id only (R-58), so the table joining them to the
 * configuration is itself asserted — including the case where the endpoint has since
 * been removed, which must not render as a blank endpoint.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ToastProvider } from '../../../components/ui';
import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch, type StubRoute } from '../../../test/query';
import { ConnectorsPanel } from './ConnectorsPanel';

const WEBHOOKS = '/api/v1/webhooks';
const DELIVERIES = '/api/v1/webhooks/deliveries';
const SECRET = 'hmac_9f4c1d2e3a4b5c6d7e8f90a1b2c3d4e5'; // pragma: allowlist secret

const EXISTING = {
  id: 'wh_1',
  url: 'https://hooks.example.com/aegis',
  description: 'SOC shift handover',
  severity_floor: 'high',
  active: true,
  created_at: '2026-10-01T09:00:00Z',
};

const ISSUED = {
  ...EXISTING,
  id: 'wh_2',
  url: 'https://hooks.example.com/critical',
  description: null,
  severity_floor: 'critical',
  created_at: '2026-10-07T09:00:00Z',
  secret: SECRET,
};

/** A delivered attempt: the outcome an operator wants to see. */
const DELIVERED = {
  delivery_id: 'd-2',
  target_id: 'wh_1',
  at: '2026-10-07T09:05:00Z',
  delivered: true,
  attempt_count: 1,
  waited_seconds: 0,
  outcome: 'delivered',
  status: 200,
  reason: 'ok',
};

/** A refused one: two requests, so a retry is visible rather than implied. */
const RETRIED = {
  delivery_id: 'd-1',
  target_id: 'wh_1',
  at: '2026-10-07T09:00:00Z',
  delivered: false,
  attempt_count: 2,
  waited_seconds: 1.5,
  outcome: 'retry',
  status: 500,
  reason: 'retryable_status',
};

function deliveriesBody(
  items: readonly unknown[] = [DELIVERED, RETRIED],
  over: Partial<Record<string, unknown>> = {},
) {
  return {
    items,
    held: items.length,
    recorded: items.length,
    dispatch_configured: true,
    caveats: [
      'A record carries no URL and no secret: an operator who needs the payload reads it at the receiver.',
      'Delivery records live in this process’s memory rather than in a store.',
    ],
    ...over,
  };
}

function routes(over: Partial<Record<'list' | 'post' | 'deliveries' | 'test', unknown>> = {}) {
  const table: StubRoute[] = [
    // Specific before collection: `stubFetch` matches by prefix in list order, and
    // `/api/v1/webhooks` is a prefix of both the deliveries path and a target's test path.
    {
      match: DELIVERIES,
      respond: () => jsonResponse(over.deliveries ?? deliveriesBody()),
    },
    {
      match: `${WEBHOOKS}/wh_1/test`,
      respond: () => jsonResponse(over.test ?? DELIVERED),
    },
    {
      match: `${WEBHOOKS}/wh_1`,
      respond: () => new Response(null, { status: 204 }),
    },
    {
      match: WEBHOOKS,
      respond: (request) =>
        request.method === 'POST'
          ? jsonResponse(over.post ?? ISSUED, 201)
          : jsonResponse({ items: over.list ?? [EXISTING] }),
    },
  ];
  return table;
}

/** Whether the secret is anywhere on the page. */
function secretOnScreen(): boolean {
  // An `<input value>` is *not* part of `textContent`, so a test that only read the text
  // would report "not shown" for the field the secret is actually sitting in.
  const fields = screen.queryAllByRole('textbox') as HTMLInputElement[];
  return (
    document.body.textContent?.includes(SECRET) === true ||
    fields.some((field) => field.value === SECRET)
  );
}

async function addAnEndpoint(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(await screen.findByRole('button', { name: 'Add an endpoint' }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText('URL'), 'https://hooks.example.com/critical');
  await user.click(within(dialog).getByRole('button', { name: 'Register' }));
  await screen.findByLabelText('The signing secret');
}

function render(): ReturnType<typeof renderWithProviders> {
  return renderWithProviders(
    <ToastProvider>
      <ConnectorsPanel />
    </ToastProvider>,
  );
}

describe('ConnectorsPanel', () => {
  it('shows the signing secret once, with the sentence that says so', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    render();

    await addAnEndpoint(user);

    const field = screen.getByLabelText('The signing secret');
    expect(field).toHaveValue(SECRET);
    expect(field).toHaveAttribute('readonly');
    expect(screen.getByText(/only time this signing secret is shown/)).toBeInTheDocument();
    // The receiver is the one that needs it, and the panel says so rather than leaving
    // an operator to wonder whether it can be read back.
    expect(screen.getByText(/has no route that returns it/)).toBeInTheDocument();
  });

  it('does not show the secret again after the dialog is closed and reopened', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    render();

    await addAnEndpoint(user);
    expect(secretOnScreen()).toBe(true);

    await user.click(screen.getByRole('button', { name: 'Done, I have stored it' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    // The dialog is gone *and* the value with it: nothing in the document holds it.
    expect(secretOnScreen()).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Add an endpoint' }));
    const reopened = await screen.findByRole('dialog');
    expect(within(reopened).queryByLabelText('The signing secret')).toBeNull();
    expect(secretOnScreen()).toBe(false);
  });

  it('never puts a signing secret in the listing', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    const { container } = render();

    await addAnEndpoint(user);
    await user.click(screen.getByRole('button', { name: 'Done, I have stored it' }));

    const table = await screen.findByRole('table', { name: 'Outbound endpoints' });
    expect(table.textContent).toContain('hooks.example.com');
    expect(table.textContent).not.toContain(SECRET);
    await expectAccessible(container);
  });

  it('reads a delivery attempt by endpoint, outcome, attempts, status and age', async () => {
    stubFetch(routes());
    render();

    const table = await screen.findByRole('table', { name: 'Recent delivery attempts' });
    // The join the record's own shape demands: it carries a target id, and the endpoint
    // comes from the configuration beside it. Both rows are for the one endpoint, so the
    // host appears once per attempt.
    expect(within(table).getAllByText('hooks.example.com')).toHaveLength(2);
    expect(within(table).getAllByText('target wh_1')).toHaveLength(2);

    const delivered = within(table).getByText('Delivered');
    expect(delivered).toBeInTheDocument();
    const deliveredRow = delivered.closest('[role="row"]');
    expect(deliveredRow).not.toBeNull();
    expect(deliveredRow).toHaveTextContent('1 attempt');
    expect(deliveredRow).toHaveTextContent('200');
    expect(deliveredRow).toHaveTextContent('ok');

    // A retry is visible as two requests and the time spent waiting between them,
    // rather than as one failed attempt.
    const retried = within(table).getByText('Retry');
    const retriedRow = retried.closest('[role="row"]');
    expect(retriedRow).not.toBeNull();
    expect(retriedRow).toHaveTextContent('2 attempts');
    expect(retriedRow).toHaveTextContent('1.5s backoff');
    expect(retriedRow).toHaveTextContent('500');
    expect(retriedRow).toHaveTextContent('retryable_status');
  });

  it('keeps the record of an attempt whose endpoint has been removed', async () => {
    // R-58 means the record carries an id, not a URL, so the join can miss. A deleted
    // endpoint must not render as a blank endpoint cell: the attempt happened.
    stubFetch(
      routes({
        deliveries: deliveriesBody([{ ...DELIVERED, target_id: 'wh_9', delivery_id: 'd-9' }]),
      }),
    );
    render();

    const table = await screen.findByRole('table', { name: 'Recent delivery attempts' });
    expect(within(table).getByText('wh_9')).toBeInTheDocument();
    expect(within(table).getByText('no longer configured')).toBeInTheDocument();
  });

  it('says what the window holds, and never paraphrases the server’s caveats', async () => {
    stubFetch(
      routes({
        deliveries: deliveriesBody([DELIVERED, RETRIED], { recorded: 112, held: 2 }),
      }),
    );
    render();

    // The summary counts what was delivered and says how much of the history is on
    // screen — a capped list that said "2 deliveries" would read as the whole story.
    expect(await screen.findByText(/1 of 2 delivered\./)).toBeInTheDocument();
    expect(screen.getByText(/Showing the newest 2 of 112 attempted\./)).toBeInTheDocument();
    // The store's sentences, as written (R-70).
    expect(screen.getByText(/Delivery records live in this process’s memory/)).toBeInTheDocument();
    expect(screen.getByText(/carries no URL and no secret/)).toBeInTheDocument();
  });

  it('reads an empty delivery list as a fact about the deployment', async () => {
    // A build with no outbound transport can never have a record. An empty table with
    // no explanation would read as a quiet network.
    stubFetch(
      routes({
        deliveries: deliveriesBody([], {
          held: 0,
          recorded: 0,
          dispatch_configured: false,
          caveats: ['This deployment has no outbound transport, so nothing can be sent'],
        }),
      }),
    );
    render();

    expect(await screen.findByText(/Nothing can be sent from this deployment/)).toBeInTheDocument();
    expect(
      screen.getByText(/has no outbound transport, so nothing can be sent/),
    ).toBeInTheDocument();
    expect(screen.getByText('No delivery has been attempted')).toBeInTheDocument();
  });

  it('sends one signed test event to the endpoint, and reports what came back', async () => {
    const user = userEvent.setup();
    const seen = stubFetch(routes());
    render();

    await user.click(await screen.findByRole('button', { name: 'Send a test event' }));

    await waitFor(() => {
      expect(
        seen.some(
          (request) =>
            new URL(request.url).pathname === '/api/v1/webhooks/wh_1/test' &&
            request.method === 'POST',
        ),
      ).toBe(true);
    });
    // A delivered test is a success, and the sentence names the endpoint and the status
    // rather than saying "done".
    expect(
      await screen.findByText(/hooks.example.com accepted the signed event/),
    ).toBeInTheDocument();
  });

  it('reports a refused test delivery as an outcome rather than as a failure', async () => {
    const user = userEvent.setup();
    stubFetch(routes({ test: RETRIED }));
    render();

    await user.click(await screen.findByRole('button', { name: 'Send a test event' }));

    expect(
      await screen.findByText(/did not accept it: retry \(retryable_status\)/),
    ).toBeInTheDocument();
  });

  it('refuses a URL it can refuse for itself, and leaves the address rules to the server', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    render();

    await user.click(await screen.findByRole('button', { name: 'Add an endpoint' }));
    const dialog = await screen.findByRole('dialog');
    const register = within(dialog).getByRole('button', { name: 'Register' });

    expect(register).toBeDisabled();
    expect(within(dialog).getByText('An endpoint needs a URL to deliver to.')).toBeInTheDocument();

    // Plain http would publish the credential the signature is made with.
    await user.type(within(dialog).getByLabelText('URL'), 'http://hooks.example.com/aegis');
    expect(register).toBeDisabled();
    expect(within(dialog).getByText(/only sent over https/)).toBeInTheDocument();

    // A URL already registered would deliver every alert twice.
    await user.clear(within(dialog).getByLabelText('URL'));
    await user.type(within(dialog).getByLabelText('URL'), EXISTING.url);
    expect(register).toBeDisabled();
    expect(within(dialog).getByText(/already registered/)).toBeInTheDocument();

    await user.clear(within(dialog).getByLabelText('URL'));
    await user.type(within(dialog).getByLabelText('URL'), 'https://hooks.example.com/new');
    expect(within(dialog).getByRole('button', { name: 'Register' })).toBeEnabled();
  });

  it('renders the server’s own refusal when R-55 blocks an address', async () => {
    // The allowlist and the resolved address are the server's rules, enforced on submit
    // and again on every attempt. The screen shows the refusal rather than guessing it.
    const user = userEvent.setup();
    stubFetch([
      {
        match: DELIVERIES,
        respond: () => jsonResponse(deliveriesBody([])),
      },
      {
        match: WEBHOOKS,
        respond: (request) =>
          request.method === 'POST'
            ? jsonResponse({ detail: 'webhook URL refused: blocked_address' }, 400)
            : jsonResponse({ items: [] }),
      },
    ]);
    render();

    await user.click(await screen.findByRole('button', { name: 'Add an endpoint' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('URL'), 'https://hooks.example.com/aegis');
    await user.click(within(dialog).getByRole('button', { name: 'Register' }));

    expect(
      await screen.findByText(/R-55 accepts only allowlisted destinations/),
    ).toBeInTheDocument();
    // And the secret is nowhere: a refused create issues nothing.
    expect(secretOnScreen()).toBe(false);
  });

  it('asks before removing an endpoint, and says what removal does not undo', async () => {
    const user = userEvent.setup();
    const seen = stubFetch(routes());
    render();

    await user.click(await screen.findByRole('button', { name: 'Remove' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/attempts already made keep their rows/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Remove the endpoint' }));

    await waitFor(() => {
      expect(
        seen.some(
          (request) =>
            new URL(request.url).pathname === '/api/v1/webhooks/wh_1' &&
            request.method === 'DELETE',
        ),
      ).toBe(true);
    });
  });

  it('reads an empty endpoint list as a fact about the deployment', async () => {
    stubFetch(routes({ list: [] }));
    render();

    expect(await screen.findByText('No endpoints are registered')).toBeInTheDocument();
    expect(await screen.findByText(/nothing leaves this deployment/)).toBeInTheDocument();
  });
});
