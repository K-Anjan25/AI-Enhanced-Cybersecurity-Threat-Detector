/**
 * Metric cards for the version that is serving (design.md §4.7, FR-31).
 *
 * The design asks for "ROC-AUC, PR-AUC, precision, recall at the deployed threshold —
 * each with the value from the recorded eval run and the run date (R-74)". So a card
 * is a value **and** the run it was read from; there is no rendering path that shows
 * the number alone, because a card that printed it would be quoted without its
 * provenance the first time somebody screenshotted the screen.
 *
 * A version with no recorded evaluation is a state, not an empty grid: the panel says
 * so in a sentence, and says which of the two things is true (nothing recorded, or
 * nothing readable), because "no data" and "no run" lead to different actions.
 */
import { Card, ErrorState, Skeleton } from '../../../components/ui';
import type { ModelMetrics } from '../../../api/models';
import { metricPanel } from '../versions';

export interface ServingMetricsProps {
  /** The heading's subject, e.g. `Flow`. */
  kindLabel: string;
  metrics: ModelMetrics | null;
  loading: boolean;
  /** The failure that stopped the read, or `null` when it succeeded. */
  error: Error | null;
  /** The sentence explaining an absent read, mapped from the error or the listing. */
  absenceNote: string;
}

export function ServingMetrics({
  kindLabel,
  metrics,
  loading,
  error,
  absenceNote,
}: ServingMetricsProps) {
  const panel = metricPanel(metrics);

  return (
    <Card title={`Serving now — ${kindLabel}`}>
      {loading ? (
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
          {[0, 1, 2, 3, 4].map((index) => (
            <Skeleton key={index} lines={2} />
          ))}
        </div>
      ) : error !== null ? (
        <ErrorState message={absenceNote} />
      ) : panel.absent ? (
        <p className="p-4 text-body text-muted">{absenceNote}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
            {panel.cards.map((card) => (
              <div key={card.name} className="rounded-card border border-line px-3 py-2">
                <p className="text-caption text-muted">{card.label}</p>
                <p className="mt-1 font-mono text-h2 tabular-nums text-ink">{card.valueText}</p>
                <p className="mt-1 text-caption text-muted">{card.provenance}</p>
              </div>
            ))}
          </div>
          <p className="px-4 pb-4 text-caption text-muted">{panel.caption}</p>
        </>
      )}
    </Card>
  );
}
