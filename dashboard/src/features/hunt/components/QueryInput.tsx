/**
 * The hunt query box: an input with autocomplete over the fields and their values
 * (design.md §4.6, "operator hints" included).
 *
 * It is a `combobox` in the ARIA sense — a text field that owns a listbox — so it is
 * reachable and readable by keyboard and by screen reader, and so the tests can find
 * it by role rather than by class. Four things about the interaction are deliberate:
 *
 *   * **The suggestion list is not a filter on what you may type.** An analyst can
 *     always type a term the console has no value list for (`family:exfiltration`),
 *     and the list stays out of the way until asked for.
 *   * **A field this build cannot search is *offered as a refusal*.** Typing `src`
 *     suggests `src_ip:` with the reason attached, rather than nothing at all: a
 *     console that silently has no answer teaches an analyst that `src_ip` is a
 *     spelling mistake.
 *   * **Enter runs the hunt; only ArrowDown puts a suggestion in its way.** Nothing
 *     is highlighted until the analyst arrows into the list, so typing a complete
 *     query and pressing Enter always searches — an Enter that silently replaced the
 *     text with a suggestion would be an analyst losing a query to an autocomplete.
 *     Inside the list, Enter accepts the highlighted suggestion and Escape leaves.
 *   * **The errors are rendered here, not after the run.** An unreadable term is
 *     refused before it is sent, so nothing shows a result set the analyst did not
 *     ask for (see `query.ts` for why an unknown field is refused).
 */
import { useId, useRef, useState } from 'react';

import { FILTER_MARK } from '../../../lib/keyboard';
import { huntCompletions, type HuntError, type HuntSuggestion } from '../query';

export interface QueryInputProps {
  value: string;
  onChange: (value: string) => void;
  /** Run the hunt. Only ever called when the parse has no errors. */
  onRun: () => void;
  /** The terms that could not be read, rendered beneath the field. */
  errors: readonly HuntError[];
  disabled?: boolean;
}

export function QueryInput({ value, onChange, onRun, errors, disabled = false }: QueryInputProps) {
  const [open, setOpen] = useState(false);
  // `null` is "the list is open but nothing is highlighted" — the state in which
  // Enter still means *run*, which is the whole point of not highlighting by default.
  const [active, setActive] = useState<number | null>(null);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const caret = input.current?.selectionStart ?? value.length;
  // Computed whether or not the list is showing, so the *first* ArrowDown can both
  // open the list and highlight its first entry — an arrow key that only revealed a
  // list would make every keyboard completion cost two presses.
  const suggestions: HuntSuggestion[] = huntCompletions(value, caret);

  const accept = (suggestion: HuntSuggestion): void => {
    const upToCaret = value.slice(0, caret);
    const tokenStart = upToCaret.lastIndexOf(' ') + 1;
    const next = `${value.slice(0, tokenStart)}${suggestion.value} ${value.slice(caret)}`;
    onChange(next);
    setOpen(false);
    setActive(null);
    input.current?.focus();
  };

  return (
    <div className="flex flex-col gap-1">
      <label className="text-caption text-muted" htmlFor={`${listId}-input`}>
        Query
      </label>
      <div className="relative flex flex-wrap items-center gap-2">
        <input
          id={`${listId}-input`}
          // `/` focuses this field: it is the screen's filter, and the marker is how
          // the global shortcut finds it (T-411).
          {...FILTER_MARK}
          ref={input}
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active === null ? undefined : `${listId}-option-${String(active)}`}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          value={value}
          placeholder="severity:high,critical family:exfiltration min_score:0.8"
          onChange={(event) => {
            onChange(event.target.value);
            // Typing re-opens the list and *un-highlights* it: the suggestion list is
            // an offer, and Enter belongs to the analyst's own query until they
            // arrow into the list.
            setActive(null);
            setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              setOpen(true);
              if (suggestions.length === 0) return;
              event.preventDefault();
              const step = event.key === 'ArrowDown' ? 1 : -1;
              setActive((current) => {
                const from = current ?? (step === 1 ? -1 : 0);
                return (from + step + suggestions.length) % suggestions.length;
              });
              return;
            }
            if (event.key === 'Escape') {
              setOpen(false);
              return;
            }
            if (event.key === 'Enter') {
              event.preventDefault();
              const chosen = active === null ? undefined : suggestions[active];
              if (chosen !== undefined) accept(chosen);
              else if (errors.length === 0) onRun();
            }
          }}
          onBlur={() => {
            // Blur closes the list, but a click on a suggestion fires this first, so
            // the list is closed on the next tick rather than swallowed by it.
            window.setTimeout(() => {
              setOpen(false);
            }, 0);
          }}
          className="h-9 w-full max-w-2xl rounded-input border border-line bg-surface px-3 font-mono text-body-sm text-ink"
        />
        {errors.length === 0 ? null : (
          <p className="text-caption text-severityText-critical">
            {errors.length === 1
              ? errors[0]?.reason
              : `${String(errors.length)} terms could not be read: ${errors
                  .map((error) => error.token)
                  .join(', ')}`}
          </p>
        )}
      </div>
      {open && suggestions.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Query suggestions"
          className="max-w-2xl rounded-card border border-line bg-surface p-1 shadow-overlay"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.value}
              id={`${listId}-option-${String(index)}`}
              role="option"
              aria-selected={index === active}
              className={`flex cursor-pointer items-baseline justify-between gap-4 rounded-input px-2 py-1 text-body-sm ${
                index === active ? 'bg-base text-ink' : 'text-muted'
              }`}
              onMouseDown={(event) => {
                event.preventDefault();
                accept(suggestion);
              }}
              onMouseEnter={() => {
                setActive(index);
              }}
            >
              <span className="font-mono">{suggestion.value}</span>
              <span className="text-caption text-muted">
                {suggestion.kind === 'unsearchable'
                  ? `not searchable — ${suggestion.detail}`
                  : suggestion.detail}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
