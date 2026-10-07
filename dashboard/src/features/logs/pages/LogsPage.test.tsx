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

/**
 * The API's own caveat sentences, as the two sources write them.
 *
 * Copied from the service rather than shortened: the assertion this file makes is that
 * the screen renders what the server said instead of a sentence of its own, and a
 * paraphrase here would test the paraphrase.
 */
const TAIL_CAVEATS = [
  'This tail holds the most recent 20,000 lines or 15 minutes of the process that accepted them, whichever comes first. It is not a store: a restart, a second worker or an aged-out line is not shown here, and only accepted lines appear in it.',
  'Nothing matched these filters, though the window does hold lines: the filter is what removed them, not the tail.',
  "A cluster's severity is the worst level among its lines, not a model's anomaly score: no log model is served in this build, so nothing here is called anomalous.",
  "This deployment answers from the process's own tail because no database URL is named. Set AEGIS_DATABASE_URL to the deployment's PostgreSQL (and run alembic upgrade head) to read stored lines instead (T-419).",
];

const STORE_CAVEATS = [
  'These lines are read from the log store (the log_events table), so they survive a restart and a second worker sees them. Only accepted lines are in it.',
  "A cluster's severity is the worst level among its lines, not a model's anomaly score: no log model is served in this build, so nothing here is called anomalous.",
  "Nothing evicts rows from the store yet: FR-05's raw-record window reaches this table through a retention job that is not built, so this read cannot say what has been removed.",
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
    source: 'tail',
    retained_lines: 10_003,
    dropped_lines: 0,
    caveats: TAIL_CAVEATS,
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
    source: 'tail',
    retained_lines: 10_003,
    dropped_lines: 0,
    caveats: [TAIL_CAVEATS[0] ?? ''],
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

    // "not a store" and "no database URL is named" are claims about the deployment, so
    // the screen renders the server's sentences rather than ones of its own.
    expect(screen.getByText(/It is not a store/)).toBeInTheDocument();
    expect(screen.getByText(/no database URL is named/)).toBeInTheDocument();
    expect(screen.getByText(/not a model's anomaly score/)).toBeInTheDocument();
  });

  it('names the read model it is showing', async () => {
    stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    expect(screen.getByText(/Read from this process’s own tail/)).toBeInTheDocument();
  });

  it('offers a store deployment the wider windows its source can read', async () => {
    // The picker cannot offer a span the server would refuse: a tail deployment gets
    // the retained spans, and a store deployment gets an hour and a day as well
    // (T-419). This is the acceptance criterion visible on the screen.
    stubLogs(tail({ source: 'store', dropped_lines: null, caveats: STORE_CAVEATS }));
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    const options = within(screen.getByLabelText('Window')).getAllByRole('option');
    expect(options.map((option) => option.textContent)).toEqual([
      'Last minute',
      'Last 5 min',
      'Last 15 min',
      'Last hour',
      'Last 24 h',
    ]);
    expect(screen.getByText(/Read from the log store/)).toBeInTheDocument();
  });

  it('offers a tail deployment only what its retention can answer', async () => {
    stubLogs();
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    const options = within(screen.getByLabelText('Window')).getAllByRole('option');
    expect(options.map((option) => option.textContent)).not.toContain('Last 24 h');
  });

  it('names no source before one has answered', () => {
    stubLogs();

    // The first paint has heard from nobody. A screen that says "read from this
    // process's own tail" here has named a source it has not asked yet, and on a store
    // deployment that sentence is wrong every time the page is opened (T-419).
    renderPage();

    expect(screen.queryByText(/Read from/)).not.toBeInTheDocument();
  });

  it('asks a store for the day-wide window the tail could not answer', async () => {
    const requests = stubLogs(
      tail({ source: 'store', dropped_lines: null, caveats: STORE_CAVEATS }),
    );
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Window' }), '24h');

    // The acceptance criterion, as a request: a window older than the tail's 15-minute
    // retention is readable, so the read is actually issued for a day.
    await waitFor(() => {
      const url = new URL(requests.at(-1)?.url ?? '');
      const span =
        Date.parse(url.searchParams.get('end') ?? '') -
        Date.parse(url.searchParams.get('start') ?? '');
      expect(span).toBe(86_400_000);
    });
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

  it("says where an expansion's lines came from, as the read that returned them did", async () => {
    // A cluster count and the lines behind it can be answered by the same source, and
    // the expansion says which one in the API's own words: an expansion taken from a
    // fifteen-minute buffer must not read like a stored read (T-419, R-70).
    const requests = stubLogs(
      tail({ source: 'store', dropped_lines: null, caveats: STORE_CAVEATS }),
      lines({ source: 'store', dropped_lines: null, caveats: STORE_CAVEATS }),
    );
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    const table = await screen.findByRole('table', { name: /Log clusters/ });
    await userEvent.click(within(table).getByRole('button', { name: 't-retry' }));

    await screen.findByRole('heading', { name: 'Raw lines · t-retry' });
    expect(screen.getByText(/matching lines/)).toHaveTextContent(
      'These lines are read from the log store',
    );
    expect(new URL(requests.at(-1)?.url ?? '').searchParams.get('key')).toBe('t-retry');
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
        caveats: [TAIL_CAVEATS[0] ?? '', 'Nothing has arrived in this window'],
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

    expect(await screen.findByText('The log lines could not be read')).toBeInTheDocument();
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

describe('the logs under a frozen clock', () => {
  it("re-reads a store-backed day at the trend cadence, not the tail's", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    const requests = stubLogs(
      tail({ source: 'store', dropped_lines: null, caveats: STORE_CAVEATS }),
    );
    renderPage();
    await screen.findByRole('table', { name: /Log clusters/ });

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Window' }), '24h');
    await waitFor(() => {
      const url = new URL(requests.at(-1)?.url ?? '');
      expect(
        Date.parse(url.searchParams.get('end') ?? '') -
          Date.parse(url.searchParams.get('start') ?? ''),
      ).toBe(86_400_000);
    });

    const afterWide = requests.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000);
    });
    // Six seconds is three tail polls. A day of clusters has not visibly moved, so
    // re-reading it at that rate is load bought for nothing (T-419).
    expect(requests.length).toBe(afterWide);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(requests.length).toBeGreaterThan(afterWide);
  });

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
