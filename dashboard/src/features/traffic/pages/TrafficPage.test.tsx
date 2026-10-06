/**
 * The traffic explorer, end to end through the page an analyst opens.
 *
 * The only faked things are the network (`fetch`, via the shared stub) and the
 * clock where a relative time is asserted. Everything between — the query, the
 * aggregation, the brush arithmetic, the graph layout, the components — is the real
 * code, so the assertions are on what the screen says.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, Providers, stubFetch } from '../../../test/query';
import { TrafficPage } from './TrafficPage';
import type { AlertRow } from '../../../api/alerts';

const START = Date.parse('2026-10-06T10:00:00Z');

function row(overrides: Partial<AlertRow> & { id: number }): AlertRow {
  return {
    created_at: new Date(START + 300_000).toISOString(),
    entity_id: 1,
    family: 'exfiltration',
    severity: 'high',
    score: 0.8,
    status: 'open',
    first_seen: new Date(START).toISOString(),
    last_seen: new Date(START + 300_000).toISOString(),
    occurrence_count: 40,
    trace_id: 'trace-1',
    ...overrides,
  };
}

const ROWS = [
  row({ id: 1, entity_id: 1, occurrence_count: 40, trace_id: 'trace-1' }),
  row({
    id: 2,
    entity_id: 2,
    occurrence_count: 5,
    trace_id: 'trace-1',
    created_at: new Date(START + 600_000).toISOString(),
    severity: 'low',
  }),
  row({
    id: 3,
    entity_id: 3,
    occurrence_count: 7,
    trace_id: null,
    created_at: new Date(START + 3_000_000).toISOString(),
    severity: 'critical',
    status: 'resolved',
  }),
];

function stubTraffic(rows: AlertRow[] = ROWS, extra: Record<string, unknown> = {}) {
  return stubFetch([
    {
      match: '/api/v1/alerts',
      respond: () =>
        jsonResponse({
          items: rows,
          next_cursor: null,
          limit: 1_000,
          order: 'desc',
          ...extra,
        }),
    },
  ]);
}

function renderPage() {
  return render(
    <Providers initialEntries={['/traffic']}>
      <TrafficPage />
    </Providers>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TrafficPage', () => {
  it('draws the series, the entity table and the graph from one read', async () => {
    const requests = stubTraffic();
    renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: 'Traffic' })).toBeInTheDocument();
    expect(await screen.findByRole('group', { name: /Alerted record volume/ })).toBeInTheDocument();
    expect(
      screen.getByRole('table', { name: /Entities in the brushed window/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Force layout/)).toBeInTheDocument();
    expect(requests.filter((request) => request.url.includes('/alerts')).length).toBe(1);
  });

  it('asks for a bounded window, because R-34 forbids an unbounded scan', async () => {
    const requests = stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    const url = new URL(requests.find((request) => request.url.includes('/alerts'))?.url ?? '');
    const start = Date.parse(url.searchParams.get('start') ?? '');
    const end = Date.parse(url.searchParams.get('end') ?? '');

    expect(Number.isNaN(start)).toBe(false);
    expect(Number.isNaN(end)).toBe(false);
    expect(end).toBeGreaterThan(start);
  });

  it('narrows the read server-side when a severity is chosen', async () => {
    const requests = stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'critical');

    await waitFor(() => {
      const urls = requests
        .filter((request) => request.url.includes('/alerts'))
        .map((request) => new URL(request.url).searchParams.get('severity'));
      expect(urls).toContain('critical');
    });
  });

  it('filters the panels below the controls and says how many it removed', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('table', { name: /Entities in the brushed window/ });

    const table = screen.getByRole('table', { name: /Entities in the brushed window/ });
    expect(within(table).getByText('3')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Min records'), '10');

    await waitFor(() => expect(screen.getByText(/2 hidden by the controls/)).toBeInTheDocument());
    expect(
      within(screen.getByRole('table', { name: /Entities in the brushed window/ })).queryByRole(
        'button',
        { name: /^2/ },
      ),
    ).toBeNull();
  });

  it('keeps only entities with an open alert when the toggle is on', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('table', { name: /Entities in the brushed window/ });

    await userEvent.click(screen.getByLabelText(/Only entities with an open alert/));

    await waitFor(() => expect(screen.getByText(/1 hidden by the controls/)).toBeInTheDocument());
  });

  it('lets a table stand in for the chart, which is what §9 requires', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));

    const table = await screen.findByRole('table', { name: /as a table/ });
    expect(within(table).getByRole('columnheader', { name: 'Records' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Mean score' })).toBeInTheDocument();
  });

  it('pins an entity from the graph and says the view is pinned', async () => {
    stubTraffic();
    renderPage();
    const graph = await screen.findByRole('group', { name: /Entity relationships/ });

    const node = within(graph).getByRole('button', { name: /Entity 1,/ });
    await userEvent.click(node);

    await waitFor(() => expect(screen.getByText(/pinned to one entity/)).toBeInTheDocument());
    expect(screen.getByText(/Entity 1 and its neighbours are shown/)).toBeInTheDocument();
  });

  it('pins from the table too, so the graph is not the only way in', async () => {
    stubTraffic();
    renderPage();
    const table = await screen.findByRole('table', { name: /Entities in the brushed window/ });

    await userEvent.click(within(table).getByRole('button', { name: '3' }));

    await waitFor(() => expect(screen.getByText(/pinned to one entity/)).toBeInTheDocument());
  });

  it('says what the numbers are not, on the screen that shows them', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    const caveats = screen.getByRole('region', { name: 'What this screen is not showing' });
    expect(within(caveats).getByText(/raw-record count carried by alerts/)).toBeInTheDocument();
    expect(within(caveats).getByText(/host or user value/)).toBeInTheDocument();
  });

  it('reports a partial read rather than presenting it as the whole window', async () => {
    // The stub serves one page and then keeps a cursor, so the walk hits its cap.
    stubFetch([
      {
        match: '/api/v1/alerts',
        respond: () =>
          jsonResponse({ items: ROWS, next_cursor: 'more', limit: 1_000, order: 'desc' }),
      },
    ]);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/Only the first 5 pages were read/)).toBeInTheDocument(),
    );
  });

  it('says a window with no alerts is empty rather than drawing a blank panel', async () => {
    stubTraffic([]);
    renderPage();

    expect(await screen.findByText(/nothing was scored high enough to alert/)).toBeInTheDocument();
  });

  it('names the failure and offers a retry when the read fails', async () => {
    stubFetch([{ match: '/api/v1/alerts', respond: () => jsonResponse({ detail: 'boom' }, 500) }]);
    renderPage();

    expect(await screen.findByText('The traffic window could not be loaded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('reads the window the operator picks', async () => {
    const requests = stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    await userEvent.selectOptions(screen.getByLabelText('Window'), '7d');

    await waitFor(() => {
      const url = new URL(
        requests.filter((request) => request.url.includes('/alerts')).at(-1)?.url ?? '',
      );
      const span =
        Date.parse(url.searchParams.get('end') ?? '') -
        Date.parse(url.searchParams.get('start') ?? '');
      expect(span).toBeGreaterThan(86_400_000);
    });
  });

  it('reads a 24 h window by default, and sends no severity filter for "all"', async () => {
    const requests = stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    const url = new URL(requests.find((request) => request.url.includes('/alerts'))?.url ?? '');
    const span =
      Date.parse(url.searchParams.get('end') ?? '') -
      Date.parse(url.searchParams.get('start') ?? '');
    expect(span).toBeGreaterThan(23 * 3_600_000);
    expect(span).toBeLessThan(25 * 3_600_000);
    // "All severities" means no filter at all: sending `severity=all` would be a
    // value the API has no reason to understand.
    expect(url.searchParams.get('severity')).toBeNull();
  });

  it('says an entity with an unrecognised severity rather than colouring it', async () => {
    stubTraffic([row({ id: 1, entity_id: 1, severity: 'catastrophic' })]);
    renderPage();
    const table = await screen.findByRole('table', { name: /Entities in the brushed window/ });

    expect(within(table).getByText('unrecognised')).toBeInTheDocument();
  });

  it('says so when the controls leave no entities, rather than drawing an empty graph', async () => {
    stubTraffic();
    renderPage();
    await screen.findByRole('group', { name: /Entity relationships/ });

    await userEvent.type(screen.getByLabelText('Min records'), '9999');

    expect(await screen.findByText('No entities in this selection')).toBeInTheDocument();
  });

  it('prints the entity table as an ordinary table, with its columns switchable', async () => {
    stubTraffic();
    renderPage();
    const table = await screen.findByRole('table', { name: /Entities in the brushed window/ });

    // The open column is off by default (a low-value column), and the picker is what
    // brings it back — the same primitive every other table in the product uses.
    expect(within(table).queryByRole('columnheader', { name: 'Open' })).toBeNull();
    // The picker sits in the table's toolbar, outside the table's own role.
    await userEvent.click(screen.getByText('Columns'));
    await userEvent.click(screen.getByLabelText('Open'));

    await waitFor(() =>
      expect(within(table).getByRole('columnheader', { name: 'Open' })).toBeInTheDocument(),
    );

    // And it says which entities still have something open, one by one: the default
    // window has two open alerts (entities 1 and 2) and one resolved (entity 3), so a
    // column that said "yes" on every row would fail here. The column's position is
    // read from the header rather than assumed, because the picker decides it.
    const header = within(table).getAllByRole('row')[0] as HTMLElement;
    const column = within(header)
      .getAllByRole('columnheader')
      .findIndex((cell) => cell.textContent === 'Open');
    const body = within(table).getAllByRole('row').slice(1);
    const open = body.map((line) => within(line).getAllByRole('cell')[column]?.textContent);

    expect(open).toHaveLength(3);
    expect(new Set(open)).toEqual(new Set(['yes', 'no']));
  });

  it('has no serious accessibility violations', async () => {
    stubTraffic();
    const { container } = renderPage();
    await screen.findByRole('group', { name: /Alerted record volume/ });

    await expectAccessible(container as HTMLElement);
  });
});
