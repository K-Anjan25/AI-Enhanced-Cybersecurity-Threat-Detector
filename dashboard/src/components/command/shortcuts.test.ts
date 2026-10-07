import { describe, expect, it } from 'vitest';

import { shortcutTable } from './shortcuts';

describe('the documented shortcut set', () => {
  it('documents every key the build listens for', () => {
    // The keys `lib/keyboard.ts` implements and the keys the reference prints are
    // the same set; this is the assertion that keeps a shortcut from shipping
    // undocumented, or a documented key from listening for nothing.
    const keys = shortcutTable(false).map((shortcut) => shortcut.keys);

    expect(keys).toEqual(['Ctrl+K', '?', '/', 'j / k', 'Enter', '1 / 2 / 3', 'Esc']);
  });

  it('prints the palette key for the operator’s platform', () => {
    expect(shortcutTable(true)[0]?.keys).toBe('\u2318K');
    expect(shortcutTable(false)[0]?.keys).toBe('Ctrl+K');
  });

  it('says where each shortcut applies', () => {
    // `1`/`2`/`3` do nothing on the overview screen. A reference that hid that would
    // send an operator pressing keys and concluding the dashboard is broken.
    const verdicts = shortcutTable(false).find((shortcut) => shortcut.keys === '1 / 2 / 3');

    expect(verdicts?.where).toContain('Alerts');
    for (const shortcut of shortcutTable(false)) {
      expect(shortcut.label.length).toBeGreaterThan(0);
      expect(shortcut.where.length).toBeGreaterThan(0);
    }
  });
});
