/**
 * Keyboard conventions the whole dashboard shares (design.md §9: "every action
 * reachable and operable by keyboard ... a documented shortcut set with an in-app
 * shortcut reference").
 *
 * This lives in `lib` because three layers need the same answers and a second copy
 * of any of them is how two screens end up disagreeing about what a keystroke
 * means: the shell's top bar prints the palette's key label, the palette's own
 * handler reads it, and the triage screen asks the same "is this keystroke the
 * field's or mine?" question its verdict shortcuts have always asked.
 *
 * Three rules are encoded here rather than in each handler:
 *
 *   * **A keypress in a text field belongs to the field.** `isTypingTarget` is the
 *     one implementation of that; a shortcut that fires while an analyst types a
 *     query is the bug that makes shortcuts dangerous.
 *   * **A modified keystroke is not a shortcut.** Cmd/Ctrl/Alt belong to the
 *     browser and the OS, so the intent functions refuse them — except for the
 *     palette itself, which is *defined* by the command key.
 *   * **The platform decides what to print.** `⌘K` on macOS and `Ctrl+K`
 *     elsewhere is the same shortcut with two spellings, and the label must match
 *     the keyboard in front of the operator.
 *
 * The four `*Intent` functions are the whole of a keystroke's meaning — the palette,
 * the reference, the filter jump and the queue step — and they are pure, so a
 * decision can be tested with a plain object rather than a rendered DOM. What is
 * *documented* is `shortcutTable` in `components/command`, and the two lists are
 * meant to be read together: this one says what is listened for, that one says what
 * the operator is told.
 */

/** True when the keystroke landed in a control that owns the keyboard. */
export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    target.closest('input, textarea, select, [contenteditable]') !== null
  );
}

/** True on the platforms whose command key prints as `⌘`. */
export function isMacPlatform(platform: string = navigator.platform): boolean {
  return /mac|iphone|ipad|ipod/i.test(platform);
}

/** The palette's key as a label: `⌘K`, or `Ctrl+K` off macOS. */
export function paletteKeyLabel(mac: boolean = isMacPlatform()): string {
  return mac ? '\u2318K' : 'Ctrl+K';
}

/**
 * The palette's key in the `aria-keyshortcuts` spelling.
 *
 * The attribute takes the DOM `KeyboardEvent.key` names rather than the printed
 * label (`Meta+K Control+K`), because that is what assistive technology reads to
 * the operator — `⌘K` is a glyph, not a key name.
 */
export const PALETTE_KEY_SHORTCUTS = 'Meta+K Control+K';

/** The help key's `aria-keyshortcuts` value. */
export const HELP_KEY_SHORTCUTS = '?';

/** Where a screen marks the field `/` should focus. */
export const FILTER_ATTRIBUTE = 'data-shortcut';

/** Selector for that mark. One filter per screen is enough for a focus target. */
export const FILTER_SELECTOR = '[data-shortcut="filter"]';

/**
 * The marker a screen spreads onto its primary filter: `{...FILTER_MARK}`.
 *
 * An object rather than an attribute written out at each call site, because the
 * marker and the selector above have to agree and nothing would fail if they did
 * not — the shortcut would simply stop finding the field.
 */
export const FILTER_MARK = { [FILTER_ATTRIBUTE]: 'filter' } as const;

/** The first marked filter on the page, or `null` when the screen has none. */
export function firstFilterField(root: ParentNode = document): HTMLElement | null {
  return root.querySelector<HTMLElement>(FILTER_SELECTOR);
}

/** True when the keystroke asks for the palette: `⌘K` / `Ctrl+K` and nothing else. */
export function paletteIntent(event: KeyboardEvent): boolean {
  // `shiftKey` is refused on purpose: Ctrl+Shift+K is a browser's own console in
  // Firefox, and a shortcut that fights the browser loses inconsistently.
  return (
    event.key.toLowerCase() === 'k' &&
    (event.metaKey || event.ctrlKey) &&
    !event.altKey &&
    !event.shiftKey
  );
}

/** True when the keystroke asks for the shortcut reference: `?`. */
export function helpIntent(event: KeyboardEvent): boolean {
  return (
    event.key === '?' &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !isTypingTarget(event.target)
  );
}

/** True when the keystroke asks to jump to the screen's filter: `/`. */
export function filterIntent(event: KeyboardEvent): boolean {
  return (
    event.key === '/' &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !event.shiftKey &&
    !isTypingTarget(event.target)
  );
}

/**
 * The step a keystroke asks for in a list: `1` for `j`, `-1` for `k`, `0` for
 * anything else.
 *
 * Exported here rather than in the triage feature because the reference documents
 * `j`/`k` and the triage screen implements them; the key's meaning is one decision.
 * A repeat is refused: holding `j` would otherwise walk the whole queue, opening an
 * alert per frame — the same reason the verdict shortcuts refuse a repeat.
 */
export function listStepIntent(event: KeyboardEvent): -1 | 0 | 1 {
  if (event.repeat || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return 0;
  if (isTypingTarget(event.target)) return 0;
  const key = event.key.toLowerCase();
  if (key === 'j') return 1;
  if (key === 'k') return -1;
  return 0;
}
