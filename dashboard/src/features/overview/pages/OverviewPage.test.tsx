/**
 * The overview page, end to end over a stubbed network.
 *
 * `fetch` is the only thing faked: the page renders the real components, the real
 * aggregations and the real React Query wiring, and every assertion is on what
 * reached the DOM. That is the difference between testing this screen and testing
 * a mock's cooperation.
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { auditKeyboard, auditStructure } from '../../../test/a11y';
import { expectAccessible, expectAxeClean } from '../../../test/axe';
import {
  jsonResponse,
  neverResponds,
  renderWithProviders,
  stubFetch,
  textResponse,
  type StubRoute,
} from '../../../test/query';
import type { AlertRow } from '../api';
import { OverviewPage } from './OverviewPage';

const NOW = new Date('2026-10-06T12:00:00Z');

function alertRow(overrides: Partial<AlertRow> = {}): AlertRow {
  return {
    id: 1,
    created_at: '2026-10-06T11:30:00Z',
    entity_id: 7,
    family: 'Reconnaissance',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: '2026-10-06T11:00:00Z',
    last_seen: '2026-10-06T11:30:00Z',
    occurrence_count: 2,
    trace_id: null,
    ...overrides,
  };
}

/** Three alerts across two severities and one entity. */
const ROWS: AlertRow[] = [
  alertRow({ id: 3, severity: 'critical', family: 'Reconnaissance' }),
  alertRow({ id: 2, severity: 'high', family: 'Brute force', entity_id: 9 }),
  alertRow({ id: 1, severity: 'high', family: 'Brute force', status: 'resolved' }),
];

const METRICS = `# TYPE aegis_flows_ingested_total counter
aegis_flows_ingested_total{modality="flow"} 1000.0
# TYPE aegis_http_request_duration_seconds histogram
aegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="0.05"} 100.0
aegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="+Inf"} 100.0
# TYPE aegis_score_latency_seconds histogram
aegis_score_latency_seconds_bucket{le="0.1"} 100.0
aegis_score_latency_seconds_bucket{le="+Inf"} 100.0
`;

