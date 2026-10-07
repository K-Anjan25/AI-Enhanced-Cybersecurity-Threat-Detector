/**
 * Drift — `/models/drift` (design.md §4.7, FR-32).
 *
 * The page is deliberately thin, because the two decisions live in `drift.ts`: the
 * threshold comes from one number (FR-32's 0.25, pinned to the ml-service constant by
 * a test) and the bars are drawn on a domain derived from the data, so the threshold
 * mark keeps its meaning when a feature drifts far past it.
 *
 * The source is the scrape, not a JSON endpoint: PSI is published as
 * `aegis_drift_psi{feature}` (T-211, architecture.md §14) and the dashboard reads the
 * same `/metrics` document Prometheus scrapes — the overview's pipeline strip does
 * exactly this (D-060), so the two screens cannot disagree about a number.
 *
 * What the page says when there is no series matters as much as the bars: the gauge is
 * published by the drift job and nothing in the process serving `/metrics` observes it
 * yet (T-421), so on this build the honest rendering is the empty state naming that —
 * not an axis with nothing on it, which reads as "nothing is drifting".
 */
import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { Card } from '../../../components/ui';
import { DriftBars } from '../components/DriftBars';
import { DRIFT_METRIC, DRIFT_THRESHOLD, driftView } from '../drift';
import { useDriftScrape } from '../hooks';

export function DriftPage() {
  const scrape = useDriftScrape();
  const view = useMemo(() => driftView(scrape.data?.samples ?? []), [scrape.data]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1">Feature drift</h1>
          <p className="mt-1 text-body text-muted">
            Population stability index per feature, against FR-32&apos;s threshold of{' '}
            {String(DRIFT_THRESHOLD)}. A feature above it means the incoming distribution has moved
            away from the reference the model was fitted on, and the badge says what to do about it.
          </p>
        </div>
        <Link className="text-body text-accent underline" to="/models">
          ← Model ops
        </Link>
      </div>

      <Card title="Per-feature PSI">
        <DriftBars
          view={view}
          at={scrape.data?.at ?? null}
          loading={scrape.isPending}
          error={scrape.error ?? null}
        />
      </Card>

      <p className="text-caption text-muted">
        Read from the <code className="font-mono">/metrics</code> scrape, series{' '}
        <code className="font-mono">{DRIFT_METRIC}</code>, refreshed every 15 s while this tab is
        visible. The threshold and the comparison rule are the drift computation&apos;s own: a
        feature is over when its PSI is strictly greater than {String(DRIFT_THRESHOLD)} (T-211).
        Drift does not stop the pipeline and does not promote anything by itself — a retrain is a
        human decision, which is why the badge recommends rather than acts.
      </p>
    </div>
  );
}
