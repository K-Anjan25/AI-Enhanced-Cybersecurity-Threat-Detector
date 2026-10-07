/**
 * Log explorer — `/logs` (design.md §4.5).
 *
 * A clustered read: identical lines collapse into one row with a count, a row holding
 * an error or critical line carries the rail, opening a row shows the raw lines behind
 * it, and the view can be paused so a stack trace does not scroll away while it is
 * being read.
 *
 * Six things this screen says out loud rather than hiding:
 *
 *   * **Where the lines came from.** A deployment answers from the log store or from
 *     its own process's tail, and the two are not interchangeable: one survives a
 *     restart and spans a day, the other holds fifteen minutes and dies with the
 *     process. The header names which one is answering, and every read carries the
 *     API's own caveats rendered verbatim beneath the table — a screen that
 *     paraphrased "not a store" would eventually word it wrong.
 *   * **How far back it can be asked.** The window picker offers what the answering
 *     source can read: a tail deployment gets the retained spans, a store deployment
 *     also gets an hour and a day (T-419), so the picker cannot offer a window the
 *     server would refuse.
 *   * **A level is not an anomaly.** The rail marks lines a reader should look at,
 *     coloured by the level, and the caveats say that no model scored them.
 *   * **Nothing is linked to an alert yet.** §4.5 asks a cluster to jump to the alert
 *     that referenced it; an alert's evidence is a window identity, not a set of
 *     lines, so there is nothing to join on and the panel says so instead of offering
 *     a dead link.
 *   * **Pause freezes, it does not buffer.** While paused the window stops moving and
 *     the poll is off, so what is on screen is what was read at the pause instant.
 *   * **How old the data is.** §8.1's staleness rule applies to a tail most of all:
 *     a log screen that stopped updating looks exactly like a quiet system.
 */
import { useMemo, useState } from 'react';

import { Button, EmptyState, ErrorState, Panel, Skeleton } from '../../../components/ui';
import { useDocumentVisible, useNow } from '../../../components/hooks/polling';
import { formatCount, formatSince } from '../../../lib/format';
import { ClusterTable } from '../components/ClusterTable';
import { RawLines } from '../components/RawLines';
import { TailControls } from '../components/TailControls';
import { SPAN_MS, spanOf, spansFor, tailWindow, templateLabel, type TailSpan } from '../cluster';
import { refreshMsFor, useLogLines, useLogTail, type LogFilters } from '../hooks';
import { buildLogView } from '../view';

export function LogsPage() {
  const [spanKey, setSpanKey] = useState<TailSpan['key']>('5m');
  const [filters, setFilters] = useState<LogFilters>({ level: 'all' });
  const [pausedAt, setPausedAt] = useState<Date | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  const visible = useDocumentVisible();
  const paused = pausedAt !== null;

  // The window is *state*, not a live expression: pausing freezes it at the instant
  // of the pause, and a resumed tail starts a fresh window. If it were computed from
  // the clock on every render, a paused screen would keep moving — which is the one
  // thing pause exists to prevent.
  //
  // Both it and the read cadence come from the span *asked for* -- its width as the
  // key defines it (SPAN_MS), not as the answering source clamps it, because the answer
  // is what this render has not heard yet and the cadence must not depend on it. That
  // is what keeps this above the query rather than in a cycle with it (T-419).
  const spanMs = SPAN_MS[spanKey];
  const [window, setWindow] = useState(() => tailWindow(Date.now(), spanMs));

  const tail = useLogTail(window, filters, visible && !paused, refreshMsFor(spanMs));
  const lines = useLogLines(window, openKey, visible);
  const now = useNow(5_000);

  // What this deployment can be asked for follows what answered: a store deployment
  // is offered an hour and a day as well, and a tail deployment keeps the retained
  // spans. `span` is resolved against the same set, so the picker's value is always
  // one of its own options even if a deployment's source ever changed underneath a
  // picked key.
  const tailSource = tail.data?.source;
  const spans = spansFor(tailSource);
  const span = spanOf(spanKey, tailSource);

  const view = useMemo(
    () => buildLogView({ tail: tail.data, window, failed: tail.isError }),
    [tail.data, tail.isError, window],
  );

  const changeSpan = (key: TailSpan['key']) => {
    setSpanKey(key);
    // A span change is a change to what is being asked for, so it moves the window
    // at once — unless the tail is paused, where the window is the thing being held.
    if (!paused) setWindow(tailWindow(Date.now(), spanOf(key, tailSource).spanMs));
  };

  const pause = (next: boolean) => {
    if (next) {
      // Freeze both halves together: the clock the label shows and the window the
      // request used must be the same instant, or the label would name a window the
      // table is not showing.
      const at = new Date();
      setWindow(tailWindow(at.getTime(), span.spanMs));
      setPausedAt(at);
      return;
    }
    setPausedAt(null);
    setWindow(tailWindow(Date.now(), span.spanMs));
  };

  const openRow = view.rows.find((row) => row.key === openKey) ?? null;
  const staleDetail = paused
    ? 'The view is paused, so this window will not change until it is resumed.'
    : view.state === 'loading'
      ? 'Reading the logs.'
      : `Last read ${formatSince(new Date(tail.dataUpdatedAt).toISOString(), now)}.`;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1">Logs</h1>
          <p className="mt-1 text-body-sm text-muted">
            Accepted log lines, with identical lines collapsed into one row. Open a cluster to read
            the lines behind it. {view.sourceLabel}
          </p>
        </div>
      </header>

      <TailControls
        paused={paused}
        pausedAt={pausedAt}
        onPause={pause}
        span={span}
        spans={spans}
        onSpan={changeSpan}
        filters={filters}
        onFilters={setFilters}
        windowLabel={view.windowLabel}
      />

      <Panel
        title="Clusters"
        state={view.state === 'rows' ? 'ready' : view.state === 'empty' ? 'empty' : 'ready'}
        loadingLines={5}
        actions={
          <span className="text-caption text-muted">
            {view.state === 'loading'
              ? 'Reading the logs…'
              : `${formatCount(view.clustersSeen)} clusters · ${formatCount(view.linesSeen)} lines · ${formatCount(view.notableCount)} with an error or worse`}
          </span>
        }
      >
        {view.state === 'loading' ? (
          <Skeleton lines={5} label="Log clusters" />
        ) : view.state === 'error' ? (
          <ErrorState
            message="The log lines could not be read"
            detail="It reads accepted log lines over the selected window. Nothing is shown rather than a stale window presented as current."
            action={<Button onClick={() => void tail.refetch()}>Retry</Button>}
          />
        ) : (
          <ClusterTable
            rows={view.rows}
            openKey={openKey}
            onOpen={setOpenKey}
            empty={
              <EmptyState
                title="No log lines in this window"
                description={view.emptyReason ?? 'Nothing matched the window and filters.'}
              />
            }
          />
        )}
      </Panel>

      <RawLines
        clusterKey={openKey}
        template={openRow === null ? '' : templateLabel(openRow.cluster)}
        lines={lines.data}
        failed={lines.isError}
        onClose={() => setOpenKey(null)}
      />

      <section aria-label="What this screen is showing" className="flex flex-col gap-1">
        <p className="text-caption text-muted">
          {view.retention} {staleDetail}
        </p>
        {view.caveats.map((caveat) => (
          <p key={caveat} className="text-caption text-muted">
            {caveat}
          </p>
        ))}
        <p className="text-caption text-muted">
          Jumping from a cluster to the alert that referenced it is not available in this build: an
          alert&rsquo;s evidence names a window, not the lines in it, so there is nothing to link to
          yet.
        </p>
      </section>
    </div>
  );
}
