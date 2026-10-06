/**
 * The log explorer, end to end through the page an operator opens.
 *
 * Only the network (`fetch`, via the shared stub) and the clock, where a window is
 * asserted, are faked. Everything between — the query, the fold into clusters, the
 * table, the pause control, the expansion — is the real code, so the assertions are
 * on what the screen says: that ten thousand identical lines are one row with a
 * count, that pausing freezes the window *and* stops the reading, and that the
 * caveats about what a bounded tail is arrive verbatim.
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { LogsPage } from './LogsPage';
import type { LogCluster, LogLines, LogTail } from '../api';

const NOW = Date.parse('2026-10-06T10:05:00Z');

function cluster(overrides: Partial<LogCluster> = {}): LogCluster {
  return {
    key: 't-1',
    template_id: 't-1',
    count: 1,
    first_seen: '2026-10-06T10:00:00Z',
    last_seen: '2026-10-06T10:00:09Z',
    worst_level: 'info',
    levels: { info: 1 },
    hosts: ['web-1'],
    services: ['api'],
    sample_message: 'connection refused',
    parameters: {},
    ...overrides,
  };
}

/** Ten thousand identical lines: the case §4.5 exists for. */
const BURST = cluster({
  key: 't-retry',
  template_id: 't-retry',
  count: 10_000,
  levels: { error: 1, info: 9_999 },
  worst_level: 'error',
  first_seen: '2026-10-06T10:00:00Z',
  last_seen: '2026-10-06T10:04:59Z',
  hosts: ['web-1', 'web-2', 'web-3'],
  services: ['api'],
  sample_message: 'connection refused to upstream billing',
});

const QUIET = cluster({
  key: 't-quiet',
  template_id: 't-quiet',
  count: 3,
  worst_level: 'warning',
  levels: { warning: 3 },
  hosts: ['web-1'],
  services: ['worker'],
  sample_message: 'queue depth above the warning mark',
});

const CAVEATS = [
  'The tail is a bounded in-process buffer of accepted log lines, not a store: it holds the most recent 20,000 lines or 15 minutes, whichever comes first.',
  'Reads are capped at 15 minutes.',
  'Every line here was accepted for ingestion, and its level is the level the sender declared — it is not a model’s anomaly score.',
  'The persistent log read model is not built yet (T-419).',
];

function tail(overrides: Partial<LogTail> = {}): LogTail {
  return {
    start: '2026-10-06T10:00:00Z',
    end: '2026-10-06T10:05:00Z',
    clusters: [BURST, QUIET],
    lines_seen: 10_003,
    clusters_seen: 2,
    clusters_truncated: false,
    retained_from: '2026-10-06T09:50:00Z',
    retained_to: '2026-10-06T10:04:59Z',
    retained_lines: 10_003,
    dropped_lines: 0,
    caveats: CAVEATS,
    ...overrides,
  };
}

function lines(overrides: Partial<LogLines> = {}): LogLines {
  return {
    start: '2026-10-06T10:00:00Z',
    end: '2026-10-06T10:05:00Z',
    key: 't-retry',
    lines: [
      {
        timestamp: '2026-10-06T10:00:00Z',
        host: 'web-1',
        service: 'api',
        level: 'error',
        message: 'connection refused to upstream billing',
        template_id: 't-retry',
        parameters: {},
        key: 't-retry',
      },
      {
        timestamp: '2026-10-06T10:04:59Z',
        host: 'web-2',
        service: 'api',
        level: 'info',
        message: 'connection refused to upstream billing',
        template_id: 't-retry',
        parameters: {},
        key: 't-retry',
      },
    ],
    lines_seen: 10_000,
    lines_truncated: true,
    retained_from: '2026-10-06T09:50:00Z',
    retained_to: '2026-10-06T10:04:59Z',
    retained_lines: 10_003,
    dropped_lines: 0,
    caveats: [CAVEATS[0] ?? ''],
    ...overrides,
  };
}

