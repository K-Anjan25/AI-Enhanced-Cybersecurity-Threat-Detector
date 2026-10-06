import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { expectAccessible } from '../../test/axe';
import { ConnectionBanner } from './ConnectionBanner';

function renderBanner(props: Partial<Parameters<typeof ConnectionBanner>[0]> = {}) {
  return render(
    <ThemeProvider>
      <ConnectionBanner
        state="disconnected"
        message="Live updates are off"
        explanation="The connection closed (1006). Showing the API's data and polling every 15 s."
        {...props}
      />
    </ThemeProvider>,
  );
}

describe('ConnectionBanner', () => {
  it('says what happened and what the dashboard is doing instead', () => {
    renderBanner();

    expect(screen.getByText('Live updates are off')).toBeInTheDocument();
    expect(screen.getByText(/polling every 15 s/)).toBeInTheDocument();
  });

  it('is a polite live region, so a screen reader is told without being interrupted', () => {
    renderBanner();

    const banner = screen.getByRole('status');
    expect(banner).toHaveAttribute('aria-live', 'polite');
  });

  it('renders nothing at all while the stream is live', () => {
    // A banner that says "all good" is a banner nobody reads by the time it matters.
    const { container } = renderBanner({ state: 'live' });

    expect(container).toBeEmptyDOMElement();
  });

  it('offers the retry when a retry could help', async () => {
    const onRetry = vi.fn();
    renderBanner({ onRetry });

    await userEvent.click(screen.getByRole('button', { name: 'Reconnect now' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('offers no action when the caller has none', () => {
    renderBanner();

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('marks the connecting state as a warning and the disconnected one as critical', () => {
    const { container: degraded } = renderBanner({ state: 'degraded' });
    expect(degraded.firstElementChild?.className).toContain('text-severityText-medium');

    const { container: disconnected } = renderBanner();
    expect(disconnected.firstElementChild?.className).toContain('text-severityText-critical');
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderBanner({ onRetry: () => undefined });

    await expectAccessible(container as HTMLElement);
  });
});
