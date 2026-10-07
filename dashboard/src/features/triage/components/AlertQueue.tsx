/**
 * The queue — the list half of "list + detail" (design.md §3, FR-51).
 *
 * It is a list of buttons rather than a `DataTable` on purpose. The rows are
 * navigation, not data: every one of them is a link to an alert, and the whole row
 * has to be reachable and activatable from the keyboard. A table's cells are not,
 * and wrapping a virtualised row in a click handler is how a table ends up
 * mouse-only. `aria-current` marks the open alert, which is what tells a screen
 * reader which row the detail beside it belongs to.
 *
 * The panel is honest about its bounds: one page of the newest alerts in a fixed
 * window, and when the API reports more, it says so instead of presenting the page
 * as the whole queue.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  isSeverity,
  SeverityPill,
  Skeleton,
} from '../../../components/ui';
import type { AlertRow } from '../../../api/alerts';
import { formatInstant, formatSince } from '../../../lib/format';
import { alertHref } from '../links';
import { queueSummary } from '../view';

export interface AlertQueueProps {
  rows: readonly AlertRow[];
  status: 'pending' | 'error' | 'success';
  /** True when the API answered with a cursor, i.e. the page is not the queue. */
  hasMore: boolean;
  windowHours: number;
  /** The open alert's id, or `null` on the list route. */
  selectedId: number | null;
  /** The ticking clock the ages are rendered against. */
  now: number;
  /** Controls for the panel's header — the batch export (T-415, FR-23). */
  actions?: ReactNode;
  onRetry?: (() => void) | undefined;
}

export function AlertQueue({
  rows,
  status,
  hasMore,
  windowHours,
  selectedId,
  now,
  actions,
  onRetry,
}: AlertQueueProps) {
  const summary = queueSummary(rows.length, hasMore, windowHours);

  return (
    <Card title="Alert queue" {...(actions === undefined ? {} : { actions })}>
      <p className="text-body-sm text-muted">{summary.text}</p>

      {status === 'error' ? (
        <div className="mt-3">
          <ErrorState
            message="The queue could not be loaded"
            detail="The rows below are the last successful read, if there was one."
            {...(onRetry === undefined
              ? {}
              : {
                  action: (
                    <Button variant="secondary" onClick={onRetry}>
                      Retry
                    </Button>
                  ),
                })}
          />
        </div>
      ) : null}

      {status === 'pending' && rows.length === 0 ? (
        <Skeleton lines={6} label="Alert queue is loading" />
      ) : null}

      {status !== 'pending' && rows.length === 0 ? (
        <EmptyState
          title="No alerts in the window"
          description={`Nothing has been raised in the last ${String(windowHours)} h.`}
        />
      ) : null}

      {rows.length === 0 ? null : (
        <ul aria-label="Alerts" className="mt-3 flex max-h-[60vh] flex-col gap-1 overflow-y-auto">
          {rows.map((row) => {
            const current = row.id === selectedId;
            return (
              <li key={`${String(row.id)}-${row.created_at}`}>
                <Link
                  to={alertHref(row)}
                  aria-current={current ? 'true' : undefined}
                  className={`flex items-center gap-2 border px-2 py-2 text-body-sm hover:border-accent ${
                    current ? 'border-accent' : 'border-line'
                  }`}
                >
                  <span className="font-mono text-muted">{formatInstant(row.created_at)}</span>
                  {isSeverity(row.severity) ? (
                    <SeverityPill severity={row.severity} />
                  ) : (
                    <span className="text-ink">{row.severity}</span>
                  )}
                  <span className="truncate text-ink">{row.family}</span>
                  <span className="ml-auto font-mono text-muted">{row.score.toFixed(2)}</span>
                  <span className="text-muted">{formatSince(row.created_at, now)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
