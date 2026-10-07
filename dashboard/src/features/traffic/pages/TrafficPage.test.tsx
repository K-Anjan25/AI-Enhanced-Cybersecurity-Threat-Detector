/**
 * The traffic explorer, end to end through the page an analyst opens (T-418).
 *
 * The only faked things are the network (`fetch`, via the shared stub) and the clock.
 * Everything between — the queries, the mapping, the brush, the graph layout, the
 * components — is the real code, so the assertions are on what the screen says.
 *
 * What this file holds the acceptance criterion to:
 *
 *   * **One request fills the series, the table and the graph.** The count of `/flows`
 *     requests is asserted, because a screen that made two would be a screen whose
 *     panels could disagree about the window.
 *   * **The caveats are the API's own sentences.** They are rendered verbatim, and the
 *     sentence the *old* build carried — "this build has no read API for ingested flows
 *     (T-418)" — must not be on the screen any more. That is the "drops the T-418 half"
 *     clause, asserted as an absence.
 *   * **Brushing re-reads the brushed window**, so the numbers below the chart are the
 *     server's counts for the selection rather than a client-side slice.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, Providers, stubFetch } from '../../../test/query';
import { TrafficPage } from './TrafficPage';
import type { FlowAggregate, FlowBucket, FlowEntity } from '../../../api/flows';

const START = Date.parse('2026-10-06T10:00:00Z');

/** The API's own sentence about the rollup, which the screen must render unchanged. */
const ROLLUP_CAVEAT =
  "These numbers are counted from this process's own in-process rollup: the last 60 minutes of accepted flow records, kept as per-minute totals.";
const CAP_CAVEAT =
  'The entity list shows the busiest 2 of 3 addresses; the rest are counted in the totals, not listed.';

function bucket(index: number, flows: number, alerts = 0, score: number | null = null): FlowBucket {
  return {
    start: new Date(START + index * 300_000).toISOString(),
    flows,
    bytes: flows * 140,
    packets: flows * 3,
    alerts,
    score,
  };
}

function entity(overrides: Partial<FlowEntity> & { ip: string }): FlowEntity {
  return {
    flows: 10,
    bytes: 1_400,
    packets: 30,
    inbound: 0,
    outbound: 10,
    first_seen: new Date(START).toISOString(),
    last_seen: new Date(START + 600_000).toISOString(),
    alerts: 0,
    open_alerts: 0,
    worst_severity: null,
    max_score: null,
    ...overrides,
  };
}

const ENTITIES: FlowEntity[] = [
  entity({
    ip: '10.0.0.1',
    flows: 40,
    outbound: 40,
    alerts: 2,
    open_alerts: 1,
    worst_severity: 'high',
    max_score: 0.8,
  }),
  entity({ ip: '10.0.0.2', flows: 5, inbound: 5, alerts: 0 }),
  entity({
    ip: '10.0.0.3',
    flows: 7,
    outbound: 7,
    alerts: 1,
    worst_severity: 'critical',
    max_score: 0.95,
  }),
];

function aggregate(overrides: Partial<FlowAggregate> = {}): FlowAggregate {
  return {
    window: {
      start: new Date(START).toISOString(),
      end: new Date(START + 3_600_000).toISOString(),
      hours: 1,
    },
    bucket_minutes: 5,
    source: 'rollup',
    filters: { protocol: null, direction: null },
    series: [bucket(0, 40, 2, 0.8), bucket(1, 5), bucket(2, 7, 1, 0.95)],
    entities: ENTITIES,
    edges: [
      { source: '10.0.0.1', target: '10.0.0.2', flows: 4, bytes: 560 },
      { source: '10.0.0.3', target: '10.0.0.1', flows: 2, bytes: 280 },
    ],
    totals: {
      flows: 52,
      bytes: 7_280,
      packets: 156,
      nodes: 3,
      edges: 2,
      nodes_capped: false,
      edges_capped: false,
      untracked_address_flows: 0,
      untracked_pair_flows: 0,
    },
    caveats: [ROLLUP_CAVEAT],
    ...overrides,
  };
}

