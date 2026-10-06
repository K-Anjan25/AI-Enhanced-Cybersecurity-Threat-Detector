/**
 * The triage screen, end to end over a stubbed network.
 *
 * `fetch` is the only thing faked: the real page, the real React Query wiring, the
 * real components and the real view model all run, and every assertion is on what
 * reached the DOM or on the request that left it. That is the difference between
 * testing this screen and testing a mock's cooperation.
 *
 * The acceptance criteria live here:
 *
 *   * *the full triage loop is completable without a mouse* — the test focuses a
 *     queue row and presses Enter, never clicking;
 *   * *`explanation_unavailable` and `evidence expired` render explicitly* — two
 *     tests assert the operator can read both states in words.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, Providers, stubFetch, type StubRoute } from '../../../test/query';
import {
  alertDetail,
  alertRow,
  evidence,
  explanation,
  occurrence,
  verdictRecord,
} from '../fixtures';
import { TriagePage } from './TriagePage';
import type { AlertDetail } from '../types';

const ENTRY = '/alerts/42?created_at=2026-03-15T10%3A00%3A00Z';

/**
 * The three routes these tests need, registered most-specific first.
 *
 * Order matters twice over: the stubs match by path prefix, so `/alerts/42` must
 * be registered before `/alerts`, and the verdict write must be registered before
 * the detail it shares a prefix with. An override replaces one route rather than
 * being prepended to all of them — a failing queue must not take the detail down
 * with it, which is itself one of the cases below.
 */
interface RouteSet {
  verdict?: StubRoute['respond'];
  detail?: StubRoute['respond'];
  queue?: StubRoute['respond'];
}

function routes(detail: AlertDetail, overrides: RouteSet = {}): StubRoute[] {
  const queue: StubRoute['respond'] = () =>
    jsonResponse({
      items: [alertRow({ id: 42 }), alertRow({ id: 41, created_at: '2026-03-15T09:20:00Z' })],
      next_cursor: null,
      limit: 100,
      order: 'desc',
    });
  return [
    {
      match: '/api/v1/alerts/42/verdict',
      respond:
        overrides.verdict ??
        (() => jsonResponse({ action: 'recorded', record: verdictRecord(), superseded: null })),
    },
    {
      match: '/api/v1/alerts/42',
      respond: overrides.detail ?? (() => jsonResponse(detail)),
    },
    { match: '/api/v1/alerts', respond: overrides.queue ?? queue },
  ];
}

function renderPage(
  detail: AlertDetail,
  entry = ENTRY,
  overrides: RouteSet = {},
): { requests: Request[]; container: HTMLElement } {
  const requests = stubFetch(routes(detail, overrides));
  const { container } = render(
    <Providers initialEntries={[entry]}>
      <Routes>
        <Route path="/alerts" element={<TriagePage />} />
        <Route path="/alerts/:alertId" element={<TriagePage />} />
      </Routes>
    </Providers>,
  );
  return { requests, container };
}

