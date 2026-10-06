/**
 * The retention panel (T-410, NFR-05).
 *
 * The plan is shown before the run, and the three awkward lists are rendered as
 * sentences rather than as counts — that is what stops "2 partitions would be dropped"
 * being read as the whole answer when two tables can never be evicted from the database
 * and an object store is outside every plan. A run that refuses (this build has no
 * database session) is asserted to say *why*, because a failure state that rendered as
 * "nothing to do" would be the one lie a retention screen must not tell.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { jsonResponse, renderWithProviders, stubFetch } from '../../../test/query';
import { RetentionPanel } from './RetentionPanel';

const PLAN = '/api/v1/retention';
const ERASURE = '/api/v1/privacy/erasure';

const PLAN_BODY = {
  planned_at: '2026-10-06T00:00:00Z',
  policy: { raw_records_days: 365, alerts_days: 400, stats_days: 730 },
  drop: [
    {
      table: 'raw_records',
      name: 'raw_records_2025_03',
      year: 2025,
      month: 3,
      covers_start: '2025-03-01',
      covers_end: '2025-04-01',
      statement: 'DROP TABLE IF EXISTS raw_records_2025_03',
    },
  ],
  kept: [],
  missing: ['2025-02'],
  unevictable: [{ table: 'audit_log', name: 'audit_log', reason: 'not-monthly' }],
  external: { object_store: 'raw flow archives, 365 days' },
  statements: [],
};

describe('RetentionPanel', () => {
  it('shows the plan, the drop, and every list a run cannot reach', async () => {
    stubFetch([{ match: PLAN, respond: () => jsonResponse(PLAN_BODY) }]);
    const { container } = renderWithProviders(<RetentionPanel />);

    expect(await screen.findByText(/1 partition would be dropped\./)).toBeInTheDocument();
    expect(
      screen.getByText(/Raw records 365 days, alerts 400 days, stats 730 days\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/2025-02 has no partition/)).toBeInTheDocument();
    expect(screen.getByText(/object_store \(raw flow archives, 365 days\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/not monthly, so a retention window does not bound them/),
    ).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('confirms before dropping, naming the partitions', async () => {
    const user = userEvent.setup();
    stubFetch([
      {
        match: `${PLAN}/run`,
        respond: () =>
          jsonResponse({
            changed_anything: false,
            planned: [],
            dropped: [],
            already_absent: [],
            started_at: '2026-10-06T00:00:00Z',
          }),
      },
      { match: PLAN, respond: () => jsonResponse(PLAN_BODY) },
    ]);
    renderWithProviders(<RetentionPanel />);

    await user.click(await screen.findByRole('button', { name: 'Run retention' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/raw_records_2025_03/)).toBeInTheDocument();
    expect(within(dialog).getByText(/rows they hold are gone/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Drop the partitions' }));

    await waitFor(() => {
      expect(screen.getByText(/found nothing to drop/)).toBeInTheDocument();
    });
  });

  it('renders a refused run as a reason, not as a clean run', async () => {
    // This build wires no partition runner, so the route answers 500. The screen
    // must carry that as itself: reporting it as "nothing to do" would be the one
    // lie a retention screen can tell.
    const user = userEvent.setup();
    stubFetch([
      { match: `${PLAN}/run`, respond: () => jsonResponse({ detail: 'no runner' }, 500) },
      { match: PLAN, respond: () => jsonResponse(PLAN_BODY) },
    ]);
    renderWithProviders(<RetentionPanel />);

    await user.click(await screen.findByRole('button', { name: 'Run retention' }));
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Drop the partitions',
      }),
    );

    await waitFor(() => {
      expect(screen.getByText(/no database session wired to drop partitions/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/found nothing to drop/)).toBeNull();
  });

  it('offers no run when the plan has nothing to drop', async () => {
    stubFetch([
      {
        match: PLAN,
        respond: () =>
          jsonResponse({ ...PLAN_BODY, drop: [], missing: [], unevictable: [], external: {} }),
      },
    ]);
    renderWithProviders(<RetentionPanel />);
    // The action bar renders with the card, so the assertion waits for the plan
    // itself rather than for the button.
    expect(await screen.findByText(/would still be\s+recorded in the trail/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run retention' })).toBeDisabled();
  });

  it('offers no run from a plan it could not read', async () => {
    stubFetch([{ match: PLAN, respond: () => jsonResponse({ detail: 'no' }, 500) }]);
    renderWithProviders(<RetentionPanel />);
    expect(await screen.findByText('The retention plan could not be read')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run retention' })).toBeNull();
  });

  it('sends an erasure and reports the tombstone, never the identifier', async () => {
    const user = userEvent.setup();
    const seen = stubFetch([
      {
        match: ERASURE,
        respond: () =>
          jsonResponse({
            kind: 'user',
            tombstone: 'sha256:6f1c',
            at: '2026-10-06T00:00:00Z',
            targets: [{ name: 'alerts', affected: 3 }],
            preserved: [{ store: 'audit_log', reason: 'legal hold' }],
            already_erased: false,
            ledger_sequence: 12,
            affected: 3,
            reason: 'request 42',
          }),
      },
      { match: PLAN, respond: () => jsonResponse(PLAN_BODY) },
    ]);
    renderWithProviders(<RetentionPanel />);

    await user.type(await screen.findByLabelText('Identifier'), 'someone@example.test');
    await user.type(screen.getByLabelText('Reason (optional, recorded)'), 'request 42');
    await user.click(screen.getByRole('button', { name: 'Erase' }));

    await waitFor(() => {
      expect(screen.getByText(/Tombstone/)).toHaveTextContent('sha256:6f1c');
    });
    const report = screen.getByText(/Tombstone/);
    expect(report).toHaveTextContent('3 rows across 1 store');
    expect(report).toHaveTextContent('Kept: audit_log (legal hold)');
    // The identifier went out and did not come back to the screen.
    expect(report.textContent).not.toContain('someone@example.test');
    const erasure = seen.find((request) => new URL(request.url).pathname === ERASURE);
    await expect(erasure?.json()).resolves.toEqual({
      kind: 'user',
      value: 'someone@example.test',
      reason: 'request 42',
    });
  });

  it('will not erase without an identifier', async () => {
    stubFetch([{ match: PLAN, respond: () => jsonResponse(PLAN_BODY) }]);
    renderWithProviders(<RetentionPanel />);
    expect(await screen.findByRole('button', { name: 'Erase' })).toBeDisabled();
  });
});
