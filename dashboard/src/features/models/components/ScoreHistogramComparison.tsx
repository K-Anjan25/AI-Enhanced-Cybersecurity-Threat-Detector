/**
 * Two overlaid, recorded score histograms for the version comparison (T-420).
 *
 * The API returns fixed, matching eval@2 probability bins. Counts are summed only
 * within each recorded bin for the plotted model distribution; a table preserves
 * the benign/threat counts for both runs. Threshold markers and the two run paths
 * are explicit. Missing, old or unreadable artifacts stop the chart rather than
 * supplying a plausible-looking zero distribution.
 */
import { scaleLinear } from 'd3-scale';

import { ApiError } from '../../../api/client';
import type { ScoreHistogram } from '../../../api/models';
import { EmptyState, ErrorState, Skeleton } from '../../../components/ui';

interface HistogramSide {
  modelId: string | null;
  histogram: ScoreHistogram | null;
  threshold: number | null;
  loading: boolean;
  error: Error | null;
}

export interface ScoreHistogramComparisonProps {
  left: HistogramSide;
  right: HistogramSide;
}

const SVG_WIDTH = 760;
const SVG_HEIGHT = 360;
const PLOT_LEFT = 72;
const PLOT_RIGHT = 24;
const PLOT_TOP = 24;
const PLOT_BOTTOM = 294;
const PLOT_WIDTH = SVG_WIDTH - PLOT_LEFT - PLOT_RIGHT;

export function ScoreHistogramComparison({ left, right }: ScoreHistogramComparisonProps) {
  const sides = [left, right] as const;
  const missingRun = sides.find(
    (side) =>
      side.modelId === null || (side.error instanceof ApiError && side.error.status === 404),
  );
  const failedRead = sides.find(
    (side) => side.error !== null && !(side.error instanceof ApiError && side.error.status === 404),
  );

  return (
    <section aria-labelledby="score-distribution-heading" className="border-t border-line p-4">
      <h3 id="score-distribution-heading" className="text-body font-semibold text-ink">
        Score-distribution comparison
      </h3>
      {left.loading || right.loading ? (
        <div className="mt-3">
          <Skeleton lines={5} label="Score-distribution comparison is loading" />
        </div>
      ) : missingRun !== undefined ? (
        <EmptyState
          title="Two recorded histograms are required"
          description={`${missingRun.modelId === null ? 'A selected version' : `Version ${missingRun.modelId.slice(0, 12)}`} has no recorded evaluation. No distribution is inferred.`}
        />
      ) : failedRead !== undefined ? (
        <ErrorState
          message="Recorded score histograms could not be read"
          detail="The comparison is withheld until both source runs can be read. No distribution is inferred."
        />
      ) : left.histogram === null || right.histogram === null ? (
        <EmptyState
          title="Score-distribution comparison unavailable"
          description="At least one recorded run has no eval@2 histogram, as with an older eval@1 artifact. The chart requires both runs and does not infer bins from scalar metrics."
        />
      ) : !isCompleteHistogram(left.histogram) || !isCompleteHistogram(right.histogram) ? (
        <ErrorState
          message="A recorded score histogram is incomplete"
          detail="The chart requires ten fixed-width, valid, non-empty probability bins over the full [0, 1] range. No partial distribution is drawn."
        />
      ) : left.threshold === null ||
        right.threshold === null ||
        !isProbability(left.threshold) ||
        !isProbability(right.threshold) ? (
        <ErrorState
          message="The operating threshold is missing"
          detail="Both recorded thresholds are required to mark the overlaid distributions."
        />
      ) : !sameBins(left.histogram, right.histogram) ? (
        <ErrorState
          message="The score histograms use incompatible bins"
          detail="The two recorded distributions are not plotted on a shared axis."
        />
      ) : (
        <HistogramOverlay left={left} right={right} />
      )}
    </section>
  );
}

