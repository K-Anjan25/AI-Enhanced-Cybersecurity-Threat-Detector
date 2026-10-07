/**
 * The in-app shortcut reference (design.md §9: "a documented shortcut set ... with
 * an in-app shortcut reference").
 *
 * It renders `shortcutTable`, and that is the point: the list on screen and the
 * list of keys the code listens for are the same list, so the reference cannot
 * drift from the behaviour. It is a real `<table>` rather than a definition list
 * because each row has three fields an operator scans by column — the key, what it
 * does, and where it applies — and because a table's headers are what a screen
 * reader announces with every cell (`scope="col"`, §9).
 *
 * **`where` is the column that keeps the reference honest.** `1`/`2`/`3` do nothing
 * on the overview screen, and a reference that hid that would have an operator
 * pressing keys and concluding the dashboard is broken. Saying which screen a
 * shortcut belongs to is the difference between a list and a promise.
 */
import { Modal } from '../ui';
import type { Shortcut } from './shortcuts';

export interface ShortcutReferenceProps {
  open: boolean;
  shortcuts: readonly Shortcut[];
  onClose: () => void;
}

export function ShortcutReference({ open, shortcuts, onClose }: ShortcutReferenceProps) {
  return (
    <Modal open={open} title="Keyboard shortcuts" onClose={onClose}>
      <p className="text-body-sm text-muted">
        Everything in the dashboard is reachable and operable from the keyboard. These are the
        shortcuts it adds on top of ordinary Tab and Enter navigation.
      </p>
      <table className="mt-4 w-full border-collapse text-body">
        <caption className="sr-only">
          Keyboard shortcuts, what each does, and where it applies
        </caption>
        <thead>
          <tr className="border-b border-line text-caption uppercase tracking-wide text-muted">
            <th scope="col" className="px-2 py-1 text-left">
              Keys
            </th>
            <th scope="col" className="px-2 py-1 text-left">
              Action
            </th>
            <th scope="col" className="px-2 py-1 text-left">
              Where
            </th>
          </tr>
        </thead>
        <tbody>
          {shortcuts.map((shortcut) => (
            <tr key={shortcut.keys} className="border-b border-line">
              <td className="px-2 py-1">
                <kbd className="rounded-input border border-line bg-base px-2 py-1 font-mono text-caption text-ink">
                  {shortcut.keys}
                </kbd>
              </td>
              <td className="px-2 py-1 text-ink">{shortcut.label}</td>
              <td className="px-2 py-1 text-body-sm text-muted">{shortcut.where}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Modal>
  );
}
