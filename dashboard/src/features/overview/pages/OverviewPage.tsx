/**
 * Overview — `/` (design.md §4.1).
 *
 * The question this screen answers is the one in the design: *"is anything
 * happening, and is AEGIS itself healthy?"* That second clause is why the pipeline
 * strip is a first-class element rather than a footer, and why every panel here has
 * a name for its empty, loading and error states: on this page an absence is the
 * normal reading, so an absence that is *not* meaningful has to be distinguishable
 * from one that is.
 *
 * Layout follows §4.1: the header with the connection pill and the window selector,
 * the KPI tiles, the severity chart, top entities beside the family mix, and the
 * pipeline strip across the bottom.
 */
import { useState } from 'react';

import { Button, Card, ConnectionStatus, EmptyState } from '../../../components/ui';
import { countBySeverity, countOpen, familyMix, severitySeries, topEntities } from '../aggregate';
import { FamilyMixChart } from '../components/FamilyMixChart';
import { KpiTiles } from '../components/KpiTiles';
import { PipelineStrip } from '../components/PipelineStrip';
import { SeverityAreaChart } from '../components/SeverityAreaChart';
import { TopEntities } from '../components/TopEntities';
import {
  rangeSpec,
  RANGES,
  useAlertWindow,
  useDocumentVisible,
  useMetrics,
  useNow,
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
  const alerts = useAlertWindow(range, visible);
  const metrics = useMetrics(visible);
  const readiness = useReadiness(visible);
  const previousMetrics = usePrevious(metrics.data);
  const palette = useChartPalette();
  const reducedMotion = usePrefersReducedMotion();

  const rows = alerts.data?.rows ?? [];
  const windowStart = alerts.data?.start ?? new Date(now - range.spanMs);
  const windowEnd = alerts.data?.end ?? new Date(now);

  const tally = countBySeverity(rows);
  const open = countOpen(rows);
  const series = severitySeries(rows, {
    start: windowStart,
    end: windowEnd,
    buckets: range.buckets,
  });
  const points = series.map((bucket) => ({
    label: bucketLabel(bucket.start, range.spanMs),
    counts: bucket.counts,
  }));
  const entities = topEntities(rows, 5);
  const families = familyMix(rows, 8);
  const peaks = Object.fromEntries(
    families.flatMap((family) => (family.peak === null ? [] : [[family.family, family.peak]])),
  );

  const state = panelState(alerts.status, rows.length);
  const windowLabel = `${range.label} \u00b7 ${String(rows.length)} alerts read`;
  const age = staleness(alerts.dataUpdatedAt === 0 ? null : alerts.dataUpdatedAt, now);
  const connection = connectionState({
    alertsFailed: alerts.isError,
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
            Detection posture and pipeline health.{' '}
            {alerts.data?.complete === false
              ? `Only the first ${String(alerts.data.pagesFetched)} pages were read, so every count below is partial.`
              : 'Every panel is read from the live API.'}
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
        tiles={kpiTiles(tally, open, range.label)}
        partial={alerts.data?.complete === false}
      />

      <SeverityAreaChart
        points={points}
        windowLabel={windowLabel}
        rangeLabel={range.label}
        palette={palette}
        reducedMotion={reducedMotion}
        state={state}
        onRetry={() => void alerts.refetch()}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Top attacked entities"
          state={state}
          loadingLines={5}
          empty={{ title: `No entity was attacked in the ${range.label}.` }}
          error={{
            message: 'Top entities could not be loaded',
            detail: 'They read the same alert window as the tiles.',
            action: <Button onClick={() => void alerts.refetch()}>Retry</Button>,
          }}
        >
          <TopEntities entities={entities} windowLabel={windowLabel} />
        </Card>

        <FamilyMixChart
          families={families}
          peaks={peaks}
          windowLabel={windowLabel}
          rangeLabel={range.label}
          palette={palette}
          reducedMotion={reducedMotion}
          state={state}
          onRetry={() => void alerts.refetch()}
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
