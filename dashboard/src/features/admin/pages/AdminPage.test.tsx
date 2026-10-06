/**
 * The admin page's routing and its section nav (T-410, design.md §3).
 *
 * The sub-routes are the point: a deep link to `/admin/audit` must render the audit
 * panel and not the whole page's set of reads, and the section nav must mark where you
 * are with `aria-current` — the same mechanism the shell's rail uses, so a reader who
 * learned one has learned both. Every route is asserted to render *something* named,
 * because a link to a path with no route is a dead end that looks live.
 */
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { ToastProvider } from '../../../components/ui';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { AdminPage } from './AdminPage';

/** Every read the five panels can issue, so a route can render without a 404. */
function stubs() {
  return [
    { match: '/api/v1/users/roles', respond: () => jsonResponse({ items: [] }) },
    {
      match: '/api/v1/users',
      respond: () => jsonResponse({ items: [], count: 0, active_admins: 0 }),
    },
    { match: '/api/v1/keys/scopes', respond: () => jsonResponse({ items: [] }) },
    { match: '/api/v1/keys', respond: () => jsonResponse({ items: [] }) },
    {
      match: '/api/v1/thresholds',
      respond: () => jsonResponse({ tenant_id: 't1', defaults: {}, items: [] }),
    },
    {
      match: '/api/v1/retention',
      respond: () =>
        jsonResponse({
          planned_at: '2026-10-06T00:00:00Z',
          policy: { raw_records_days: 365, alerts_days: 400, stats_days: 730 },
          drop: [],
          kept: [],
          missing: [],
          unevictable: [],
          external: {},
          statements: [],
        }),
    },
    { match: '/api/v1/audit', respond: () => jsonResponse({ items: [], next_before: null }) },
  ];
}

/**
 * The page under the route the app gives it.
 *
 * `AdminPage` renders its own `<Routes>` with paths relative to the parent, so
 * rendering it bare would match nothing and the test would pass by rendering the nav
 * and no panel — the failing test would then look like a passing one.
 */
function renderAdmin(path: string) {
  return renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/admin/*" element={<AdminPage />} />
      </Routes>
    </ToastProvider>,
    undefined,
    [path],
  );
}

describe('AdminPage', () => {
  it('lists each section with what it answers at /admin', async () => {
    stubFetch(stubs());
    renderAdmin('/admin');
    const heading = await screen.findByRole('heading', { name: 'Sections' });
    expect(heading).toBeInTheDocument();
    for (const label of [
      'Users & roles',
      'API keys',
      'Thresholds',
      'Retention & GDPR',
      'Audit log',
    ]) {
      expect(screen.getAllByRole('link', { name: label }).length).toBeGreaterThan(0);
    }
    // The one section design.md §3 lists that no task has built: it says so with the
    // task that will build it rather than pretending the screen exists.
    expect(screen.getByText('Connectors')).toBeInTheDocument();
    expect(screen.getByText(/T-422/)).toBeInTheDocument();
  });

  it('marks the current section in the nav', async () => {
    stubFetch(stubs());
    renderAdmin('/admin/keys');
    const nav = await screen.findByRole('navigation', { name: 'Admin sections' });
    expect(within(nav).getByRole('link', { name: 'API keys' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Audit log' })).not.toHaveAttribute(
      'aria-current',
    );
  });

  it.each([
    ['/admin/users', 'Users and roles'],
    ['/admin/keys', 'API keys'],
    ['/admin/thresholds', 'Thresholds'],
    ['/admin/retention', 'Retention'],
    ['/admin/audit', 'Audit log'],
    ['/admin/users/roles', 'What each role may do'],
  ])('renders the panel behind %s', async (path, heading) => {
    stubFetch(stubs());
    renderAdmin(path);
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
  });
});
