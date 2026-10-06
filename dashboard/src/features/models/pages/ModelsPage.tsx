/**
 * Model ops — `/models` (design.md §4.7, FR-30…FR-33).
 *
 * The screen answers two questions: *what is serving, and what did it score?* and
 * *how does a version replace another?* Everything else on the page exists to keep
 * those two honest:
 *
 *   * **What is serving leads.** One panel per active kind, with FR-31's metric cards
 *     and the run each number came from (R-74). A version whose evaluation is absent
 *     says so; a version whose metrics the listing omitted is fetched once.
 *   * **The table carries the rules.** A version that cannot be promoted shows the
 *     reason in its row (R-63's manifest, R-68's terminal `retired`) rather than a
 *     disabled button with no explanation.
 *   * **A change is announced and explained.** Promotion and rollback are mutations;
 *     the result is a toast, and the last transition also stays on the page as a
 *     sentence — a toast that disappears takes the answer with it. A no-op promotion
 *     (`changed=false`) says the audit trail recorded nothing, which is the part an
 *     operator would otherwise assume wrongly.
 *   * **What the read model cannot answer is named.** The comparison's confusion
 *     matrices and score histograms are T-420, and the drift screen is where PSI
 *     lives; both are linked or named rather than approximated here.
 *
 * The role check is the server's: this screen does not know the operator's role, and
 * a 403 is mapped to a sentence by `promotionRefusalMessage`/`rollbackRefusalMessage`
 * rather than predicted from a token the dashboard cannot verify.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button, Card, EmptyState, ErrorState, Skeleton, useToast } from '../../../components/ui';
import { formatStamp } from '../../../lib/format';
import type { ModelTransition } from '../../../api/models';
import { ComparePanel } from '../components/ComparePanel';
import { PromotionModal } from '../components/PromotionModal';
import { RollbackModal } from '../components/RollbackModal';
import { ServingMetrics } from '../components/ServingMetrics';
import { VersionTable } from '../components/VersionTable';
import {
  metricsAbsenceMessage,
  promotionRefusalMessage,
  rollbackRefusalMessage,
  useModelMetrics,
  useModels,
  usePromoteModel,
  useRollbackModel,
} from '../hooks';
import { rollbackKinds, transitionSentence, versionRows, type VersionRow } from '../versions';

/** Where the drift screen lives; design.md §4.7 puts it under model ops. */
export const DRIFT_PATH = '/models/drift';

