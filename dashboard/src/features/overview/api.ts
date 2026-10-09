/**
 * The overview page's data sources.
 *
 * Three of them, and each one is a documented decision rather than a convenience:
 *
 *   * **`GET /api/v1/overview`** (T-416) answers the tiles, the series, the entity
 *     list and the family mix in one read of one window. It replaced a client-side
 *     walk of `GET /api/v1/alerts` pages (T-305): the walk could only ever count
 *     what it had read, so past its cap the screen showed a number it described as
 *     partial, and three panels derived from three walks could disagree about the
 *     same window. The server aggregates where the rows are, so the counts are the
 *     window's counts and the entity list carries the host or user value.
 *   * **`/metrics`** is where the pipeline strip gets its numbers: the same
 *     exposition Prometheus scrapes, parsed in `src/lib/prometheus.ts`. It is
 *     unauthenticated by decision (D-050) and carries no content, only counts. The
 *     fetch moved to `src/api/metrics.ts` when the drift screen became its second
 *     reader (T-409): a feature may not import another feature, and two copies of
 *     the path would be two things to keep in step.
 *   * **`/readyz`** answers the one question metrics cannot: whether a dependency
 *     the process needs is currently refused.
 *
 * The bounded window walk still exists for the screens that list alerts
 * (`src/api/alerts.ts`, read by triage and the traffic explorer); the overview no
 * longer imports it, which is why the re-export that used to be here is gone.
 */
import type { AlertPage, AlertRow } from '../../api/alerts';
import { getJson, query } from '../../api/client';

// The alert row and page shapes still live in `src/api/alerts.ts` (T-305), because
// triage and the traffic explorer read them too and two copies of a wire field name
// is one copy too many. Re-exported here because this module is where the overview
// reads them from -- and only the *types*: the overview no longer walks pages.
export type { AlertPage, AlertRow };

/** One entity in the window, named where the registry could name it. */
export interface OverviewEntity {
  entity_id: number;
  /** The entity's kind — ``host``, ``user`` … — or ``null`` when unnamed. */
  kind: string | null;
  value: string | null;
  /** Whether ``kind``/``value`` are real. A client must not infer it from null. */
  named: boolean;
  alerts: number;
  occurrences: number;
  open: number;
  worst_severity: string;
  max_score: number;
  last_seen: string;
}

/** One threat family's share of the window. */
export interface OverviewFamily {
  family: string;
  alerts: number;
  worst_severity: string;
}

/** One bucket of the severity series. */
export interface OverviewBucket {
  start: string;
  total: number;
  by_severity: Record<string, number>;
}

/** The window's complete counts (T-416's `OverviewTotals`). */
export interface OverviewTotals {
  alerts: number;
  open: number;
  by_severity: Record<string, number>;
  unrecognised_severity: number;
  verdicts: Record<string, number>;
  unrecorded: number;
  verdicts_measured: number;
  mean_time_to_verdict_seconds: number | null;
}

/** Everything the overview's panels read, from one request (FR-50). */
export interface Overview {
  window: { start: string; end: string; hours: number };
  bucket_minutes: number;
  totals: OverviewTotals;
  series: OverviewBucket[];
  entities: OverviewEntity[];
  /** Whether the window held more entities than the list shows. */
  entities_capped: boolean;
  families: OverviewFamily[];
  families_capped: boolean;
}

export interface OverviewRequest {
  /** Inclusive lower bound of the window (R-34). */
  start: Date | string;
  /** Exclusive upper bound of the window (R-34). */
  end: Date | string;
  bucketMinutes: number;
  entityLimit: number;
  signal?: AbortSignal | undefined;
}

/**
 * Read one window's aggregate.
 *
 * `start` and `end` are required by the route for the same reason the alert list's
 * are (R-34): an aggregate over a partitioned table with no time predicate is the
 * unbounded scan the rule names.
 */
export async function fetchOverview(request: OverviewRequest): Promise<Overview> {
  const path = `/api/v1/overview${query({
    start: request.start instanceof Date ? request.start.toISOString() : request.start,
    end: request.end instanceof Date ? request.end.toISOString() : request.end,
    bucket_minutes: request.bucketMinutes,
    entity_limit: request.entityLimit,
  })}`;
  return getJson<Overview>(path, { signal: request.signal });
}

/** One dependency probe from `/readyz` (T-301/T-317's shape). */
export interface ProbeCheck {
  name: string;
  status: 'ok' | 'degraded' | 'unavailable';
  detail: string;
}

export interface Readiness {
  status: 'ready' | 'not_ready';
  service: string;
  version: string;
  checks: ProbeCheck[];
}

/**
 * Read the readiness probes.
 *
 * A 503 is a valid answer here, not an error: `/readyz` serves "not ready" with a
 * body naming the dependency that is down, and throwing that away would leave the
 * strip able to say *something* is wrong but not *what*.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  return getJson<Readiness>('/readyz', { signal, okStatuses: [503] });
}

/** Detection engine status. */
export interface DetectionStatus {
  rule_engine?: {
    total_detections?: number;
    total_alerts?: number;
    buffer_size?: number;
    cycle_count?: number;
    last_cycle_alerts?: number;
    running?: boolean;
  };
  ml_consumer?: {
    windows_scored?: number;
    scoring_errors?: number;
    alerts_created?: number;
    buffer_size?: number;
  };
}

/** Read the rule-based detection engine status. */
export async function fetchDetectionStatus(signal?: AbortSignal): Promise<DetectionStatus> {
  return getJson<DetectionStatus>('/api/v1/detection/status', { signal });
}
