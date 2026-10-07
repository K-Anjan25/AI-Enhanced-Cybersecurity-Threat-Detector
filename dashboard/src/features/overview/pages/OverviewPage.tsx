/**
 * Overview — `/` (design.md §4.1, FR-50).
 *
 * The question this screen answers is the one in the design: *"is anything
 * happening, and is AEGIS itself healthy?"* That second clause is why the pipeline
 * strip is a first-class element rather than a footer, and why every panel here has
 * a name for its empty, loading and error states: on this page an absence is the
 * normal reading, so an absence that is *not* meaningful has to be distinguishable
 * from one that is.
 *
 * **One window, one read (T-416).** The tiles, the severity chart, the entity list
 * and the family mix all render `GET /api/v1/overview`, which aggregates the window
 * where the rows are. Before this, the page walked alert pages and counted what it
 * had read: three panels over three walks could disagree, and past the walk's cap
 * every figure came with a "partial coverage" asterisk. The counts are now the
 * window's counts, which is why the page has no partial-coverage language left —
 * there is nothing partial to describe. The pipeline strip is still `/metrics`
 * (D-060): a scrape is not a window.
 *
 * Layout follows §4.1: the header with the connection pill and the window selector,
 * the KPI tiles, the severity chart, top entities beside the family mix, and the
 * pipeline strip across the bottom.
 */
import { useState } from 'react';

import { Button, Card, ConnectionStatus, EmptyState } from '../../../components/ui';
import {
  emptyTally,
  entitiesFromOverview,
  familiesFromOverview,
  seriesFromOverview,
  tallyFromOverview,
} from '../aggregate';
import { FamilyMixChart } from '../components/FamilyMixChart';
import { KpiTiles } from '../components/KpiTiles';
import { PipelineStrip } from '../components/PipelineStrip';
import { SeverityAreaChart } from '../components/SeverityAreaChart';
import { TopEntities } from '../components/TopEntities';
import {
  rangeSpec,
  RANGES,
  useDocumentVisible,
  useMetrics,
  useNow,
  useOverviewWindow,
  usePrefersReducedMotion,
  usePrevious,
  useReadiness,
  type RangeKey,
} from '../hooks';
import { useChartPalette } from '../palette';
import { readPipeline } from '../pipeline';
import { bucketLabel, connectionState, kpiTiles, panelState, staleness } from '../view';

export function OverviewPage() {
  const [rangeKey, setRangeKey] = useState<RangeKey>('24h');
  const range = rangeSpec(rangeKey);

  const visible = useDocumentVisible();
  const now = useNow(1_000, visible);
  const overview = useOverviewWindow(range, visible);
  const metrics = useMetrics(visible);
  const readiness = useReadiness(visible);
  const previousMetrics = usePrevious(metrics.data);
  const palette = useChartPalette();
  const reducedMotion = usePrefersReducedMotion();

  const summary = overview.data;
  const tally = summary === undefined ? emptyTally() : tallyFromOverview(summary.totals);
  const series = summary === undefined ? [] : seriesFromOverview(summary.series);
  const points = series.map((bucket) => ({
    label: bucketLabel(bucket.start, range.spanMs),
    counts: bucket.counts,
  }));
  const entities = summary === undefined ? [] : entitiesFromOverview(summary.entities);
  const families = summary === undefined ? [] : familiesFromOverview(summary.families);
  const peaks = Object.fromEntries(
    families.flatMap((family) => (family.peak === null ? [] : [[family.family, family.peak]])),
  );

  const alerts = summary?.totals.alerts ?? 0;
  const state = panelState(overview.status, alerts);
  // The window's own label, and the count is the window's, not a page walk's.
  const windowLabel = `${range.label} \u00b7 ${String(alerts)} alerts in this window`;
  const age = staleness(overview.dataUpdatedAt === 0 ? null : overview.dataUpdatedAt, now);
  const connection = connectionState({
    alertsFailed: overview.isError,
    metricsFailed: metrics.isError,
    stale: age.stale,
  });

  const stages =
    metrics.data === undefined ? [] : readPipeline(metrics.data, previousMetrics ?? null);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-h1">Overview</h1>
          <p className="mt-1 text-body-sm text-muted">
            Detection posture and pipeline health. Every panel below is one read of the{' '}
            {range.label} window.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <p className={`text-caption ${age.stale ? 'text-severityText-critical' : 'text-muted'}`}>
            {age.label}
            {age.stale ? ' \u2014 stale' : ''}
          </p>
          <ConnectionStatus state={connection} detail={range.label} />
          <div className="flex items-center gap-2">
            <label className="text-caption text-muted" htmlFor="overview-range">
              Window
            </label>
            <select
              id="overview-range"
              value={rangeKey}
              onChange={(event) => setRangeKey(event.target.value as RangeKey)}
              className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
            >
              {RANGES.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <KpiTiles
        tiles={kpiTiles(tally, summary?.totals.open ?? 0, range.label, {
          meanSeconds: summary?.totals.mean_time_to_verdict_seconds ?? null,
          measured: summary?.totals.verdicts_measured ?? 0,
        })}
      />

      <SeverityAreaChart
        points={points}
        windowLabel={windowLabel}
        rangeLabel={range.label}
        palette={palette}
        reducedMotion={reducedMotion}
        state={state}
        onRetry={() => void overview.refetch()}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Top attacked entities"
          state={state}
          loadingLines={5}
          empty={{ title: `No entity was attacked in the ${range.label}.` }}
          error={{
            message: 'Top entities could not be loaded',
            detail: 'They are part of the same window as the tiles.',
            action: <Button onClick={() => void overview.refetch()}>Retry</Button>,
          }}
        >
          <TopEntities
            entities={entities}
            windowLabel={windowLabel}
            capped={summary?.entities_capped ?? false}
          />
        </Card>

        <FamilyMixChart
          families={families}
          peaks={peaks}
          windowLabel={windowLabel}
          rangeLabel={range.label}
          palette={palette}
          reducedMotion={reducedMotion}
          state={state}
          onRetry={() => void overview.refetch()}
        />
      </div>

      {stages.length === 0 ? (
        // Deliberately not labelled: a labelled <section> is a `region`, and the
        // real strip is the only thing on this page that should answer to
        // "Detection pipeline health" — otherwise a screen reader (or a test)
        // cannot tell the placeholder from the panel.
        <section className="rounded-card border border-line bg-base p-4">
          <h2 className="text-h2">Detection pipeline health</h2>
          {metrics.isError ? (
            <div className="mt-2">
              <EmptyState
                title="The metrics scrape could not be read"
                description="Pipeline health comes from /metrics, which did not answer. The indicator above says whether this console is still hearing from the server."
              />
            </div>
          ) : (
            <p className="mt-2 text-body-sm text-muted">Reading the metrics scrape…</p>
          )}
        </section>
      ) : (
        <PipelineStrip
          stages={stages}
          hasRates={previousMetrics !== undefined}
          probes={readiness.data?.checks}
        />
      )}
    </div>
  );
}
