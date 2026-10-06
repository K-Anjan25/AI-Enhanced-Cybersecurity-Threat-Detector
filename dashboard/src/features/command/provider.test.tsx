import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useSearchParams } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { FILTER_MARK } from '../../lib/keyboard';
import { renderWithProviders } from '../../test/query';
import { CommandProvider, useCommands, type SavedHuntRef } from './provider';

/**
 * A stand-in for the shell: the top bar's search control, and three routes so
 * "navigates" is observable. The real shell and the real routes are exercised by
 * `App.test.tsx`; what this file is about is the provider's wiring — which command
 * goes where, and which key opens what.
 */
function Harness({ saved }: { saved: readonly SavedHuntRef[] }) {
  return (
    <CommandProvider listSavedHunts={() => saved}>
      <Shell />
    </CommandProvider>
  );
}

function Shell() {
  const { openPalette } = useCommands();
  return (
    <>
      <button type="button" onClick={openPalette}>
        Search
      </button>
      <input aria-label="A field" {...FILTER_MARK} />
      <Routes>
        <Route path="/" element={<p>Overview screen</p>} />
        <Route path="/logs" element={<p>Logs screen</p>} />
        <Route path="/hunt" element={<HuntProbe />} />
      </Routes>
    </>
  );
}

function HuntProbe() {
  const [search] = useSearchParams();
  return <p>Hunt screen: {search.get('q') ?? 'no query'}</p>;
}

/** Open the palette the way an operator does: the keyboard, not the button. */
async function openWithPaletteKey(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.keyboard('{Control>}k{/Control}');
  await screen.findByRole('listbox', { name: 'Commands' });
}

describe('the command provider', () => {
  it('opens the palette on the command key', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await user.keyboard('{Meta>}k{/Meta}');

    expect(await screen.findByRole('listbox', { name: 'Commands' })).toBeInTheDocument();
  });

  it('toggles the palette with the same key', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await openWithPaletteKey(user);
    await user.keyboard('{Control>}k{/Control}');

    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: 'Commands' })).not.toBeInTheDocument();
    });
  });

  it('opens the palette from the top bar control too', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByRole('listbox', { name: 'Commands' })).toBeInTheDocument();
  });

  it('navigates to the screen that was typed and chosen', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />, undefined, ['/']);

    await openWithPaletteKey(user);
    await user.type(screen.getByRole('combobox'), 'logs');
    await user.keyboard('{Enter}');

    expect(await screen.findByText('Logs screen')).toBeInTheDocument();
    expect(screen.queryByRole('listbox', { name: 'Commands' })).not.toBeInTheDocument();
  });

  it('runs a saved hunt by navigating to it with the query', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Harness saved={[{ name: 'nightly beat', text: 'severity:high family:exfiltration' }]} />,
      undefined,
      ['/'],
    );

    await openWithPaletteKey(user);
    expect(screen.getByRole('group', { name: 'Saved hunts' })).toBeInTheDocument();
    await user.type(screen.getByRole('combobox'), 'nightly');
    await user.keyboard('{Enter}');

    // A saved hunt is a query, not a window: the console reads it from the URL and
    // applies its own default window (T-408).
    expect(
      await screen.findByText('Hunt screen: severity:high family:exfiltration'),
    ).toBeInTheDocument();
  });

  it('reads the saved hunts when the palette opens, not once at start-up', async () => {
    const user = userEvent.setup();
    const saved: SavedHuntRef[] = [];
    renderWithProviders(<Harness saved={saved} />, undefined, ['/']);

    await openWithPaletteKey(user);
    expect(screen.queryByRole('group', { name: 'Saved hunts' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');

    // A hunt saved a minute ago — from the console, or in another tab — is offered
    // the next time the palette opens.
    saved.push({ name: 'saved later', text: 'host:web-01' });
    await openWithPaletteKey(user);

    expect(screen.getByRole('option', { name: /saved later/ })).toBeInTheDocument();
  });

  it('offers the shortcut reference as an action, and opens it', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await openWithPaletteKey(user);
    await user.type(screen.getByRole('combobox'), 'keyboard shortcuts');
    await user.keyboard('{Enter}');

    expect(await screen.findByTestId('shortcut-table')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Keyboard shortcuts' })).toBeInTheDocument();
  });

  it('opens the shortcut reference on ?', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await user.keyboard('?');

    expect(await screen.findByTestId('shortcut-table')).toBeInTheDocument();
  });

  it('focuses the marked filter on /', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await user.keyboard('/');

    expect(screen.getByRole('textbox', { name: 'A field' })).toHaveFocus();
    expect(screen.queryByRole('listbox', { name: 'Commands' })).not.toBeInTheDocument();
  });

  it('leaves a keystroke in a field to the field', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);
    const field = screen.getByRole('textbox', { name: 'A field' });

    await user.click(field);
    await user.keyboard('?/j');

    // `/` and `?` are text here, and `j` is not a queue step: the field owns all
    // three, which is the rule that keeps a shortcut from eating a query.
    expect(field).toHaveValue('?/j');
    expect(screen.queryByTestId('shortcut-table')).not.toBeInTheDocument();
  });

  it('switches the theme from the palette', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness saved={[]} />);

    await openWithPaletteKey(user);
    const before = document.documentElement.getAttribute('data-theme');
    await user.type(screen.getByRole('combobox'), 'theme');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(document.documentElement.getAttribute('data-theme')).not.toBe(before);
    });
  });

  it('renders the shell without the palette when nothing is open', () => {
    renderWithProviders(<Harness saved={[]} />);

    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('throws rather than rendering a dead search control outside the provider', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    expect(() => renderWithProviders(<Shell />)).toThrow(/CommandProvider/);
    error.mockRestore();
  });
});
