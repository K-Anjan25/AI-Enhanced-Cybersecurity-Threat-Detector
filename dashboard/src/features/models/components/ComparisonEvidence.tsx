/**
 * Recorded confusion matrix for one side of the version comparison (T-420).
 *
 * The matrix is read from that version's immutable eval@2 artifact. Its artifact and
 * field path stay visible beside it, and the component has explicit loading,
 * read-failure, no-run and older-report states; it never derives counts from scalar
 * metrics or turns a missing artifact into an empty matrix.
 */
import { ApiError } from '../../../api/client';
import type { EvaluationDetails } from '../../../api/models';
import { EmptyState, ErrorState, Skeleton } from '../../../components/ui';

export interface ComparisonEvidenceProps {
  side: string;
  modelId: string | null;
  evaluation: EvaluationDetails | null;
  loading: boolean;
  error: Error | null;
}

export function ComparisonEvidence({
  side,
  modelId,
  evaluation,
  loading,
  error,
}: ComparisonEvidenceProps) {
  const title =
    modelId === null ? `${side} · no version selected` : `${side} · ${modelId.slice(0, 12)}`;

  return (
    <section
      aria-label={`Evaluation evidence ${title}`}
      className="flex flex-col gap-3 rounded-card border border-line bg-surface p-4"
    >
      <h3 className="text-body font-semibold text-ink">{title}</h3>
      {modelId === null ? (
        <EmptyState
          title="Choose a model version"
          description="No evaluation artifact was requested."
        />
      ) : loading ? (
        <Skeleton lines={4} label={`${title} evaluation evidence is loading`} />
      ) : error !== null ? (
        error instanceof ApiError && error.status === 404 ? (
          <EmptyState
            title="No recorded evaluation for this version"
            description="The registry has no evaluation run attached to this model version, so its confusion matrix is unavailable."
          />
        ) : (
          <ErrorState
            message="Recorded evaluation evidence could not be read"
            detail="No confusion matrix is shown until its source run can be read."
          />
        )
      ) : evaluation === null ? (
        <EmptyState
          title="Confusion matrix unavailable"
          description="This recorded run has no eval@2 confusion matrix. Existing scalar metrics are shown separately; no matrix values are inferred."
        />
      ) : (
        <ConfusionView evaluation={evaluation} />
      )}
    </section>
  );
}

function ConfusionView({ evaluation }: { evaluation: EvaluationDetails }) {
  const matrix = evaluation.confusion;

  return (
    <div className="min-w-0">
      <h4 className="text-body-sm font-semibold text-ink">Confusion matrix</h4>
      <p className="mt-1 text-caption text-muted">
        Threshold {matrix.threshold.toFixed(2)} · {matrix.artifact} · field{' '}
        <code className="font-mono">{matrix.field}</code>
      </p>
      <table className="mt-2 w-full border-collapse text-body-sm">
        <caption className="sr-only">
          Confusion matrix at threshold {matrix.threshold.toFixed(2)} from {matrix.artifact}, field{' '}
          {matrix.field}
        </caption>
        <thead>
          <tr className="border-b border-line text-left text-caption text-muted">
            <th scope="col" className="px-2 py-2 font-medium">
              Actual
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Predicted threat
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Predicted benign
            </th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-line">
            <th scope="row" className="px-2 py-2 text-left font-medium text-ink">
              Threat
            </th>
            <td className="px-2 py-2 font-mono tabular-nums text-ink">{matrix.tp}</td>
            <td className="px-2 py-2 font-mono tabular-nums text-ink">{matrix.fn}</td>
          </tr>
          <tr className="border-b border-line">
            <th scope="row" className="px-2 py-2 text-left font-medium text-ink">
              Benign
            </th>
            <td className="px-2 py-2 font-mono tabular-nums text-ink">{matrix.fp}</td>
            <td className="px-2 py-2 font-mono tabular-nums text-ink">{matrix.tn}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
