/**
 * Alert triage — `/alerts` and `/alerts/:id` (design.md §4.3, FR-51).
 *
 * The screen is a queue beside a detail, and the acceptance criterion is a
 * property of the pair: *a full triage loop is completable without a mouse*. So
 * the loop is one keyboard journey, with no mouse-only step anywhere in it:
 *
 *   1. Tab into the queue and press Enter — the rows are links, so this is native
 *      behaviour rather than a key handler that has to reimplement it.
 *   2. The detail opens with the verdict bar sticky at the top.
 *   3. Press `1`, `2` or `3` — the bar owns the shortcut, the page owns the write.
 *   4. The verdict is announced in the bar's live region, and "Next alert ▸" is a
 *      link, so Tab then Enter moves on.
 *
 * `j` and `k` (T-411) are the same journey without the Tab: they open the next and
 * previous alert from wherever the analyst's focus is, which is what makes a queue
 * of two hundred alerts survivable. They step the *selection* rather than the focus,
 * so the step is a route change through `stepHref` — the same rule the "Next alert"
 * link uses.
 *
 * Three states on this page are decisions rather than visual details:
 *
 *   * **A route without `created_at` cannot be answered.** The detail is addressed
 *     by `(id, created_at)` (D-030), so the page says which part of the address is
 *     missing and links back to the queue instead of firing a request that must
 *     fail.
 *   * **A failed verdict write is stated where the buttons are** (R-58: the message
 *     names the kind of failure and never a URL or a response body).
 *   * **The queue's own failure does not blank the detail.** The two reads are
 *     separate; an analyst looking at an open alert keeps looking at it while the
 *     list behind them is broken, and says so.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { Card, EmptyState, ErrorState, Skeleton } from '../../../components/ui';
import { formatSince } from '../../../lib/format';
import { useNow } from '../../../components/hooks/polling';
import { AlertQueue } from '../components/AlertQueue';
import { ExportControls } from '../components/ExportControls';
import { ContextPanel } from '../components/ContextPanel';
import { EvidencePanel } from '../components/EvidencePanel';
import { TimelinePanel } from '../components/TimelinePanel';
import { VerdictBar } from '../components/VerdictBar';
import { WhyPanel } from '../components/WhyPanel';
import { QUEUE_WINDOW_HOURS } from '../api';
import {
  useAlertDetail,
  useQueue,
  useQueueShortcuts,
  useRecordVerdict,
  verdictFailureMessage,
  verdictOutcomeMessage,
} from '../hooks';
import { ALERTS_PATH, nextHref, stepHref } from '../links';
import type { VerdictName } from '../verdicts';

/** The live verdict region, so a recorded verdict is announced after it is written. */
function VerdictAnnouncement({ message }: { message: string | null }) {
  return (
    <p aria-live="polite" className="text-body-sm text-muted">
      {message ?? ''}
    </p>
  );
}

export function TriagePage() {
  const { alertId } = useParams<{ alertId: string }>();
  const [search] = useSearchParams();
  const createdAt = search.get('created_at');
  const now = useNow(1_000);
  const queue = useQueue();
  const record = useRecordVerdict();
  const [announcement, setAnnouncement] = useState<string | null>(null);

  const parsedId = alertId === undefined ? null : Number.parseInt(alertId, 10);
  const selectedId = parsedId !== null && Number.isFinite(parsedId) ? parsedId : null;
  const detail = useAlertDetail(selectedId, createdAt);

  // A new alert clears the previous verdict's announcement: the region is about
  // *this* alert's write, and stale praise for the last one is worse than silence.
  useEffect(() => {
    setAnnouncement(null);
  }, [selectedId, createdAt]);

  // A stable identity for the queue's rows: `j`/`k` step through them, and a fresh
  // array on every render would rebuild the step callback on each keystroke.
  const rows = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const hasMore = (queue.data?.next_cursor ?? null) !== null;
  const next = nextHref(rows, selectedId);

  // `j`/`k` open the next and previous alert — the queue's step, not a list
  // widget's focus move (T-411). Disabled while the queue has no rows, so the key
  // does nothing rather than navigating to a row the screen does not have.
  const navigate = useNavigate();
  const stepBy = useCallback(
    (delta: -1 | 1) => {
      const href = stepHref(rows, selectedId, delta);
      if (href !== null) navigate(href);
    },
    [navigate, rows, selectedId],
  );
  useQueueShortcuts(rows.length > 0, stepBy);

  const onVerdict = (verdict: VerdictName) => {
    if (selectedId === null || createdAt === null) return;
    setAnnouncement(null);
    record.mutate(
      { alertId: selectedId, createdAt, verdict },
      { onSuccess: (outcome) => setAnnouncement(verdictOutcomeMessage(outcome)) },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-h1">Alert triage</h1>
        <p className="text-body-sm text-muted">
          Queue of the last {QUEUE_WINDOW_HOURS} h
          {queue.dataUpdatedAt === 0
            ? ''
            : ` · last update ${formatSince(new Date(queue.dataUpdatedAt).toISOString(), now)}`}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[22rem_1fr]">
        <AlertQueue
          rows={rows}
          status={queue.isPending ? 'pending' : queue.isError ? 'error' : 'success'}
          hasMore={hasMore}
          windowHours={QUEUE_WINDOW_HOURS}
          selectedId={selectedId}
          now={now}
          actions={<ExportControls />}
          onRetry={() => {
            void queue.refetch();
          }}
        />

        <div className="flex flex-col gap-4">
          {selectedId === null ? (
            <Card title="No alert open">
              <EmptyState
                title="Select an alert from the queue"
                description="Every row in the queue opens here: the reasons behind the alert, its timeline, the evidence trail and the context. The whole screen works from the keyboard."
              />
            </Card>
          ) : createdAt === null ? (
            <Card title="This alert cannot be opened from this link">
              <ErrorState
                message="The link is missing the alert's created_at"
                detail="An alert is addressed by its id and its created_at (D-030); without the second half the same id in another month is a different alert."
                action={
                  <Link className="underline" to={ALERTS_PATH}>
                    Back to the queue
                  </Link>
                }
              />
            </Card>
          ) : detail.isPending ? (
            <Card title="Loading the alert">
              <Skeleton lines={6} label="Loading the alert" />
            </Card>
          ) : detail.isError ? (
            <Card title="The alert could not be loaded">
              <ErrorState
                message="No alert was returned for this address"
                detail="It may have been erased under the retention policy (FR-05), or the link may carry a created_at from a different partition."
                action={
                  <Link className="underline" to={ALERTS_PATH}>
                    Back to the queue
                  </Link>
                }
              />
            </Card>
          ) : detail.data === undefined ? (
            <Card title="Loading the alert">
              <Skeleton lines={6} label="Loading the alert" />
            </Card>
          ) : (
            <>
              <VerdictBar
                detail={detail.data}
                onVerdict={onVerdict}
                pending={record.isPending}
                {...(record.isError ? { errorMessage: verdictFailureMessage(record.error) } : {})}
                next={next}
              />
              <VerdictAnnouncement message={announcement} />
              <WhyPanel detail={detail.data} />
              <TimelinePanel detail={detail.data} />
              <EvidencePanel detail={detail.data} />
              <ContextPanel detail={detail.data} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