function isProbability(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

function isCompleteHistogram(histogram: ScoreHistogram): boolean {
  if (
    !Array.isArray(histogram.bins) ||
    histogram.bins.length !== 10 ||
    typeof histogram.artifact !== 'string' ||
    histogram.artifact.trim() === '' ||
    typeof histogram.field !== 'string' ||
    histogram.field.trim() === ''
  ) {
    return false;
  }
  let total = 0;
  for (let index = 0; index < histogram.bins.length; index += 1) {
    const bin = histogram.bins[index];
    if (
      bin === undefined ||
      !isProbability(bin.lower) ||
      !isProbability(bin.upper) ||
      bin.lower >= bin.upper ||
      bin.lower !== index / 10 ||
      bin.upper !== (index + 1) / 10 ||
      !Number.isSafeInteger(bin.benign) ||
      bin.benign < 0 ||
      !Number.isSafeInteger(bin.threat) ||
      bin.threat < 0 ||
      (index > 0 && histogram.bins[index - 1]?.upper !== bin.lower)
    ) {
      return false;
    }
    total += bin.benign + bin.threat;
  }
  return histogram.bins[0]?.lower === 0 && histogram.bins[9]?.upper === 1 && total > 0;
}

function sameBins(left: ScoreHistogram, right: ScoreHistogram): boolean {
  return (
    left.bins.length === right.bins.length &&
    left.bins.every(
      (bin, index) =>
        bin.lower === right.bins[index]?.lower && bin.upper === right.bins[index]?.upper,
    )
  );
}

function HistogramOverlay({ left, right }: { left: HistogramSide; right: HistogramSide }) {
  // The enclosing states have checked both ids and histograms. Keep local checks so a
  // malformed JSON body cannot turn a missing series into a crash or fabricated zero.
  if (
    left.modelId === null ||
    right.modelId === null ||
    left.histogram === null ||
    right.histogram === null
  ) {
    return null;
  }

  const leftHistogram = left.histogram;
  const rightHistogram = right.histogram;
  const leftTotals = leftHistogram.bins.map((bin) => bin.benign + bin.threat);
  const rightTotals = rightHistogram.bins.map((bin) => bin.benign + bin.threat);
  const maxCount = Math.max(1, ...leftTotals, ...rightTotals);
  const xScale = scaleLinear()
    .domain([0, 1])
    .range([PLOT_LEFT, SVG_WIDTH - PLOT_RIGHT]);
  const yScale = scaleLinear().domain([0, maxCount]).range([PLOT_BOTTOM, PLOT_TOP]);
  const yTicks = [...new Set([0, Math.ceil(maxCount / 2), maxCount])];
  const binWidth = PLOT_WIDTH / leftHistogram.bins.length;
  const barWidth = binWidth * 0.78;
  const leftLabel = `A · ${left.modelId.slice(0, 12)}`;
  const rightLabel = `B · ${right.modelId.slice(0, 12)}`;

  return (
    <div className="mt-3 flex flex-col gap-3">
      <p className="text-caption text-muted">
        Overlaid total scores per bin (benign + threat); exact class counts are tabulated below.
      </p>
      <p className="text-caption text-muted">
        {leftLabel}: {leftHistogram.artifact} · field{' '}
        <code className="font-mono">{leftHistogram.field}</code>
        {' · '}
        {rightLabel}: {rightHistogram.artifact} · field{' '}
        <code className="font-mono">{rightHistogram.field}</code>
      </p>
      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${String(SVG_WIDTH)} ${String(SVG_HEIGHT)}`}
          width={SVG_WIDTH}
          height={SVG_HEIGHT}
          role="img"
          aria-labelledby="score-histogram-title score-histogram-description"
          className="max-w-none"
        >
          <title id="score-histogram-title">Overlaid score histograms for two model versions</title>
          <desc id="score-histogram-description">
            {`Probability score from 0 to 1. ${leftLabel} is accent and ${rightLabel} is blue. Solid and dashed lines mark each recorded operating threshold.`}
          </desc>
          {yTicks.map((tick) => {
            const y = yScale(tick);
            return (
              <g key={`y-${String(tick)}`}>
                <line
                  x1={PLOT_LEFT}
                  x2={SVG_WIDTH - PLOT_RIGHT}
                  y1={y}
                  y2={y}
                  stroke="var(--color-border)"
                  strokeWidth="1"
                />
                <text
                  x={PLOT_LEFT - 10}
                  y={y + 4}
                  textAnchor="end"
                  fill="var(--color-text-muted)"
                  fontSize="12"
                >
                  {tick}
                </text>
              </g>
            );
          })}
          {leftHistogram.bins.map((bin, index) => {
            const x = xScale(bin.lower) + (binWidth - barWidth) / 2;
            const count = leftTotals[index] ?? 0;
            const y = yScale(count);
            const height = PLOT_BOTTOM - y;
            return (
              <rect
                key={`a-${bin.lower}-${bin.upper}`}
                x={x}
                y={y}
                width={barWidth}
                height={height}
                fill="var(--color-accent)"
                fillOpacity="0.55"
                stroke="var(--color-accent)"
                strokeWidth="1"
              >
                <title>{`${leftLabel}: ${count} scores from ${bin.lower.toFixed(1)} to ${bin.upper.toFixed(1)}`}</title>
              </rect>
            );
          })}
          {rightHistogram.bins.map((bin, index) => {
            const x = xScale(bin.lower) + (binWidth - barWidth) / 2;
            const count = rightTotals[index] ?? 0;
            const y = yScale(count);
            const height = PLOT_BOTTOM - y;
            return (
              <rect
                key={`b-${bin.lower}-${bin.upper}`}
                x={x}
                y={y}
                width={barWidth}
                height={height}
                fill="var(--severity-low)"
                fillOpacity="0.55"
                stroke="var(--severity-low)"
                strokeWidth="1"
              >
                <title>{`${rightLabel}: ${count} scores from ${bin.lower.toFixed(1)} to ${bin.upper.toFixed(1)}`}</title>
              </rect>
            );
          })}
          {left.threshold === null ? null : (
            <line
              x1={xScale(left.threshold)}
              x2={xScale(left.threshold)}
              y1={PLOT_TOP}
              y2={PLOT_BOTTOM}
              stroke="var(--color-accent)"
              strokeWidth="2"
            />
          )}
          {right.threshold === null ? null : (
            <line
              x1={xScale(right.threshold)}
              x2={xScale(right.threshold)}
              y1={PLOT_TOP}
              y2={PLOT_BOTTOM}
              stroke="var(--severity-low)"
              strokeWidth="2"
              strokeDasharray="5 4"
            />
          )}
          <line
            x1={PLOT_LEFT}
            x2={SVG_WIDTH - PLOT_RIGHT}
            y1={PLOT_BOTTOM}
            y2={PLOT_BOTTOM}
            stroke="var(--color-text-muted)"
            strokeWidth="1"
          />
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map((score) => {
            const x = xScale(score);
            return (
              <text
                key={score}
                x={x}
                y={PLOT_BOTTOM + 20}
                textAnchor="middle"
                fill="var(--color-text-muted)"
                fontSize="12"
              >
                {score.toFixed(1)}
              </text>
            );
          })}
          <text
            x={(PLOT_LEFT + SVG_WIDTH - PLOT_RIGHT) / 2}
            y={SVG_HEIGHT - 14}
            textAnchor="middle"
            fill="var(--color-text-primary)"
            fontSize="13"
          >
            Model score (probability)
          </text>
          <text
            x="18"
            y={(PLOT_TOP + PLOT_BOTTOM) / 2}
            textAnchor="middle"
            transform={`rotate(-90 18 ${(PLOT_TOP + PLOT_BOTTOM) / 2})`}
            fill="var(--color-text-primary)"
            fontSize="13"
          >
            Examples per bin
          </text>
        </svg>
      </div>
      <div className="flex flex-wrap gap-4 text-caption text-muted">
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="size-3 rounded-sm bg-accent" />
          {leftLabel}
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="size-3 rounded-sm bg-severity-low" />
          {rightLabel}
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="w-4 border-t-2 border-accent" />A threshold{' '}
          {left.threshold === null ? 'unavailable' : left.threshold.toFixed(2)} (solid)
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden="true" className="w-4 border-t-2 border-severity-low border-dashed" />B
          threshold {right.threshold === null ? 'unavailable' : right.threshold.toFixed(2)} (dashed)
        </span>
      </div>
      <div className="w-full overflow-x-auto">
        <table className="min-w-max border-collapse text-body-sm">
          <caption className="sr-only">
            Per-bin recorded benign and threat score counts for both model versions
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-caption text-muted">
              <th scope="col" rowSpan={2} className="px-2 py-2 font-medium">
                Score interval
              </th>
              <th scope="colgroup" colSpan={3} className="px-2 py-2 text-center font-medium">
                {leftLabel}
              </th>
              <th scope="colgroup" colSpan={3} className="px-2 py-2 text-center font-medium">
                {rightLabel}
              </th>
            </tr>
            <tr className="border-b border-line text-left text-caption text-muted">
              {['Total', 'Benign', 'Threat', 'Total', 'Benign', 'Threat'].map((label, index) => (
                <th
                  key={`${index}-${label}`}
                  scope="col"
                  className="px-2 py-2 text-right font-medium"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {leftHistogram.bins.map((bin, index) => {
              const other = rightHistogram.bins[index];
              if (other === undefined) return null;
              return (
                <tr key={`${bin.lower}-${bin.upper}`} className="border-b border-line">
                  <th
                    scope="row"
                    className="whitespace-nowrap px-2 py-2 text-left font-mono font-normal text-ink"
                  >
                    {bin.lower.toFixed(1)}–{bin.upper.toFixed(1)}
                    {index === leftHistogram.bins.length - 1 ? ' (includes 1.0)' : ''}
                  </th>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {bin.benign + bin.threat}
                  </td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {bin.benign}
                  </td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {bin.threat}
                  </td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {other.benign + other.threat}
                  </td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {other.benign}
                  </td>
                  <td className="px-2 py-2 text-right font-mono tabular-nums text-ink">
                    {other.threat}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
