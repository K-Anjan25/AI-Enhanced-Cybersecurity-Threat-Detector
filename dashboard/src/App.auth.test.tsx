import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { resetSessionForTests, sessionToken } from './api/session';
import { expectAccessible } from './test/axe';
import { jsonResponse, renderWithProviders, stubFetch, type StubRoute } from './test/query';

const CREDENTIALS = {
  access_token: 'signed-access-token',
  refresh_token: 'signed-refresh-token',
  token_type: 'bearer',
  expires_in: 900,
  subject: 'operator@example.test',
  role: 'admin',
};

function authenticatedRoutes(setupAvailable: boolean): StubRoute[] {
  return [
    {
      match: '/api/v1/auth/status',
      respond: () =>
        jsonResponse({
          setup_enabled: setupAvailable,
          setup_available: setupAvailable,
          account_exists: !setupAvailable,
        }),
    },
    { match: '/api/v1/auth/login', respond: () => jsonResponse(CREDENTIALS) },
    { match: '/api/v1/auth/setup', respond: () => jsonResponse(CREDENTIALS, 201) },
    { match: '/api/v1/auth/logout', respond: () => new Response(null, { status: 204 }) },
    { match: '/api/v1/models', respond: () => jsonResponse({ items: [], count: 0 }) },
  ];
}

afterEach(() => {
  resetSessionForTests();
  vi.unstubAllGlobals();
});

describe('the dashboard authentication gate', () => {
  it('signs in, sends the bearer token to protected endpoints, and signs out', async () => {
    const user = userEvent.setup();
    const requests = stubFetch(authenticatedRoutes(false));
    const { container } = renderWithProviders(<App />, undefined, ['/models']);

    expect(await screen.findByRole('heading', { name: 'ACCESS TERMINAL' })).toBeInTheDocument();
    await expectAccessible(container as HTMLElement);
    await user.type(screen.getByLabelText('Email address'), 'operator@example.test');
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery-42');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('heading', { name: 'Model ops' })).toBeInTheDocument();
    const modelRequest = requests.find(
      (request) => new URL(request.url).pathname === '/api/v1/models',
    );
    expect(modelRequest?.headers.get('authorization')).toBe('Bearer signed-access-token');
    expect(sessionToken()).toBe('signed-access-token');

    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('heading', { name: 'ACCESS TERMINAL' })).toBeInTheDocument();
    await waitFor(() => expect(sessionToken()).toBeNull());
    expect(
      requests.some((request) => new URL(request.url).pathname === '/api/v1/auth/logout'),
    ).toBe(true);
  });

  it('lets the operator choose first-run credentials when local setup is enabled', async () => {
    const user = userEvent.setup();
    const requests = stubFetch(authenticatedRoutes(true));
    renderWithProviders(<App />, undefined, ['/models']);

    expect(
      await screen.findByRole('heading', { name: 'CREATE ADMINISTRATOR' }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText('Email address'), 'operator@example.test');
    await user.type(screen.getByLabelText('Password'), 'a-strong-local-password-42');
    await user.type(screen.getByLabelText('Confirm password'), 'a-strong-local-password-42');
    await user.click(screen.getByRole('button', { name: 'Create administrator' }));

    expect(await screen.findByRole('heading', { name: 'Model ops' })).toBeInTheDocument();
    const setupRequest = requests.find(
      (request) => new URL(request.url).pathname === '/api/v1/auth/setup',
    );
    expect(setupRequest?.method).toBe('POST');
    expect(setupRequest?.headers.get('authorization')).toBeNull();
    await expect(setupRequest?.json()).resolves.toEqual({
      email: 'operator@example.test',
      password: 'a-strong-local-password-42', // pragma: allowlist secret
    });
  });
});
