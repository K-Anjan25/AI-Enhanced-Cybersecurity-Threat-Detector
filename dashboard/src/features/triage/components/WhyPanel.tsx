/**
 * Zone 1 — "Why we flagged this" (design.md §4.3).
 *
 * The two states this panel exists to keep apart:
 *
 *   * **reasons.** Rendered in the order the model ranked them, with a plain
 *     statement that this payload carries no contribution weights. design.md draws
 *     a bar beside each reason; drawing one from a number nobody sent would be a
 *     fabricated ranking, and this panel's whole job is to be believable.
 *   * **`explanation_unavailable`.** Rendered with the reason it is missing (R-70).
 *     An explanation that failed must never look like an alert with nothing to
 *     explain, and the marker is the state's *name*, on screen, not a comment in
 *     the code — an analyst comparing this alert against a runbook needs the same
 *     word the runbook uses.
 *
 * §8.1's "partial evidence" case is labelled here too: some reasons and a missing
 * modality is a third state, and it must not read as complete.
 */
import { Card } from '../../../components/ui';
import type { AlertDetail } from '../types';
import { evidenceWindowLabel, explanationView } from '../view';

export function WhyPanel({ detail }: { detail: AlertDetail }) {
  const view = explanationView(detail.explanation);
  const { models, evidence } = detail;
  const model = models.flow ?? models.log ?? 'not recorded';
  const window = evidenceWindowLabel(evidence);

  return (
    <Card title="Why we flagged this">
      {view.unavailable ? (
        <div role="status" className="flex flex-col gap-2 border border-severity-medium p-3">
          <p className="font-mono text-body-sm font-semibold text-severityText-medium">
            {view.headline}
          </p>
          <p className="text-body-sm text-muted">{view.reasonDetail}</p>
          {view.unavailableModalities.length === 0 ? null : (
            <p className="text-body-sm text-muted">
              No reasons from: {view.unavailableModalities.join(', ')}.
            </p>
          )}
        </div>
      ) : (
        <ol className="flex flex-col gap-2">
          {view.reasons.map((reason) => (
            <li key={reason} className="flex flex-col gap-1">
              <span className="font-mono text-body-sm text-ink">{reason}</span>
            </li>
          ))}
        </ol>
      )}

      {view.partialEvidence ? (
        <p className="mt-3 text-body-sm text-severityText-medium">
          partial evidence
          {view.unavailableModalities.length === 0
            ? ''
            : ` — ${view.unavailableModalities.join(', ')} unavailable`}
        </p>
      ) : null}

      {view.weightsNote === null ? null : (
        <p className="mt-3 text-body-sm text-muted">{view.weightsNote}</p>
      )}

      <p className="mt-3 text-body-sm text-muted">
        Model: {model} · evidence window: {window}
      </p>
    </Card>
  );
}
