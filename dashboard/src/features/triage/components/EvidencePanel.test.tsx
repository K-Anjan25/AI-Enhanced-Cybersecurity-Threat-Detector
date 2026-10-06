/**
 * Zone 3: the trail, its tabs, and the two states the acceptance criterion names.
 *
 * The tests assert on text the analyst reads — `evidence expired at 14 Apr 2026,
 * 10:00:00Z`, the unreadable count, the related-alert links — rather than on the
 * props that produced it.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, alertRow, evidence, occurrence, related } from '../fixtures';
import { EvidencePanel } from './EvidencePanel';
import type { AlertDetail } from '../types';

function renderPanel(overrides: Partial<AlertDetail> = {}) {
  const view = render(
    <MemoryRouter>
      <EvidencePanel detail={alertDetail(overrides)} />
    </MemoryRouter>,
  );
  return view;
}

const TWO_MODALITIES = evidence({
  occurrences: [
    occurrence({ id: 'f1', modality: 'flow', at: '2026-03-15T09:59:00Z' }),
    occurrence({ id: 'f2', modality: 'flow', at: '2026-03-15T10:00:00Z' }),
    occurrence({ id: 'l1', modality: 'log', at: '2026-03-15T10:00:30Z' }),
  ],
});

describe('EvidencePanel', () => {
  it('tabs by modality with their counts, and related alerts beside them', () => {
    renderPanel({ evidence: TWO_MODALITIES, related: related({ items: [alertRow({ id: 9 })] }) });

    expect(screen.getByRole('tab', { name: 'Flows 2' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Log lines 1' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Related alerts 1' })).toBeInTheDocument();
  });

  it('shows the windows of the selected modality', async () => {
    renderPanel({ evidence: TWO_MODALITIES });

    const table = screen.getByRole('table', { name: /scored as flows/i });
    expect(within(table).getAllByRole('row')).toHaveLength(3); // header + 2 windows
    expect(within(table).getByText('09:59:00Z')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Log lines 1' }));

    const logs = screen.getByRole('table', { name: /scored as log lines/i });
    expect(within(logs).getByText('10:00:30Z')).toBeInTheDocument();
  });

  it('moves along the tabs with the arrow keys', async () => {
    // A tablist that only answers Tab and Space fights the keyboard, and this
    // screen's whole point is the no-mouse loop.
    renderPanel({ evidence: TWO_MODALITIES });
    screen.getByRole('tab', { name: 'Flows 2' }).focus();

    await userEvent.keyboard('{ArrowRight}');

    expect(screen.getByRole('tab', { name: 'Log lines 1' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('says when the evidence expired, with the date', () => {
    renderPanel({
      evidence: evidence({
        expired: true,
        note: 'raw records are past the retention window',
        occurrences: [occurrence({ expired: true, expires_at: '2026-04-14T10:00:00Z' })],
      }),
    });

    expect(screen.getByText('evidence expired at 14 Apr 2026, 10:00:00Z')).toBeInTheDocument();
    // The trail keeps rendering: the pointers survive what the records did not.
    expect(screen.getByRole('table', { name: /scored as flows/i })).toBeInTheDocument();
  });

  it('does not claim expiry while the records are inside the window', () => {
    renderPanel();

    expect(screen.queryByText(/evidence expired at/)).not.toBeInTheDocument();
    expect(screen.getByText(/kept for 30 d/)).toBeInTheDocument();
  });

  it('reports trail entries it could not read', () => {
    renderPanel({ evidence: evidence({ unreadable: 2 }) });

    expect(screen.getByText(/2 trail entries could not be read/)).toBeInTheDocument();
  });

  it('links a related alert with both halves of its key', async () => {
    renderPanel({
      related: related({
        items: [alertRow({ id: 9, created_at: '2026-03-15T09:30:00Z' })],
        truncated: true,
      }),
    });

    await userEvent.click(screen.getByRole('tab', { name: 'Related alerts 1' }));

    expect(screen.getByRole('link', { name: /09:30:00Z/ })).toHaveAttribute(
      'href',
      '/alerts/9?created_at=2026-03-15T09%3A30%3A00Z',
    );
    expect(screen.getByText(/more related alerts exist/)).toBeInTheDocument();
  });

  it('says so when there are no related alerts', async () => {
    renderPanel();

    await userEvent.click(screen.getByRole('tab', { name: 'Related alerts 0' }));

    expect(screen.getByText('No related alerts')).toBeInTheDocument();
    expect(screen.getByText(/within ±60 min/)).toBeInTheDocument();
  });

  it('states a missing trail rather than rendering an empty table', () => {
    renderPanel({ evidence: evidence({ occurrences: [] }) });

    expect(screen.getByText('No evidence trail was recorded for this alert.')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Related alerts 0' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('names the window and the trace the alert came from', () => {
    renderPanel();

    expect(screen.getByText(/Window win-1/)).toBeInTheDocument();
    expect(screen.getByText('trace-1')).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <EvidencePanel detail={alertDetail({ evidence: TWO_MODALITIES })} />
      </MemoryRouter>,
    );

    await expectAccessible(container);
  });
});
