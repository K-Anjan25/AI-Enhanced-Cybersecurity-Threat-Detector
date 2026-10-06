/**
 * @vitest-environment node
 */
/**
 * The pipeline strip's arithmetic and — more importantly — its budgets.
 *
 * The budgets are the acceptance criterion ("degraded pipeline stages render red
 * with the exceeded budget"), so the first test reads architecture.md and prd.md
 * and asserts the constants here equal what those documents publish. A budget
 * edited in the prose and not in the code fails this test rather than quietly
 * comparing against a stale number.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { parseExposition } from '../../lib/prometheus';
import { INGEST_ROUTE, readPipeline, STAGES, worstStatus, type MetricsSnapshot } from './pipeline';

const REPO = fileURLToPath(new URL('../../../../', import.meta.url));
const architecture = readFileSync(`${REPO}architecture.md`, 'utf8');
const prd = readFileSync(`${REPO}prd.md`, 'utf8');
const design = readFileSync(`${REPO}design.md`, 'utf8');

/** The §5 latency budget table, as {stage: ms}. */
function documentedBudgets(): Record<string, number> {
  const section = architecture.slice(
    architecture.indexOf('**Latency budget**'),
    architecture.indexOf('## 6. Data model'),
  );
  const budgets: Record<string, number> = {};
  for (const line of section.split('\n')) {
    const match = /^\|\s*([^|]+?)\s*\|\s*(\d+)\s*ms\s*\|$/.exec(line);
    if (match !== null) budgets[(match[1] as string).trim()] = Number(match[2]);
  }
  return budgets;
}

const BASE = `aegis_flows_ingested_total{modality="flow"} 1000.0
aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="0.01"} 90.0
aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="0.05"} 95.0
aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="+Inf"} 100.0
# Another route, busier and far slower: if the ingest reading were not narrowed to
# its route, these buckets would drag its p95 from 50 ms to 475 ms.
aegis_http_request_duration_seconds_bucket{method="GET",route="/api/v1/alerts",le="0.5"} 1000.0
aegis_http_request_duration_seconds_bucket{method="GET",route="/api/v1/alerts",le="+Inf"} 1000.0
aegis_score_latency_seconds_bucket{le="0.05"} 50.0
aegis_score_latency_seconds_bucket{le="0.1"} 100.0
aegis_score_latency_seconds_bucket{le="+Inf"} 100.0
aegis_score_latency_seconds_count 100.0
aegis_alerts_created_total{severity="high"} 7.0
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="0"} 3.0
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="1"} 1500.0
`;

/** A scrape at `at`, with the ingest counter and request count scaled by `ticks`. */
function scrape(at: number, ingest: number): MetricsSnapshot {
  return {
    at,
    samples: parseExposition(
      BASE.replace(
        'aegis_flows_ingested_total{modality="flow"} 1000.0',
        `aegis_flows_ingested_total{modality="flow"} ${String(ingest)}.0`,
      ),
    ),
  };
}

describe('the published budgets', () => {
  const budgets = documentedBudgets();

  it('reads the budget table out of architecture.md §5', () => {
    // If this is empty the test below is vacuous, so it is asserted first.
    expect(Object.keys(budgets).length).toBeGreaterThanOrEqual(6);
  });

  it('uses the ingest budget the architecture publishes', () => {
    const ingest = STAGES.find((stage) => stage.id === 'ingest');
    expect(ingest?.budgetMs).toBe(budgets['Ingest validate + Kafka produce']);
  });

  it('uses the correlate and notify budgets the architecture publishes', () => {
    expect(STAGES.find((stage) => stage.id === 'correlate')?.budgetMs).toBe(
      budgets['Fusion + correlate + persist'],
    );
    expect(STAGES.find((stage) => stage.id === 'notify')?.budgetMs).toBe(
      budgets['WebSocket delivery'],
    );
  });

  it('uses NFR-01 for the score budget, which is published with its own wording', () => {
    const line = prd.split('\n').find((row) => row.startsWith('| NFR-01 |'));
    expect(line).toBeDefined();
    const published = /scoring latency ≤ (\d+) ms/.exec(line as string);
    expect(published).not.toBeNull();
    expect(STAGES.find((stage) => stage.id === 'score')?.budgetMs).toBe(
      Number((published as RegExpExecArray)[1]),
    );
  });

  it('names the source of every budget, so the strip can show it', () => {
    for (const stage of STAGES) {
      expect(stage.budgetSource, stage.id).toMatch(/architecture\.md §5|NFR-01/);
    }
  });
});

