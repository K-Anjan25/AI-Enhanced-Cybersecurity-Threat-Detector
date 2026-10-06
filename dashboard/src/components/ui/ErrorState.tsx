/**
 * ErrorState — R-29 / design.md §8.1: "What failed, whether it is retrying, and a
 * Retry action. Never a raw stack trace in the UI."
 *
 * Three things follow from that sentence, and they are enforced here rather than
 * left to callers. The message renders as text (R-28: telemetry content is
 * untrusted and must never become HTML). `retrying` is *said*, in words — a
 * spinner would leave the analyst guessing whether anything is happening. And
 * there is no slot for a stack trace or an error object: the props take human
 * copy, so a trace cannot reach the screen out of habit.
 */
import { CircleAlert } from 'lucide-react';
import { type ReactNode } from 'react';

export interface ErrorStateProps {
  /** What failed, in the operator's words. */
  message: string;
  /** What it means for the data on screen — "showing the last successful load". */
  detail?: string;
  /** True while a retry is in flight, so the state is stated rather than implied. */
  retrying?: boolean;
  /** A Retry control. Omitted only when retrying is impossible or meaningless. */
  action?: ReactNode;
}

export function ErrorState({ message, detail, retrying = false, action }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 border border-line px-6 py-4">
      <p className="flex items-center gap-2 text-body font-semibold text-severityText-critical">
        <CircleAlert aria-hidden="true" className="size-icon-md" />
        {message}
      </p>
      {detail === undefined ? null : <p className="text-body-sm text-muted">{detail}</p>}
      {retrying ? <p className="text-body-sm text-muted">Retrying…</p> : null}
      {action === undefined ? null : <div>{action}</div>}
    </div>
  );
}
