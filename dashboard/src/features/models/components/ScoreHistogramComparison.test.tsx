/**
 * The comparison histogram refuses missing or incompatible evidence and overlays only
 * the two recorded eval@2 distributions.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../../api/client';
import type { ScoreHistogram } from '../../../api/models';
import { expectAccessible } from '../../../test/axe';
import { ScoreHistogramComparison } from './ScoreHistogramComparison';

const COUNTS = [
  [0, 0],
  [1, 0],
  [0, 0],
  [0, 1],
  [1, 0],
  [0, 0],
  [0, 0],
  [0, 0],
  [0, 1],
  [0, 0],
] as const;

function histogram(artifact: string): ScoreHistogram {
  return {
    bins: COUNTS.map(([benign, threat], index) => ({
      lower: index / 10,
      upper: (index + 1) / 10,
      benign,
      threat,
    })),
    artifact,
    field: 'score_histogram',
  };
}

function side(modelId: string, artifact: string) {
  return {
    modelId,
    histogram: histogram(artifact),
    threshold: 0.5,
    loading: false,
    error: null,
  };
}

describe('ScoreHistogramComparison', () => {
  it('overlays both recorded runs, marks both thresholds, and keeps exact counts accessible', async () => {
    const { container } = render(
      <ScoreHistogramComparison
        left={side('flow-a', 'runs/flow-a/eval.json')}
        right={side('flow-b', 'runs/flow-b/eval.json')}
      />,
    );

    expect(screen.getByRole('img', { name: /Overlaid score histograms/ })).toBeInTheDocument();
    expect(screen.getByText(/A threshold 0\.50 \(solid\)/)).toBeInTheDocument();
    expect(screen.getByText(/B threshold 0\.50 \(dashed\)/)).toBeInTheDocument();
    expect(screen.getByText(/runs\/flow-a\/eval\.json/)).toBeInTheDocument();
    expect(screen.getByText(/runs\/flow-b\/eval\.json/)).toBeInTheDocument();
    const table = screen.getByRole('table', { name: /Per-bin recorded benign and threat/ });
    expect(
      within(table).getByRole('row', { name: /0\.3–0\.4.*1.*0.*1.*1.*0.*1/ }),
    ).toBeInTheDocument();
    await expectAccessible(container);
  });

  it('does not draw when a run is missing', () => {
    const missing = {
      modelId: 'flow-old',
      histogram: null,
      threshold: null,
      loading: false,
      error: new ApiError('status', 404, 'not found'),
    };
    render(<ScoreHistogramComparison left={side('flow-a', 'runs/a.json')} right={missing} />);

    expect(screen.getByText('Two recorded histograms are required')).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('refuses contiguous but variable-width bins instead of spacing them evenly', () => {
    const base = histogram('runs/flow-a/eval.json');
    const uneven: ScoreHistogram = {
      ...base,
      bins: base.bins.map((bin, index) =>
        index === 0 ? { ...bin, upper: 0.15 } : index === 1 ? { ...bin, lower: 0.15 } : bin,
      ),
    };
    render(
      <ScoreHistogramComparison
        left={{ ...side('flow-a', 'runs/flow-a/eval.json'), histogram: uneven }}
        right={side('flow-b', 'runs/flow-b/eval.json')}
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('A recorded score histogram is incomplete');
    expect(screen.getByRole('alert')).toHaveTextContent('ten fixed-width');
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('keeps eval@1 scalar-only runs visibly unavailable', () => {
    const older = {
      modelId: 'flow-old',
      histogram: null,
      threshold: null,
      loading: false,
      error: null,
    };
    render(<ScoreHistogramComparison left={side('flow-a', 'runs/a.json')} right={older} />);

    expect(screen.getByText('Score-distribution comparison unavailable')).toBeInTheDocument();
    expect(screen.getByText(/older eval@1 artifact/)).toBeInTheDocument();
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('does not show a partial chart when a read fails', () => {
    const failed = {
      ...side('flow-b', 'runs/b.json'),
      error: new ApiError('status', 503, 'private error detail'),
    };
    render(<ScoreHistogramComparison left={side('flow-a', 'runs/a.json')} right={failed} />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Recorded score histograms could not be read',
    );
    expect(screen.getByRole('alert')).not.toHaveTextContent('private error detail');
    expect(screen.queryByRole('img')).toBeNull();
  });
});
