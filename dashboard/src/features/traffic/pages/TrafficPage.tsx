/**
 * Traffic explorer — `/traffic` (design.md §4.4, FR-52).
 *
 * Top to bottom, one brush and one row set: a brushable series of alerted record
 * volume with the composite score overlaid, then the entity table and the graph
 * side by side, then the caveats. Brushing filters everything below it because
 * `buildTrafficView` derives all three panels from one brushed row set — there is no
 * second place where the brush could be forgotten.
 *
 * Three things this screen says out loud rather than hiding:
 *
 *   * **What the numbers are.** The series counts records *that raised alerts*, and
 *     the graph's edges are shared correlation traces — not total traffic and not
 *     flow counts. The note is part of the view model, so it renders with the data
 *     it describes and a reader cannot get the chart without the caveat.
 *   * **What was filtered away.** The controls are absolute, so the page reports how
 *     many entities they removed; a table that quietly shrank is how an analyst
 *     concludes there is nothing there.
 *   * **What is partial.** When the page walk hit its cap, the counts say so
 *     (`complete: false`, the rule D-060 recorded for the overview).
 */
import { useMemo, useState } from 'react';

import { useChartPalette } from '../../../components/charts/palette';
import { Button, ConnectionStatus, ErrorState, Panel, Skeleton } from '../../../components/ui';
import { useConnectionView } from '../../../components/realtime/useConnectionView';
import { SEVERITIES, type Severity } from '../../../components/ui/severity';
import { BrushSeries } from '../components/BrushSeries';
import { EntityGraph } from '../components/EntityGraph';
import { EntityTable } from '../components/EntityTable';
import { rangeOf, useTrafficWindow, TRAFFIC_RANGES, type TrafficRangeKey } from '../hooks';
import { DEFAULT_FILTERS, buildTrafficView, type TrafficFilters } from '../view';
import { SERIES_BUCKETS } from '../view';
import type { BrushRange } from '../aggregate';

export function TrafficPage() {
  const [rangeKey, setRangeKey] = useState<TrafficRangeKey>('24h');
  const [filters, setFilters] = useState<TrafficFilters>(DEFAULT_FILTERS);
  const [brush, setBrush] = useState<BrushRange | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);

  const range = rangeOf(rangeKey);
  const query = useTrafficWindow(range, filters.severity, true);
  const palette = useChartPalette();
  const connection = useConnectionView();

  // `useTrafficWindow` subscribes the window to pushed alerts (T-405) — including
  // the frames the REST fallback delivers once the socket is down. The brush, the
  // filters and the pin are view state and are deliberately *not* re-read, so a live
  // update cannot move a selection the analyst is working in.

  const view = useMemo(() => {
    if (query.data === undefined) return null;
    return buildTrafficView({
      rows: query.data.rows,
      start: query.data.start,
      end: query.data.end,
      complete: query.data.complete,
      pagesFetched: query.data.pagesFetched,
      brush,
      filters,
      pinnedEntityId: pinned,
      buckets: SERIES_BUCKETS,
    });
  }, [query.data, brush, filters, pinned]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1">Traffic</h1>
          <p className="mt-1 text-body-sm text-muted">
            Record volume and composite score over the window, with the entities those records
            belong to. Brushing the series filters the table and the graph.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <ConnectionStatus state={connection.state} detail={connection.detail} />
          <div className="flex items-center gap-2">
            <label className="text-caption text-muted" htmlFor="traffic-range">
              Window
            </label>
            <select
              id="traffic-range"
              value={rangeKey}
              onChange={(event) => setRangeKey(event.target.value as TrafficRangeKey)}
              className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
            >
              {TRAFFIC_RANGES.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {query.isError && query.data === undefined ? (
        <ErrorState
          message="The traffic window could not be loaded"
          detail="It reads the alert API over the selected window."
          action={<Button onClick={() => void query.refetch()}>Retry</Button>}
        />
      ) : null}

      <Panel
        title="Flow volume and score"
        state={view === null ? 'loading' : 'ready'}
        loadingLines={6}
        actions={
          <span className="text-caption text-muted">
            {range.label} · {String(SERIES_BUCKETS)} buckets
          </span>
        }
      >
        {view === null ? (
          <Skeleton lines={6} />
        ) : view.series.every((bucket) => bucket.alerts === 0) ? (
          <p className="text-body-sm text-muted">
            No alerts in the {range.label.toLowerCase()}: nothing was scored high enough to alert,
            so there is no volume to draw.
          </p>
        ) : (
          <BrushSeries
            buckets={view.series}
            range={brush}
            onRange={setBrush}
            palette={palette}
            label={`Alerted record volume over the ${range.label.toLowerCase()}, with the mean composite score`}
          />
        )}
      </Panel>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex items-center gap-2">
          <label className="text-caption text-muted" htmlFor="traffic-severity">
            Severity
          </label>
          <select
            id="traffic-severity"
            value={filters.severity}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                severity: event.target.value as Severity | 'all',
              }))
            }
            className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
          >
            <option value="all">All severities</option>
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-caption text-muted" htmlFor="traffic-min-records">
            Min records
          </label>
          <input
            id="traffic-min-records"
            type="number"
            min={0}
            value={filters.minRecords}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                minRecords: Math.max(0, Number(event.target.value) || 0),
              }))
            }
            className="h-8 w-24 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
          />
        </div>

        <label className="flex items-center gap-2 text-body-sm text-ink">
          <input
            type="checkbox"
            checked={filters.openOnly}
            onChange={(event) =>
              setFilters((current) => ({ ...current, openOnly: event.target.checked }))
            }
          />
          Only entities with an open alert
        </label>

        {view === null ? null : (
          <p className="text-caption text-muted">
            {String(view.entities.length)} entities shown
            {view.hiddenByControls === 0
              ? ''
              : `, ${String(view.hiddenByControls)} hidden by the controls`}
            {pinned === null ? '' : ', pinned to one entity and its neighbours'}.
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Entities"
          state={view === null ? 'loading' : 'ready'}
          loadingLines={5}
          actions={
            pinned === null ? undefined : (
              <Button variant="ghost" size="sm" onClick={() => setPinned(null)}>
                Unpin
              </Button>
            )
          }
        >
          {view === null ? (
            <Skeleton lines={5} />
          ) : (
            <EntityTable
              entities={view.entities}
              pinnedEntityId={pinned}
              onPin={(entityId) => setPinned((current) => (current === entityId ? null : entityId))}
            />
          )}
        </Panel>

        <Panel
          title="Entity relationships"
          state={view === null ? 'loading' : 'ready'}
          loadingLines={5}
        >
          {view === null ? (
            <Skeleton lines={5} />
          ) : (
            <EntityGraph
              model={view.graph}
              palette={palette}
              pinnedEntityId={pinned}
              onPin={setPinned}
            />
          )}
        </Panel>
      </div>

      {view === null ? null : (
        <section aria-label="What this screen is not showing" className="flex flex-col gap-1">
          {view.notes.map((note) => (
            <p key={note} className="text-caption text-muted">
              {note}
            </p>
          ))}
        </section>
      )}
    </div>
  );
}