/** The lines route is registered first: the stub takes the first matching prefix. */
function stubLogs(body: LogTail | (() => LogTail) = tail(), raw: LogLines = lines()) {
  return stubFetch([
    { match: '/api/v1/logs/lines', respond: () => jsonResponse(raw) },
    {
      match: '/api/v1/logs',
      respond: () => jsonResponse(typeof body === 'function' ? body() : body),
    },
  ]);
}

function renderPage() {
  return renderWithProviders(<LogsPage />, undefined, ['/logs']);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('LogsPage', () => {
  it('folds ten thousand identical lines into one row with a count', async () => {
    stubLogs();
    renderPage();

    const table = await screen.findByRole('table', { name: /Log clusters/ });

    expect(within(table).getByRole('button', { name: 't-retry' })).toBeInTheDocument();
    expect(within(table).getByText('×10,000')).toBeInTheDocument();
    // Two templates, so two rows — not ten thousand.
    expect(within(table).getAllByRole('row')).toHaveLength(3);
  });

  it('summarises what was read, including how many rows hold an error or worse', async () => {
    stubLogs();
    renderPage();

    // The counts are the read result: `Reading the tail…` cannot satisfy this,
    // so the assertion waits for the read rather than for the element.
    await waitFor(() =>
      expect(
        screen.getByText(/2 clusters · 10,003 lines · 1 with an error or worse/),
      ).toBeInTheDocument(),
    );
  });

  it('carries the API’s caveats through word for word', async () => {
    stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    // "not a store" is a claim about the deployment, so the screen renders the
    // server's sentence rather than one of its own.
    expect(screen.getByText(/not a store/)).toBeInTheDocument();
    expect(screen.getByText(/not a model’s anomaly score/)).toBeInTheDocument();
    expect(screen.getByText(/T-419/)).toBeInTheDocument();
  });

  it('says an alert cannot be jumped to rather than offering a dead link', async () => {
    stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    expect(screen.getByText(/not available in this build/)).toBeInTheDocument();
  });

  it('reads a bounded window and sends no level filter for "all"', async () => {
    const requests = stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    const url = new URL(requests.at(0)?.url ?? '');
    const span =
      Date.parse(url.searchParams.get('end') ?? '') -
      Date.parse(url.searchParams.get('start') ?? '');

    expect(span).toBe(300_000);
    // "All levels" means no filter at all: `level=all` is a value the API has no
    // reason to understand.
    expect(url.searchParams.get('level')).toBeNull();
  });

  it('narrows the read server-side when a level is chosen', async () => {
    const requests = stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    // By role, not by label text: the table's column picker has a "Level" too.
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Level' }), 'error');

    await waitFor(() => {
      const levels = requests.map((request) => new URL(request.url).searchParams.get('level'));
      expect(levels).toContain('error');
    });
  });

  it('moves the window when a wider span is chosen', async () => {
    const requests = stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Window' }), '15m');

    await waitFor(() => {
      const url = new URL(requests.at(-1)?.url ?? '');
      const span =
        Date.parse(url.searchParams.get('end') ?? '') -
        Date.parse(url.searchParams.get('start') ?? '');
      expect(span).toBe(900_000);
    });
  });

  it('reads no raw lines until a row is opened', async () => {
    const requests = stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    // The expansion is a look, not a stream: an unkeyed read here would answer with
    // every line in the window, on a screen nobody has asked a question of yet.
    expect(requests.filter((request) => request.url.includes('/logs/lines'))).toHaveLength(0);
  });

  it('opens a cluster and reads the raw lines behind it', async () => {
    const requests = stubLogs();
    renderPage();
    const table = await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.click(within(table).getByRole('button', { name: 't-retry' }));

    // The sample message is on the row too, so the panel is found by its heading
    // rather than by a message that appears twice.
    expect(await screen.findByRole('heading', { name: 'Raw lines · t-retry' })).toBeInTheDocument();
    // Oldest first, and the button says which row is open rather than only changing
    // colour.
    expect(within(table).getByRole('button', { name: 't-retry' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(
      requests.map((request) => new URL(request.url).searchParams.get('key')).filter(Boolean),
    ).toEqual(['t-retry']);
  });

  it('says which end a truncated expansion kept', async () => {
    stubLogs();
    renderPage();
    const table = await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.click(within(table).getByRole('button', { name: 't-retry' }));

    await waitFor(() =>
      expect(screen.getByText(/Showing the newest 2 of 10,000 matching lines/)).toBeInTheDocument(),
    );
  });

  it('closes an expansion with the row, so the panel cannot outlive its row', async () => {
    stubLogs();
    renderPage();
    const table = await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.click(within(table).getByRole('button', { name: 't-retry' }));
    await screen.findByText(/Showing the newest 2 of 10,000 matching lines/);
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));

    await waitFor(() => expect(screen.queryByText(/Raw lines/)).toBeNull());
    // The row's sample message is a different element from the panel's, so this is
    // the table's text and it is still there.
    expect(within(table).getByText('connection refused to upstream billing')).toBeInTheDocument();
  });

  it('describes an empty window with the API’s own reason', async () => {
    stubLogs(
      tail({
        clusters: [],
        lines_seen: 0,
        clusters_seen: 0,
        caveats: [CAVEATS[0] ?? '', 'Nothing has arrived in this window'],
      }),
    );
    renderPage();

    expect(await screen.findByText('Nothing has arrived in this window')).toBeInTheDocument();
  });

  it('names the failure and offers a retry when the read fails', async () => {
    stubFetch([
      { match: '/api/v1/logs/lines', respond: () => jsonResponse({ detail: 'no route' }, 404) },
      { match: '/api/v1/logs', respond: () => jsonResponse({ detail: 'boom' }, 500) },
    ]);
    renderPage();

    expect(await screen.findByText('The log tail could not be read')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('does not move a paused window when the span is changed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    const requests = stubLogs();
    renderPage();
    const table = await screen.findByRole('table', { name: /Log clusters/ });
    await userEvent.click(within(table).getByRole('button', { name: 't-retry' }));
    await screen.findByRole('heading', { name: 'Raw lines · t-retry' });

    await userEvent.click(screen.getByRole('button', { name: 'Pause tail' }));
    const reads = requests.filter((request) => request.url.includes('/logs/lines')).length;

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Window' }), '15m');

    // While paused the window is the thing being held: a span change is a change to
    // what would be asked for, not to what is on screen, so it re-reads nothing.
    await waitFor(() =>
      expect(requests.filter((request) => request.url.includes('/logs/lines'))).toHaveLength(reads),
    );
    expect(screen.getByText(/Paused at/)).toBeInTheDocument();
  });

  it('has no serious accessibility violations once loaded', async () => {
    stubLogs();
    const { container } = renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    await expectAccessible(container as HTMLElement);
  });
});

describe('the tail under a frozen clock', () => {
  it('freezes the window and stops reading while paused, and picks both up on resume', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    const requests = stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    // Live: the poll keeps the window moving (2 s cadence).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    expect(requests.length).toBeGreaterThanOrEqual(2);

    await userEvent.click(screen.getByRole('button', { name: 'Pause tail' }));
    expect(screen.getByRole('button', { name: 'Resume tail' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText(/Paused at \d\d:\d\d:\d\dZ/)).toBeInTheDocument();
    expect(screen.getByText(/nothing is being read/)).toBeInTheDocument();

    const afterPause = requests.length;
    const frozen = new URL(requests.at(-1)?.url ?? '').searchParams.get('end');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });

    // Pause is a freeze, not a buffer: no read is issued while it is held, so a
    // stack trace cannot scroll away while it is being read.
    expect(requests.length).toBe(afterPause);

    await userEvent.click(screen.getByRole('button', { name: 'Resume tail' }));
    await waitFor(() => expect(requests.length).toBeGreaterThan(afterPause));
    const resumed = new URL(requests.at(-1)?.url ?? '').searchParams.get('end');

    // Resuming starts a fresh window from *now* rather than replaying the paused one.
    expect(Date.parse(resumed ?? '')).toBeGreaterThan(Date.parse(frozen ?? ''));
  });
});
