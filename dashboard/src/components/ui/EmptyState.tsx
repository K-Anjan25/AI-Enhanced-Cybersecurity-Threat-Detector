/**
 * EmptyState — R-29 / design.md §8.1: "Say what is empty and what to do: 'No open
 * critical alerts in the last 24 h.' + a link to widen the filter. Never a blank
 * panel."
 *
 * The primitive therefore requires a `title` that names what is empty, and takes
 * an optional action: an empty panel with no next step is the failure mode the rule
 * exists to prevent. It is a `role="status"` region so an emptied panel announces
 * itself rather than leaving a screen reader on a silent page.
 */
import { Inbox } from 'lucide-react';
import { type ReactNode } from 'react';

export interface EmptyStateProps {
  /** What is empty, in the operator's words. Required — see the rule above. */
  title: string;
  /** What to do about it, or why it is empty. */
  description?: string;
  /** A control that widens the filter or creates the thing. */
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div role="status" className="flex flex-col items-center gap-2 px-6 py-8 text-center">
      <Inbox aria-hidden="true" className="size-icon-md text-muted" />
      <p className="text-body font-semibold text-ink">{title}</p>
      {description === undefined ? null : <p className="text-body-sm text-muted">{description}</p>}
      {action === undefined ? null : <div className="mt-2">{action}</div>}
    </div>
  );
}
