import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { ThemeProvider, useTheme } from './ThemeProvider';

function Probe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button type="button" onClick={toggleTheme}>
        toggle
      </button>
    </div>
  );
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to the dark theme, which is the SOC default', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('restores a previously chosen theme', () => {
    window.localStorage.setItem('aegis.theme', 'light');

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });

  it('toggles the theme and persists the choice', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await user.click(screen.getByRole('button', { name: 'toggle' }));

    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    expect(window.localStorage.getItem('aegis.theme')).toBe('light');
  });

  it('ignores an unrecognised stored value rather than applying a bad theme', () => {
    window.localStorage.setItem('aegis.theme', 'solarised');

    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
  });

  it('throws when useTheme is used outside a provider', () => {
    // A silent fallback would hide a wiring mistake until runtime styling broke.
    expect(() => render(<Probe />)).toThrow(/inside a ThemeProvider/);
  });

  it('updates the document attribute when the theme is set imperatively', () => {
    function Setter() {
      const { setTheme } = useTheme();
      return (
        <button type="button" onClick={() => act(() => setTheme('light'))}>
          set light
        </button>
      );
    }

    render(
      <ThemeProvider>
        <Setter />
      </ThemeProvider>,
    );

    screen.getByRole('button', { name: 'set light' }).click();
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });
});
