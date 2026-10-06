/**
 * @vitest-environment node
 */
/**
 * The Prometheus exposition parser and the quantile.
 *
 * These are the two functions every number on the pipeline strip passes through,
 * so they are tested against real exposition text — the shape `prometheus_client`
 * actually emits, including the `+Inf` bucket and the escapes — rather than against
 * a paraphrase of it.
 */
import { describe, expect, it } from 'vitest';

import {
  counterRate,
  histogramBuckets,
  histogramP95Seconds,
  histogramQuantile,
  parseExposition,
  samplesNamed,
  sumOf,
  valueOf,
} from './prometheus';

const EXPOSITION = `# HELP aegis_flows_ingested_total Records accepted by the ingest API.
# TYPE aegis_flows_ingested_total counter
aegis_flows_ingested_total{modality="flow"} 1200.0
aegis_flows_ingested_total{modality="log"} 300.0

# HELP aegis_score_latency_seconds Time the scoring worker spent waiting for one window's score.
# TYPE aegis_score_latency_seconds histogram
aegis_score_latency_seconds_bucket{le="0.005"} 0.0
aegis_score_latency_seconds_bucket{le="0.05"} 90.0
aegis_score_latency_seconds_bucket{le="0.1"} 95.0
aegis_score_latency_seconds_bucket{le="0.25"} 100.0
aegis_score_latency_seconds_bucket{le="+Inf"} 100.0
aegis_score_latency_seconds_sum 4.2
aegis_score_latency_seconds_count 100.0

# HELP aegis_kafka_consumer_lag Records a consumer group has yet to read, per partition.
# TYPE aegis_kafka_consumer_lag gauge
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="0"} 12.0
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="1"} 940.0

# HELP aegis_http_requests_total HTTP requests, by method, route template and status.
# TYPE aegis_http_requests_total counter
aegis_http_requests_total{method="POST",route="/api/v1/ingest/flows",status="202"} 41.0
`;

describe('parseExposition', () => {
  const samples = parseExposition(EXPOSITION);

  it('reads samples and leaves the comments behind', () => {
    expect(samples).toHaveLength(12);
    expect(samples.every((sample) => !sample.name.startsWith('#'))).toBe(true);
  });

  it('reads label sets', () => {
    const lag = samplesNamed(samples, 'aegis_kafka_consumer_lag');
    expect(lag).toHaveLength(2);
    expect(lag[0]?.labels).toEqual({ group: 'scoring', topic: 'flows.raw', partition: '0' });
  });

  it('keeps the +Inf bucket, because a quantile needs the total', () => {
    const buckets = histogramBuckets(samples, 'aegis_score_latency_seconds');
    expect(buckets.at(-1)?.le).toBe(Number.POSITIVE_INFINITY);
    expect(buckets.at(-1)?.cumulative).toBe(100);
  });

  it('refuses a line it cannot read instead of skipping it', () => {
    // A silently dropped series renders as "not measured", which is a claim about
    // the system; a parse error is a claim about the exposition.
    expect(() => parseExposition('aegis_flows_ingested_total{modality="flow"}')).toThrow(
      /not a sample/,
    );
  });

  it('unescapes label values', () => {
    const [sample] = parseExposition('aegis_x{detail="a \\"b\\" \\\\ c"} 1');
    expect(sample?.labels.detail).toBe('a "b" \\ c');
  });

  it('sums a counter across its label values and returns null with no series', () => {
    expect(sumOf(samplesNamed(samples, 'aegis_flows_ingested_total'))).toBe(1_500);
    expect(sumOf(samplesNamed(samples, 'aegis_nothing_total'))).toBeNull();
  });

  it('reads one series by label, and null when it was never observed', () => {
    expect(valueOf(samples, 'aegis_http_requests_total', { route: '/api/v1/ingest/flows' })).toBe(
      41,
    );
    expect(valueOf(samples, 'aegis_alerts_created_total')).toBeNull();
  });
});

describe('histogramQuantile', () => {
  const buckets = [
    { le: 0.005, cumulative: 0 },
    { le: 0.05, cumulative: 90 },
    { le: 0.1, cumulative: 95 },
    { le: 0.25, cumulative: 100 },
    { le: Number.POSITIVE_INFINITY, cumulative: 100 },
  ];

  it('interpolates inside the bucket that holds the rank', () => {
    // 95 alerts are at or below 100 ms; the 95th percentile is the last one in
    // that bucket, so the answer is the bucket's upper bound.
    expect(histogramQuantile(buckets, 0.95)).toBeCloseTo(0.1, 5);
    // The 50th percentile lands inside the 50 ms bucket, interpolated linearly
    // from the bucket below it: 5 ms + (50 ms − 5 ms) × (50 − 0) / (90 − 0).
    expect(histogramQuantile(buckets, 0.5)).toBeCloseTo(0.03, 6);
  });

  it('has no quantile for a histogram nobody observed', () => {
    // `0` would print as "0 ms" and read as "fast"; `null` prints as unmeasured.
    expect(histogramQuantile([{ le: 1, cumulative: 0 }], 0.95)).toBeNull();
    expect(histogramQuantile([], 0.95)).toBeNull();
  });

  it('bounds a rank that falls in the +Inf bucket by the last finite bound', () => {
    const tail = [
      { le: 0.1, cumulative: 1 },
      { le: Number.POSITIVE_INFINITY, cumulative: 10 },
    ];
    expect(histogramQuantile(tail, 0.95)).toBe(0.1);
  });

  it('reads the p95 of a named histogram straight off the exposition', () => {
    const samples = parseExposition(EXPOSITION);
    // 95 of 100 windows scored at or under 100 ms, so the p95 *is* 100 ms.
    expect(histogramP95Seconds(samples, 'aegis_score_latency_seconds')).toBeCloseTo(0.1, 6);
  });
});

describe('counterRate', () => {
  it('is a rate between two scrapes', () => {
    expect(counterRate({ at: 0, value: 100 }, { at: 10_000, value: 350 })).toBe(25);
  });

  it('is unmeasured without a previous scrape', () => {
    expect(counterRate(null, { at: 10_000, value: 350 })).toBeNull();
  });

  it('is unmeasured when no time passed, rather than infinite', () => {
    expect(counterRate({ at: 5, value: 1 }, { at: 5, value: 9 })).toBeNull();
  });

  it('is unmeasured after a reset, rather than negative', () => {
    // A restarted process resets its counters. A negative throughput on a health
    // strip reads as an incident; a hidden spike to zero reads as a lie.
    expect(counterRate({ at: 0, value: 900 }, { at: 10_000, value: 5 })).toBeNull();
  });
});
