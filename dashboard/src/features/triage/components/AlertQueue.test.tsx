/**
 * The queue: rows are keyboard-reachable links, and the panel is honest about how
 * much of the queue it is showing.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { expectAccessible } from '../../../test/axe';
import { alertRow } from '../fixtures';
import { AlertQueue } from './AlertQueue';

const NOW = Date.parse('2026-03-15T10:05:00Z');

function renderQueue(props: Partial<Parameters<typeof AlertQueue>[0]> = {}) {
  return render(
    <MemoryRouter>
      <AlertQueue
        rows={[alertRow({ id: 42 }), alertRow({ id: 41, created_at: '2026-03-15T09:20:00Z' })]}
        status="success"
        hasMore={false}
        windowHours={24}
        selectedId={42}
        now={NOW}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe('AlertQueue', () => {
  it('makes every row a link, so the whole row is keyboard-reachable', () => {
    renderQueue();

    const rows = screen.getAllByRole('link');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute('href', '/alerts/42?created_at=2026-03-15T10%3A00%3A00Z');
  });

  it('marks the open alert, so the detail beside it has an owner', () => {
    renderQueue();

    const current = screen.getAllByRole('link')[0];
    expect(current).toHaveAttribute('aria-current', 'true');
    expect(screen.getAllByRole('link')[1]).not.toHaveAttribute('aria-current');
  });

  it('shows severity, family, score and age for each row', () => {
    renderQueue();

    const first = screen.getAllByRole('link')[0] as HTMLElement;
    // The pill renders its glyph as a sibling of the label, so read the row's text.
    expect(first.textContent).toContain('Critical');
    expect(first.textContent).toContain('Reconnaissance');
    expect(first.textContent).toContain('0.96');
    expect(first.textContent).toContain('5 m ago');
  });

  it('says how much of the queue it is showing', () => {
    renderQueue();
    expect(screen.getByText('2 alerts in the last 24 h.')).toBeInTheDocument();
  });

  it('says more are waiting rather than presenting a page as the queue', () => {
    renderQueue({ hasMore: true });

    expect(screen.getByText(/more are waiting/)).toBeInTheDocument();
  });

  it('states an empty window instead of an empty list', () => {
    renderQueue({ rows: [], selectedId: null });

    expect(screen.getByText('No alerts in the window')).toBeInTheDocument();
    expect(screen.getByText(/Nothing has been raised in the last 24 h\./)).toBeInTheDocument();
  });

  it('keeps the rows on screen when a later read failed, and offers a retry', async () => {
    const onRetry = vi.fn();
    renderQueue({ status: 'error', onRetry });

    expect(screen.getByText('The queue could not be loaded')).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(2);

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderQueue();

    await expectAccessible(container);
  });
});
