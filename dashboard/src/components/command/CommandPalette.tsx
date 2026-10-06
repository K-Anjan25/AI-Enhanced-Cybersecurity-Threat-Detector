/**
 * CommandPalette — design.md §5.5: "`⌘K`; navigates, filters, and runs saved
 * hunts"; §6 lists it as a component, and it is presentational: commands come in
 * as props, and nothing here knows a route or a store.
 *
 * It is a **combobox over a listbox**, which is the ARIA pattern for "type to
 * filter, arrows to choose": focus never leaves the input, and the highlighted row
 * is named by `aria-activedescendant`. That matters for a screen reader — moving
 * focus into the list would take the caret out of the field the operator is typing
 * in, and the row under the arrows would be announced after every keystroke instead
 * of the count of matches.
 *
 * Four behaviours are the ones a palette gets wrong:
 *
 *   * **The query resets on every open.** A palette that remembers last time's
 *     query filters its own list by something the operator cannot see.
 *   * **The selection resets with the query.** Keeping the index while the list
 *     changes length is how Enter runs a command nobody selected.
 *   * **Enter runs the highlighted command, and the palette closes before it
 *     runs**, so the command's own dialog (or the screen it navigates to) opens
 *     with focus in the right place.
 *   * **An empty result says so.** A blank list reads as a broken palette.
 *
 * `Esc` is the Modal's: it closes the dialog and returns focus to whatever opened
 * it (design.md §6).
 */
import { useEffect, useId, useMemo, useState } from 'react';

import { Modal } from '../ui';
import { commandDomId, filterCommands, groupCommands, moveSelection, type Command } from './model';

export interface CommandPaletteProps {
  open: boolean;
  /** Every command this build offers; the filter is applied here. */
  commands: readonly Command[];
  onClose: () => void;
}

export function CommandPalette({ open, commands, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const base = useId();
  const listId = `${base}-list`;

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActive(0);
  }, [open]);

  const matches = useMemo(() => filterCommands(commands, query), [commands, query]);
  const groups = useMemo(() => groupCommands(matches), [matches]);
  // The rendered items lose their position in the flat list, and the arrows move by
  // that position, so the map is what keeps the two in the same order.
  const positions = useMemo(
    () => new Map(matches.map((command, index) => [command.id, index])),
    [matches],
  );
  const selected = matches[active];
  const activeId = selected === undefined ? undefined : commandDomId(base, selected.id);

  const run = (command: Command): void => {
    // Close first: a command that opens a dialog must not do it from under a dialog
    // that is still mounted, and focus has to go back to the trigger before the next
    // thing claims it.
    onClose();
    command.run();
  };

  return (
    <Modal open={open} title="Commands" onClose={onClose}>
      <div className="flex flex-col gap-1">
        <label className="text-caption text-muted" htmlFor={`${base}-input`}>
          Search
        </label>
        <input
          id={`${base}-input`}
          role="combobox"
          aria-expanded
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          autoComplete="off"
          spellCheck={false}
          value={query}
          placeholder="Type to filter — screens, saved hunts, actions"
          onChange={(event) => {
            setQuery(event.target.value);
            // The list just changed length; the old index would point at a
            // different command, or at nothing.
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              setActive((current) => moveSelection(current, 1, matches.length));
            } else if (event.key === 'ArrowUp') {
              event.preventDefault();
              setActive((current) => moveSelection(current, -1, matches.length));
            } else if (event.key === 'Home') {
              event.preventDefault();
              setActive(0);
            } else if (event.key === 'End') {
              event.preventDefault();
              setActive(Math.max(matches.length - 1, 0));
            } else if (event.key === 'Enter') {
              event.preventDefault();
              if (selected !== undefined) run(selected);
            }
          }}
          className="h-8 rounded-input border border-line bg-base px-3 text-body text-ink"
        />
      </div>

      {matches.length === 0 ? (
        <p data-testid="palette-empty" className="mt-4 text-body-sm text-muted">
          Nothing matches “{query.trim()}”. The list filters as you type — clear it to see every
          screen, saved hunt and action.
        </p>
      ) : (
        <div
          id={listId}
          role="listbox"
          aria-label="Commands"
          className="mt-4 flex max-h-[60vh] flex-col gap-4 overflow-y-auto"
        >
          {groups.map(({ group, items }) => {
            const headingId = `${base}-group-${group.replace(/\s+/g, '-').toLowerCase()}`;
            return (
              <div key={group} role="group" aria-labelledby={headingId}>
                <p id={headingId} className="px-2 text-caption uppercase tracking-wide text-muted">
                  {group}
                </p>
                {/* Options are the group's own children, with no list element in
                    between: `option` is required to be owned by a `listbox` or a
                    `group`, and a `ul` in between is a violation axe reports as
                    `aria-required-parent`. */}
                <div className="flex flex-col">
                  {items.map((command) => {
                    const index = positions.get(command.id) ?? 0;
                    const isActive = index === active;
                    return (
                      <button
                        key={command.id}
                        type="button"
                        role="option"
                        aria-selected={isActive}
                        id={commandDomId(base, command.id)}
                        tabIndex={-1}
                        onClick={() => run(command)}
                        onMouseMove={() => setActive(index)}
                        className={`flex w-full flex-col rounded-control border-l-2 px-2 py-1 text-left ${
                          isActive
                            ? 'border-accent bg-surface text-ink'
                            : 'border-transparent text-muted'
                        }`}
                      >
                        <span className="text-body">{command.label}</span>
                        {command.hint === undefined ? null : (
                          <span className="truncate text-caption text-muted">{command.hint}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Modal>
  );
}
