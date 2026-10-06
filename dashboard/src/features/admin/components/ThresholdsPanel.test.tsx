/**
 * The thresholds panel (T-410, design.md §4.8).
 *
 * §4.8's clause is a *sequence*, so the test follows it: type a value, see the impact
 * the server would report, and only then save. The URL the preview is asked for is
 * asserted, because "the preview is wired to the endpoint" is the claim — a panel that
 * counted alerts itself would pass a test that only read the number.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { ToastProvider } from '../../../components/ui';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { ThresholdsPanel } from './ThresholdsPanel';

/** The panel raises a toast on a successful recalibration, so it needs the provider. */
function panel() {
  return renderWithProviders(
    <ToastProvider>
      <ThresholdsPanel />
    </ToastProvider>,
  );
}

const BASE = '/api/v1/thresholds';

const LIST = {
  tenant_id: 't1',
  defaults: { critical: 0.9, high: 0.7, medium: 0.4, low: 0.2 },
  items: [
    {
      tenant_id: 't1',
      family: 'flow',
      band: 'high',
      value: 0.72,
      source: 'recalculation',
      source_label: 'calibrated',
      updated_at: '2026-10-01T00:00:00Z',
      changed_by: 'ops@example.test',
    },
  ],
};

const IMPACT = {
  tenant_id: 't1',
  family: 'flow',
  band: 'high',
  proposed: 0.8,
  current: 0.72,
  current_source: 'calibrated',
  window_start: '2026-09-29T10:00:00Z',
  window_end: '2026-10-06T10:00:00Z',
  alerts_read: 412,
  would_fire: 98,
  would_stop_firing: 12,
  would_start_firing: 0,
  complete: true,
};

function routes(impact: typeof IMPACT = IMPACT) {
  return [
    { match: `${BASE}/preview`, respond: () => jsonResponse(impact) },
    { match: BASE, respond: () => jsonResponse(LIST) },
  ];
}

describe('ThresholdsPanel', () => {
  it('shows the value in force, its source and who moved it', async () => {
    stubFetch(routes());
    const { container } = panel();

    const table = await screen.findByRole('table', { name: /Bands, the value in force/ });
    expect(table).toHaveTextContent('calibrated');
    expect(table).toHaveTextContent('ops@example.test');
    // The three bands with no stored row read as FR-13's defaults, not as absent.
    expect(screen.getAllByText('default')).toHaveLength(3);
    expect(table).toHaveTextContent('0.72');
    await expectAccessible(container);
  });

  it('previews the impact from the server before saving', async () => {
    const user = userEvent.setup();
    const seen = stubFetch(routes());
    panel();

    await user.click(await screen.findByRole('button', { name: 'Preview a new high value' }));
    const dialog = await screen.findByRole('dialog');
    const input = within(dialog).getByLabelText('Proposed high lower bound');
    await user.clear(input);
    await user.type(input, '0.8');

    await waitFor(() => {
      expect(
        screen.getByText(/98 of the 412 recorded alerts would have been banded high or worse\./),
      ).toBeInTheDocument();
    });
    const preview = seen.find((request) => new URL(request.url).pathname === `${BASE}/preview`);
    const url = new URL(preview?.url ?? '');
    expect(url.searchParams.get('family')).toBe('flow');
    expect(url.searchParams.get('band')).toBe('high');
    expect(url.searchParams.get('value')).toBe('0.8');
    // The preview is a read: the method is the API's, and a preview that wrote
    // would be an action behind a control labelled "preview".
    expect(preview?.method).toBe('GET');
    expect(
      screen.getByText('Raising high from 0.72 to 0.80: 12 alerts would no longer reach it.'),
    ).toBeInTheDocument();
  });

  it('says the counts are floored when the walk hit its page cap', async () => {
    const user = userEvent.setup();
    stubFetch(routes({ ...IMPACT, complete: false }));
    panel();

    await user.click(await screen.findByRole('button', { name: 'Preview a new high value' }));
    const dialog = await screen.findByRole('dialog');
    await user.clear(within(dialog).getByLabelText('Proposed high lower bound'));
    await user.type(within(dialog).getByLabelText('Proposed high lower bound'), '0.8');

    await waitFor(() => {
      expect(screen.getByText(/at least 98/)).toBeInTheDocument();
    });
    expect(screen.getByText(/floored counts rather than totals/)).toBeInTheDocument();
  });

  it('lists the four bands that have a bound, and says where info begins', async () => {
    stubFetch(routes());
    panel();
    const table = await screen.findByRole('table', { name: /Bands, the value in force/ });
    // `info` is not a row with a settable value: it is the bucket everything below
    // the lowest band falls into, and the sentence under the table says so.
    expect(table).not.toHaveTextContent('info');
    expect(
      await screen.findByText(/Everything below the 0\.20 info bound is info/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Preview a new info value/ })).toBeNull();
  });

  it('refuses to save the value already in force', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    panel();

    await user.click(await screen.findByRole('button', { name: 'Preview a new high value' }));
    const dialog = await screen.findByRole('dialog');
    // The field opens at the value in force, so the control is disabled until it moves.
    expect(within(dialog).getByRole('button', { name: 'Save the value' })).toBeDisabled();
    expect(within(dialog).getByText('This is the value already in force.')).toBeInTheDocument();
  });

  it('refuses a value outside the open interval', async () => {
    const user = userEvent.setup();
    stubFetch(routes());
    panel();

    await user.click(await screen.findByRole('button', { name: 'Preview a new high value' }));
    const dialog = await screen.findByRole('dialog');
    await user.clear(within(dialog).getByLabelText('Proposed high lower bound'));
    await user.type(within(dialog).getByLabelText('Proposed high lower bound'), '1.5');
    expect(
      within(dialog).getByText('A threshold is strictly between 0 and 1.'),
    ).toBeInTheDocument();
  });

  it('renders the server’s refusal to invert the band order', async () => {
    const user = userEvent.setup();
    stubFetch([
      { match: `${BASE}/preview`, respond: () => jsonResponse(IMPACT) },
      {
        match: BASE,
        respond: (request) =>
          request.method === 'PUT'
            ? jsonResponse({ detail: 'out of order' }, 409)
            : jsonResponse(LIST),
      },
    ]);
    panel();

    await user.click(await screen.findByRole('button', { name: 'Preview a new high value' }));
    const dialog = await screen.findByRole('dialog');
    await user.clear(within(dialog).getByLabelText('Proposed high lower bound'));
    await user.type(within(dialog).getByLabelText('Proposed high lower bound'), '0.8');
    // Wait for the preview before saving: the refusal is the answer to the save.
    await screen.findByText(/98 of the 412 recorded alerts/);
    await user.click(within(dialog).getByRole('button', { name: 'Save the value' }));

    await waitFor(() => {
      expect(screen.getByText(/leave the bands out of order/)).toBeInTheDocument();
    });
  });

  it('does not read a family the deployment has never moved as having no thresholds', async () => {
    stubFetch([
      { match: `${BASE}/preview`, respond: () => jsonResponse(IMPACT) },
      {
        match: BASE,
        respond: () => jsonResponse({ tenant_id: 't1', defaults: LIST.defaults, items: [] }),
      },
    ]);
    panel();
    const table = await screen.findByRole('table', { name: /Bands, the value in force/ });
    expect(table).toHaveTextContent('0.70');
    expect(screen.getByText(/no band has been moved on this deployment/)).toBeInTheDocument();
  });
});
