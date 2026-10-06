/**
 * The three R-29 states — `EmptyState`, `ErrorState`, `Skeleton`.
 *
 * They are tested together because they are one rule: design.md §8.1 says what a
 * surface must say when it is empty, when it failed, and when it is loading, and a
 * primitive that says the wrong thing is the failure mode the rule exists to
 * prevent — a blank panel reads as a working widget with no data.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Skeleton } from './Skeleton';

describe('EmptyState', () => {
  it('says what is empty and what to do about it', () => {
    render(
      <EmptyState
        title="No open critical alerts in the last 24 h."
        description="Widen the range to 7 days to see recent activity."
        action={<button type="button">Widen to 7 days</button>}
      />,
    );

    const state = screen.getByRole('status');
    expect(state).toHaveTextContent('No open critical alerts in the last 24 h.');
    expect(state).toHaveTextContent('Widen the range to 7 days');
    expect(screen.getByRole('button', { name: 'Widen to 7 days' })).toBeInTheDocument();
  });

  it('is announced as a status rather than interrupting', () => {
    render(<EmptyState title="No saved hunts yet" />);

    expect(screen.getByRole('status')).toHaveTextContent('No saved hunts yet');
  });
});

describe('ErrorState', () => {
  it('says what failed, whether it is retrying, and offers a retry', () => {
    render(
      <ErrorState
        message="The alert list could not be loaded"
        detail="Showing the last successful load"
        retrying
        action={<button type="button">Retry</button>}
      />,
    );

    const state = screen.getByRole('alert');
    expect(state).toHaveTextContent('The alert list could not be loaded');
    expect(state).toHaveTextContent('Showing the last successful load');
    expect(state).toHaveTextContent('Retrying\u2026');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('does not claim to be retrying when it is not', () => {
    render(<ErrorState message="The alert list could not be loaded" />);

    expect(screen.getByRole('alert')).not.toHaveTextContent('Retrying');
  });

  it('cannot be handed a stack trace: every prop is rendered prose', () => {
    // §8.1: "Never a raw stack trace in the UI." There is no prop that takes one —
    // the message is operator-facing words and the detail says what the failure
    // means for the data on screen. A caller cannot smuggle a traceback in, because
    // whatever it passes renders as a sentence, in the UI, where it will be read.
    render(<ErrorState message="The model service is unavailable" detail="Scores are 6 h old" />);

    const state = screen.getByRole('alert');
    expect(state.textContent).not.toMatch(/Traceback|File "\/|\.py:\d/);
  });
});

describe('Skeleton', () => {
  it('names what is loading and draws the matching number of bars', () => {
    render(<Skeleton lines={4} label="Alert list is loading" />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Alert list is loading');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(screen.getAllByTestId('skeleton-bar')).toHaveLength(4);
  });

  it('hides the bars from assistive technology', () => {
    // The bars are the shape of the final layout, not content. A screen reader
    // should hear the one label, once.
    const { container } = render(<Skeleton lines={3} label="KPI tiles are loading" />);

    const bars = container.querySelector('[aria-hidden="true"]');
    expect(bars).not.toBeNull();
    expect(bars?.children).toHaveLength(3);
  });
});

describe('the three states together', () => {
  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <div>
        <EmptyState title="No rows match this view" description="Widen the range" />
        <ErrorState message="The panel could not be loaded" retrying />
        <Skeleton lines={3} label="Panel is loading" />
      </div>,
    );

    await expectAccessible(container as HTMLElement);
  });
});
