/**
 * Saved and recent hunts: a small menu, kept in this browser only.
 *
 * The menu says *where* the list lives ("in this browser") rather than calling it a
 * saved view: the store is `localStorage` (see `saved.ts`), so a hunt saved on an
 * analyst's laptop is not on their colleague's, and a screen that implied otherwise
 * would have them hunting for a query that was never saved anywhere shared. That is
 * also why the per-user key is the token's unverified subject: it is a namespacing
 * convenience, not a boundary, and the notice makes the limit visible instead of
 * pretending the namespace is security.
 */
import { useState } from 'react';

import { Button } from '../../../components/ui';
import type { RecentHunt, SavedHunt } from '../saved';

export interface SavedHuntsProps {
  saved: readonly SavedHunt[];
  recent: readonly RecentHunt[];
  /** Run a stored query, exactly as it was stored. */
  onLoad: (text: string) => void;
  /** Save the text currently in the box under a name. */
  onSave: (name: string) => void;
  /** Forget one saved hunt. */
  onForget: (name: string) => void;
  disabled?: boolean;
}

export function SavedHunts({
  saved,
  recent,
  onLoad,
  onSave,
  onForget,
  disabled = false,
}: SavedHuntsProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Button
        variant="secondary"
        size="sm"
        aria-expanded={open}
        onClick={() => {
          setOpen((current) => !current);
        }}
        disabled={disabled}
      >
        Saved hunts ({saved.length})
      </Button>
      {open ? (
        <div className="flex flex-col gap-2 rounded-card border border-line bg-surface p-2">
          <p className="text-caption text-muted">
            Saved and recent hunts live in this browser only. They are not shared with anyone else,
            and clearing site data removes them.
          </p>
          {saved.length === 0 ? (
            <p className="text-body-sm text-muted">No saved hunts yet.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {saved.map((record) => (
                <li key={record.name} className="flex items-center gap-2">
                  <button
                    type="button"
                    className="font-mono text-body-sm text-accent underline-offset-2 hover:underline"
                    onClick={() => {
                      onLoad(record.text);
                      setOpen(false);
                    }}
                  >
                    {record.name}
                  </button>
                  <Button variant="ghost" size="sm" onClick={() => onForget(record.name)}>
                    Forget
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {recent.length === 0 ? null : (
            <>
              <p className="text-caption text-muted">Recent</p>
              <ul className="flex flex-col gap-1">
                {recent.map((record) => (
                  <li key={record.text}>
                    <button
                      type="button"
                      className="font-mono text-caption text-muted underline-offset-2 hover:underline"
                      onClick={() => {
                        onLoad(record.text);
                        setOpen(false);
                      }}
                    >
                      {record.text}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : null}
      <form
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() === '') return;
          onSave(name.trim());
          setName('');
        }}
      >
        <label className="text-caption text-muted" htmlFor="hunt-save-name">
          Save as
        </label>
        <input
          id="hunt-save-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={disabled}
          className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
        />
        <Button
          variant="secondary"
          size="sm"
          type="submit"
          disabled={disabled || name.trim() === ''}
        >
          Save
        </Button>
      </form>
    </div>
  );
}
