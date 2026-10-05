import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ThemeProvider } from '../../theme/ThemeProvider';
import { expectAccessible } from '../../test/axe';
import { ConnectionStatus, type ConnectionState } from './ConnectionStatus';

function renderStatus(state: 'live' | 'degraded' | 'disconnected', detail?: string) {
  return render(
    <ThemeProvider>
      <ConnectionStatus state={state} detail={detail} />
    </ThemeProvider>,
  );
}

describe('ConnectionStatus', () => {
  const cases: ReadonlyArray<[ConnectionState, string]> = [
    ['live', 'Live'],
    ['degraded', 'Degraded'],
    ['disconnected', 'Disconnected'],
  ];

  it.each(cases)('labels the %s state in words, not colour alone', (state, label) => {
    renderStatus(state);

    expect(screen.getByRole('status')).toHaveTextContent(label);
  });

  it('shows the supplied detail, such as data age', () => {
    renderStatus('disconnected', 'last update 2 m ago');

    expect(screen.getByRole('status')).toHaveTextContent('last update 2 m ago');
  });

  it('is announced politely so screen readers pick up a state change', () => {
    renderStatus('degraded');

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
  });

  it('hides the decorative glyph from assistive technology', () => {
    const { container } = renderStatus('live');

    const glyph = container.querySelector('[aria-hidden="true"]');
    expect(glyph).not.toBeNull();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderStatus('live');

    await expectAccessible(container as HTMLElement);
  });
});
