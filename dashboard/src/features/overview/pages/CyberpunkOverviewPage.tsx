/**
 * CyberpunkOverviewPage — Cyberpunk-styled overview using ONLY real API data.
 *
 * No simulated globe, radar, pulse waves, or fake stats.
 * Every visual element maps to real backend data from /api/v1/overview and /metrics.
 *
 * Cyberpunk effects are applied TO the real data:
 * - KPI tiles get neon borders and glow
 * - Severity chart gets neon gradient fills
 * - Entity table gets cyberpunk row styling
 * - Family mix gets neon pie/bar treatment
 * - Pipeline strip gets HUD styling
 */
import { useState } from 'react';

import { GlitchText, NeonCard, VectorShield, ThreatLevelBar } from '../../../components/cyberpunk';
import { usePerformance } from '../../../components/cyberpunk/PerformanceContext';
import { Card, ConnectionStatus, EmptyState, Button } from '../../../components/ui';
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

export function CyberpunkOverviewPage() {
  const [rangeKey, setRangeKey] = useState<RangeKey>('24h');
  const range = rangeSpec(rangeKey);
  const perf = usePerformance();

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
  const windowLabel = `${range.label} \u00b7 ${String(alerts)} alerts in this window`;
  const age = staleness(overview.dataUpdatedAt === 0 ? null : overview.dataUpdatedAt, now);
  const connection = connectionState({
    alertsFailed: overview.isError,
    metricsFailed: metrics.isError,
    stale: age.stale,
  });

  const stages =
    metrics.data === undefined ? [] : readPipeline(metrics.data, previousMetrics ?? null);

  const threatLevel =
    alerts === 0 ? 8 : alerts < 10 ? 15 + alerts * 3 : alerts < 50 ? 40 + alerts : Math.min(95, 60 + alerts * 0.5);

  const critCount = summary?.totals.by_severity?.critical ?? 0;
  const highCount = summary?.totals.by_severity?.high ?? 0;
  const hasThreats = critCount > 0 || highCount > 0;

  return (
    <div className="relative flex flex-col gap-6">
      {/* Real data banner */}
      <div className="flex items-center gap-2 rounded border border-line bg-surface/50 px-3 py-2 font-mono text-caption text-muted">
        <span className={`inline-block h-2 w-2 rounded-full ${overview.isSuccess ? 'bg-green' : overview.isLoading ? 'bg-yellow' : 'bg-red'}`} />
        <span>
          LIVE DATA from <code className="text-accent">/api/v1/overview</code> &amp; <code className="text-accent">/metrics</code>
          {overview.isLoading && ' — loading...'}
          {overview.isError && ' — connection error'}
        </span>
        <span className="ml-auto">
          <ConnectionStatus state={connection} detail={range.label} />
        </span>
      </div>

      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <VectorShield
            size={48}
            status={hasThreats ? 'breach' : alerts > 0 ? 'warning' : 'secure'}
            animate={perf.showAnimations}
          />
          <div>
            <GlitchText as="h1" intensity={hasThreats ? 'medium' : 'subtle'}>
              {hasThreats ? '⚠ THREATS DETECTED' : 'OVERVIEW'}
            </GlitchText>
            <p className="mt-1 font-mono text-caption text-muted">
              {alerts} alerts · {critCount} critical · {highCount} high · {range.label} window
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <p className={`font-mono text-caption ${age.stale ? 'text-severityText-critical' : 'text-muted'}`}>
            {age.label}{age.stale ? ' \u2014 STALE' : ''}
          </p>
          <div className="flex items-center gap-2">
            <label className="font-mono text-caption text-muted" htmlFor="overview-range">
              WINDOW
            </label>
            <select
              id="overview-range"
              value={rangeKey}
              onChange={(event) => setRangeKey(event.target.value as RangeKey)}
              className="h-8 rounded-input border border-line bg-surface px-2 font-mono text-body-sm text-ink"
            >
              {RANGES.map((option) => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Cyber Threat Level — based on real alert data */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="md:col-span-2">
          <NeonCard
            title="SYSTEM THREAT LEVEL"
            subtitle={`Based on ${alerts} alerts in ${range.label} window`}
            color={threatLevel > 60 ? 'magenta' : threatLevel > 30 ? 'yellow' : 'green'}
            animate={perf.showAnimations}
          >
            <ThreatLevelBar level={threatLevel} animated />
            <div className="mt-3 grid grid-cols-2 gap-3 font-mono text-caption md:grid-cols-4">
              <div className="text-muted">CRIT: <span className="text-severityText-critical">{critCount}</span></div>
              <div className="text-muted">HIGH: <span className="text-severityText-high">{highCount}</span></div>
              <div className="text-muted">MED: <span className="text-severityText-medium">{summary?.totals.by_severity?.medium ?? 0}</span></div>
              <div className="text-muted">LOW: <span className="text-severityText-low">{summary?.totals.by_severity?.low ?? 0}</span></div>
            </div>
          </NeonCard>
        </div>
        <NeonCard
          title="SYSTEM STATUS"
          color={overview.isSuccess ? 'green' : 'magenta'}
          animate={perf.showAnimations}
        >
          <div className="flex items-center gap-3 py-2">
            <VectorShield
              size={40}
              status={overview.isSuccess ? 'secure' : overview.isError ? 'breach' : 'warning'}
              animate={false}
            />
            <div>
              <p className={`font-mono text-body ${overview.isSuccess ? 'text-green' : 'text-red'}`}>
                {overview.isSuccess ? 'ALL SYSTEMS OPERATIONAL' : 'CONNECTION ERROR'}
              </p>
              <p className="font-mono text-caption text-muted">
                {overview.isSuccess ? 'Backend API responding normally' : 'Cannot reach backend API'}
              </p>
            </div>
          </div>
          {overview.isError && (
            <Button onClick={() => void overview.refetch()} className="mt-2 w-full">
              Retry Connection
            </Button>
          )}
        </NeonCard>
      </div>

      {/* Real KPI Tiles */}
      <KpiTiles
        tiles={kpiTiles(tally, summary?.totals.open ?? 0, range.label, {
          meanSeconds: summary?.totals.mean_time_to_verdict_seconds ?? null,
          measured: summary?.totals.verdicts_measured ?? 0,
        })}
      />

      {/* Real Severity Area Chart */}
      <NeonCard title="ALERT SEVERITY TIMELINE" subtitle={windowLabel} color="cyan">
        <SeverityAreaChart
          points={points}
          windowLabel={windowLabel}
          rangeLabel={range.label}
          palette={palette}
          reducedMotion={reducedMotion}
          state={state}
          onRetry={() => void overview.refetch()}
        />
      </NeonCard>

      {/* Real Top Entities + Family Mix */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <NeonCard title="TOP ATTACKED ENTITIES" color="magenta">
          <Card
            title="Entities"
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
        </NeonCard>

        <NeonCard title="THREAT FAMILY DISTRIBUTION" color="yellow">
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
        </NeonCard>
      </div>

      {/* Real Pipeline Strip */}
      {stages.length === 0 ? (
        <NeonCard title="DETECTION PIPELINE HEALTH" color="cyan">
          {metrics.isError ? (
            <div className="mt-2">
              <EmptyState
                title="The metrics scrape could not be read"
                description="Pipeline health comes from /metrics, which did not answer."
              />
              <Button onClick={() => void metrics.refetch()} className="mt-3">Retry</Button>
            </div>
          ) : (
            <p className="mt-2 text-body-sm text-muted">Reading the metrics scrape…</p>
          )}
        </NeonCard>
      ) : (
        <NeonCard title="DETECTION PIPELINE HEALTH" subtitle="Live from /metrics" color="cyan">
          <PipelineStrip
            stages={stages}
            hasRates={previousMetrics !== undefined}
            probes={readiness.data?.checks}
          />
        </NeonCard>
      )}
    </div>
  );
}