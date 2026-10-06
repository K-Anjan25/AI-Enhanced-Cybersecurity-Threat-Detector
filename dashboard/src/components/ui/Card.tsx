/**
 * Card / Panel — design.md §6: "titled container with optional actions slot and a
 * built-in loading/empty/error state".
 *
 * The state is a prop rather than something the caller assembles, and that is the
 * point: R-29 requires every surface to be able to say loading, empty and error,
 * and a panel that forgets one of them renders as a blank rectangle that looks
 * like a working widget with no data. With `state` as a discriminator the panel
 * *cannot* be blank — each state has a rendering, and `children` only appears in
 * `ready`.
 *
 * Elevation follows §5.5: flat by default, so a card is a border and a surface, not
 * a shadow. Shadows are reserved for overlays (see `Modal`).
 */
import { type ReactNode } from 'react';

import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { Skeleton } from './Skeleton';

export type CardState = 'ready' | 'loading' | 'empty' | 'error';

export interface CardProps {
  /** The panel's title, rendered as a real heading so it is navigable. */
  title: string;
  /** Controls for the panel's own header — a range picker, a refresh, a menu. */
  actions?: ReactNode;
  /** Which of R-29's states the panel is in. Defaults to `ready`. */
  state?: CardState;
  /** What to say when `state` is `empty`. Falls back to a neutral sentence. */
  empty?: { title: string; description?: string; action?: ReactNode };
  /** What to say when `state` is `error`. Falls back to a plain failure message. */
  error?: { message: string; detail?: string; action?: ReactNode };
  /** How many skeleton bars a loading card draws, to match its final layout. */
  loadingLines?: number;
  children?: ReactNode;
}

export function Card({
  title,
  actions,
  state = 'ready',
  empty,
  error,
  loadingLines = 3,
  children,
}: CardProps) {
  return (
    <section aria-labelledby={headingId(title)} className="rounded-card border border-line bg-base">
      <header className="flex items-center justify-between gap-4 border-b border-line px-4 py-2">
        <h2 id={headingId(title)} className="text-h2">
          {title}
        </h2>
        {actions === undefined ? null : <div className="flex items-center gap-2">{actions}</div>}
      </header>
      <div className="p-4">
        {state === 'loading' ? (
          <Skeleton lines={loadingLines} label={`${title} is loading`} />
        ) : null}
        {state === 'empty' ? (
          <EmptyState
            title={empty?.title ?? 'Nothing to show'}
            {...(empty?.description === undefined ? {} : { description: empty.description })}
            {...(empty?.action === undefined ? {} : { action: empty.action })}
          />
        ) : null}
        {state === 'error' ? (
          <ErrorState
            message={error?.message ?? 'This panel could not be loaded'}
            {...(error?.detail === undefined ? {} : { detail: error.detail })}
            {...(error?.action === undefined ? {} : { action: error.action })}
          />
        ) : null}
        {state === 'ready' ? children : null}
      </div>
    </section>
  );
}

/** A stable, readable id for the heading a panel is labelled by. */
function headingId(title: string): string {
  return `panel-${title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`;
}
