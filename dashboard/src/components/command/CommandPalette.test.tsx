import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { expectAccessible } from '../../test/axe';
import { renderWithProviders } from '../../test/query';
import { CommandPalette } from './CommandPalette';
import type { Command } from './model';

/**
 * The four commands these tests run against.
 *
 * `overrides` replaces a command's `run` by id — a command is a readonly object, so
 * a test that needs to observe *when* one runs gets its own function here rather
 * than assigning to the list.
 */
function build(overrides: Record<string, Command['run']> = {}): Command[] {
  const commands: Command[] = [
    { id: 'nav:/alerts', label: 'Alerts', hint: '/alerts', group: 'Navigation', run: vi.fn() },
    {
      id: 'nav:/admin/audit',
      label: 'Audit log',
      hint: '/admin/audit',
      group: 'Navigation',
      run: vi.fn(),
    },
    {
      id: 'hunt:nightly',
      label: 'nightly beat',
      hint: 'severity:high family:exfiltration',
      group: 'Saved hunts',
      run: vi.fn(),
    },
    {
      id: 'action:shortcuts',
      label: 'Keyboard shortcuts',
      hint: '?',
      group: 'Actions',
      run: vi.fn(),
    },
  ];
  return commands.map((command) => ({ ...command, run: overrides[command.id] ?? command.run }));
}

function open(commands: Command[], onClose = vi.fn()) {
  const view = renderWithProviders(<CommandPalette open commands={commands} onClose={onClose} />);
  return { ...view, onClose };
}

describe('the command palette', () => {
  it('lists every command under its section heading', () => {
    open(build());

    expect(screen.getByRole('listbox', { name: 'Commands' })).toBeInTheDocument();
    expect(screen.getAllByRole('option')).toHaveLength(4);
    for (const section of ['Navigation', 'Saved hunts', 'Actions']) {
      expect(screen.getByRole('group', { name: section })).toBeInTheDocument();
    }
  });

  it('filters as the operator types, and keeps the section with the match', async () => {
    const user = userEvent.setup();
    open(build());

    await user.type(screen.getByRole('combobox'), 'audit');

    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Audit log/admin/audit',
    ]);
    expect(screen.queryByRole('group', { name: 'Saved hunts' })).not.toBeInTheDocument();
  });

  it('says so when nothing matches, rather than rendering a blank list', async () => {
    const user = userEvent.setup();
    open(build());

    await user.type(screen.getByRole('combobox'), 'zzz');

    expect(screen.getByTestId('palette-empty')).toHaveTextContent('Nothing matches “zzz”');
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });

  it('moves the selection with the arrows and wraps at the ends', async () => {
    const user = userEvent.setup();
    open(build());
    const input = screen.getByRole('combobox');

    expect(screen.getByRole('option', { name: /Alerts/ })).toHaveAttribute('aria-selected', 'true');

    await user.type(input, '{ArrowDown}');
    expect(screen.getByRole('option', { name: /Audit log/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // The input owns the focus; the highlighted row is named by the combobox.
    expect(input).toHaveAttribute(
      'aria-activedescendant',
      screen.getByRole('option', { name: /Audit log/ }).id,
    );

    await user.type(input, '{ArrowUp}{ArrowUp}');
    expect(screen.getByRole('option', { name: /Keyboard shortcuts/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('resets the selection when the filter changes length', async () => {
    const user = userEvent.setup();
    open(build());
    const input = screen.getByRole('combobox');

    await user.type(input, '{ArrowDown}{ArrowDown}');
    await user.type(input, 'audit');

    expect(screen.getByRole('option', { name: /Audit log/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('runs the highlighted command on Enter, closing first', async () => {
    const user = userEvent.setup();
    const order: string[] = [];
    const onClose = vi.fn(() => {
      order.push('close');
    });
    const commands = build({
      'nav:/admin/audit': () => {
        order.push('run');
      },
    });
    open(commands, onClose);

    await user.type(screen.getByRole('combobox'), '{ArrowDown}{Enter}');

    expect(order).toEqual(['close', 'run']);
  });

  it('runs the command that was clicked', async () => {
    const user = userEvent.setup();
    const commands = build();
    open(commands);

    await user.click(screen.getByRole('option', { name: /nightly beat/ }));

    expect(commands[2]!.run).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape without running anything', async () => {
    const user = userEvent.setup();
    const commands = build();
    const { onClose } = open(commands);

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(1);
    for (const entry of commands) expect(entry.run).not.toHaveBeenCalled();
  });

  it('opens empty every time, whatever was typed last time', async () => {
    const user = userEvent.setup();
    const commands = build();
    const view = renderWithProviders(<CommandPalette open commands={commands} onClose={vi.fn()} />);
    await user.type(screen.getByRole('combobox'), 'nightly');
    expect(screen.getAllByRole('option')).toHaveLength(1);

    view.rerender(<CommandPalette open={false} commands={commands} onClose={vi.fn()} />);
    view.rerender(<CommandPalette open commands={commands} onClose={vi.fn()} />);

    // A palette that remembered the query would filter its list by something the
    // operator cannot see.
    expect(screen.getByRole('combobox')).toHaveValue('');
    expect(screen.getAllByRole('option')).toHaveLength(4);
  });

  it('has no serious accessibility violations', async () => {
    const { container } = open(build());

    await expectAccessible(container as HTMLElement);
  });
});
