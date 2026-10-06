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
      respond: (request) =>
        // The list answers an empty page; anything *below* the list (`/alerts/42`)
        // is a detail this stub has no row for, so it says so rather than handing
        // the detail read a page-shaped body.
        new URL(request.url).pathname === '/api/v1/alerts'
          ? jsonResponse({ items: [], next_cursor: null, limit: 1_000, order: 'desc' })
          : jsonResponse({ detail: 'no alert at that address' }, 404),
    },
    {
      match: '/api/v1/logs',
      respond: () =>
        jsonResponse({
          start: '2026-10-06T10:00:00Z',
          end: '2026-10-06T10:05:00Z',
          clusters: [],
          lines_seen: 0,
          clusters_seen: 0,
          clusters_truncated: false,
          retained_from: null,
          retained_to: null,
          retained_lines: 0,
          dropped_lines: 0,
          caveats: ['Nothing has arrived in this window'],
        }),
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

  it('navigates to the traffic explorer, which is built now', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Traffic' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Traffic' })).toBeInTheDocument();
    expect(screen.queryByText('Not built yet')).not.toBeInTheDocument();
  });

  it('navigates to the log explorer, which is built now', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Logs' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Logs' })).toBeInTheDocument();
    expect(screen.queryByText('Not built yet')).not.toBeInTheDocument();
    // The stubbed tail is empty and says why, which is the log screen's own claim
    // about a bounded buffer rather than a blank table.
    expect(await screen.findByText('Nothing has arrived in this window')).toBeInTheDocument();
  });

  it('navigates to a screen that is not built and names the task that owns it', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Hunt' }));

    expect(screen.getByRole('heading', { level: 1, name: 'Not built yet' })).toBeInTheDocument();
    expect(screen.getByText('T-408')).toBeInTheDocument();
  });

  it('mounts the triage screen at /alerts, which is built now', async () => {
    renderAt('/alerts');

    expect(screen.getByRole('heading', { level: 1, name: 'Alert triage' })).toBeInTheDocument();
    // The queue is a real read: the stubbed empty window is described as empty.
    expect(await screen.findByText('No alerts in the window')).toBeInTheDocument();
  });

  it('opens an alert detail route that carries a partition key', async () => {
    renderAt('/alerts/42?created_at=2026-03-15T10%3A00%3A00Z');

    // The stub answers every alert path with an empty queue, so the detail read
    // fails; what is asserted here is that the route reaches the detail branch
    // rather than the list — the zones belong to TriagePage.test.tsx.
    expect(await screen.findByText('No alert was returned for this address')).toBeInTheDocument();
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