describe('TriagePage', () => {
  it('renders the four zones design.md §4.3 draws', async () => {
    renderPage(alertDetail());

    expect(await screen.findByRole('heading', { name: 'Why we flagged this' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Timeline' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Raw evidence' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Context' })).toBeInTheDocument();
  });

  it('opens an alert from the queue and records a verdict with the keyboard alone', async () => {
    // The acceptance criterion: pick, read, press a key. No clicks anywhere — the
    // row is focused and activated with the keyboard, as a Tabbing analyst would.
    const { requests } = renderPage(alertDetail(), '/alerts');
    const queue = await screen.findByRole('list', { name: 'Alerts' });
    const row = within(queue).getAllByRole('link')[0] as HTMLElement;
    row.focus();
    await userEvent.keyboard('{Enter}');

    await screen.findByRole('heading', { name: 'Raw evidence' });
    await userEvent.keyboard('1');

    const write = await waitFor(() => {
      const found = requests.find((request) => request.method === 'POST');
      if (found === undefined) throw new Error('no verdict write was sent');
      return found;
    });
    expect(new URL(write.url).pathname).toBe('/api/v1/alerts/42/verdict');
    await expect(write.json()).resolves.toEqual({
      created_at: '2026-03-15T10:00:00Z',
      verdict: 'true_positive',
    });
    expect(await screen.findByText('Verdict recorded: true positive.')).toBeInTheDocument();
  });

  it('announces an unchanged verdict as no change rather than as a write', async () => {
    renderPage(alertDetail(), ENTRY, {
      verdict: () =>
        jsonResponse({ action: 'unchanged', record: verdictRecord(), superseded: null }),
    });
    await screen.findByRole('heading', { name: 'Why we flagged this' });

    // The key pressed and the verdict the server reports need not agree here: an
    // `unchanged` answer is the server saying what is *already* current, and the
    // screen must repeat that rather than claim the key's verdict was written.
    await userEvent.keyboard('2');

    expect(
      await screen.findByText('true positive was already the current verdict.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Verdict recorded:/)).not.toBeInTheDocument();
  });

  it('states a refused verdict write where the buttons are', async () => {
    renderPage(alertDetail(), ENTRY, {
      verdict: () => jsonResponse({ detail: 'your role may not record verdicts' }, 403),
    });
    await screen.findByRole('heading', { name: 'Why we flagged this' });

    await userEvent.keyboard('1');

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe('Your role may not record verdicts.');
    expect(alert.textContent).not.toMatch(/http|api\/v1|detail/);
  });

  it('renders explanation_unavailable with its reason, explicitly', async () => {
    renderPage(
      alertDetail({
        explanation: explanation({
          reasons: [],
          unavailable: true,
          detail: 'occlusion timed out',
        }),
      }),
    );

    expect(await screen.findByText(/explanation_unavailable/)).toBeInTheDocument();
    expect(screen.getByText('occlusion timed out')).toBeInTheDocument();
  });

  it('renders evidence expired with the date the records went', async () => {
    renderPage(
      alertDetail({
        evidence: evidence({
          expired: true,
          occurrences: [occurrence({ expired: true, expires_at: '2026-04-14T10:00:00Z' })],
        }),
      }),
    );

    expect(
      await screen.findByText('evidence expired at 14 Apr 2026, 10:00:00Z'),
    ).toBeInTheDocument();
  });

  it('shows the family hint on the alert being triaged', async () => {
    renderPage(
      alertDetail({
        family_history: {
          family: 'Reconnaissance',
          window_days: 30,
          prior_alerts: 3,
          labelled: 3,
          false_positive: 2,
          benign: 0,
          true_positive: 1,
        },
      }),
    );

    expect(await screen.findByText(/2 of 3 reviewed alerts a false positive/)).toBeInTheDocument();
  });

  it('says which half of the address is missing, and does not ask for the alert', async () => {
    // D-030: an id alone is not an address, so the page must not send a request
    // that cannot be answered.
    const { requests } = renderPage(alertDetail(), '/alerts/42');

    expect(
      await screen.findByText("The link is missing the alert's created_at"),
    ).toBeInTheDocument();
    expect(requests.some((request) => new URL(request.url).pathname === '/api/v1/alerts/42')).toBe(
      false,
    );
  });

  it('asks for nothing until an alert is open', async () => {
    const { requests } = renderPage(alertDetail(), '/alerts');

    expect(await screen.findByText('Select an alert from the queue')).toBeInTheDocument();
    expect(
      requests.some((request) => new URL(request.url).pathname.startsWith('/api/v1/alerts/')),
    ).toBe(false);
  });

  it('keeps the open alert on screen when the queue read fails', async () => {
    renderPage(alertDetail(), ENTRY, { queue: () => jsonResponse({ detail: 'boom' }, 500) });

    expect(await screen.findByText('The queue could not be loaded')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Why we flagged this' })).toBeInTheDocument();
  });

  it('states a detail that could not be loaded instead of an empty screen', async () => {
    renderPage(alertDetail(), ENTRY, {
      detail: () => jsonResponse({ detail: 'no alert' }, 404),
    });

    expect(await screen.findByText('No alert was returned for this address')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to the queue' })).toBeInTheDocument();
  });

  it('marks the open alert in the queue', async () => {
    renderPage(alertDetail());

    const queue = await screen.findByRole('list', { name: 'Alerts' });
    const current = within(queue)
      .getAllByRole('link')
      .find((link) => link.getAttribute('aria-current') === 'true');
    expect(current).toHaveAttribute('href', '/alerts/42?created_at=2026-03-15T10%3A00%3A00Z');
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderPage(alertDetail());
    await screen.findByRole('heading', { name: 'Why we flagged this' });

    await expectAccessible(container);
  });
});
