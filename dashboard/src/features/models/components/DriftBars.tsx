/**
 * Drift bars (design.md §4.7, FR-32).
 *
 * "PSI per feature as horizontal bars with the 0.25 threshold marked; features over
 * threshold get a red bar and a 'retrain recommended' badge" — the acceptance
 * criterion is the marking, so the threshold is drawn on **every** bar rather than
 * described in a caption: a mark that appears only when something drifts cannot show
 * how close a stable feature is, and a reader comparing two features needs one scale.
 *
 * Three renderings that are deliberate:
 *
 *   * **A real table.** The bars are a visual encoding of a table that exists in the
 *     DOM, so a screen reader reads feature, value and state without a parallel
 *     "accessible version" that would be the one nobody tests.
 *   * **The state is a word, not a colour.** `RETRAIN_BADGE` renders as a badge and
 *     the value renders as text; the red fill is an addition, never the message
 *     (NFR-10, R-27).
 *   * **An empty scrape says why.** `view.absentNote` renders where the bars would be,
 *     naming the missing series and the task that wires it (T-421). A blank chart
 *     would read as "nothing is drifting", which is the opposite of "nothing measured".
 */
import { Badge, EmptyState, ErrorState, Skeleton } from '../../../components/ui';
import { formatStamp } from '../../../lib/format';
import { DRIFT_METRIC, DRIFT_THRESHOLD, RETRAIN_BADGE, type DriftView } from '../drift';

export interface DriftBarsProps {
  view: DriftView;
  /** When the scrape was read, in epoch milliseconds. */
  at: number | null;
  loading: boolean;
  error: Error | null;
}

export function DriftBars({ view, at, loading, error }: DriftBarsProps) {
  if (loading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        {[0, 1, 2, 3, 4].map((index) => (
          <Skeleton key={index} lines={1} />
        ))}
      </div>
    );
  }
  if (error !== null) {
    return (
      <ErrorState
        message="The scrape could not be read, so no PSI is shown."
        detail="The drift screen reads the same /metrics document Prometheus scrapes; a refused or unreachable scrape leaves it with nothing to draw."
      />
    );
  }
  if (view.absent) {
    return (
      <EmptyState title="No drift series in this scrape" description={view.absentNote ?? ''} />
    );
  }

  const thresholdPercent = `${String(view.thresholdFraction * 100)}%`;

  return (
    <div className="flex flex-col">
      <p className="px-4 pt-3 text-caption text-muted">
        {DRIFT_METRIC} for {view.bars.length} features, read{' '}
        {at === null ? 'not yet' : formatStamp(new Date(at).toISOString())} ·{' '}
        {view.drifting === 0
          ? 'none over the threshold'
          : `${String(view.drifting)} over the threshold`}{' '}
        · the 0.25 mark is drawn on every bar, and a feature past it is red with a “{RETRAIN_BADGE}”
        badge (FR-32).
      </p>
      <table className="w-full border-collapse text-body-sm">
        <caption className="sr-only">
          {`Population stability index per feature, from the ${DRIFT_METRIC} gauge, with FR-32's ${String(DRIFT_THRESHOLD)} threshold marked.`}
        </caption>
        <thead>
          <tr className="border-b border-line text-left text-caption text-muted">
            <th scope="col" className="px-4 py-2 font-medium">
              Feature
            </th>
            <th scope="col" className="w-1/2 px-4 py-2 font-medium">
              PSI (0 – {String(view.domainMax)})
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              Value
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              State
            </th>
          </tr>
        </thead>
        <tbody>
          {view.bars.map((bar) => (
            <tr key={bar.feature} className="border-b border-line">
              <th scope="row" className="px-4 py-2 text-left font-mono font-normal text-ink">
                {bar.feature}
              </th>
              <td className="px-4 py-2">
                <div className="relative h-2 rounded-input bg-surface" aria-hidden="true">
                  <div
                    className={
                      bar.drifting
                        ? 'h-2 rounded-input bg-severity-critical'
                        : 'h-2 rounded-input bg-severity-benign'
                    }
                    style={{ width: `${String(bar.fraction * 100)}%` }}
                  />
                  <div
                    data-testid="threshold-mark"
                    title={`FR-32 threshold ${String(DRIFT_THRESHOLD)}`}
                    className="absolute -top-1 h-4 w-px bg-muted"
                    style={{ left: thresholdPercent }}
                  />
                </div>
              </td>
              <td className="px-4 py-2 font-mono tabular-nums text-ink">{bar.valueText}</td>
              <td className="px-4 py-2">
                {bar.drifting ? (
                  <Badge tone="critical">{RETRAIN_BADGE}</Badge>
                ) : (
                  <span className="text-muted">within threshold</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
