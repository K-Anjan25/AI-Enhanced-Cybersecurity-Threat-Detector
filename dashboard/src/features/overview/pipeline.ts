/**
 * The detection pipeline strip (design.md §4.1, FR-50).
 *
 * "The pipeline health strip is a first-class element, not a footer. When AEGIS
 * itself is degraded the analyst must know that the quiet screen means *broken*,
 * not *safe*." That sentence is the whole design: the strip is the only place on
 * the overview that can tell an operator that an empty alert list is a fact about
 * the world rather than a fact about AEGIS.
 *
 * **Budgets come from the documents, not from this file.** Each stage names the
 * architecture.md §5 row(s) it covers, or the NFR that publishes its number, and
 * `pipeline.test.ts` parses those documents and asserts the constant here equals
 * what they say. A budget edited in the prose and not here fails the test rather
 * than quietly comparing against a stale number.
 *
 * **A stage with no measurement says so.** Three of the four stages have no
 * latency histogram today (there is no per-stage timer for correlation or
 * notification), so they render as *not measured* with their budget visible —
 * which is a statement about the system, and a much better one than a zero that
 * would read as "fast". R-74 is the same rule: never print a number no run backs.
 */
import {
  counterRate,
  type CounterSample,
  histogramP95Seconds,
  valueOf,
  type Sample,
  sumOf,
  samplesNamed,
} from '../../lib/prometheus';

export type StageId = 'ingest' | 'score' | 'correlate' | 'notify';

export type StageStatus =
  /** Measured, inside its budget. */
  | 'ok'
  /** Measured, over its budget. design.md §4.1: this stage renders red. */
  | 'degraded'
  /**
   * Nothing times this stage, so it cannot be compared against its budget. A stage
   * may still report throughput in this state; it is the *latency* that is missing,
   * and the strip says so rather than showing a zero that would read as "fast".
   */
  | 'unmeasured';

export interface StageSpec {
  id: StageId;
  label: string;
  /** What the stage covers, in architecture.md §5's words. */
  covers: string;
  /** The published p95 budget, in milliseconds. */
  budgetMs: number;
  /** Where that budget is published, for the tooltip and for the test. */
  budgetSource: string;
}

export const STAGES: readonly StageSpec[] = [
  {
    id: 'ingest',
    label: 'Ingest',
    covers: 'Ingest validate + Kafka produce',
    budgetMs: 40,
    budgetSource: 'architecture.md §5',
  },
  {
    id: 'score',
    label: 'Score',
    covers: 'windowing → feature extraction → transformer inference',
    budgetMs: 150,
    budgetSource: 'NFR-01',
  },
  {
    id: 'correlate',
    label: 'Correlate',
    covers: 'Fusion + correlate + persist',
    budgetMs: 30,
    budgetSource: 'architecture.md §5',
  },
  {
    id: 'notify',
    label: 'Notify',
    covers: 'WebSocket delivery',
    budgetMs: 20,
    budgetSource: 'architecture.md §5',
  },
];

/** The ingest route, as the HTTP histogram labels it (T-317). */
export const INGEST_ROUTE = '/api/v1/ingest/flows';

export interface MetricsSnapshot {
  /** When the scrape was read, in epoch milliseconds. */
  at: number;
  samples: readonly Sample[];
}

export interface StageReading {
  /** Measured p95 latency in milliseconds, or `null` when nothing measures it. */
  p95Ms: number | null;
  /** Events per second, or `null` when no counter covers the stage. */
  throughputPerSecond: number | null;
  /** Kafka records behind, or `null` when no lag gauge is published. */
  lag: number | null;
}

export interface StageHealth {
  spec: StageSpec;
  reading: StageReading;
  status: StageStatus;
  /** The reading as a fraction of the budget, or `null` when unmeasured. */
  shareOfBudget: number | null;
}

/** The worst partition's lag: a stuck partition must not average away (T-306). */
function worstLag(samples: readonly Sample[]): number | null {
  const lags = samplesNamed(samples, 'aegis_kafka_consumer_lag').map((sample) => sample.value);
  return lags.length === 0 ? null : Math.max(...lags);
}

/** p95 from a histogram, converted to milliseconds. */
function p95Ms(samples: readonly Sample[], name: string, labels = {}): number | null {
  const seconds = histogramP95Seconds(samples, name, labels);
  return seconds === null ? null : seconds * 1_000;
}

/** A counter's current total, for the next scrape to difference against. */
export function counterOf(samples: readonly Sample[], name: string): CounterSample['value'] | null {
  return sumOf(samplesNamed(samples, name));
}

/**
 * Read every stage from one scrape, using the previous scrape for rates.
 *
 * Without a previous scrape the rates are `null` rather than `0`: a first render
 * that claimed "0 flows/s" would look like an outage.
 */
export function readPipeline(
  current: MetricsSnapshot,
  previous: MetricsSnapshot | null,
): StageHealth[] {
  const { samples } = current;
  const before = previous?.samples ?? [];

  /** The rate of a counter, summed across its label values. */
  const rateOf = (name: string): number | null => {
    const now = sumOf(samplesNamed(samples, name));
    const then = sumOf(samplesNamed(before, name));
    if (now === null || then === null) return null;
    return counterRate(
      { at: previous?.at ?? current.at, value: then },
      { at: current.at, value: now },
    );
  };

  const readings: Record<StageId, StageReading> = {
    ingest: {
      p95Ms: p95Ms(samples, 'aegis_http_request_duration_seconds', { route: INGEST_ROUTE }),
      throughputPerSecond: rateOf('aegis_flows_ingested_total'),
      lag: null,
    },
    score: {
      p95Ms: p95Ms(samples, 'aegis_score_latency_seconds'),
      throughputPerSecond: rateOf('aegis_score_latency_seconds_count'),
      lag: worstLag(samples),
    },
    correlate: {
      p95Ms: null,
      throughputPerSecond: rateOf('aegis_alerts_created_total'),
      lag: null,
    },
    notify: {
      // Nothing counts or times a delivery yet: the webhook sender logs failures
      // and the socket hub keeps no counter. Recorded as a gap rather than
      // approximated from the alert counter.
      p95Ms: null,
      throughputPerSecond: null,
      lag: null,
    },
  };

  return STAGES.map((spec) => {
    const reading = readings[spec.id];
    const exceeded = reading.p95Ms !== null && reading.p95Ms > spec.budgetMs;
    return {
      spec,
      reading,
      status: reading.p95Ms === null ? 'unmeasured' : exceeded ? 'degraded' : 'ok',
      shareOfBudget: reading.p95Ms === null ? null : reading.p95Ms / spec.budgetMs,
    };
  });
}

/** The most serious stage status, for the strip's summary badge. */
export function worstStatus(stages: readonly StageHealth[]): StageStatus {
  if (stages.some((stage) => stage.status === 'degraded')) return 'degraded';
  if (stages.some((stage) => stage.status === 'ok')) return 'ok';
  return 'unmeasured';
}

/** The single number a summary line can honestly give: the alerts counter. */
export function alertsCreated(samples: readonly Sample[]): number | null {
  return valueOf(samples, 'aegis_alerts_created_total');
}
