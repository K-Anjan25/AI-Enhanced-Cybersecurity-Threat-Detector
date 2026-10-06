import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { expectAccessible } from './test/axe';
import { jsonResponse, stubFetch, testQueryClient, textResponse } from './test/query';
import { ThemeProvider } from './theme/ThemeProvider';

/**
 * The overview fetches on mount, so the shell's tests stub the network too rather
 * than rendering it against a real one. What is being checked here is the routing
 * and the shell; the page's own behaviour is OverviewPage.test.tsx.
 */
function renderAt(path: string) {
  stubFetch([
    {
      match: '/api/v1/alerts',
      respond: () => jsonResponse({ items: [], next_cursor: null, limit: 1_000, order: 'desc' }),
    },
    { match: '/metrics', respond: () => textResponse('') },
    {
      match: '/readyz',
      respond: () =>
        jsonResponse({ status: 'ready', service: 'aegis', version: '0.1.0', checks: [] }),
    },
  ]);
  return render(
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('routing and shell', () => {
  it('renders the overview page at the root', () => {
    renderAt('/');

    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
  });

  it('renders the full information architecture in the nav', () => {
    renderAt('/');

    const nav = screen.getByRole('navigation', { name: 'Primary' });
    for (const label of ['Overview', 'Alerts', 'Traffic', 'Logs', 'Hunt', 'Models', 'Admin']) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it('navigates to a pending screen and names the task that owns it', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Alerts' }));

    expect(screen.getByRole('heading', { level: 1, name: 'Not built yet' })).toBeInTheDocument();
    expect(screen.getByText('T-404')).toBeInTheDocument();
  });

  it('shows a 404 state rather than a blank page for an unknown route', () => {
    renderAt('/does-not-exist');

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
  });

  it('mounts the overview, which is the real screen now', async () => {
    renderAt('/');

    expect(
      await screen.findByRole('heading', { name: 'Alert volume by severity' }),
    ).toBeInTheDocument();
    // The empty window is described as empty, not drawn as a blank panel.
    expect(screen.getByText(/No alerts in the Last 24 h\./)).toBeInTheDocument();
  });

  it('has no serious accessibility violations on the overview screen', async () => {
    const { container } = renderAt('/');

    await expectAccessible(container as HTMLElement);
  });
});
