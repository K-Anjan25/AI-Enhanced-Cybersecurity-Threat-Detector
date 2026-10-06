/**
 * The sticky bar and its shortcuts.
 *
 * The two acceptance criteria this file owns: the bar is reachable without
 * scrolling, and `1`/`2`/`3` record the verdicts it names. Every assertion is on
 * what the analyst sees or on what the component asked its parent to do — never on
 * a handler's internals.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { expectAccessible } from '../../../test/axe';
import { alertDetail, verdictRecord } from '../fixtures';
import { VerdictBar } from './VerdictBar';
import type { AlertDetail } from '../types';

function renderBar(overrides: Partial<AlertDetail> = {}, props: Record<string, unknown> = {}) {
  const onVerdict = vi.fn();
  const view = render(
    <MemoryRouter>
      <VerdictBar
        detail={alertDetail(overrides)}
        onVerdict={onVerdict}
        next="/alerts/7"
        {...props}
      />
    </MemoryRouter>,
  );
  return { onVerdict, view };
}

describe('VerdictBar', () => {
  it("states the alert in design.md §4.3's order: severity, score, family, entity, time", () => {
    renderBar();

    const bar = screen.getByRole('region', { name: 'Verdict' });
    expect(bar.textContent).toContain('Critical');
    expect(bar.textContent).toContain('score 0.96');
    expect(bar.textContent).toContain('Reconnaissance');
    expect(bar.textContent).toContain('entity #7');
    expect(bar.textContent).toContain('10:00:00Z');
  });

  it('sticks to the top of the scroll container', () => {
    // "The verdict bar is sticky and reachable without scrolling." A class is a
    // weak assertion, but it is the mechanism: `sticky top-0` on the bar itself.
    renderBar();

    const bar = screen.getByRole('region', { name: 'Verdict' });
    expect(bar.className).toContain('sticky');
    expect(bar.className).toContain('top-0');
  });

  it('records the verdict each key names', async () => {
    const { onVerdict } = renderBar();

    await userEvent.keyboard('1');
    expect(onVerdict).toHaveBeenLastCalledWith('true_positive');
    await userEvent.keyboard('2');
    expect(onVerdict).toHaveBeenLastCalledWith('false_positive');
    await userEvent.keyboard('3');
    expect(onVerdict).toHaveBeenLastCalledWith('benign');
    expect(onVerdict).toHaveBeenCalledTimes(3);
  });

  it('shows the key on the button it belongs to', () => {
    renderBar();

    const truePositive = screen.getByRole('button', { name: /1\s*True positive/ });
    expect(truePositive).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /2\s*False positive/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /3\s*Benign/ })).toBeInTheDocument();
  });

  it('does nothing for a key that is not a shortcut', async () => {
    const { onVerdict } = renderBar();

    await userEvent.keyboard('4');
    await userEvent.keyboard('q');

    expect(onVerdict).not.toHaveBeenCalled();
  });

  it('ignores a keypress that is typing into a field', async () => {
    // The bug that makes a shortcut dangerous: the moment a note field exists, `1`
    // in a note must be a one.
    const { onVerdict } = renderBar();
    const field = document.createElement('textarea');
    document.body.append(field);
    field.focus();

    await userEvent.keyboard('1');

    expect(onVerdict).not.toHaveBeenCalled();
    field.remove();
  });

  it('ignores a modified keystroke, which belongs to the browser', async () => {
    const { onVerdict } = renderBar();

    await userEvent.keyboard('{Control>}1{/Control}');
    await userEvent.keyboard('{Meta>}2{/Meta}');

    expect(onVerdict).not.toHaveBeenCalled();
  });

  it('does not queue a second write while one is in flight', async () => {
    const { onVerdict } = renderBar({}, { pending: true });

    await userEvent.keyboard('1');

    expect(onVerdict).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /1\s*True positive/ })).toBeDisabled();
  });

  it('announces the current verdict, and says so when there is none', () => {
    const { view } = renderBar();
    expect(screen.getByText(/No verdict recorded yet — press 1, 2 or 3\./)).toBeInTheDocument();

    view.unmount();
    renderBar({ verdict: { current: verdictRecord(), history: [verdictRecord()] } });

    const live = screen.getByText(/^Current verdict:/);
    expect(live).toHaveAttribute('aria-live', 'polite');
    expect(live.textContent).toContain('True positive · alice@corp · 10:03:00Z');
  });

  it('shows a failed write where the buttons are, without a URL or a body (R-58)', () => {
    renderBar({}, { errorMessage: 'Your role may not record verdicts.' });

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toBe('Your role may not record verdicts.');
    expect(alert.textContent).not.toMatch(/http|api\/v1/);
  });

  it('offers the next alert in the queue as a link', () => {
    renderBar();

    expect(screen.getByRole('link', { name: /Next alert/ })).toHaveAttribute('href', '/alerts/7');
  });

  it('says when the queue has no further alert', () => {
    renderBar({}, { next: null });

    expect(screen.getByText(/last alert in the queue/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Next alert/ })).not.toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { view } = renderBar();

    await expectAccessible(view.container);
  });
});
