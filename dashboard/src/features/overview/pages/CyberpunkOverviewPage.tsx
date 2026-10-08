/**
 * CyberpunkOverviewPage — Full cyberpunk-styled overview dashboard.
 *
 * Integrates: 3D Globe, Threat Radar, Pulse Waves, GlitchText,
 * NeonCards, ThreatLevelBar, DataStream, VectorShield, KPI Tiles.
 */
import { useEffect, useState, useMemo } from 'react';

import {
  GlitchText,
  NeonCard,
  ThreatRadar,
  PulseWave,
  ThreatLevelBar,
  VectorShield,
  CyberGlobe,
  DataStream,
} from '../../../components/cyberpunk';
import { Card, ConnectionStatus, EmptyState } from '../../../components/ui';
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

/** Fake live stats for the cyberpunk HUD header */
function useLiveStats() {
  const [stats, setStats] = useState({
    packetsPerSec: 14523,
    activeConnections: 892,
    threatsBlocked: 47,
    uptime: '99.97%',
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setStats((prev) => ({
        packetsPerSec: prev.packetsPerSec + Math.floor(Math.random() * 200 - 80),
        activeConnections: prev.activeConnections + Math.floor(Math.random() * 20 - 10),
        threatsBlocked: prev.threatsBlocked + (Math.random() > 0.85 ? 1 : 0),
        uptime: '99.97%',
      }));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return stats;
}

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
  const liveStats = useLiveStats();

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

  // Simulated threat level for the cyberpunk display
  const threatLevel = useMemo(() => {
    if (alerts === 0) return 8;
    if (alerts < 10) return 15 + alerts * 3;
    if (alerts < 50) return 40 + alerts;
    return Math.min(95, 60 + alerts * 0.5);
  }, [alerts]);

  return (
    <div className="relative flex flex-col gap-6">
      {/* HUD Data Stream (decorative) */}
      <div className="pointer-events-none absolute right-0 top-0 h-full w-16 overflow-hidden opacity-20">
        <DataStream columns={4} speed="slow" />
      </div>

      {/* Page Header with Cyberpunk styling */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <VectorShield
            size={48}
            status={threatLevel > 60 ? 'breach' : threatLevel > 30 ? 'warning' : 'secure'}
          />
          <div>
            <GlitchText as="h1" intensity="subtle">
              OVERVIEW
            </GlitchText>
            <p className="mt-1 font-mono text-caption text-muted">
              DETECTION POSTURE &amp; PIPELINE HEALTH :: {range.label.toUpperCase()} WINDOW
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <p className={`font-mono text-caption ${age.stale ? 'text-severityText-critical' : 'text-muted'}`}>
            {age.label}
            {age.stale ? ' \u2014 STALE' : ''}
          </p>
          <ConnectionStatus state={connection} detail={range.label} />
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

      {/* Cyberpunk HUD Stats Strip */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: 'PACKETS/SEC', value: liveStats.packetsPerSec.toLocaleString(), color: '#00f0ff' },
          { label: 'ACTIVE CONN', value: liveStats.activeConnections.toLocaleString(), color: '#05ffa1' },
          { label: 'THREATS BLOCKED', value: String(liveStats.threatsBlocked), color: '#ff2a6d' },
          { label: 'UPTIME', value: liveStats.uptime, color: '#fcee0a' },
        ].map((stat) => (
          <NeonCard key={stat.label} color={stat.label === 'THREATS BLOCKED' ? 'magenta' : stat.label === 'UPTIME' ? 'yellow' : stat.label === 'ACTIVE CONN' ? 'green' : 'cyan'}>
            <div className="flex flex-col items-center py-1">
              <span className="font-mono text-caption uppercase tracking-widest text-muted">
                {stat.label}
              </span>
              <span
                className="font-mono text-h1 tabular neon-glow-cyan"
                style={{ color: stat.color, fontSize: '28px' }}
              >
                {stat.value}
              </span>
            </div>
          </NeonCard>
        ))}
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        {/* 3D Globe — spans 2 columns */}
        <div className="xl:col-span-2">
          <NeonCard title="GLOBAL NETWORK TRAFFIC" subtitle="Live threat visualization" color="cyan" animate>
            <div className="flex justify-center">
              <CyberGlobe width={520} height={380} />
            </div>
          </NeonCard>
        </div>

        {/* Threat Radar */}
        <div>
          <NeonCard title="THREAT RADAR" subtitle="Real-time sweep" color="magenta" animate>
            <div className="flex flex-col items-center gap-3">
              <ThreatRadar size={240} />
              <ThreatLevelBar level={threatLevel} />
            </div>
          </NeonCard>
        </div>
      </div>

      {/* System Vitals Row */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <NeonCard title="NETWORK PULSE" color="cyan">
          <PulseWave width={280} height={50} color="#00f0ff" speed={2} />
        </NeonCard>
        <NeonCard title="CPU UTILIZATION" color="green">
          <PulseWave width={280} height={50} color="#05ffa1" speed={1.5} amplitude={0.4} />
        </NeonCard>
        <NeonCard title="MEMORY FLOW" color="magenta">
          <PulseWave width={280} height={50} color="#ff2a6d" speed={1} amplitude={0.3} />
        </NeonCard>
      </div>

      {/* Standard KPI Tiles from the original overview */}
      <KpiTiles
        tiles={kpiTiles(tally, summary?.totals.open ?? 0, range.label, {
          meanSeconds: summary?.totals.mean_time_to_verdict_seconds ?? null,
          measured: summary?.totals.verdicts_measured ?? 0,
        })}
      />

      {/* Severity Chart */}
      <SeverityAreaChart
        points={points}
        windowLabel={windowLabel}
        rangeLabel={range.label}
        palette={palette}
        reducedMotion={reducedMotion}
        state={state}
        onRetry={() => void overview.refetch()}
      />

      {/* Entities + Family Mix */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Top attacked entities"
          state={state}
          loadingLines={5}
          empty={{ title: `No entity was attacked in the ${range.label}.` }}
          error={{
            message: 'Top entities could not be loaded',
            detail: 'They are part of the same window as the tiles.',
            action: <button onClick={() => void overview.refetch()}>Retry</button>,
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

      {/* Pipeline Strip */}
      {stages.length === 0 ? (
        <section className="rounded-card border border-line bg-base p-4">
          <h2 className="text-h2">Detection pipeline health</h2>
          {metrics.isError ? (
            <div className="mt-2">
              <EmptyState
                title="The metrics scrape could not be read"
                description="Pipeline health comes from /metrics, which did not answer."
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