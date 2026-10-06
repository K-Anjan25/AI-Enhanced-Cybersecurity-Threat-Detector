/**
 * The global shortcut listener (T-411).
 *
 * One listener on `window`, installed by the provider, for the three keys that
 * belong to the application rather than to a screen:
 *
 *   * `⌘K` / `Ctrl+K` opens the palette — and toggles it, because pressing the key
 *     that opened a dialog is the first thing an operator tries when they want it
 *     gone;
 *   * `?` opens the shortcut reference;
 *   * `/` focuses the screen's marked filter, if it has one.
 *
 * The screen's own keys are deliberately *not* here: `j`/`k` and `1`/`2`/`3` mean
 * something about the alerts on screen, and a global handler for them would have to
 * know which screen is mounted. `j`/`k` live in the triage feature, using the same
 * `listStepIntent` this module documents.
 *
 * The listener is on `window` rather than on a container because the shell is not an
 * ancestor of every keystroke's target in the way a menu is: the operator may have
 * focus anywhere on the page, including inside a table, and the shortcut still has
 * to work.
 */
import { useCallback, useEffect } from 'react';

import { filterIntent, firstFilterField, helpIntent, paletteIntent } from '../../lib/keyboard';

export interface GlobalShortcutActions {
  /** Open or close the palette. */
  onPalette: () => void;
  /** Open the shortcut reference. */
  onShortcuts: () => void;
}

export function useGlobalShortcuts({ onPalette, onShortcuts }: GlobalShortcutActions): void {
  const handler = useCallback(
    (event: KeyboardEvent) => {
      if (paletteIntent(event)) {
        // The browser's own Ctrl+K (a search bar in some builds) must not win; this
        // is the one shortcut the app takes ownership of.
        event.preventDefault();
        onPalette();
        return;
      }
      if (helpIntent(event)) {
        event.preventDefault();
        onShortcuts();
        return;
      }
      if (filterIntent(event)) {
        const field = firstFilterField();
        // A screen with no filter leaves `/` alone rather than swallowing it: the
        // reference says the shortcut applies where a filter exists, and a key that
        // does nothing quietly is better than one that does nothing loudly.
        if (field === null) return;
        event.preventDefault();
        field.focus();
        if (field instanceof HTMLInputElement) field.select();
      }
    },
    [onPalette, onShortcuts],
  );

  useEffect(() => {
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handler]);
}
