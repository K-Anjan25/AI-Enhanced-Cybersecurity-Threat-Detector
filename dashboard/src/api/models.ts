/**
 * The model ops API's wire shapes and paths (T-315's routes, read by T-409).
 *
 * One copy of the contract, in the `api` layer: the model ops screen is the only
 * feature that reads it today, and the rule that makes it a shared module anyway is
 * that a screen must not own a route it does not define. `GET /api/v1/models`,
 * `GET /api/v1/models/{id}/metrics`, `POST /api/v1/models/{id}/promote` and
 * `POST /api/v1/models/{kind}/rollback` are the backend's, and the shape of
 * `ModelOut` is the schema's, not this file's.
 *
 * Three things are rules rather than formatting:
 *
 *   * **A metric is never a bare number** (R-74). `MetricPoint` carries the value
 *     *and* the recorded run it was read from, and there is no client-side type that
 *     drops the provenance.
 *   * **Metrics are a separate read.** The listing omits them so a long history
 *     does not weigh down the version table; the per-version endpoint carries scalar
 *     metrics and, when the recorded artifact is eval@2, its confusion matrix and
 *     score histogram with their own provenance.
 *   * **A promotion and a rollback are one call each.** The justification and the
 *     reason travel in the body because both are required by the API
 *     (`min_length=1`), and a blank string is refused here as well as there: a
 *     request that the server can only answer with a 422 is not worth sending.
 */
import { getJson, postJson, query } from './client';

/** One recorded metric value, beside the run it came from (R-74). */
export interface MetricPoint {
  value: number;
  /** The recorded run the value was read from, e.g. `runs/flownet/2026-09-30.json`. */
  artifact: string;
  /** Where inside that artifact, e.g. `test.roc_auc`. */
  field: string;
}

/** FR-31's metrics for one version, on the split they were measured on. */
export interface ConfusionMatrix {
  /** Operating point used to count the four cells. */
  threshold: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  /** The immutable recorded evaluation run this matrix came from. */
  artifact: string;
  /** Field path in that run; never inferred from scalar metrics. */
  field: string;
}

export interface ScoreHistogramBin {
  /** Lower-inclusive boundary; the final bin also includes 1.0. */
  lower: number;
  upper: number;
  benign: number;
  threat: number;
}

export interface ScoreHistogram {
  bins: ScoreHistogramBin[];
  artifact: string;
  field: string;
}

export interface EvaluationDetails {
  confusion: ConfusionMatrix;
  score_histogram: ScoreHistogram;
}

export interface ModelMetrics {
  split: string;
  /** When the evaluation ran — the date a reader quotes with the number (R-74). */
  evaluated_at: string;
  /** Keyed by the harness's own metric names: precision, recall, f1, roc_auc, pr_auc. */
  metrics: Record<string, MetricPoint>;
  /** Null for older recorded eval@1 runs, never synthesized from scalar values. */
  evaluation: EvaluationDetails | null;
}

/** One registered model version (`ModelOut`). */
export interface ModelVersion {
  model_id: string;
  kind: string;
  status: string;
  artifact_uri: string;
  sha256: string;
  /** False means R-63 refuses its promotion. */
  manifest_present: boolean;
  promoted_at: string | null;
  promoted_by: string | null;
  justification: string;
}

export interface ModelList {
  items: ModelVersion[];
  count: number;
}

/** What a promotion or a rollback changed (`ModelTransitionOut`). */
export interface ModelTransition {
  model_id: string;
  kind: string;
  status: string;
  /** The version that stepped down, if any — what a rollback will need next. */
  retired: string | null;
  /** False when the version was already serving: nothing moved, nothing was audited. */
  changed: boolean;
  at: string;
  actor: string;
}

export interface ModelListParams {
  kind?: string | undefined;
  status?: string | undefined;
  signal?: AbortSignal | undefined;
}

/** `GET /api/v1/models`. */
export const MODELS_PATH = '/api/v1/models';

/** `GET /api/v1/models/{model_id}/metrics`. */
export function modelMetricsPath(modelId: string): string {
  return `${MODELS_PATH}/${encodeURIComponent(modelId)}/metrics`;
}

/** `POST /api/v1/models/{model_id}/promote` — one call, admin-only (FR-33). */
export function promotePath(modelId: string): string {
  return `${MODELS_PATH}/${encodeURIComponent(modelId)}/promote`;
}

/** `POST /api/v1/models/{kind}/rollback` — addressed by kind, not by version. */
export function rollbackPath(kind: string): string {
  return `${MODELS_PATH}/${encodeURIComponent(kind)}/rollback`;
}

/** The registered versions, newest first as the API orders them. */
export async function fetchModels(params: ModelListParams = {}): Promise<ModelList> {
  const { kind, status, signal } = params;
  return getJson<ModelList>(`${MODELS_PATH}${query({ kind, status })}`, { signal });
}

/**
 * One version's recorded metrics.
 *
 * A version that is registered but unmeasured answers 404 with a body saying so
 * (T-315) — an absence that is a fact about the model, not a failed read, which is
 * why the caller distinguishes it from a network error instead of the client hiding
 * it.
 */
export async function fetchModelMetrics(
  modelId: string,
  options: { signal?: AbortSignal | undefined } = {},
): Promise<ModelMetrics> {
  return getJson<ModelMetrics>(modelMetricsPath(modelId), options);
}

/** Make a version active and retire the incumbent, in one call. */
export async function promoteModel(
  modelId: string,
  justification: string,
): Promise<ModelTransition> {
  return postJson<ModelTransition>(promotePath(modelId), { justification });
}

/** Reverse the most recent promotion of a kind, in one call, with a reason. */
export async function rollbackModel(kind: string, reason: string): Promise<ModelTransition> {
  return postJson<ModelTransition>(rollbackPath(kind), { reason });
}