function routes(
  overrides: {
    alerts?: StubRoute['respond'];
    metrics?: StubRoute['respond'];
    readz?: StubRoute['respond'];
  } = {},
) {
  return [
    {
      match: '/api/v1/alerts',
      respond:
        overrides.alerts ??
        (() => jsonResponse({ items: ROWS, next_cursor: null, limit: 1_000, order: 'desc' })),
    },
    { match: '/metrics', respond: overrides.metrics ?? (() => textResponse(METRICS)) },
    {
      match: '/readyz',
      respond:
        overrides.readz ??
        (() => jsonResponse({ status: 'ready', service: 'aegis', version: '0.1.0', checks: [] })),
    },
  ];
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('OverviewPage', () => {
  it('renders the page title and the panels design.md §4.1 draws', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'Alert volume by severity' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Top attacked entities' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Threat family mix' })).toBeInTheDocument();
    expect(
      await screen.findByRole('region', { name: 'Detection pipeline health' }),
    ).toBeInTheDocument();
  });

  it('says it is reading the window rather than drawing zeros (T-414)', async () => {
    stubFetch(routes({ alerts: () => neverResponds(), metrics: () => neverResponds() }));
    renderWithProviders(<OverviewPage />);

    // Every panel that will hold a figure announces what it is waiting for, by name.
    const announced = (await screen.findAllByRole('status')).map((node) => node.textContent ?? '');
    const said = announced.join(' | ');
    expect(said).toContain('Alert volume by severity is loading');
    expect(said).toContain('Top attacked entities is loading');
    expect(said).toContain('Threat family mix is loading');

    // And none of them has answered: a zero, or an empty window, would be a claim about
    // the last 24 hours that nothing has read yet.
    expect(screen.queryByText(/alerts read/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No entity was attacked/)).not.toBeInTheDocument();
  });

  it('asks for a bounded window, because R-34 forbids an unbounded scan', async () => {
    const requests = stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    await screen.findByRole('heading', { name: 'Alert volume by severity' });

    const alerts = requests.filter((request) => request.url.includes('/api/v1/alerts'));
    expect(alerts.length).toBeGreaterThan(0);
    const url = new URL(alerts[0]?.url ?? '');
    const start = Date.parse(url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end') ?? '');
    expect(Number.isNaN(start)).toBe(false);
    expect(end).toBeGreaterThan(start);
    // The default window is §4.1's "Last 24 h".
    expect(end - start).toBeCloseTo(86_400_000, -3);
  });

  it('counts the alerts it read into the KPI tiles', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const critical = await screen.findByText('Critical');
    const tile = critical.closest('div');
    expect(await within(tile as HTMLElement).findByText('1')).toBeInTheDocument();

    // Two are open, one is resolved.
    const open = screen.getByText('Open alerts').closest('div');
    expect(within(open as HTMLElement).getByText('2')).toBeInTheDocument();
  });

  it('says the verdict tile has no source rather than showing zero seconds', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const tile = (await screen.findByText('Mean time to verdict')).closest('div');

    expect(within(tile as HTMLElement).getByText('—')).toBeInTheDocument();
    expect(within(tile as HTMLElement).getByText(/no verdict aggregation yet/)).toBeInTheDocument();
  });

  it('offers the chart as a table, which is the alternative §9 requires', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const chart = (
      await screen.findByRole('heading', { name: 'Alert volume by severity' })
    ).closest('section');
    const toggle = within(chart as HTMLElement).getByRole('button', { name: 'View as table' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);

    const table = await screen.findByRole('table', {
      name: /Alert volume by severity, Last 24 h \u00b7 3 alerts read, as a table/,
    });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(25); // 24 buckets plus the header
    expect(screen.getByRole('button', { name: 'View as chart' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('gives the canvas an accessible name, so the pixels are not the only encoding', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const canvas = await screen.findByRole('img', { name: /Alert volume by severity/ });

    expect(canvas).toHaveAttribute('aria-label');
    expect(canvas.getAttribute('aria-label')).toMatch(/available as a table/);
  });

  it('names the entity ids it has, and says the names are missing', async () => {
    // The query API returns entity_id only; T-416 is filed for the names.
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('entity 7')).toBeInTheDocument();
    expect(screen.getByText('entity 9')).toBeInTheDocument();
    expect(screen.getByText(/not exposed by the query API yet \(T-416\)/)).toBeInTheDocument();
  });

  it('shows the family mix with its counts', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const mix = (await screen.findByRole('heading', { name: 'Threat family mix' })).closest(
      'section',
    );
    expect(
      within(mix as HTMLElement).getByText('Last 24 h \u00b7 3 alerts read'),
    ).toBeInTheDocument();
  });

  it('renders a pipeline stage over its budget in red, with the budget named', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const strip = await screen.findByRole('region', { name: 'Detection pipeline health' });

    // The fixture's ingest p95 is 50 ms against a 40 ms budget.
    expect(within(strip).getByText(/over budget/)).toBeInTheDocument();
    expect(within(strip).getByText(/vs budget 40 ms/)).toBeInTheDocument();
  });

  it('says a window with no alerts is empty rather than drawing a blank panel', async () => {
    stubFetch(
      routes({
        alerts: () => jsonResponse({ items: [], next_cursor: null, limit: 1_000, order: 'desc' }),
      }),
    );
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/No alerts in the Last 24 h\./)).toBeInTheDocument();
    expect(screen.getByText(/No entity was attacked/)).toBeInTheDocument();
  });

  it('names the failure and offers a retry when the alert query fails', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch(
      routes({
        alerts: () => {
          attempts += 1;
          return attempts === 1
            ? jsonResponse({ detail: 'boom' }, 500)
            : jsonResponse({ items: ROWS, next_cursor: null, limit: 1_000, order: 'desc' });
        },
      }),
    );
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/Alert volume could not be loaded/)).toBeInTheDocument();
    const retry = screen.getAllByRole('button', { name: 'Retry' })[0] as HTMLElement;

    await user.click(retry);

    expect(
      await screen.findByRole('heading', { name: 'Alert volume by severity' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('entity 7')).toBeInTheDocument();
  });

  it('says the metrics scrape failed instead of quietly omitting the pipeline', async () => {
    stubFetch(routes({ metrics: () => textResponse('nonsense', 500) }));
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/The metrics scrape could not be read/)).toBeInTheDocument();
  });

  it('reports the connection as disconnected when the API is unreachable', async () => {
    stubFetch(routes({ alerts: () => jsonResponse({ detail: 'down' }, 503) }));
    renderWithProviders(<OverviewPage />);

    const status = await screen.findByRole('status');

    expect(status).toHaveTextContent('Disconnected');
  });

  it('reads the window the operator picks', async () => {
    const user = userEvent.setup();
    const requests = stubFetch(routes());
    renderWithProviders(<OverviewPage />);
    await screen.findByRole('heading', { name: 'Alert volume by severity' });

    await user.selectOptions(screen.getByLabelText('Window'), '7d');

    await waitFor(() => {
      const requested = requests
        .filter((request) => request.url.includes('/api/v1/alerts'))
        .map((request) => new URL(request.url))
        .some((url) => {
          const start = Date.parse(url.searchParams.get('start') ?? '');
          const end = Date.parse(url.searchParams.get('end') ?? '');
          return Math.abs(end - start - 604_800_000) < 5_000;
        });
      expect(requested).toBe(true);
    });
  });

  it('reads a not-ready readiness answer as an answer, and names the dependency', async () => {
    // /readyz serves "not ready" as 503 *with* a body naming the probe that is
    // down; throwing it away would leave the strip unable to say what is wrong.
    stubFetch(
      routes({
        readz: () =>
          jsonResponse(
            {
              status: 'not_ready',
              service: 'aegis-backend',
              version: '0.1.0',
              checks: [{ name: 'postgres', status: 'unavailable', detail: 'connection refused' }],
            },
            503,
          ),
      }),
    );
    renderWithProviders(<OverviewPage />);

    const strip = await screen.findByRole('region', { name: 'Detection pipeline health' });

    expect(within(strip).getByText(/postgres unavailable/)).toBeInTheDocument();
  });

  it('reports a partial count when the page cap stops the walk', async () => {
    // Five full pages, each announcing another page: the walk stops at the cap and
    // the header says so rather than presenting a partial count as a total.
    let page = 0;
    stubFetch(
      routes({
        alerts: () => {
          page += 1;
          return jsonResponse({
            items: Array.from({ length: 1_000 }, (_unused, index) =>
              alertRow({ id: page * 1_000 + index }),
            ),
            next_cursor: `cursor-${String(page)}`,
            limit: 1_000,
            order: 'desc',
          });
        },
      }),
    );
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/Only the first 5 pages were read/)).toBeInTheDocument();
    expect(screen.getAllByText(/partial coverage/)).toHaveLength(4);
  });

  it('passes the accessibility audit: structure, landmarks and keyboard reach (T-413)', async () => {
    // design.md §9's structure and keyboard claims on this screen, in one place: the
    // reading order axe cannot check, and the tab order no per-control test checks.
    const user = userEvent.setup();
    stubFetch(routes());
    const { container } = renderWithProviders(<OverviewPage />);
    await screen.findByRole('region', { name: 'Detection pipeline health' });

    expect(auditStructure(container as HTMLElement)).toEqual([]);
    expect(await auditKeyboard(container as HTMLElement, user)).toEqual([]);
  });

  it('reports no axe violation at any impact level (T-413)', async () => {
    // Stronger than §9's gate, and measured before it was asserted: this screen reports
    // nothing at all with the best-practice rules included.
    stubFetch(routes());
    const { container } = renderWithProviders(<OverviewPage />);
    await screen.findByRole('region', { name: 'Detection pipeline health' });

    await expectAxeClean(container as HTMLElement);
  });

  it('has no serious accessibility violations once loaded', async () => {
    stubFetch(routes());
    const { container } = renderWithProviders(<OverviewPage />);
    await screen.findByRole('region', { name: 'Detection pipeline health' });

    await expectAccessible(container as HTMLElement);
  });

  it('describes the window in the chart caption', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect((await screen.findAllByText('Last 24 h · 3 alerts read')).length).toBeGreaterThanOrEqual(
      2,
    );
  });
});

