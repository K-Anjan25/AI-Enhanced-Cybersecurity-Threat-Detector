/**
 * Zone 4 — "Context" (design.md §4.3), including the trust hint.
 *
 * "The 'history on this family' hint is how the product earns trust: it tells the
 * analyst the model has been wrong here before." So the hint is not a footer or a
 * tooltip — it is a marked line in the panel, and it carries the counts it is
 * derived from: how many prior alerts there were, how many were reviewed, and how
 * many of those were false positives. An analyst can disagree with "2 of 3 reviewed
 * were false positives"; they cannot disagree with a warning triangle.
 *
 * The verdict history is here rather than in the bar because the bar states the
 * current decision and this panel is what a second analyst reads to understand how
 * the first one got there — including which record each verdict superseded.
 */
import { Card } from '../../../components/ui';
import { formatInstant } from '../../../lib/format';
import type { AlertDetail } from '../types';
import { contextFacts, familyHint } from '../view';
import { verdictLabel } from '../verdicts';

export function ContextPanel({ detail }: { detail: AlertDetail }) {
  const hint = familyHint(detail.family_history);
  const history = detail.verdict.history;

  return (
    <Card title="Context">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        {contextFacts(detail).map((fact) => (
          <div key={fact.label} className="flex flex-col">
            <dt className="text-caption text-muted">{fact.label}</dt>
            <dd className="font-mono text-body-sm text-ink">{fact.value}</dd>
          </div>
        ))}
      </dl>

      <p
        role="status"
        className={
          hint.tone === 'warn'
            ? 'mt-4 text-body-sm font-semibold text-severityText-medium'
            : 'mt-4 text-body-sm text-muted'
        }
      >
        {hint.tone === 'warn' ? (
          <span aria-hidden="true" className="mr-2">
            {'\u26A0'}
          </span>
        ) : null}
        {hint.text}
      </p>

      {history.length === 0 ? (
        <p className="mt-4 text-body-sm text-muted">No verdict has been recorded on this alert.</p>
      ) : (
        <ol className="mt-4 flex flex-col gap-2">
          {history.map((record) => (
            <li key={record.id} className="text-body-sm text-ink">
              <span className="font-mono">{formatInstant(record.at)}</span> ·{' '}
              {verdictLabel(record.verdict)} · {record.actor}
              {record.supersedes === null ? null : (
                <span className="text-muted"> (supersedes {record.supersedes})</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
