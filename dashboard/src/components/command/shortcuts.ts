/**
 * The documented shortcut set (design.md §9: "a documented shortcut set (`⌘K`,
 * `j`/`k`, `Enter`, `1`/`2`/`3`, `Esc`, `/`) with an in-app shortcut reference").
 *
 * **The table is the reference.** `shortcutTable` is what the in-app dialog
 * renders, so a shortcut cannot work without being documented and cannot be
 * documented without existing — the failure this prevents is a reference that lists
 * a key nothing listens for, which teaches an operator to distrust the whole list.
 * `?` is the one addition: a reference that cannot be opened from the keyboard is
 * not much of a keyboard reference.
 *
 * The *keys* are the reference; what each key means to a handler is decided in
 * `lib/keyboard.ts` (`paletteIntent`, `listStepIntent`, ...), because the triage
 * screen reads `j`/`k` and the palette reads `⌘K`, and the two must not disagree
 * about what a field's keystroke is.
 */
export interface Shortcut {
  /** The keys as they are printed, e.g. `⌘K`, `j / k`, `1 / 2 / 3`. */
  readonly keys: string;
  /** What it does, in the imperative. */
  readonly label: string;
  /** Where it applies, so a key that does nothing on this screen is not a surprise. */
  readonly where: string;
}

/**
 * Every shortcut this build implements, in the order an operator meets them.
 *
 * `mac` selects the palette's spelling rather than showing both: the label has to
 * match the keyboard in front of the operator, and `Ctrl` on a Mac keyboard is a
 * key they do not have.
 */
export function shortcutTable(mac: boolean): readonly Shortcut[] {
  return [
    { keys: mac ? '\u2318K' : 'Ctrl+K', label: 'Open the command palette', where: 'Anywhere' },
    { keys: '?', label: 'Show this shortcut list', where: 'Anywhere' },
    { keys: '/', label: 'Focus the screen’s filter', where: 'Screens with a filter' },
    { keys: 'j / k', label: 'Open the next or previous alert', where: 'Alerts' },
    {
      keys: 'Enter',
      label: 'Follow the focused link or run the selection',
      where: 'Links, the palette',
    },
    {
      keys: '1 / 2 / 3',
      label: 'Record a verdict on the open alert',
      where: 'Alerts, with one open',
    },
    { keys: 'Esc', label: 'Close the palette or a dialog', where: 'An open dialog' },
  ];
}
