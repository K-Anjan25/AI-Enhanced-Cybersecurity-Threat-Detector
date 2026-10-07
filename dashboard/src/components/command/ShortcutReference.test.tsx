import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { renderWithProviders } from '../../test/query';
import { ShortcutReference } from './ShortcutReference';
import { shortcutTable } from './shortcuts';

describe('the shortcut reference', () => {
  it('renders the documented set as a table with scoped headers', () => {
    renderWithProviders(
      <ShortcutReference open shortcuts={shortcutTable(false)} onClose={vi.fn()} />,
    );

    const table = screen.getByRole('table', { name: /Keyboard shortcuts, what each does/ });
    for (const heading of ['Keys', 'Action', 'Where']) {
      expect(screen.getByRole('columnheader', { name: heading })).toBeInTheDocument();
    }
    // Every documented shortcut is a row: the dialog is the table, so a shortcut
    // cannot be documented without being rendered.
    expect(within(table).getAllByRole('row')).toHaveLength(shortcutTable(false).length + 1);
  });

  it('prints the palette key for the platform it was given', () => {
    renderWithProviders(
      <ShortcutReference open shortcuts={shortcutTable(true)} onClose={vi.fn()} />,
    );

    expect(screen.getByText('\u2318K')).toBeInTheDocument();
    expect(screen.queryByText('Ctrl+K')).not.toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = renderWithProviders(
      <ShortcutReference open shortcuts={shortcutTable(false)} onClose={vi.fn()} />,
    );

    await expectAccessible(container as HTMLElement);
  });
});
