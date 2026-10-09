/**
 * CyberpunkOverviewPage — Real API data with pure CSS cyberpunk styling.
 *
 * ZERO heavy JS: no canvas, no requestAnimationFrame, no setInterval,
 * no Three.js, no WebGL. All effects are CSS-only.
 */
import { useState } from 'react';

import { GlitchText, NeonCard, VectorShield, ThreatLevelBar } from '../../../components/cyberpunk';
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
import { fetchDetectionStatus, type DetectionStatus } from '../api';
import { useQuery } from '@tanstack/react-query';
import { useChartPalette } from '../palette';
import { readPipeline } from '../pipeline';
import { bucketLabel, connectionState, kpiTiles, panelState, staleness } from '../view';

export function CyberpunkOverviewPage() {
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
  const windowLabel = `${range.label} \u00b7 ${String(alerts)} alerts in this window`;
  const age = staleness(overview.dataUpdatedAt === 0 ? null : overview.dataUpdatedAt, now);
  const connection = connectionState({
    alertsFailed: overview.isError,
    metricsFailed: metrics.isError,
    stale: age.stale,
  });

  const detectionStatus = useQuery<DetectionStatus>({
    queryKey: ['detection-status'],
    queryFn: ({ signal }) => fetchDetectionStatus(signal),
    refetchInterval: 5_000,
  });
  const det = detectionStatus.data;

  const stages =
    metrics.data === undefined ? [] : readPipeline(metrics.data, previousMetrics ?? null);

  const threatLevel =
    alerts === 0
      ? 8
      : alerts < 10
        ? 15 + alerts * 3
        : alerts < 50
          ? 40 + alerts
          : Math.min(95, 60 + alerts * 0.5);

  const critCount = summary?.totals.by_severity?.critical ?? 0;
  const highCount = summary?.totals.by_severity?.high ?? 0;
  const hasThreats = critCount > 0 || highCount > 0;

  return (
    <div className="flex flex-col gap-6">
      {/* Connection status banner */}
      <div className="flex items-center gap-2 rounded border border-line bg-surface/50 px-3 py-2 font-mono text-caption text-muted">
        <span
          className={`inline-block h-2 w-2 rounded-full ${overview.isSuccess ? 'bg-green' : overview.isLoading ? 'bg-yellow' : 'bg-red'}`}
        />
        <span>
          LIVE from <code className="text-accent">/api/v1/overview</code>
          {overview.isLoading && ' — loading...'}
          {overview.isError && ' — disconnected'}
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
          />
          <div>
            <GlitchText as="h1" intensity={hasThreats ? 'medium' : 'subtle'}>
              {hasThreats ? 'THREATS DETECTED' : 'OVERVIEW'}
            </GlitchText>
            <p className="mt-1 font-mono text-caption text-muted">
              {alerts} alerts · {critCount} critical · {highCount} high · {range.label}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <p
            className={`font-mono text-caption ${age.stale ? 'text-severityText-critical' : 'text-muted'}`}
          >
            {age.label}
            {age.stale ? ' — STALE' : ''}
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
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Threat Level + System Status */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="md:col-span-2">
          <NeonCard
            title="SYSTEM THREAT LEVEL"
            subtitle={`${alerts} alerts in ${range.label}`}
            color={threatLevel > 60 ? 'magenta' : threatLevel > 30 ? 'yellow' : 'green'}
          >
            <ThreatLevelBar level={threatLevel} />
            <div className="mt-3 grid grid-cols-2 gap-3 font-mono text-caption md:grid-cols-4">
              <div>
                CRIT: <span className="text-severityText-critical">{critCount}</span>
              </div>
              <div>
                HIGH: <span className="text-severityText-high">{highCount}</span>
              </div>
              <div>
                MED:{' '}
                <span className="text-severityText-medium">
                  {summary?.totals.by_severity?.medium ?? 0}
                </span>
              </div>
              <div>
                LOW:{' '}
                <span className="text-severityText-low">
                  {summary?.totals.by_severity?.low ?? 0}
                </span>
              </div>
            </div>
          </NeonCard>
        </div>
        <NeonCard title="SYSTEM STATUS" color={overview.isSuccess ? 'green' : 'magenta'}>
          <div className="flex items-center gap-3 py-2">
            <VectorShield
              size={40}
              status={overview.isSuccess ? 'secure' : overview.isError ? 'breach' : 'warning'}
              animate={false}
            />
            <div>
              <p
                className={`font-mono text-body ${overview.isSuccess ? 'text-green' : 'text-red'}`}
              >
                {overview.isSuccess ? 'ALL SYSTEMS OPERATIONAL' : 'CONNECTION ERROR'}
              </p>
              <p className="font-mono text-caption text-muted">
                {overview.isSuccess
                  ? 'Backend API responding normally'
                  : 'Cannot reach backend API'}
              </p>
            </div>
          </div>
          {overview.isError && (
            <Button onClick={() => void overview.refetch()} className="mt-2 w-full">
              Retry
            </Button>
          )}
        </NeonCard>
      </div>

      {/* Detection Engine Status */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <NeonCard
          title="RULE DETECTOR"
          subtitle="Heuristic threat detection"
          color={det?.rule_engine?.running ? 'green' : 'yellow'}
        >
          <div className="grid grid-cols-2 gap-3 font-mono text-caption">
            <div>
              <span className="text-muted">STATUS</span>
              <div
                className={
                  det?.rule_engine?.running ? 'text-green text-body' : 'text-yellow text-body'
                }
              >
                {det?.rule_engine?.running ? 'ACTIVE' : det ? 'STOPPED' : '...'}
              </div>
            </div>
            <div>
              <span className="text-muted">DETECTIONS</span>
              <div className="text-cyan text-body">{det?.rule_engine?.total_detections ?? 0}</div>
            </div>
            <div>
              <span className="text-muted">ALERTS</span>
              <div className="text-magenta text-body">{det?.rule_engine?.total_alerts ?? 0}</div>
            </div>
            <div>
              <span className="text-muted">BUFFER</span>
              <div className="text-yellow text-body">{det?.rule_engine?.buffer_size ?? 0}</div>
            </div>
          </div>
          <p className="mt-2 text-caption text-muted">
            Port scans, beacons, exfil, brute force, DNS tunnels, lateral movement
          </p>
        </NeonCard>
        <NeonCard
          title="ML PIPELINE"
          subtitle="Statistical anomaly scoring"
          color={det?.ml_consumer ? 'cyan' : 'yellow'}
        >
          <div className="grid grid-cols-2 gap-3 font-mono text-caption">
            <div>
              <span className="text-muted">WINDOWS SCORED</span>
              <div className="text-cyan text-body">{det?.ml_consumer?.windows_scored ?? 0}</div>
            </div>
            <div>
              <span className="text-muted">ML ALERTS</span>
              <div className="text-magenta text-body">{det?.ml_consumer?.alerts_created ?? 0}</div>
            </div>
            <div>
              <span className="text-muted">SCORING ERRORS</span>
              <div className="text-red text-body">{det?.ml_consumer?.scoring_errors ?? 0}</div>
            </div>
            <div>
              <span className="text-muted">BUFFER</span>
              <div className="text-yellow text-body">{det?.ml_consumer?.buffer_size ?? 0}</div>
            </div>
          </div>
          <p className="mt-2 text-caption text-muted">
            Flows scored by ML service via /score endpoint
          </p>
        </NeonCard>
      </div>

      {/* Real KPI Tiles */}
      <KpiTiles
        tiles={kpiTiles(tally, summary?.totals.open ?? 0, range.label, {
          meanSeconds: summary?.totals.mean_time_to_verdict_seconds ?? null,
          measured: summary?.totals.verdicts_measured ?? 0,
        })}
      />

      {/* Real Severity Chart */}
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

      {/* Real Entities + Family Mix */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <NeonCard title="TOP ATTACKED ENTITIES" color="magenta">
          <Card
            title="Entities"
            state={state}
            loadingLines={5}
            empty={{ title: `No entity was attacked in the ${range.label}.` }}
            error={{
              message: 'Top entities could not be loaded',
              detail: 'Same window as tiles.',
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
                description="Pipeline health comes from /metrics."
              />
              <Button onClick={() => void metrics.refetch()} className="mt-3">
                Retry
              </Button>
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
