/**
 * Traffic explorer — `/traffic` (design.md §4.4, FR-52).
 *
 * Top to bottom, one brush and one window: a brushable series of **ingested flow volume**
 * with the composite score overlaid, then the address table and the graph side by side,
 * then the caveats. Since T-418 the numbers are the traffic's — counted by the flow read
 * model over the window, with the alert side joined on by the endpoint — and brushing
 * re-reads the *brushed window* rather than filtering a page of alerts (`hooks.ts`), so
 * "filters everything below" is true of the server's own counts, not just of a list that
 * happened to be in the browser.
 *
 * Three things this screen says out loud rather than hiding:
 *
 *   * **What the numbers are, and what the source cannot see.** The caveats come from
 *     the API verbatim: which read model answered (a persistent store, or this process's
 *     in-memory rollup), what a cap did to a list, and why a window is empty. A reader
 *     cannot get the chart without them.
 *   * **What was filtered away.** The controls are absolute, so the page reports how many
 *     addresses they removed; a table that quietly shrank is how an analyst concludes
 *     there is nothing there.
 *   * **What is partial.** `nodes_capped` and `edges_capped` come from the response, so
 *     a top-N list says it is one — and the caveats name both numbers, so the reader
 *     learns how many addresses were not listed rather than that "some" were.
 */
import { useMemo, useState } from 'react';

import { useChartPalette } from '../../../components/charts/palette';
import { Button, ConnectionStatus, ErrorState, Panel, Skeleton } from '../../../components/ui';
import { useConnectionView } from '../../../components/realtime/useConnectionView';
import { FLOW_DIRECTIONS, FLOW_PROTOCOLS } from '../../../api/flows';
import { BrushSeries } from '../components/BrushSeries';
import { EntityGraph } from '../components/EntityGraph';
import { EntityTable } from '../components/EntityTable';
import {
  rangeOf,
  useTrafficBrush,
  useTrafficWindow,
  TRAFFIC_RANGES,
  type TrafficRangeKey,
} from '../hooks';
import { buildTrafficView, DEFAULT_FILTERS, type TrafficFilters } from '../view';
import type { BrushRange } from '../aggregate';

export function TrafficPage() {
  const [rangeKey, setRangeKey] = useState<TrafficRangeKey>('24h');
  const [filters, setFilters] = useState<TrafficFilters>(DEFAULT_FILTERS);
  const [brush, setBrush] = useState<BrushRange | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  const range = rangeOf(rangeKey);
  const window = useTrafficWindow(range, filters, true);
  // The brushed read is enabled only when there is a brush, so an unbrushed screen makes
  // one request. While it loads, the unbrushed aggregate is what the panels show — see
  // the view below — so a committed selection never blanks the screen it was drawn on.
  const brushed = useTrafficBrush(range, filters, brush, true);
  const palette = useChartPalette();
  const connection = useConnectionView();

  const full = window.data;
  const panels = brushed.data ?? full;

  const view = useMemo(() => {
    if (full === undefined || panels === undefined) return null;
    return buildTrafficView({
      aggregate: full,
      panels,
      brush,
      filters,
      pinnedId: pinned,
    });
  }, [full, panels, brush, filters, pinned]);

  const loading = view === null;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1">Traffic</h1>
          <p className="mt-1 text-body-sm text-muted">
            Flow volume and composite score over the window, with the addresses those flows belong
            to. Brushing the series re-reads the selected window for the table and the graph.
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
              onChange={(event) => {
                setRangeKey(event.target.value as TrafficRangeKey);
                // The selection was drawn on the old series; keeping it would leave the
                // panels describing a window the chart no longer draws.
                setBrush(null);
              }}
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

      {window.isError && full === undefined ? (
        <ErrorState
          message="The traffic window could not be loaded"
          detail="It reads the flow API over the selected window, which composes the alert overlay."
          action={<Button onClick={() => void window.refetch()}>Retry</Button>}
        />
      ) : null}

      {brushed.isError && brush !== null ? (
        <ErrorState
          message="The brushed window could not be loaded"
          detail="The table and the graph still describe the whole window; widen the brush to see everything again."
          action={<Button onClick={() => setBrush(null)}>Clear the brush</Button>}
        />
      ) : null}

      <Panel
        title="Flow volume and score"
        state={loading ? 'loading' : 'ready'}
        loadingLines={6}
        actions={
          <span className="text-caption text-muted">
            {range.label} · {String(full?.bucket_minutes ?? 0)}-minute buckets
          </span>
        }
      >
        {view === null ? (
          <Skeleton lines={6} />
        ) : view.series.every((bucket) => bucket.flows === 0) ? (
          <p className="text-body-sm text-muted">
            No flow records in the {range.label.toLowerCase()}. The panel&apos;s caveats say whether
            anything has been ingested at all.
          </p>
        ) : (
          <BrushSeries
            buckets={view.series}
            range={brush}
            onRange={setBrush}
            palette={palette}
            label={`Flow volume over the ${range.label.toLowerCase()}, with the mean composite score of the alerts in each bucket`}
          />
        )}
      </Panel>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex items-center gap-2">
          <label className="text-caption text-muted" htmlFor="traffic-protocol">
            Protocol
          </label>
          <select
            id="traffic-protocol"
            value={filters.protocol}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                protocol: event.target.value as TrafficFilters['protocol'],
              }))
            }
            className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
          >
            <option value="all">All protocols</option>
            {FLOW_PROTOCOLS.map((protocol) => (
              <option key={protocol} value={protocol}>
                {protocol}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-caption text-muted" htmlFor="traffic-direction">
            Direction
          </label>
          <select
            id="traffic-direction"
            value={filters.direction}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                direction: event.target.value as TrafficFilters['direction'],
              }))
            }
            className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
          >
            <option value="all">All directions</option>
            {FLOW_DIRECTIONS.map((direction) => (
              <option key={direction} value={direction}>
                {direction}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-caption text-muted" htmlFor="traffic-min-flows">
            Min flows
          </label>
          <input
            id="traffic-min-flows"
            type="number"
            min={0}
            value={filters.minFlows}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                minFlows: Math.max(0, Number(event.target.value) || 0),
              }))
            }
            className="h-8 w-24 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
          />
        </div>

        <label className="flex items-center gap-2 text-body-sm text-ink">
          <input
            type="checkbox"
            checked={filters.openAlertsOnly}
            onChange={(event) =>
              setFilters((current) => ({ ...current, openAlertsOnly: event.target.checked }))
            }
          />
          Only addresses with an open alert
        </label>

        {view === null ? null : (
          <p className="text-caption text-muted">
            {String(view.nodes.length)} addresses shown
            {view.hiddenByControls === 0
              ? ''
              : `, ${String(view.hiddenByControls)} hidden by the controls`}
            {pinned === null ? '' : ', pinned to one address and its neighbours'}.
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Addresses"
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
              entities={view.nodes}
              pinnedId={pinned}
              onPin={(id) => setPinned((current) => (current === id ? null : id))}
            />
          )}
        </Panel>

        <Panel
          title="Flow relationships"
          state={view === null ? 'loading' : 'ready'}
          loadingLines={5}
        >
          {view === null ? (
            <Skeleton lines={5} />
          ) : (
            <EntityGraph model={view.graph} palette={palette} pinnedId={pinned} onPin={setPinned} />
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
