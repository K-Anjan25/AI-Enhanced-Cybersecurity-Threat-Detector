import { describe, expect, it, vi } from 'vitest';

import { commandDomId, filterCommands, groupCommands, moveSelection, type Command } from './model';

function command(over: Partial<Command> = {}): Command {
  return {
    id: 'nav:/alerts',
    label: 'Alerts',
    group: 'Navigation',
    run: vi.fn(),
    ...over,
  };
}

describe('command filtering', () => {
  const commands = [
    command({ id: 'nav:/', label: 'Overview' }),
    command({ id: 'nav:/alerts', label: 'Alerts' }),
    command({ id: 'nav:/admin/keys', label: 'API keys', hint: '/admin/keys' }),
    command({ id: 'hunt:nightly', label: 'nightly beat', group: 'Saved hunts' }),
    command({ id: 'action:theme', label: 'Switch theme', group: 'Actions' }),
  ];

  it('keeps everything, in order, for an empty query', () => {
    expect(filterCommands(commands, '   ')).toEqual(commands);
  });

  it('matches case-insensitively on the label', () => {
    expect(filterCommands(commands, 'ALERT').map((entry) => entry.id)).toEqual(['nav:/alerts']);
  });

  it('answers to the words an operator uses, not only the label', () => {
    expect(filterCommands(commands, 'keys').map((entry) => entry.id)).toEqual(['nav:/admin/keys']);
  });

  it('ranks an exact label above a prefix and a prefix above a substring', () => {
    const ranked = filterCommands(
      [
        command({ id: 'a', label: 'One alert arrived' }),
        command({ id: 'b', label: 'Alert' }),
        command({ id: 'c', label: 'Alerts' }),
      ],
      'alert',
    );

    expect(ranked.map((entry) => entry.id)).toEqual(['b', 'c', 'a']);
  });

  it('keeps the sections in place, whatever the query', () => {
    // A palette whose sections reshuffled as you typed would move the row under the
    // arrows between keystrokes.
    const ranked = filterCommands(commands, 'e');

    expect(ranked.map((entry) => entry.group)).toEqual([
      'Navigation',
      'Navigation',
      'Navigation',
      'Saved hunts',
      'Actions',
    ]);
  });

  it('finds nothing when nothing matches', () => {
    expect(filterCommands(commands, 'zzz')).toEqual([]);
  });
});

describe('command selection', () => {
  it('wraps at both ends', () => {
    expect(moveSelection(2, 1, 3)).toBe(0);
    expect(moveSelection(0, -1, 3)).toBe(2);
  });

  it('is zero when there is nothing to select', () => {
    expect(moveSelection(3, 1, 0)).toBe(0);
  });
});

describe('command rendering helpers', () => {
  it('groups consecutive runs of a section', () => {
    const groups = groupCommands([
      command({ id: 'a', group: 'Navigation' }),
      command({ id: 'b', group: 'Navigation' }),
      command({ id: 'c', group: 'Actions' }),
    ]);

    expect(groups.map((entry) => entry.group)).toEqual(['Navigation', 'Actions']);
    expect(groups[0]?.items.map((entry) => entry.id)).toEqual(['a', 'b']);
  });

  it('builds an id fit for aria-activedescendant', () => {
    expect(commandDomId('r1', 'nav:/admin/keys')).toBe('r1-nav--admin-keys');
  });
});