describe('readPipeline', () => {
  it('reads the ingest p95 from the HTTP histogram, on the ingest route only', () => {
    const stages = readPipeline(scrape(0, 1_000), null);
    const ingest = stages.find((stage) => stage.spec.id === 'ingest');

    // 95 of 100 requests came in at or under 50 ms.
    expect(ingest?.reading.p95Ms).toBeCloseTo(50, 3);
    expect(ingest?.status).toBe('degraded');
    expect(ingest?.shareOfBudget).toBeCloseTo(50 / 40, 3);
  });

  it('reads only the ingest route, not every route in the histogram', () => {
    // The /api/v1/alerts route in the fixture is both busier and ten times slower,
    // so an un-narrowed read would report 475 ms instead of 50 ms for ingest.
    const stages = readPipeline(scrape(0, 1_000), null);

    expect(stages.find((stage) => stage.spec.id === 'ingest')?.reading.p95Ms).toBeCloseTo(50, 3);
    expect(stages.find((stage) => stage.spec.id === 'ingest')?.status).toBe('degraded');
  });

  it('calls a stage exactly at its budget within budget, not over it', () => {
    // p95 lands on 40 ms exactly: 20 ms + (50 − 20) × (95 − 85) / (100 − 85).
    const atBudget =
      parseExposition(`aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="0.02"} 85.0
aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="0.05"} 100.0
aegis_http_request_duration_seconds_bucket{method="POST",route="${INGEST_ROUTE}",le="+Inf"} 100.0
`);

    const ingest = readPipeline({ at: 0, samples: atBudget }, null).find(
      (stage) => stage.spec.id === 'ingest',
    );

    expect(ingest?.reading.p95Ms).toBeCloseTo(40, 6);
    expect(ingest?.status).toBe('ok');
    expect(ingest?.shareOfBudget).toBeCloseTo(1, 6);
  });

  it('marks a stage within its budget ok', () => {
    const stages = readPipeline(scrape(0, 1_000), null);
    // Every one of the 100 score windows is at or under 100 ms, so the p95 is
    // interpolated inside that bucket: 95 ms, against a 150 ms budget.
    const score = stages.find((stage) => stage.spec.id === 'score');
    expect(score?.reading.p95Ms).toBeCloseTo(95, 3);
    expect(score?.status).toBe('ok');
  });

  it('reports lag as the worst partition, not the average', () => {
    // A single stuck partition is the incident; averaging it with the healthy ones
    // makes it disappear (T-306).
    const stages = readPipeline(scrape(0, 1_000), null);
    expect(stages.find((stage) => stage.spec.id === 'score')?.reading.lag).toBe(1_500);
  });

  it('says not measured for a stage nothing instruments', () => {
    const stages = readPipeline(scrape(0, 1_000), null);
    const notify = stages.find((stage) => stage.spec.id === 'notify');

    expect(notify?.reading.p95Ms).toBeNull();
    expect(notify?.status).toBe('unmeasured');
    expect(notify?.shareOfBudget).toBeNull();
  });

  it('leaves throughput unmeasured without a previous scrape, rather than zero', () => {
    // "0 flows/s" on a first render would read as an outage.
    const stages = readPipeline(scrape(10_000, 1_000), null);

    expect(
      stages.find((stage) => stage.spec.id === 'ingest')?.reading.throughputPerSecond,
    ).toBeNull();
  });

  it('differences the counter between two scrapes', () => {
    const stages = readPipeline(scrape(10_000, 1_300), scrape(0, 1_000));

    // 300 records in 10 s.
    expect(
      stages.find((stage) => stage.spec.id === 'ingest')?.reading.throughputPerSecond,
    ).toBeCloseTo(30, 6);
  });

  it('takes the correlate throughput from the alerts counter, and still calls its latency unmeasured', () => {
    const stages = readPipeline(scrape(10_000, 1_300), scrape(0, 1_000));
    const correlate = stages.find((stage) => stage.spec.id === 'correlate');

    // The counter did not move between the two scrapes, and a rate of zero is a
    // measurement — unlike the latency, which nothing times.
    expect(correlate?.reading.throughputPerSecond).toBe(0);
    expect(correlate?.reading.p95Ms).toBeNull();
    expect(correlate?.status).toBe('unmeasured');
  });

  it('survives an empty scrape by calling every stage unmeasured', () => {
    const stages = readPipeline({ at: 0, samples: [] }, null);

    expect(stages).toHaveLength(STAGES.length);
    expect(stages.every((stage) => stage.status === 'unmeasured')).toBe(true);
    expect(worstStatus(stages)).toBe('unmeasured');
  });

  it('summarises by the worst stage present', () => {
    expect(worstStatus(readPipeline(scrape(0, 1_000), null))).toBe('degraded');
    const ok = readPipeline(scrape(0, 1_000), null).map((stage) =>
      stage.spec.id === 'ingest' ? { ...stage, status: 'ok' as const } : stage,
    );
    expect(worstStatus(ok)).toBe('ok');
  });
});

describe('the design contract the strip renders', () => {
  it('uses the four stages design.md §4.1 names', () => {
    const section = design.slice(design.indexOf('### 4.1'), design.indexOf('### 4.2'));
    const named = [...section.matchAll(/ingest ▸ score ▸ correlate ▸ notify/gu)];
    expect(named).toHaveLength(1);
    expect(STAGES.map((stage) => stage.id)).toEqual(['ingest', 'score', 'correlate', 'notify']);
  });

  it('checks the ingest route the backend actually serves', () => {
    expect(INGEST_ROUTE).toBe('/api/v1/ingest/flows');
  });
});