export function ModelsPage() {
  const models = useModels();
  const rows = useMemo(() => versionRows(models.data?.items ?? []), [models.data]);
  const active = useMemo(() => rows.filter((row) => row.status === 'active'), [rows]);

  const [promotion, setPromotion] = useState<VersionRow | null>(null);
  const [rollback, setRollback] = useState<{ kind: string; label: string } | null>(null);
  const [lastTransition, setLastTransition] = useState<ModelTransition | null>(null);

  const promote = usePromoteModel();
  const rollbackRun = useRollbackModel();
  const toast = useToast();

  const kinds = rollbackKinds(rows);
  const promotionRefusal = promotionRefusalMessage(promote.error);
  const rollbackRefusal = rollbackRefusalMessage(rollbackRun.error);

  const submitPromotion = (modelId: string, justification: string): void => {
    promote.mutate(
      { modelId, justification },
      {
        onSuccess: (transition) => {
          setPromotion(null);
          setLastTransition(transition);
          toast('success', transitionSentence(transition));
        },
      },
    );
  };

  const submitRollback = (kind: string, reason: string): void => {
    rollbackRun.mutate(
      { kind, reason },
      {
        onSuccess: (transition) => {
          setRollback(null);
          setLastTransition(transition);
          toast('success', transitionSentence(transition));
        },
      },
    );
  };

  const header = (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-h1">Model ops</h1>
        <p className="mt-1 text-body text-muted">
          Which versions are registered, what each scored on its own recorded run, and how one
          replaces another. Promoting requires typing the version id (design.md §4.7).
        </p>
      </div>
      <Link className="text-body text-accent underline" to={DRIFT_PATH}>
        Feature drift (PSI) →
      </Link>
    </div>
  );

  if (models.isPending) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <Skeleton lines={6} label="Model registry" />
      </div>
    );
  }

  if (models.isError) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <ErrorState
          message="The model registry could not be read"
          detail="Nothing is shown rather than a stale table: a promotion offered from a list this screen cannot vouch for would be a guess with an admin action attached."
          action={
            <Button
              onClick={() => {
                void models.refetch();
              }}
            >
              Retry
            </Button>
          }
          retrying={models.isFetching}
        />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <EmptyState
          title="No model versions are registered"
          description="The registry is empty, so nothing can be promoted. Registering a version is a training-pipeline step (T-202/T-212), not something this screen does."
        />
      </div>
    );
  }

  const lastChange =
    lastTransition === null ? null : (
      <p className="text-body-sm text-muted" data-testid="last-transition">
        Last change: {transitionSentence(lastTransition)} at {formatStamp(lastTransition.at)} by{' '}
        {lastTransition.actor}.
      </p>
    );

  return (
    <div className="flex flex-col gap-4">
      {header}
      {lastChange}

      <div className="flex flex-col gap-4">
        {active.map((row) => (
          <ServingRow key={row.id} row={row} />
        ))}
      </div>

      <Card
        title="Registered versions"
        actions={
          kinds.length === 0 ? null : (
            <div className="flex gap-2">
              {kinds.map((kind) => (
                <Button
                  key={kind}
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setRollback({
                      kind,
                      label: kind === 'flow' ? 'Flow' : kind === 'log' ? 'Log' : kind,
                    });
                  }}
                >
                  Roll back {kind}
                </Button>
              ))}
            </div>
          )
        }
      >
        <VersionTable
          rows={rows}
          onPromote={(row) => {
            setPromotion(row);
          }}
        />
        <p className="px-4 py-3 text-caption text-muted">
          Promotion and rollback need the <code className="font-mono">admin</code> role, and both
          are audit records (FR-42): the justification and the reason stay on the version record,
          while the trail keeps the ids, the kind and the status.
        </p>
      </Card>

      <ComparePanel rows={rows} />

      <PromotionModal
        open={promotion !== null}
        row={promotion}
        incumbent={
          promotion === null
            ? null
            : (active.find((row) => row.kind === promotion.kind && row.id !== promotion.id) ?? null)
        }
        pending={promote.isPending}
        refusal={promotionRefusal}
        onClose={() => {
          promote.reset();
          setPromotion(null);
        }}
        onSubmit={submitPromotion}
      />

      <RollbackModal
        open={rollback !== null}
        kind={rollback?.kind ?? null}
        kindLabel={rollback?.label ?? ''}
        pending={rollbackRun.isPending}
        refusal={rollbackRefusal}
        onClose={() => {
          rollbackRun.reset();
          setRollback(null);
        }}
        onSubmit={submitRollback}
      />
    </div>
  );
}

/** One active version's metric cards, fetching the metrics the listing omitted. */
function ServingRow({ row }: { row: VersionRow }) {
  const needsFetch = row.version.metrics === null;
  const fetched = useModelMetrics(row.id, needsFetch);
  const metrics = row.version.metrics ?? fetched.data ?? null;
  const error = needsFetch ? (fetched.error ?? null) : null;

  return (
    <ServingMetrics
      kindLabel={row.kindLabel}
      metrics={metrics}
      loading={needsFetch && fetched.isFetching}
      error={error}
      absenceNote={
        error === null
          ? (metricsAbsenceMessage(null) ??
            'This version has no recorded evaluation attached to it.')
          : (metricsAbsenceMessage(error) ?? 'The metrics could not be read.')
      }
    />
  );
}
