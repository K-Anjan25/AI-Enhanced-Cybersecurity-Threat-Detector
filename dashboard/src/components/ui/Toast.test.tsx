import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { ToastProvider, useToast } from './Toast';

const DURATION = 1_000;

function Trigger() {
  const toast = useToast();
  return (
    <>
      <button type="button" onClick={() => toast('success', 'Verdict saved')}>
        Save
      </button>
      <button type="button" onClick={() => toast('warning', 'Scores are 6 h old')}>
        Warn
      </button>
      <button
        type="button"
        onClick={() => toast('error', 'Export failed: you need the responder role')}
      >
        Fail
      </button>
    </>
  );
}

function renderToasts() {
  return render(
    <ToastProvider duration={DURATION}>
      <Trigger />
    </ToastProvider>,
  );
}

/** Advance the clock inside `act`, so React has flushed the dismissal. */
function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the message it was given, in words', () => {
    renderToasts();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    const toast = screen.getByRole('status');
    expect(toast).toHaveTextContent('Done: Verdict saved');
  });

  it('announces a warning politely and an error assertively', () => {
    renderToasts();

    fireEvent.click(screen.getByRole('button', { name: 'Warn' }));
    expect(screen.getByRole('status')).toHaveTextContent('Warning:');

    fireEvent.click(screen.getByRole('button', { name: 'Fail' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Error:');
  });

  it('dismisses an acknowledgement on its own', () => {
    renderToasts();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByRole('status')).toBeInTheDocument();

    advance(DURATION);

    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('never takes an error away on a timer', () => {
    // design.md §6: "auto-dismiss except errors". The failure is the message the
    // operator most needs, so it waits for a human.
    renderToasts();
    fireEvent.click(screen.getByRole('button', { name: 'Fail' }));

    advance(DURATION * 60);

    expect(screen.getByRole('alert')).toHaveTextContent('Export failed');
  });

  it('lets a human dismiss an error', () => {
    renderToasts();
    fireEvent.click(screen.getByRole('button', { name: 'Fail' }));

    fireEvent.click(screen.getByRole('button', { name: /Dismiss error notification/ }));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('leaves no timer behind when the provider unmounts', () => {
    const { unmount } = renderToasts();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const pending = vi.getTimerCount();
    expect(pending).toBeGreaterThan(0);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it('refuses to drop a toast raised outside a provider', () => {
    expect(() => render(<Trigger />)).toThrow(/ToastProvider/);
  });

  it('has no serious accessibility violations', async () => {
    // axe awaits its own timers internally; running it against a faked clock hangs.
    vi.useRealTimers();
    const { container } = renderToasts();
    fireEvent.click(screen.getByRole('button', { name: 'Fail' }));

    await expectAccessible(container as HTMLElement);
  });
});
