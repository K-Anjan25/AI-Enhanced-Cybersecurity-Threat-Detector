/**
 * The keys panel (T-410's second acceptance criterion).
 *
 * *The API key secret renders exactly once* has two halves, and both are tested by
 * rendering rather than by reading the model:
 *
 *   1. **Once, visibly.** Issuing a key puts the secret in the dialog; that is the one
 *      moment it exists on screen.
 *   2. **Not a second time.** Closing the dialog and reopening it must not show it
 *      again — the case a screenshot review would never catch, because the modal looks
 *      identical whether the field holds a live key or nothing. The reopened form is
 *      asserted to be empty of the secret, and the *listing* is asserted never to
 *      contain it either.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { ToastProvider } from '../../../components/ui';
import { KeysPanel } from './KeysPanel';

const KEYS = '/api/v1/keys';
const SECRET = 'aegis_sk_7_9f4c1d2e3a4b5c6d7e8f90a1b2c3d4e5';

const EXISTING = {
  id: 3,
  name: 'collector-00',
  prefix: 'aegis_sk_3_',
  owner: 'ops@example.test',
  scopes: ['ingest:write'],
  created_at: '2026-10-01T00:00:00Z',
  last_used_at: '2026-10-05T00:00:00Z',
  revoked_at: null,
};

const SCOPES = {
  items: [{ name: 'ingest:write', capabilities: ['ingest'] }],
};

function routes(): Parameters<typeof stubFetch>[0] {
  return [
    // Specific before collection: `stubFetch` matches by prefix in list order.
    { match: `${KEYS}/scopes`, respond: () => jsonResponse(SCOPES) },
    {
      match: KEYS,
      respond: (request) =>
        request.method === 'POST'
          ? jsonResponse(
              { ...EXISTING, id: 7, name: 'collector-01', prefix: 'aegis_sk_7_', secret: SECRET },
              201,
            )
          : jsonResponse({ items: [EXISTING] }),
    },
    { match: `${KEYS}/3`, respond: () => new Response(null, { status: 204 }) },
  ];
}

/**
 * Whether the secret is anywhere on the page.
 *
 * Both halves are needed: an `<input value>` is *not* part of `textContent`, so a test
 * that only read the text would report "not shown" for the field the secret is actually
 * sitting in.
 */
function secretOnScreen(): boolean {
  const fields = [...document.querySelectorAll<HTMLInputElement>('input, textarea')];
  return (
    document.body.textContent?.includes(SECRET) === true ||
    fields.some((field) => field.value === SECRET)
  );
}

function issueAKey(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  return (async () => {
    await user.click(await screen.findByRole('button', { name: 'Issue a key' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Name'), 'collector-01');
    await user.click(within(dialog).getByLabelText('ingest:write'));
    await user.click(within(dialog).getByRole('button', { name: 'Issue' }));
    await screen.findByTestId('secret-once');
  })();
}

describe('KeysPanel', () => {
  it('shows the secret once, with the sentence that says so', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );

    await issueAKey(user);

    const field = screen.getByLabelText('The new key');
    expect(field).toHaveValue(SECRET);
    expect(field).toHaveAttribute('readonly');
    expect(screen.getByText(/only time this key is shown/)).toBeInTheDocument();
  });

  it('does not show the secret again after the dialog is closed and reopened', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );

    await issueAKey(user);
    expect(secretOnScreen()).toBe(true);

    await user.click(screen.getByRole('button', { name: 'Done, I have stored it' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    // The dialog is gone *and* the value with it: nothing in the document holds it.
    expect(secretOnScreen()).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Issue a key' }));
    const reopened = await screen.findByRole('dialog');
    expect(within(reopened).queryByLabelText('The new key')).toBeNull();
    expect(secretOnScreen()).toBe(false);
  });

  it('never puts a secret in the listing', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    const { container } = renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );

    await issueAKey(user);
    await user.click(screen.getByRole('button', { name: 'Done, I have stored it' }));

    const table = await screen.findByRole('table');
    expect(table.textContent).toContain('aegis_sk_3_');
    expect(table.textContent).not.toContain(SECRET);
    await expectAccessible(container);
  });

  it('refuses to issue without a name or without a scope', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );

    await user.click(await screen.findByRole('button', { name: 'Issue a key' }));
    const dialog = await screen.findByRole('dialog');
    const issue = within(dialog).getByRole('button', { name: 'Issue' });
    expect(issue).toBeDisabled();
    expect(within(dialog).getByText('A key needs a name to recognise it by.')).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText('Name'), 'collector-01');
    // A name without a scope is still not a key: an empty scope set is refused
    // rather than read as "everything".
    expect(within(dialog).getByRole('button', { name: 'Issue' })).toBeDisabled();
    await user.click(within(dialog).getByLabelText('ingest:write'));
    expect(within(dialog).getByRole('button', { name: 'Issue' })).toBeEnabled();
  });

  it('asks before revoking, and says the row stays', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );

    await user.click(await screen.findByRole('button', { name: 'Revoke' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/record of a credential having existed/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Revoke the key' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('reads an empty key list as a fact about the deployment', async () => {
    stubFetch([
      { match: `${KEYS}/scopes`, respond: () => jsonResponse(SCOPES) },
      { match: KEYS, respond: () => jsonResponse({ items: [] }) },
    ]);
    renderWithProviders(
      <ToastProvider>
        <KeysPanel />
      </ToastProvider>,
    );
    expect(await screen.findByTestId('keys-empty')).toHaveTextContent('No keys have been issued');
  });
});
