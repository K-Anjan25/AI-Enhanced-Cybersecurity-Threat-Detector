/**
 * The triage loop through the shell, as one task (T-414, R-87).
 *
 * It lives beside `App.test.tsx` because that is the layer it tests — a features-layer test
 * may not import the shell (the boundary check says so, and it is right): `TriagePage.test.tsx`
 * mounts the page with its own route table and checks each zone, and `App.test.tsx` mounts the
 * shell and checks the routing and the landmarks. Neither
 * answers the question an operator's shift asks: *arriving at the console, can one alert
 * be worked and the queue moved on, with nothing but what is on screen to go by?* That is
 * this file, and it is deliberately one test — the loop is a sequence, and a suite of
 * small steps would pass with the links between them broken, because each step would set
 * up its own screen.
 *
 * Nothing is mocked but the network, and every query is by role, label or visible text.
 * The shell is the reason: a query by test id would not be able to name a single one of
 * the landmarks, headings or rows this walk depends on (R-87).
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from './App';
import { resetSessionForTests, setSessionToken } from './api/session';
import { jsonResponse, renderWithProviders, stubFetch, type StubRoute } from './test/query';
import { alertDetail, alertRow, verdictRecord } from './features/triage/fixtures';

const FIRST_CREATED_AT = '2026-03-15T10:00:00Z';
const SECOND_CREATED_AT = '2026-03-15T09:20:00Z';

afterEach(() => {
  resetSessionForTests();
});

/**
 * The loop's four reads and one write, most specific prefix first.
 *
 * `stubFetch` matches by prefix, so `/alerts/42/verdict` has to be registered before the
 * detail it shares a prefix with, and both before the queue.
 */
function routes(): StubRoute[] {
  return [
    {
      match: '/api/v1/alerts/42/verdict',
      respond: () =>
        jsonResponse({ action: 'recorded', record: verdictRecord(), superseded: null }),
    },
    { match: '/api/v1/alerts/42', respond: () => jsonResponse(alertDetail()) },
    {
      match: '/api/v1/alerts/41',
      respond: () =>
        jsonResponse(
          alertDetail({
            alert: alertRow({ id: 41, created_at: SECOND_CREATED_AT }),
          }),
        ),
    },
    {
      match: '/api/v1/alerts',
      respond: () =>
        jsonResponse({
          items: [
            alertRow({ id: 42, created_at: FIRST_CREATED_AT }),
            alertRow({ id: 41, created_at: SECOND_CREATED_AT }),
          ],
          next_cursor: null,
          limit: 100,
          order: 'desc',
        }),
    },
  ];
}

/** The queue link the analyst is currently working, read from the screen. */
function openRow(queue: HTMLElement): HTMLElement | undefined {
  return within(queue)
    .getAllByRole('link')
    .find((link) => link.getAttribute('aria-current') === 'true');
}

describe('the triage loop, from the console as it is mounted', () => {
  it('is walkable end to end: arrive, step, read, record, move on', async () => {
    const user = userEvent.setup();
    const requests = stubFetch(routes());
    setSessionToken('triage-loop-token');
    renderWithProviders(<App />, undefined, ['/alerts']);

    // 1. Arrive. The queue is a named list inside the shell — not a page rendered alone,
    //    which is what makes this an integration test rather than a repeat of the page's.
    const queue = await screen.findByRole('list', { name: 'Alerts' });
    expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
    expect(within(queue).getAllByRole('link')).toHaveLength(2);
    expect(openRow(queue)).toBeUndefined();

    // 2. Step in with the keyboard alone: `j` opens the top alert.
    await user.keyboard('j');
    await waitFor(() =>
      expect(openRow(queue)).toHaveAttribute(
        'href',
        `/alerts/42?created_at=${encodeURIComponent(FIRST_CREATED_AT)}`,
      ),
    );

    // 3. Read it. The four zones §4.3 draws are reachable by their headings, which is
    //    what a screen-reader operator navigates by.
    for (const heading of ['Why we flagged this', 'Timeline', 'Raw evidence', 'Context']) {
      expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument();
    }

    // 4. Record a verdict where the buttons are. The write carries the open alert's
    //    identity, taken from the queue row the loop arrived through.
    await user.keyboard('1');
    expect(await screen.findByText('Verdict recorded: true positive.')).toBeInTheDocument();
    const writes = requests.filter((request) => request.method === 'POST');
    expect(writes).toHaveLength(1);
    expect(new URL(writes[0]?.url ?? '').pathname).toBe('/api/v1/alerts/42/verdict');
    await expect(writes[0]?.json()).resolves.toEqual({
      created_at: FIRST_CREATED_AT,
      verdict: 'true_positive',
    });

    // 5. Move on. `j` again opens the neighbour, and the queue says so.
    await user.keyboard('j');
    await waitFor(() =>
      expect(openRow(queue)).toHaveAttribute(
        'href',
        `/alerts/41?created_at=${encodeURIComponent(SECOND_CREATED_AT)}`,
      ),
    );
    await waitFor(() =>
      expect(
        requests.map((request) => new URL(request.url).pathname).includes('/api/v1/alerts/41'),
      ).toBe(true),
    );

    // 6. And back: the loop is a loop. Nothing was written twice on the way.
    await user.keyboard('k');
    await waitFor(() =>
      expect(openRow(queue)).toHaveAttribute(
        'href',
        `/alerts/42?created_at=${encodeURIComponent(FIRST_CREATED_AT)}`,
      ),
    );
    expect(requests.filter((request) => request.method === 'POST')).toHaveLength(1);
  });
});
