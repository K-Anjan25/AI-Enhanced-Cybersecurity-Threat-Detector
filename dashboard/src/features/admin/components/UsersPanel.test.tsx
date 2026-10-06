/**
 * The users panel (T-410's first acceptance criterion).
 *
 * *The last `admin` cannot self-demote* is the server's refusal, and the screen's job is
 * to make the operator meet it rather than to prevent them from trying. So the test does
 * what an operator would: pick the role, confirm, and read the 409 as the sentence that
 * names the rule. Two neighbouring cases are asserted too, because they are the ones a
 * "hide the control" implementation would pass and a working one must not: the control
 * stays available, and a no-op is reported as a no-op.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { UsersPanel } from './UsersPanel';

const USERS = '/api/v1/users';

const ROLES = {
  items: [
    { role: 'viewer', capabilities: ['read'] },
    { role: 'analyst', capabilities: ['read', 'verdict'] },
    { role: 'responder', capabilities: ['read', 'verdict', 'export'] },
    { role: 'admin', capabilities: ['read', 'users', 'models', 'retention', 'api_keys'] },
  ],
};

function directory(activeAdmins: number) {
  return {
    items: [
      {
        id: 1,
        email: 'only@example.test',
        role: 'admin',
        created_at: '2026-01-01T00:00:00Z',
        disabled_at: null,
      },
      {
        id: 2,
        email: 'analyst@example.test',
        role: 'analyst',
        created_at: '2026-01-02T00:00:00Z',
        disabled_at: null,
      },
    ],
    count: 2,
    active_admins: activeAdmins,
  };
}

/**
 * The stub routes, **most specific first**.
 *
 * `stubFetch` matches by path prefix in list order, so `${USERS}` before
 * `${USERS}/1/role` answers the POST with the directory and the test would then be
 * asserting on a success that the server never sent. The order is the fixture's
 * contract, not a detail.
 */
function routes(options: { activeAdmins: number; role?: () => Response }) {
  return [
    { match: `${USERS}/roles`, respond: () => jsonResponse(ROLES) },
    ...(options.role === undefined ? [] : [{ match: `${USERS}/1/role`, respond: options.role }]),
    { match: USERS, respond: () => jsonResponse(directory(options.activeAdmins)) },
  ];
}

describe('UsersPanel', () => {
  it('marks the only active admin with the server’s own count', async () => {
    stubFetch(routes({ activeAdmins: 1 }));
    const { container } = renderWithProviders(<UsersPanel />);

    const mark = await screen.findByTestId('last-admin-mark');
    expect(mark).toHaveTextContent('Last active admin');
    // The sentence names the rule, so the mark is not a bare adjective.
    expect(screen.getByText(/would leave nobody able to administer/)).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('marks nobody when two admins exist', async () => {
    stubFetch(routes({ activeAdmins: 2 }));
    renderWithProviders(<UsersPanel />);
    await screen.findByText('analyst@example.test');
    expect(screen.queryByTestId('last-admin-mark')).toBeNull();
  });

  it('offers the demotion and renders the refusal when the server refuses it', async () => {
    const user = userEvent.setup();
    stubFetch(
      routes({
        activeAdmins: 1,
        role: () => jsonResponse({ detail: 'would leave no active admin' }, 409),
      }),
    );
    renderWithProviders(<UsersPanel />);

    const picker = await screen.findByLabelText('New role for only@example.test');
    await user.selectOptions(picker, 'viewer');
    const save = screen.getByRole('button', { name: 'Save the new role for only@example.test' });
    // The refusal is the server's answer, so the control is offered: an operator
    // learns the rule by meeting it.
    expect(save).toBeEnabled();
    await user.click(save);

    // Confirmation first (design.md §4.8), then the request.
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(/only@example\.test goes from admin to viewer/),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Change the role' }));

    await waitFor(() => {
      expect(screen.getByTestId('role-refusal')).toHaveTextContent(
        'this change would leave the deployment with no active admin',
      );
    });
  });

  it('reports a change the server made, naming who and when', async () => {
    const user = userEvent.setup();
    stubFetch(
      routes({
        activeAdmins: 2,
        role: () =>
          jsonResponse({
            user_id: 1,
            previous: 'admin',
            applied: 'viewer',
            changed: true,
            at: '2026-10-06T10:00:00Z',
            actor: 'ops@example.test',
          }),
      }),
    );
    renderWithProviders(<UsersPanel />);

    const picker = await screen.findByLabelText('New role for only@example.test');
    await user.selectOptions(picker, 'viewer');
    await user.click(
      screen.getByRole('button', { name: 'Save the new role for only@example.test' }),
    );
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Change the role' }));

    await waitFor(() => {
      expect(screen.getByTestId('role-applied')).toHaveTextContent('Account set to viewer');
    });
    expect(screen.queryByTestId('role-noop')).toBeNull();
  });

  it('reports a no-op as nothing having changed, not as a successful change', async () => {
    // D-038's rule: a repeat writes nothing and audits nothing. Rendering it as a
    // change would put a claim in front of an operator that the trail contradicts.
    const user = userEvent.setup();
    stubFetch(
      routes({
        activeAdmins: 2,
        role: () =>
          jsonResponse({
            user_id: 1,
            previous: 'admin',
            applied: 'viewer',
            changed: false,
            at: '2026-10-06T10:00:00Z',
            actor: 'ops@example.test',
          }),
      }),
    );
    renderWithProviders(<UsersPanel />);

    const picker = await screen.findByLabelText('New role for only@example.test');
    await user.selectOptions(picker, 'viewer');
    await user.click(
      screen.getByRole('button', { name: 'Save the new role for only@example.test' }),
    );
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Change the role' }));

    await waitFor(() => {
      expect(screen.getByTestId('role-noop')).toHaveTextContent('Nothing changed');
    });
    expect(screen.queryByTestId('role-applied')).toBeNull();
  });

  it('disables the save control until a different role is picked', async () => {
    const user = userEvent.setup();
    stubFetch(routes({ activeAdmins: 2 }));
    renderWithProviders(<UsersPanel />);

    const save = await screen.findByRole('button', {
      name: 'Save the new role for only@example.test',
    });
    expect(save).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('New role for only@example.test'), 'viewer');
    expect(
      screen.getByRole('button', { name: 'Save the new role for only@example.test' }),
    ).toBeEnabled();
  });

  it('says a directory of accounts with no active admin is stranded', async () => {
    stubFetch(routes({ activeAdmins: 0 }));
    renderWithProviders(<UsersPanel />);
    expect(
      await screen.findByText(/No active admin: every action on this screen will be refused/),
    ).toBeInTheDocument();
  });

  it('names the empty-directory fact rather than showing a blank table', async () => {
    stubFetch([
      { match: `${USERS}/roles`, respond: () => jsonResponse(ROLES) },
      { match: USERS, respond: () => jsonResponse({ items: [], count: 0, active_admins: 0 }) },
    ]);
    renderWithProviders(<UsersPanel />);
    expect(await screen.findByTestId('users-empty')).toHaveTextContent('no bootstrap account');
  });

  it('refuses to render a roster it could not read', async () => {
    stubFetch([
      { match: `${USERS}/roles`, respond: () => jsonResponse(ROLES) },
      { match: USERS, respond: () => jsonResponse({ detail: 'nope' }, 500) },
    ]);
    renderWithProviders(<UsersPanel />);
    // An error state, not an empty one: "no accounts" is the opposite of what
    // actually happened, and it is the state an operator would act on.
    expect(await screen.findByText('The user directory could not be read')).toBeInTheDocument();
  });
});