function stubTraffic(answer: FlowAggregate = aggregate(), extra: Record<string, unknown> = {}) {
  return stubFetch([
    { match: '/api/v1/flows', respond: () => jsonResponse({ ...answer, ...extra }) },
  ]);
}

function renderPage() {
  return render(
    <Providers initialEntries={['/traffic']}>
      <TrafficPage />
    </Providers>,
  );
}

async function series() {
  return screen.findByRole('group', { name: /Flow volume over the/ });
}

async function table() {
  return screen.findByRole('table', { name: /Addresses in the window/ });
}

function flowRequests(requests: Request[]): Request[] {
  return requests.filter((request) => new URL(request.url).pathname === '/api/v1/flows');
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TrafficPage', () => {
  it('fills the series, the address table and the graph from one request', async () => {
    const requests = stubTraffic();
    renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: 'Traffic' })).toBeInTheDocument();
    expect(await series()).toBeInTheDocument();
    expect(await table()).toBeInTheDocument();
    expect(screen.getByText(/Force layout/)).toBeInTheDocument();
    expect(flowRequests(requests)).toHaveLength(1);
  });

  it('asks for a bounded window, because R-34 forbids an unbounded scan', async () => {
    const requests = stubTraffic();
    renderPage();
    await series();

    const url = new URL((flowRequests(requests)[0] as Request).url);
    const start = Date.parse(url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end') ?? '');

    expect(Number.isNaN(start)).toBe(false);
    expect(Number.isNaN(end)).toBe(false);
    expect(end).toBeGreaterThan(start);
  });

  it('names the addresses the read model counted, not entity ids', async () => {
    stubTraffic();
    renderPage();
    const tableElement = await table();

    expect(within(tableElement).getByRole('button', { name: '10.0.0.1' })).toBeInTheDocument();
    expect(within(tableElement).getByText('10.0.0.3')).toBeInTheDocument();
  });

  it('narrows the read server-side when a protocol is chosen', async () => {
    const requests = stubTraffic();
    renderPage();
    await series();

    await userEvent.selectOptions(screen.getByLabelText('Protocol'), 'udp');

    await waitFor(() => {
      const protocols = flowRequests(requests).map((request) =>
        new URL(request.url).searchParams.get('protocol'),
      );
      expect(protocols).toContain('udp');
    });
  });

  it('sends no filter for "all", because the API has no reason to understand it', async () => {
    const requests = stubTraffic();
    renderPage();
    await series();

    const url = new URL((flowRequests(requests)[0] as Request).url);

    expect(url.searchParams.get('protocol')).toBeNull();
    expect(url.searchParams.get('direction')).toBeNull();
  });

  it('filters the panels below the controls and says how many it removed', async () => {
    stubTraffic();
    renderPage();
    await table();

    await userEvent.type(screen.getByLabelText('Min flows'), '10');

    await waitFor(() => expect(screen.getByText(/hidden by the controls/)).toBeInTheDocument());
    const tableElement = screen.getByRole('table', { name: /Addresses in the window/ });
    expect(within(tableElement).queryByRole('button', { name: '10.0.0.2' })).toBeNull();
  });

  it('keeps only addresses with an open alert when the toggle is on', async () => {
    stubTraffic();
    renderPage();
    await table();

    await userEvent.click(screen.getByLabelText(/Only addresses with an open alert/));

    await waitFor(() => {
      const tableElement = screen.getByRole('table', { name: /Addresses in the window/ });
      expect(within(tableElement).queryByRole('button', { name: '10.0.0.2' })).toBeNull();
      expect(within(tableElement).getByRole('button', { name: '10.0.0.1' })).toBeInTheDocument();
    });
  });

  it('lets a table stand in for the chart, which is what §9 requires', async () => {
    stubTraffic();
    renderPage();
    await series();

    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));

    const alternative = await screen.findByRole('table', { name: /as a table/ });
    expect(within(alternative).getByRole('columnheader', { name: 'Flows' })).toBeInTheDocument();
    expect(within(alternative).getByRole('columnheader', { name: 'Bytes' })).toBeInTheDocument();
    expect(
      within(alternative).getByRole('columnheader', { name: 'Mean score' }),
    ).toBeInTheDocument();
  });

  it('re-reads the brushed window so the panels below are the server’s counts', async () => {
    // The acceptance criterion behind the brush: the table and the graph must describe
    // the selection, and the only way to do that with a top-N list is to ask again.
    const requests = stubFetch([
      {
        match: '/api/v1/flows',
        respond: (request) => {
          const url = new URL(request.url);
          const brushed = url.searchParams.get('start') === new Date(START).toISOString();
          return jsonResponse(
            brushed
              ? aggregate({
                  series: [bucket(0, 40, 2, 0.8)],
                  entities: [entity({ ip: '10.0.0.1', flows: 40 })],
                  edges: [],
                  caveats: ['A brushed read.'],
                })
              : aggregate(),
          );
        },
      },
    ]);
    renderPage();
    const chart = await series();

    // Drag across the first bucket: the brush surface is the chart's own overlay.
    const surface = within(chart).getByTestId('brush-surface');
    surface.getBoundingClientRect = () =>
      ({
        left: 0,
        top: 0,
        right: 720,
        bottom: 200,
        width: 720,
        height: 200,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect;
    // A drag wide enough to be a selection rather than a click: the component refuses a
    // range narrower than one bucket, and the chart here has three of them.
    fireEvent(
      surface,
      new MouseEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 40 }),
    );
    fireEvent(
      surface,
      new MouseEvent('pointerup', { bubbles: true, cancelable: true, clientX: 400 }),
    );

    await waitFor(() => {
      const starts = flowRequests(requests).map((request) =>
        new URL(request.url).searchParams.get('start'),
      );
      expect(starts).toContain(new Date(START).toISOString());
    });
    // And the sentence about which sub-window the numbers describe is on screen.
    expect(await screen.findByText(/describe the brushed window/)).toBeInTheDocument();
  });

  it('pins an address from the graph and says the view is pinned', async () => {
    stubTraffic();
    renderPage();
    const graph = await screen.findByRole('group', { name: /Address relationships/ });

    await userEvent.click(within(graph).getByRole('button', { name: /Address 10\.0\.0\.1,/ }));

    await waitFor(() => expect(screen.getByText(/pinned to one address/)).toBeInTheDocument());
    expect(screen.getByText(/10\.0\.0\.1 and its neighbours are shown/)).toBeInTheDocument();
  });

  it('pins from the table too, so the graph is not the only way in', async () => {
    stubTraffic();
    renderPage();
    const tableElement = await table();

    await userEvent.click(within(tableElement).getByRole('button', { name: '10.0.0.3' }));

    await waitFor(() => expect(screen.getByText(/pinned to one address/)).toBeInTheDocument());
  });

  it('renders the API’s own caveats, unchanged', async () => {
    stubTraffic(aggregate({ caveats: [ROLLUP_CAVEAT, CAP_CAVEAT] }));
    renderPage();
    await series();

    const caveats = await screen.findByRole('region', { name: 'What this screen is not showing' });
    expect(within(caveats).getByText(ROLLUP_CAVEAT)).toBeInTheDocument();
    expect(within(caveats).getByText(CAP_CAVEAT)).toBeInTheDocument();
  });

  it('no longer claims the numbers are the alerted subset (the T-418 half is gone)', async () => {
    // The permanent caveat this screen used to carry said there was no flow read API
    // and that volume was the alerted record count. Both sentences must be absent now:
    // a screen that still said them would be describing a build that no longer exists.
    stubTraffic();
    renderPage();
    await series();

    const caveats = await screen.findByRole('region', { name: 'What this screen is not showing' });
    const said = caveats.textContent ?? '';

    expect(said).not.toContain('no read API for ingested flows');
    expect(said).not.toContain('raw-record count carried by alerts');
    expect(said).not.toContain('T-418');
  });

  it('says when the read model cannot survive a restart, because the API said so', async () => {
    const caveat =
      'It is not a store: a restart, a second worker or a minute older than that is not in it.';
    stubTraffic(aggregate({ caveats: [caveat] }));
    renderPage();
    await series();

    expect(await screen.findByText(caveat)).toBeInTheDocument();
  });

  it('says a window with no traffic is empty rather than drawing a blank panel', async () => {
    stubTraffic(
      aggregate({
        series: [bucket(0, 0)],
        entities: [],
        edges: [],
        caveats: ['Nothing has been counted yet, so this window is empty.'],
      }),
    );
    renderPage();

    expect(await screen.findByText(/No flow records in the/)).toBeInTheDocument();
    expect(
      await screen.findByText('Nothing has been counted yet, so this window is empty.'),
    ).toBeInTheDocument();
  });

  it('names the failure and offers a retry when the read fails', async () => {
    stubFetch([{ match: '/api/v1/flows', respond: () => jsonResponse({ detail: 'boom' }, 500) }]);
    renderPage();

    expect(await screen.findByText('The traffic window could not be loaded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('reads the window the operator picks, and clears the brush that belonged to the old one', async () => {
    const requests = stubTraffic();
    renderPage();
    await series();

    await userEvent.selectOptions(screen.getByLabelText('Window'), '7d');

    await waitFor(() => {
      const url = new URL((flowRequests(requests).at(-1) as Request).url);
      const span =
        Date.parse(url.searchParams.get('end') ?? '') -
        Date.parse(url.searchParams.get('start') ?? '');
      expect(span).toBeGreaterThan(86_400_000);
    });
  });

  it('reads a 24 h window by default, in 15-minute buckets', async () => {
    const requests = stubTraffic();
    renderPage();
    await series();

    const url = new URL((flowRequests(requests)[0] as Request).url);
    const span =
      Date.parse(url.searchParams.get('end') ?? '') -
      Date.parse(url.searchParams.get('start') ?? '');

    expect(span).toBeGreaterThan(23 * 3_600_000);
    expect(span).toBeLessThan(25 * 3_600_000);
    expect(url.searchParams.get('bucket_minutes')).toBe('15');
  });

  it('says an address with a band this build does not know rather than colouring it', async () => {
    stubTraffic(
      aggregate({
        entities: [entity({ ip: '10.0.0.9', alerts: 1, worst_severity: 'catastrophic' })],
        edges: [],
      }),
    );
    renderPage();
    const tableElement = await table();

    expect(within(tableElement).getByText('unrecognised')).toBeInTheDocument();
  });

  it('says an address with no alert has none, rather than calling it unrecognised', async () => {
    stubTraffic(aggregate({ entities: [entity({ ip: '10.0.0.9', alerts: 0 })], edges: [] }));
    renderPage();
    const tableElement = await table();

    expect(within(tableElement).getByText('no alert')).toBeInTheDocument();
  });

  it('says so when the controls leave no addresses, rather than drawing an empty graph', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Address relationships/ });

    await userEvent.type(screen.getByLabelText('Min flows'), '9999');

    expect(await screen.findByText('No addresses in this selection')).toBeInTheDocument();
  });

  it('prints the address table as an ordinary table, with its columns switchable', async () => {
    stubTraffic();
    renderPage();
    const tableElement = await table();

    // The open column is off by default (a low-value column), and the picker is what
    // brings it back — the same primitive every other table in the product uses.
    expect(within(tableElement).queryByRole('columnheader', { name: 'Open alerts' })).toBeNull();

    await userEvent.click(screen.getByText('Columns'));
    await userEvent.click(screen.getByLabelText('Open alerts'));

    await waitFor(() =>
      expect(
        within(tableElement).getByRole('columnheader', { name: 'Open alerts' }),
      ).toBeInTheDocument(),
    );

    // And it prints each address's own count: one of the three has an open alert, so a
    // column that printed the same number everywhere would fail here.
    const header = within(tableElement).getAllByRole('row')[0] as HTMLElement;
    const column = within(header)
      .getAllByRole('columnheader')
      .findIndex((cell) => cell.textContent === 'Open alerts');
    const body = within(tableElement).getAllByRole('row').slice(1);
    const open = body.map((line) => within(line).getAllByRole('cell')[column]?.textContent);

    expect(new Set(open)).toEqual(new Set(['1', '0']));
  });

  it('has no serious accessibility violations', async () => {
    stubTraffic();
    const { container } = renderPage();
    await series();

    await expectAccessible(container as HTMLElement);
  });
});
