/**
 * The overview page, end to end over a stubbed network.
 *
 * `fetch` is the only thing faked: the page renders the real components, the real
 * mappings and the real React Query wiring, and every assertion is on what reached
 * the DOM. That is the difference between testing this screen and testing a mock's
 * cooperation.
 *
 * Since T-416 this file's stub is *one* route — `GET /api/v1/overview` — because
 * that is the page's one source. The tests therefore also assert the request
 * itself: one aggregate per window, carrying the window the operator selected, and
 * no page walk at all. A screen that quietly went back to counting pages would fail
 * on the request count rather than only on a number.
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
import type { Overview, OverviewBucket, OverviewEntity } from '../api';
import { OverviewPage } from './OverviewPage';

const NOW = new Date('2026-10-06T12:00:00Z');
const WINDOW_START = new Date(NOW.getTime() - 86_400_000);

/** 24 buckets of 60 minutes, the shape the server sends for the 24 h range. */
function buckets(overrides: Record<number, Record<string, number>> = {}): OverviewBucket[] {
  return Array.from({ length: 24 }, (_unused, index) => {
    const by_severity = overrides[index] ?? {};
    return {
      start: new Date(WINDOW_START.getTime() + index * 3_600_000).toISOString(),
      total: Object.values(by_severity).reduce((sum, count) => sum + count, 0),
      by_severity,
    };
  });
}

function entity(overrides: Partial<OverviewEntity> = {}): OverviewEntity {
  return {
    entity_id: 7,
    kind: 'host',
    value: 'web-01.corp',
    named: true,
    alerts: 2,
    occurrences: 3,
    open: 1,
    worst_severity: 'critical',
    max_score: 0.97,
    last_seen: '2026-10-06T11:30:00Z',
    ...overrides,
  };
}

/** Three alerts across two severities and two named entities. */
function aggregate(overrides: Partial<Overview> = {}): Overview {
  return {
    window: {
      start: WINDOW_START.toISOString(),
      end: NOW.toISOString(),
      hours: 24,
    },
    bucket_minutes: 60,
    totals: {
      alerts: 3,
      open: 2,
      by_severity: { critical: 1, high: 2 },
      unrecognised_severity: 0,
      verdicts: { true_positive: 1 },
      unrecorded: 2,
      verdicts_measured: 3,
      mean_time_to_verdict_seconds: 47.42,
    },
    series: buckets({ 1: { critical: 1 }, 23: { high: 2 } }),
    entities: [
      entity(),
      entity({
        entity_id: 9,
        kind: 'user',
        value: 'j.doe@corp',
        alerts: 1,
        occurrences: 1,
        worst_severity: 'high',
        max_score: 0.8,
      }),
    ],
    entities_capped: false,
    families: [
      { family: 'Reconnaissance', alerts: 2, worst_severity: 'critical' },
      { family: 'Brute force', alerts: 1, worst_severity: 'high' },
    ],
    families_capped: false,
    ...overrides,
  };
}

const METRICS = `# TYPE aegis_flows_ingested_total counter\naegis_flows_ingested_total{modality="flow"} 1000.0\n# TYPE aegis_http_request_duration_seconds histogram\naegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="0.05"} 100.0\naegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="+Inf"} 100.0\n# TYPE aegis_score_latency_seconds histogram\naegis_score_latency_seconds_bucket{le="0.1"} 100.0\naegis_score_latency_seconds_bucket{le="+Inf"} 100.0\n`;

