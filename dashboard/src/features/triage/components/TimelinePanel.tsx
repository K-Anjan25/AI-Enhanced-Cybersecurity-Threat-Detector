/**
 * Zone 2 — "Timeline" (design.md §4.3).
 *
 * The design's timeline is a flow-rate series with the anomaly score overlaid, and
 * that chart is T-406's (`Timeline`/`TimeSeriesChart`, design.md §6). What this
 * panel draws instead is the part of the timeline this task *can* support from the
 * detail response: the evidence windows on a span, the first anomalous one marked,
 * and the axis labelled with the instants it runs between.
 *
 * It says what it is not. An operator who has read §4.3 expects a chart, and a
 * panel that silently drew something else would be worse than one that names the
 * gap — the same rule as everywhere else here: a missing thing is stated, not
 * disguised. The positions are fractions of the span, so the marker at "first
 * anomalous window" is placed from the data rather than at the left edge.
 */
import { Card } from '../../../components/ui';
import { formatInstant } from '../../../lib/format';
import type { AlertDetail } from '../types';
import { timelineView } from '../view';

export function TimelinePanel({ detail }: { detail: AlertDetail }) {
  const view = timelineView(detail);

  return (
    <Card title="Timeline">
      {view.emptyLine === null ? (
        <>
          <div
            role="img"
            aria-label={`Evidence windows between ${view.spanLabel}`}
            className="relative h-10 border-b border-line"
          >
            {view.ticks.map((tick) => (
              <span
                key={tick.id}
                data-testid={`tick-${tick.id}`}
                title={`${tick.modality} · ${formatInstant(tick.at)}`}
                className="absolute bottom-0 h-6 w-2 -translate-x-1/2 bg-accent"
                style={{ left: `${String(Math.round(tick.fraction * 100))}%` }}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-body-sm text-muted">
            <span className="font-mono">{formatInstant(view.spanStart)}</span>
            <span className="font-mono">{formatInstant(view.spanEnd)}</span>
          </div>
        </>
      ) : (
        <p role="status" className="text-body-sm text-muted">
          {view.emptyLine}
        </p>
      )}

      {view.firstAnomaly === null ? null : (
        <p className="mt-2 text-body-sm text-ink">
          first anomalous window{' '}
          <span className="font-mono">{formatInstant(view.firstAnomaly)}</span>
        </p>
      )}

      <p className="mt-2 text-body-sm text-muted">
        Flow rate and anomaly score over this span arrive with the T-406 chart primitives; this
        panel plots the windows the alert kept.
      </p>
    </Card>
  );
}
