/**
 * Detection pipeline health (design.md §4.1) — the strip that decides whether a
 * quiet screen means "nothing is happening" or "we stopped hearing from the
 * pipeline".
 *
 * The presentation rule is the acceptance criterion: **a stage over its budget is
 * red, and it says which budget it exceeded** — "p95 412 ms vs budget 150 ms
 * (NFR-01)". Colour alone would fail NFR-09 anyway, so the status is written out in
 * words beside the mark, and the mark is a glyph as well as a hue.
 *
 * A stage nothing measures renders as *not measured*, with its budget still shown:
 * the absence of an instrument is information an operator needs, and the
 * alternative — a zero — would read as a healthy, fast pipeline.
 */
import { Badge, type Severity } from '../../../components/ui';
import { formatMilliseconds, formatRate } from '../../../lib/format';
import type { StageHealth, StageStatus } from '../pipeline';

const STATUS_BADGE: Record<
  StageStatus,
  { tone: Severity | 'neutral'; label: string; glyph: string }
> = {
  ok: { tone: 'benign', label: 'within budget', glyph: '\u25CF' },
  degraded: { tone: 'critical', label: 'over budget', glyph: '\u25CF' },
  unmeasured: { tone: 'neutral', label: 'latency not measured', glyph: '\u25CB' },
};

export interface PipelineStripProps {
  stages: readonly StageHealth[];
  /** Whether a second scrape has arrived to compute rates from. */
  hasRates: boolean;
  /** Dependency probes from `/readyz`, when they could be read. */
  probes?: { name: string; status: string; detail: string }[] | undefined;
}

/** One stage's numbers, each in its own words when it is absent. */
function measures(stage: StageHealth, hasRates: boolean): string[] {
  const { reading, spec } = stage;
  const parts: string[] = [];

  parts.push(
    reading.p95Ms === null
      ? `p95 not measured · budget ${formatMilliseconds(spec.budgetMs)} (${spec.budgetSource})`
      : `p95 ${formatMilliseconds(reading.p95Ms)} vs budget ${formatMilliseconds(spec.budgetMs)} (${spec.budgetSource})`,
  );

  parts.push(
    reading.throughputPerSecond === null
      ? hasRates
        ? 'throughput not measured'
        : 'throughput needs a second scrape'
      : formatRate(reading.throughputPerSecond, stage.spec.id === 'ingest' ? 'records' : 'events'),
  );

  if (reading.lag !== null) {
    parts.push(`lag ${reading.lag.toLocaleString('en-US')} records`);
  }

  return parts;
}

export function PipelineStrip({ stages, hasRates, probes }: PipelineStripProps) {
  return (
    <section
      aria-labelledby="pipeline-health"
      className="rounded-card border border-line bg-base p-4"
    >
      <h2 id="pipeline-health" className="text-h2">
        Detection pipeline health
      </h2>
      <p className="mt-1 text-caption text-muted">
        What each stage is doing right now. A quiet alert list with a red stage below means AEGIS is
        degraded, not that the estate is calm.
      </p>

      <ol className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {stages.map((stage) => {
          const badge = STATUS_BADGE[stage.status];
          return (
            <li key={stage.spec.id} className="rounded-input border border-line p-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-body font-semibold text-ink">{stage.spec.label}</h3>
                <Badge tone={badge.tone}>
                  <span aria-hidden="true">{badge.glyph} </span>
                  {badge.label}
                </Badge>
              </div>
              <p className="mt-1 text-caption text-muted">{stage.spec.covers}</p>
              <ul className="mt-1 flex flex-col gap-1">
                {measures(stage, hasRates).map((measure) => (
                  <li key={measure} className="text-caption tabular-nums text-ink">
                    {measure}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>

      <p className="mt-3 text-caption text-muted">
        Dependencies:{' '}
        {probes === undefined || probes.length === 0 ? (
          // The registry is empty in this build: nothing has registered a probe
          // yet, which is a fact about the build and not a healthy result.
          'no readiness probe is registered in this build'
        ) : (
          <span>{probes.map((probe) => `${probe.name} ${probe.status}`).join(' · ')}</span>
        )}
      </p>
    </section>
  );
}