describe('the overview under a frozen clock', () => {
  it('shows the age of the last successful load', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    await waitFor(() => {
      expect(screen.getByText(/last update/)).toBeInTheDocument();
    });
  });

  it('marks the data stale once two refreshes have been missed, and degrades the indicator', async () => {
    // §8.1: "if live data stops arriving, show `last update 2 m ago` in the header
    // rather than silently showing old numbers." The refresh is made to hang, so
    // the last successful load stays on screen while its age grows past two chart
    // polls — the exact situation the rule is for.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
    let answered = 0;
    stubFetch([
      {
        match: '/api/v1/alerts',
        respond: () => {
          answered += 1;
          return answered === 1
            ? jsonResponse({ items: ROWS, next_cursor: null, limit: 1_000, order: 'desc' })
            : new Promise<Response>(() => {
                /* never answers: the refresh has stopped working */
              });
        },
      },
      { match: '/metrics', respond: () => textResponse(METRICS) },
      {
        match: '/readyz',
        respond: () =>
          jsonResponse({ status: 'ready', service: 'aegis', version: '0.1.0', checks: [] }),
      },
    ]);
    renderWithProviders(<OverviewPage />);
    await screen.findByText('entity 7');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000);
    });

    expect(screen.getByText(/last update .* \u2014 stale/)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Degraded');
    // The data itself is still on screen: stale is not the same as gone.
    expect(screen.getByText('entity 7')).toBeInTheDocument();
  });
});
