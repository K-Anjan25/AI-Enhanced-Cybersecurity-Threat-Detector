/**
 * The model ops screens' data wiring (T-409).
 *
 * Three cadences, each chosen rather than defaulted:
 *
 *   * **The version table and its metrics are reads on demand.** A registry changes
 *     when somebody promotes something, which is minutes-to-weeks apart, so the list
 *     is not polled; a successful promotion invalidates it, which is the only event
 *     that can change it in the operator's own session.
 *   * **The drift scrape polls at the overview's chart cadence (15 s) and pauses in a
 *     hidden tab.** It is one small text document from the same `/metrics` endpoint
 *     the pipeline strip reads, and a dashboard left open overnight must not be a
 *     client hammering the API from a background tab.
 *   * **Promotion and rollback are mutations**, because they are actions with a
 *     pending state, a possible refusal (the server's answer, not a prediction) and a
 *     result the operator has to be told about — including the no-op case, where
 *     `changed=false` means the audit trail recorded nothing.
 *
 * Refusals are mapped to sentences here rather than in each panel, and the mapping is
 * status-keyed: the API's error bodies are not read (R-58 — a body echoes the request
 * and this client never parses one), so the status is the whole of what is known. A
 * 403 says which role the action needs; a 409 says which lifecycle rule refused the
 * move. Neither is invented from a token the dashboard cannot verify: the screen does
 * not know the operator's role, and guessing one would be a guess rendered as a rule.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import { fetchMetrics, type MetricsSnapshot } from '../../api/metrics';
import {
  fetchModelMetrics,
  fetchModels,
  promoteModel,
  rollbackModel,
  type ModelList,
  type ModelMetrics,
  type ModelTransition,
} from '../../api/models';
import { useDocumentVisible } from '../../components/hooks/polling';

/** The drift scrape's cadence: design.md §4.1's chart refresh, in seconds. */
export const DRIFT_REFRESH_MS = 15_000;

/** The registered versions. Three callers share one entry in the cache. */
export function useModels(): UseQueryResult<ModelList, Error> {
  return useQuery({
    queryKey: ['models', 'list'],
    queryFn: ({ signal }) => fetchModels({ signal }),
  });
}

/**
 * One version's recorded metrics.
 *
 * `enabled` is the caller's: the table only fetches for a version the operator asked
 * to inspect, because a registry with a long history would otherwise issue one
 * request per row to fill cards nobody is looking at.
 */
export function useModelMetrics(
  modelId: string | null,
  enabled = true,
): UseQueryResult<ModelMetrics, Error> {
  return useQuery({
    queryKey: ['models', 'metrics', modelId],
    queryFn: ({ signal }) => {
      if (modelId === null) throw new Error('metrics were requested without a version');
      return fetchModelMetrics(modelId, { signal });
    },
    enabled: enabled && modelId !== null,
  });
}

/** The scrape, parsed. Paused while the tab is hidden; keeps the last value while refetching. */
export function useDriftScrape(): UseQueryResult<MetricsSnapshot, Error> {
  const visible = useDocumentVisible();
  return useQuery({
    queryKey: ['models', 'drift'],
    queryFn: ({ signal }) => fetchMetrics(signal),
    refetchInterval: visible ? DRIFT_REFRESH_MS : false,
    placeholderData: keepPreviousData,
  });
}

/** Promote a version. Admin is the server's check; the refusal mapping is below. */
export function usePromoteModel(): UseMutationResult<
  ModelTransition,
  Error,
  { modelId: string; justification: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ modelId, justification }) => promoteModel(modelId, justification),
    onSuccess: () => {
      // The only thing that changes the table is a transition, and this was one.
      void client.invalidateQueries({ queryKey: ['models', 'list'] });
    },
  });
}

/** Reverse the most recent promotion of a kind. */
export function useRollbackModel(): UseMutationResult<
  ModelTransition,
  Error,
  { kind: string; reason: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, reason }) => rollbackModel(kind, reason),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['models', 'list'] });
    },
  });
}

/** A 403's sentence, per action, or the shared fallbacks. */
function refusalMessage(error: Error | null, action: 'promote' | 'rollback'): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 403) {
    return action === 'promote'
      ? 'Promoting needs the admin role. Your account does not have it, so nothing changed and the audit trail recorded nothing.'
      : 'Rolling back needs the admin role. Your account does not have it, so nothing changed and the audit trail recorded nothing.';
  }
  if (error instanceof ApiError && error.status === 401) {
    return 'The session is not authenticated, so the change was refused.';
  }
  if (error instanceof ApiError && error.status === 409) {
    return action === 'promote'
      ? 'The registry refused the move: a retired version is terminal (R-68), and a version with no training manifest cannot be promoted (R-63). The table says which rule applies.'
      : 'There is nothing to roll back to: no promotion of this kind has displaced a version yet.';
  }
  if (error instanceof ApiError && error.status === 404) {
    return 'That version is no longer in the registry. Reload the table and choose again.';
  }
  if (error instanceof ApiError && error.status === 400) {
    return 'The registry refuses floating ids such as “latest”; address a version by its own id (R-68).';
  }
  return action === 'promote'
    ? 'The promotion could not be made. Nothing was changed.'
    : 'The rollback could not be made. Nothing was changed.';
}

/** What a refused promotion says. `null` while nothing has been refused. */
export function promotionRefusalMessage(error: Error | null): string | null {
  return refusalMessage(error, 'promote');
}

/** What a refused rollback says. `null` while nothing has been refused. */
export function rollbackRefusalMessage(error: Error | null): string | null {
  return refusalMessage(error, 'rollback');
}

/**
 * Why a version's metric panel is empty, when it is.
 *
 * The listing deliberately carries no metrics; the metrics route answers 404 with a
 * message distinguishing "no run attached" from "no such model". The dashboard does
 * not read that body, so it says the first, which is the one that can reach this
 * screen: a 404 for an unknown id cannot arrive from a row the table just rendered.
 */
export function metricsAbsenceMessage(error: Error | null): string | null {
  if (error === null) return null;
  if (error instanceof ApiError && error.status === 404) {
    return 'This version has no recorded evaluation, so FR-31 has no numbers to show for it.';
  }
  if (error instanceof ApiError && error.status === 403) {
    return 'Reading model metrics needs a signed-in account with read access.';
  }
  return 'The metrics could not be read. The table still shows the registry as it was listed.';
}
