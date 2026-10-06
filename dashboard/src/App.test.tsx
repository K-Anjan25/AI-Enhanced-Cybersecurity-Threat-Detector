import { render, screen } from '@testing-library/react';
import { act } from 'react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { NAV_ITEMS } from './components/layout/nav';
import { expectAccessible } from './test/axe';
import { jsonResponse, stubFetch, testQueryClient, textResponse } from './test/query';
import { stubViewport } from './test/viewport';
import { ThemeProvider } from './theme/ThemeProvider';

/**
 * The overview fetches on mount, so the shell's tests stub the network too rather
 * than rendering it against a real one. What is being checked here is the routing
 * and the shell; the page's own behaviour is OverviewPage.test.tsx.
 */
function renderAt(path: string) {
  const seen = stubFetch([
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
  const view = render(
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient()}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  // The requests, for the one claim that is about the network rather than the DOM: a
  // screen the viewport refuses must not be fetched (T-412).
  return Object.assign(seen, view);
}

afterEach(() => {
  // Removes the `fetch` stub and the viewport stub (T-412) together, so no test
  // inherits a window width.
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

describe('below 768 px the console is the triage loop (T-412)', () => {
  it('offers the queue, and says why the rest of the console is absent', async () => {
    stubViewport(500);
    renderAt('/alerts');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Alert triage' }),
    ).toBeInTheDocument();
    // §8.3's banner: the statement, the number that makes it checkable, and what to do
    // about it.
    const banner = await screen.findByRole('status', { name: 'Screen size' });
    expect(banner).toHaveTextContent('Only alert triage is offered at this window size.');
    expect(banner).toHaveTextContent('at least 768 px wide');
    expect(screen.getByRole('link', { name: 'Go to the alert queue' })).toBeInTheDocument();
  });

  it('does not render a nav rail whose entries would refuse to open', () => {
    stubViewport(500);
    renderAt('/alerts');

    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Traffic' })).not.toBeInTheDocument();
  });

  it('replaces a screen the window cannot show, and fetches nothing for it', () => {
    stubViewport(500);
    const seen = renderAt('/');

    // The whole page is absent rather than hidden, which is what makes the criterion
    // checkable by request count: a phone must not load a dashboard nobody can read.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Not offered at this window size' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Alert volume by severity' }),
    ).not.toBeInTheDocument();
    expect(seen, 'a narrow window still fetched a hidden screen').toHaveLength(0);
  });

  it('refuses every area the design keeps for a larger screen', () => {
    stubViewport(500);
    for (const path of ['/traffic', '/logs', '/hunt', '/models', '/models/drift', '/admin']) {
      const first = renderAt(path);
      expect(
        screen.getByRole('heading', { level: 1, name: 'Not offered at this window size' }),
        `${path} was offered below 768 px`,
      ).toBeInTheDocument();
      first.unmount();
    }
  });

  it('offers only the queue in the palette', async () => {
    stubViewport(500);
    const user = userEvent.setup();
    renderAt('/alerts');

    await user.keyboard('{Control>}k{/Control}');

    expect(await screen.findByRole('option', { name: /Alerts/ })).toBeInTheDocument();
    for (const label of ['Traffic', 'Logs', 'Hunt', 'Model ops', 'Admin']) {
      expect(screen.queryByRole('option', { name: new RegExp(label) })).not.toBeInTheDocument();
    }
  });

  it('offers the full console again once the window is wide enough', async () => {
    // The guard is reactive, not a decision taken once at start-up: resizing has to
    // bring the screens back, or an operator who rotates a tablet is stuck.
    const viewport = stubViewport(500);
    renderAt('/');

    expect(
      screen.getByRole('heading', { level: 1, name: 'Not offered at this window size' }),
    ).toBeInTheDocument();

    act(() => {
      viewport.setWidth(1280);
    });

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Screen size' })).not.toBeInTheDocument();
  });

  it('starts the rail collapsed to icons between 1024 and 1439 px', async () => {
    // §8.3's second row. The labels are the thing that disappears, so the wordmark is
    // what this asserts on: a rail that is present, 56 px wide and showing letters is
    // not the icon rail the design asks for.
    stubViewport(1200);
    renderAt('/');
    const rail = screen.getByRole('navigation', { name: 'Primary' });
    expect(rail).toBeInTheDocument();
    expect(rail).not.toHaveTextContent('AEGIS');
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument();

    // And the operator's own choice wins over the default.
    await userEvent.setup().click(screen.getByRole('button', { name: 'Expand navigation' }));
    expect(rail).toHaveTextContent('AEGIS');
  });

  it('starts the rail expanded on a large monitor', () => {
    stubViewport(1600);
    renderAt('/');

    expect(screen.getByRole('navigation', { name: 'Primary' })).toHaveTextContent('AEGIS');
    expect(screen.getByRole('button', { name: 'Collapse navigation' })).toBeInTheDocument();
  });

  it('has no serious accessibility violations on the narrow screen', async () => {
    stubViewport(500);
    const { container } = renderAt('/alerts');

    await expectAccessible(container as HTMLElement);
  });
});
