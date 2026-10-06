import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { expectAccessible } from '../../../test/axe';
import { parseExposition } from '../../../lib/prometheus';
import { readPipeline, STAGES, type MetricsSnapshot } from '../pipeline';
import { PipelineStrip } from './PipelineStrip';

/**
 * Two scrapes: several ingest requests over the 40 ms budget, and a stuck Kafka
 * partition.
 */
function snapshots(): [MetricsSnapshot, MetricsSnapshot] {
  const exposure = (at: number, ingest: number, lag: number): MetricsSnapshot => ({
    at,
    samples: parseExposition(`aegis_flows_ingested_total{modality="flow"} ${String(ingest)}.0
aegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="0.05"} 90.0
aegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="0.25"} 100.0
aegis_http_request_duration_seconds_bucket{method="POST",route="/api/v1/ingest/flows",le="+Inf"} 100.0
aegis_score_latency_seconds_bucket{le="0.05"} 100.0
aegis_score_latency_seconds_bucket{le="+Inf"} 100.0
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="0"} 3.0
aegis_kafka_consumer_lag{group="scoring",topic="flows.raw",partition="1"} ${String(lag)}.0
`),
  });
  return [exposure(10_000, 1_200, 1_500), exposure(0, 1_000, 1_200)];
}

const [current, previous] = snapshots();

describe('PipelineStrip', () => {
  it('renders the four stages design.md §4.1 names, in pipeline order', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    const strip = screen.getByRole('region', { name: 'Detection pipeline health' });
    const names = within(strip)
      .getAllByRole('heading', { level: 3 })
      .map((heading) => heading.textContent);
    expect(names).toEqual(['Ingest', 'Score', 'Correlate', 'Notify']);
  });

  it('renders a stage over its budget as red AND says which budget it exceeded', () => {
    // The acceptance criterion, and NFR-09: colour is never the only encoding, so
    // the status is a word as well as a hue.
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    const ingest = screen.getByRole('heading', { level: 3, name: 'Ingest' }).closest('li');
    expect(ingest).not.toBeNull();

    // 90 of 100 requests at or under 50 ms, 100 at or under 250 ms: the p95 is
    // interpolated inside the top bucket, well past the 40 ms budget.
    expect(within(ingest as HTMLElement).getByText(/over budget/)).toBeInTheDocument();
    expect(
      within(ingest as HTMLElement).getByText(/p95 \d+ ms vs budget 40 ms/),
    ).toBeInTheDocument();
    expect(within(ingest as HTMLElement).getByText(/architecture\.md §5/)).toBeInTheDocument();
  });

  it('renders a stage inside its budget as within budget, with its numbers', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    const score = screen.getByRole('heading', { level: 3, name: 'Score' }).closest('li');
    expect(within(score as HTMLElement).getByText(/within budget/)).toBeInTheDocument();
    expect(within(score as HTMLElement).getByText(/budget 150 ms \(NFR-01\)/)).toBeInTheDocument();
  });

  it('reports the worst partition lag', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    expect(screen.getByText(/lag 1,500 records/)).toBeInTheDocument();
  });

  it('marks a stage nothing times as latency not measured, with its budget still shown', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    const notify = screen.getByRole('heading', { level: 3, name: 'Notify' }).closest('li');
    expect(within(notify as HTMLElement).getByText(/latency not measured/)).toBeInTheDocument();
    expect(
      within(notify as HTMLElement).getByText(/p95 not measured · budget 20 ms/),
    ).toBeInTheDocument();
  });

  it('says throughput needs a second scrape rather than showing zero', () => {
    render(<PipelineStrip stages={readPipeline(current, null)} hasRates={false} />);

    expect(screen.getAllByText(/throughput needs a second scrape/).length).toBeGreaterThan(0);
  });

  it('shows the rate between two scrapes', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    // 200 records in 10 s.
    expect(screen.getByText('20 records/s')).toBeInTheDocument();
  });

  it('says no readiness probe is registered rather than implying health', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates probes={[]} />);

    expect(screen.getByText(/no readiness probe is registered in this build/)).toBeInTheDocument();
  });

  it('lists the readiness probes when there are some', () => {
    render(
      <PipelineStrip
        stages={readPipeline(current, previous)}
        hasRates
        probes={[{ name: 'postgres', status: 'ok', detail: '' }]}
      />,
    );

    expect(screen.getByText(/postgres ok/)).toBeInTheDocument();
  });

  it('explains why a quiet alert list is not the same as a calm estate', () => {
    render(<PipelineStrip stages={readPipeline(current, previous)} hasRates />);

    expect(
      screen.getByText(/means AEGIS is degraded, not that the estate is calm/),
    ).toBeInTheDocument();
  });

  it('has no serious accessibility violations', async () => {
    const { container } = render(
      <PipelineStrip stages={readPipeline(current, previous)} hasRates probes={[]} />,
    );

    await expectAccessible(container as HTMLElement);
  });

  it('covers every stage, so a stage cannot silently disappear from the strip', () => {
    render(<PipelineStrip stages={readPipeline({ at: 0, samples: [] }, null)} hasRates={false} />);

    for (const stage of STAGES) {
      expect(screen.getByRole('heading', { level: 3, name: stage.label })).toBeInTheDocument();
    }
  });
});
