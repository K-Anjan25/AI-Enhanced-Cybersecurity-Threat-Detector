import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { App } from './App';
import { expectAccessible } from './test/axe';
import { ThemeProvider } from './theme/ThemeProvider';

function renderAt(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('routing and shell', () => {
  it('renders the overview page at the root', () => {
    renderAt('/');

    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
  });

  it('renders the full information architecture in the nav', () => {
    renderAt('/');

    const nav = screen.getByRole('navigation', { name: 'Primary' });
    for (const label of ['Overview', 'Alerts', 'Traffic', 'Logs', 'Hunt', 'Models', 'Admin']) {
      expect(nav).toHaveTextContent(label);
    }
  });

  it('navigates to a pending screen and names the task that owns it', async () => {
    const user = userEvent.setup();
    renderAt('/');

    await user.click(screen.getByRole('link', { name: 'Alerts' }));

    expect(screen.getByRole('heading', { level: 1, name: 'Not built yet' })).toBeInTheDocument();
    expect(screen.getByText('T-404')).toBeInTheDocument();
  });

  it('shows a 404 state rather than a blank page for an unknown route', () => {
    renderAt('/does-not-exist');

    expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeInTheDocument();
  });

  it('states honestly that nothing is being analysed yet', () => {
    renderAt('/');

    expect(screen.getByText(/No telemetry is being analysed yet/)).toBeInTheDocument();
    expect(screen.getByText('not started — T-201')).toBeInTheDocument();
  });

  it('has no serious accessibility violations on the overview screen', async () => {
    const { container } = renderAt('/');

    await expectAccessible(container as HTMLElement);
  });
});
