import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { NAV_ITEMS } from './components/layout/nav';
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
    {
      match: '/api/v1/models',
      respond: () => jsonResponse({ items: [], count: 0 }),
    },
    // The admin page's index is a menu, so these four reads are what its panels
    // would issue; the one that runs on mount at `/admin` is none of them.
    {
      match: '/api/v1/users',
      respond: () => jsonResponse({ items: [], count: 0, active_admins: 0 }),
    },
    { match: '/api/v1/keys', respond: () => jsonResponse({ items: [] }) },
    {
      match: '/api/v1/thresholds',
      respond: () => jsonResponse({ tenant_id: 't1', defaults: {}, items: [] }),
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
    // Read from the model the rail is built from (T-411), so renaming a screen
    // cannot leave this test asserting the old information architecture.
    for (const item of NAV_ITEMS) expect(nav).toHaveTextContent(item.label);
    for (const section of new Set(NAV_ITEMS.map((item) => item.section))) {
      expect(nav).toHaveTextContent(section);
    }
  });

  it('opens the palette from anywhere in the shell and runs what it names (T-411)', async () => {
    // The acceptance criterion at the level an operator meets it: the key opens the
    // palette over the screen they are on, the palette filters, and Enter goes there.
    const user = userEvent.setup();
    renderAt('/');

    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('combobox', { name: 'Search' }), 'hunt');
    await user.keyboard('{Enter}');

    expect(await screen.findByRole('heading', { level: 1, name: 'Hunt' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been searched yet/)).toBeInTheDocument();
    // The dialog closed behind the navigation rather than staying over the screen
    // it just opened.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers the admin sections the rail keeps behind one entry (T-411)', async () => {
    // design.md §3 gives Admin one rail entry and the page its own section nav; the
    // palette lists the children anyway, which is the point of a command palette.
    const user = userEvent.setup();
    renderAt('/');

    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('combobox', { name: 'Search' }), 'audit');

    expect(await screen.findByRole('option', { name: /Audit log/ })).toBeInTheDocument();
  });

  it('opens the in-app shortcut reference from the shell (T-411)', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.keyboard('?');

    const dialog = await screen.findByRole('dialog', { name: 'Keyboard shortcuts' });
    // The reference documents the set design.md §9 fixes, not a subset of it.
    expect(dialog).toHaveTextContent('Open the command palette');
    expect(dialog).toHaveTextContent('Open the next or previous alert');
    expect(dialog).toHaveTextContent('Record a verdict on the open alert');
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

  it('navigates to the hunt console, which is built now', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Hunt' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Hunt' })).toBeInTheDocument();
    expect(screen.queryByText('Not built yet')).not.toBeInTheDocument();
    // The console does not search until asked, and says so rather than showing an
    // empty table that would read as a quiet network.
    expect(screen.getByText(/Nothing has been searched yet/)).toBeInTheDocument();
  });

  it('mounts the model ops screen at /models, which is built now', async () => {
    renderAt('/models');

    expect(await screen.findByRole('heading', { level: 1, name: 'Model ops' })).toBeInTheDocument();
    expect(screen.queryByText('Not built yet')).not.toBeInTheDocument();
    // The stubbed registry is empty and the screen says so rather than rendering an
    // empty table that would read as a deployment with no models.
    expect(await screen.findByText('No model versions are registered')).toBeInTheDocument();
  });

  it('mounts the admin screen at /admin, which is built now', async () => {
    renderAt('/admin');

    expect(screen.getByRole('heading', { level: 1, name: 'Admin' })).toBeInTheDocument();
    // The index is a map of the sections, and the one section with no task says so.
    // Twice by design: the section rail and the index map both list it.
    expect(await screen.findAllByRole('link', { name: 'Audit log' })).toHaveLength(2);
    expect(screen.getByText(/until T-422/)).toBeInTheDocument();
    expect(screen.queryByText('Not built yet')).not.toBeInTheDocument();
  });

  it('navigates to a screen that is not built and names the task that owns it', () => {
    // `/admin/connectors` is design.md §3's sixth admin route and the only one left
    // with no task row (T-422). At least one pending path must stay stubbed, or the
    // not-built state would be an untested claim.
    renderAt('/admin/connectors');

    expect(screen.getByRole('heading', { level: 1, name: 'Not built yet' })).toBeInTheDocument();
    expect(screen.getByText('T-422')).toBeInTheDocument();
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