function routes(
  overrides: {
    overview?: StubRoute['respond'];
    metrics?: StubRoute['respond'];
    readz?: StubRoute['respond'];
  } = {},
) {
  return [
    {
      match: '/api/v1/overview',
      respond: overrides.overview ?? (() => jsonResponse(aggregate())),
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

  it('fills the tiles, the series and the entities from one request (T-416)', async () => {
    // The acceptance criterion, asserted on the wire as well as on the screen: one
    // aggregate answers all three panels, so they cannot disagree about the window.
    const requests = stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('web-01.corp')).toBeInTheDocument();

    const overview = requests.filter((request) => request.url.includes('/api/v1/overview'));
    expect(overview).toHaveLength(1);
    // And nothing walked pages behind its back: the alert list route is not read.
    expect(requests.filter((request) => request.url.includes('/api/v1/alerts'))).toHaveLength(0);

    const url = new URL(overview[0]?.url ?? '');
    expect(url.searchParams.get('bucket_minutes')).toBe('60');
    expect(url.searchParams.get('entity_limit')).toBe('5');
    const start = Date.parse(url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end') ?? '');
    expect(Number.isNaN(start)).toBe(false);
    expect(end - start).toBeCloseTo(86_400_000, -3);
  });

  it('never describes a count as partial, because the count is the window’s (T-416)', async () => {
    // The old screen admitted "partial coverage" past the page cap. The aggregate
    // has no cap on a count, so the language is gone -- and this asserts its
    // absence, which is the half of T-416 a screenshot cannot show.
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    await screen.findByText('web-01.corp');

    expect(screen.queryByText(/partial coverage/)).toBeNull();
    expect(screen.queryByText(/pages were read/)).toBeNull();
    expect(screen.queryByText(/complete: false/)).toBeNull();
  });

  it('says it is reading the window rather than drawing zeros (T-414)', async () => {
    stubFetch(routes({ overview: () => neverResponds(), metrics: () => neverResponds() }));
    renderWithProviders(<OverviewPage />);

    // Every panel that will hold a figure announces what it is waiting for, by name.
    const announced = (await screen.findAllByRole('status')).map((node) => node.textContent ?? '');
    const said = announced.join(' | ');
    expect(said).toContain('Alert volume by severity is loading');
    expect(said).toContain('Top attacked entities is loading');
    expect(said).toContain('Threat family mix is loading');

    // And none of them has answered: a zero, or an empty window, would be a claim about
    // the last 24 hours that nothing has read yet.
    expect(screen.queryByText(/alerts in this window/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No entity was attacked/)).not.toBeInTheDocument();
  });

  it('counts the window into the KPI tiles, from the aggregate’s own totals', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const critical = await screen.findByText('Critical');
    const tile = critical.closest('div');
    expect(await within(tile as HTMLElement).findByText('1')).toBeInTheDocument();

    // Two are open, one is resolved -- the tile does not re-derive this from rows.
    const open = screen.getByText('Open alerts').closest('div');
    expect(within(open as HTMLElement).getByText('2')).toBeInTheDocument();
  });

  it('shows the mean time to verdict with the number of verdicts it covers', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const tile = (await screen.findByText('Mean time to verdict')).closest('div');

    expect(within(tile as HTMLElement).getByText('47')).toBeInTheDocument();
    expect(within(tile as HTMLElement).getByText(/3 verdicts measured/)).toBeInTheDocument();
  });

  it('says the mean is unknown rather than showing zero seconds', async () => {
    // A window with no recorded verdict has no mean: `0 s` would claim instant
    // triage, so the tile keeps its dash and says what is missing.
    stubFetch(
      routes({
        overview: () =>
          jsonResponse(
            aggregate({
              totals: {
                ...aggregate().totals,
                verdicts: {},
                verdicts_measured: 0,
                mean_time_to_verdict_seconds: null,
              },
            }),
          ),
      }),
    );
    renderWithProviders(<OverviewPage />);

    const tile = (await screen.findByText('Mean time to verdict')).closest('div');

    expect(within(tile as HTMLElement).getByText('—')).toBeInTheDocument();
    expect(
      within(tile as HTMLElement).getByText(/no verdict recorded in this window/),
    ).toBeInTheDocument();
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
      name: /Alert volume by severity, Last 24 h \u00b7 3 alerts in this window, as a table/,
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

  it('renders every entity’s host or user value, not its id (T-416)', async () => {
    // The acceptance criterion on the panel: a row is named by what the entity is.
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('web-01.corp')).toBeInTheDocument();
    expect(screen.getByText('j.doe@corp')).toBeInTheDocument();
    expect(screen.getByText('host')).toBeInTheDocument();
    expect(screen.getByText('user')).toBeInTheDocument();
    // The id is not a name, and the old caveat about missing names is gone.
    expect(screen.queryByText('entity 7')).toBeNull();
    expect(screen.queryByText(/not exposed by the query API/)).toBeNull();
  });

  it('renders an id the registry could not name as an id, and says why', async () => {
    stubFetch(
      routes({
        overview: () =>
          jsonResponse(
            aggregate({
              entities: [
                entity({ entity_id: 142, kind: null, value: null, named: false }),
                entity(),
              ],
            }),
          ),
      }),
    );
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText('entity 142')).toBeInTheDocument();
    expect(screen.getByText(/the entity registry has not seen/)).toBeInTheDocument();
  });

  it('says a capped entity list is a top-N of more (T-416)', async () => {
    stubFetch(routes({ overview: () => jsonResponse(aggregate({ entities_capped: true })) }));
    renderWithProviders(<OverviewPage />);

    await screen.findByText('web-01.corp');

    expect(screen.getByText(/the window held more/)).toBeInTheDocument();
  });

  it('shows the family mix with its counts and the window it describes', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    const mix = (await screen.findByRole('heading', { name: 'Threat family mix' })).closest(
      'section',
    );
    expect(
      within(mix as HTMLElement).getByText('Last 24 h \u00b7 3 alerts in this window'),
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
        overview: () =>
          jsonResponse(
            aggregate({
              totals: { ...aggregate().totals, alerts: 0, open: 0, by_severity: {} },
              series: [],
              entities: [],
              families: [],
            }),
          ),
      }),
    );
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/No alerts in the Last 24 h\./)).toBeInTheDocument();
    expect(screen.getByText(/No entity was attacked/)).toBeInTheDocument();
  });

  it('names the failure and offers a retry when the aggregate fails', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    stubFetch(
      routes({
        overview: () => {
          attempts += 1;
          return attempts === 1 ? jsonResponse({ detail: 'boom' }, 500) : jsonResponse(aggregate());
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
    expect(await screen.findByText('web-01.corp')).toBeInTheDocument();
  });

  it('says the metrics scrape failed instead of quietly omitting the pipeline', async () => {
    stubFetch(routes({ metrics: () => textResponse('nonsense', 500) }));
    renderWithProviders(<OverviewPage />);

    expect(await screen.findByText(/The metrics scrape could not be read/)).toBeInTheDocument();
  });

  it('reports the connection as disconnected when the API is unreachable', async () => {
    stubFetch(routes({ overview: () => jsonResponse({ detail: 'down' }, 503) }));
    renderWithProviders(<OverviewPage />);

    const status = await screen.findByRole('status');

    expect(status).toHaveTextContent('Disconnected');
  });

  it('reads the window the operator picks, resolution included', async () => {
    const user = userEvent.setup();
    const requests = stubFetch(routes());
    renderWithProviders(<OverviewPage />);
    await screen.findByRole('heading', { name: 'Alert volume by severity' });

    await user.selectOptions(screen.getByLabelText('Window'), '7d');

    await waitFor(() => {
      const requested = requests
        .filter((request) => request.url.includes('/api/v1/overview'))
        .map((request) => new URL(request.url))
        .some((url) => {
          const start = Date.parse(url.searchParams.get('start') ?? '');
          const end = Date.parse(url.searchParams.get('end') ?? '');
          return (
            Math.abs(end - start - 604_800_000) < 5_000 &&
            url.searchParams.get('bucket_minutes') === '360'
          );
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

  it('describes the window in every panel caption, from the one count', async () => {
    stubFetch(routes());
    renderWithProviders(<OverviewPage />);

    expect(
      (await screen.findAllByText('Last 24 h \u00b7 3 alerts in this window')).length,
    ).toBeGreaterThanOrEqual(2);
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
    stubFetch(
      routes({
        overview: () => {
          answered += 1;
          return answered === 1
            ? jsonResponse(aggregate())
            : new Promise<Response>(() => {
                /* never answers: the refresh has stopped working */
              });
        },
      }),
    );
    renderWithProviders(<OverviewPage />);
    await screen.findByText('web-01.corp');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000);
    });

    expect(screen.getByText(/last update .* \u2014 stale/)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Degraded');
    // The data itself is still on screen: stale is not the same as gone.
    expect(screen.getByText('web-01.corp')).toBeInTheDocument();
  });
});
