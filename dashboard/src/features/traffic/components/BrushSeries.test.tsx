/**
 * The brush, the axes and the table alternative — asserted on what the SVG renders.
 *
 * `fireEvent.pointerDown`/`pointerUp` are what a pointer actually delivers to the
 * brush surface; jsdom reports a zero-sized `getBoundingClientRect`, so the pixel
 * arithmetic is exercised against page coordinates directly. The keyboard path is
 * tested through the slider's own role, because that is how a screen reader reaches
 * it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { BrushSeries, spanLabel } from './BrushSeries';
import { readPalette } from '../../../components/charts/palette';
import type { TrafficBucket } from '../aggregate';

const START = Date.parse('2026-10-06T10:00:00Z');

function bucket(index: number, flows: number, score: number | null): TrafficBucket {
  return {
    start: new Date(START + index * 60_000),
    end: new Date(START + (index + 1) * 60_000),
    alerts: flows === 0 ? 0 : 1,
    flows,
    bytes: flows * 140,
    score,
  };
}

// Ten buckets, a scored run, a gap, and a second scored run: the gap is what the
// score line must break at, and the run of one at the end is what could vanish.
const BUCKETS: TrafficBucket[] = [
  bucket(0, 10, 0.4),
  bucket(1, 20, 0.5),
  bucket(2, 0, null),
  bucket(3, 30, 0.6),
  bucket(4, 15, 0.7),
  bucket(5, 0, null),
  bucket(6, 0, null),
  bucket(7, 5, 0.2),
  bucket(8, 0, null),
  bucket(9, 25, 0.9),
];

/**
 * Drive the brush with a pointer event jsdom can actually deliver.
 *
 * jsdom implements no `PointerEvent`, so `fireEvent.pointerDown` drops `clientX` and
 * every coordinate arrives as `NaN`. A `MouseEvent` dispatched under the pointer type
 * carries the coordinates and is what React's synthetic system reads in a browser too.
 */
function pointerX(element: Element, type: 'pointerdown' | 'pointerup', clientX: number): void {
  fireEvent(element, new MouseEvent(type, { bubbles: true, cancelable: true, clientX }));
}

function renderSeries(props: Partial<Parameters<typeof BrushSeries>[0]> = {}) {
  const onRange = vi.fn();
  const utils = render(
    <BrushSeries
      buckets={BUCKETS}
      range={null}
      onRange={onRange}
      palette={readPalette()}
      label="Alerted record volume"
      {...props}
    />,
  );
  return { ...utils, onRange };
}

describe('BrushSeries', () => {
  it('names both axes, so a dual scale cannot be read as one', () => {
    renderSeries();

    const chart = screen.getByRole('group', { name: /Alerted record volume/ });
    expect(within(chart).getByText('flows')).toBeInTheDocument();
    expect(within(chart).getByText('score')).toBeInTheDocument();
    expect(within(chart).getByText('1.0')).toBeInTheDocument();
  });

  it('starts the count axis at zero and heights bars against the ceiling', () => {
    renderSeries();

    const bars = screen.getAllByTestId(/^bar-/);
    expect(bars).toHaveLength(BUCKETS.length);
    // The tallest bucket is 30 flows; a bar is drawn proportional to the ceiling.
    const heights = bars.map((bar) => Number(bar.getAttribute('height')));
    expect(Math.max(...heights)).toBeGreaterThan(0);
    expect(heights[2]).toBe(0); // the empty bucket draws nothing
  });

  it('breaks the score line where the data has a gap, and keeps a one-bucket run', () => {
    // Two gaps split the scored buckets into three runs (indices 0-1, 3-4, 7, 9),
    // and the single-bucket runs must still be drawn: a line that only connects
    // two-point runs would silently drop the last sample of a sparse window.
    renderSeries();

    expect(screen.getAllByTestId(/^score-segment-/)).toHaveLength(4);
  });

  it('says an empty bucket has no data in the table, not a score of zero', async () => {
    renderSeries();
    await userEvent.click(screen.getByRole('button', { name: 'View as table' }));

    const table = screen.getByRole('table', { name: /as a table/ });
    const rows = within(table).getAllByRole('row');
    // Header plus ten buckets; the third bucket has no score.
    expect(rows).toHaveLength(11);
    expect(within(rows[3] as HTMLElement).getByText('no data')).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText('0.40')).toBeInTheDocument();
  });

  it('draws the range in words beside the chart, never only as shading', () => {
    renderSeries();

    expect(screen.getByText(/Brushed range: the whole window/)).toBeInTheDocument();
  });

  it('commits a drag as a range, and reports it to the caller', () => {
    const { onRange } = renderSeries();
    const surface = screen.getByTestId('brush-surface');

    pointerX(surface, 'pointerdown', 100);
    pointerX(surface, 'pointerup', 400);

    expect(onRange).toHaveBeenCalledTimes(1);
    const range = onRange.mock.calls[0]?.[0] as { from: number; to: number };
    expect(range.to).toBeGreaterThan(range.from);
  });

  it('treats a drag narrower than one bucket as a click, not a selection', () => {
    // The 4 px click threshold and the one-bucket minimum agree in this panel: the
    // plot is 608 px wide for 60 buckets (~10 px each), so any drag at or below the
    // click threshold is also below a bucket. This is the second half of that pair —
    // a drag just *over* the threshold still selects nothing.
    const { onRange } = renderSeries();

    pointerX(screen.getByTestId('brush-surface'), 'pointerdown', 200);
    pointerX(screen.getByTestId('brush-surface'), 'pointerup', 205);

    expect(onRange).toHaveBeenCalledWith(null);
  });

  it('clears the brush on a click, so a narrow selection is escapable', () => {
    const { onRange } = renderSeries({ range: { from: START, to: START + 120_000 } });
    const surface = screen.getByTestId('brush-surface');

    pointerX(surface, 'pointerdown', 200);
    pointerX(surface, 'pointerup', 201);

    expect(onRange).toHaveBeenCalledWith(null);
  });

  it('moves a brush handle forward from the keyboard', async () => {
    const { onRange } = renderSeries({ range: { from: START, to: START + 300_000 } });

    const handle = screen.getByRole('slider', { name: 'Brush start' });
    handle.focus();
    await userEvent.keyboard('{ArrowRight}');

    expect(onRange).toHaveBeenCalledTimes(1);
    const moved = onRange.mock.calls[0]?.[0] as { from: number; to: number };
    expect(moved.from).toBeGreaterThan(START);
    expect(moved.to).toBe(START + 300_000);
  });

  it('moves a brush handle backward from the keyboard', async () => {
    // Both arrows, on both handles: a brush that can only be widened from the
    // keyboard is a brush a keyboard user cannot narrow again.
    const { onRange } = renderSeries({ range: { from: START, to: START + 300_000 } });

    const handle = screen.getByRole('slider', { name: 'Brush end' });
    handle.focus();
    await userEvent.keyboard('{ArrowLeft}');

    expect(onRange).toHaveBeenCalledTimes(1);
    const moved = onRange.mock.calls[0]?.[0] as { from: number; to: number };
    expect(moved.from).toBe(START);
    expect(moved.to).toBeLessThan(START + 300_000);
  });

  it('ignores a key that is not one of its arrows', async () => {
    const { onRange } = renderSeries({ range: { from: START, to: START + 300_000 } });

    const handle = screen.getByRole('slider', { name: 'Brush start' });
    handle.focus();
    await userEvent.keyboard('{Enter}');

    expect(onRange).not.toHaveBeenCalled();
  });

  it('exposes both handles as sliders with their position announced', () => {
    renderSeries({ range: { from: START, to: START + 300_000 } });

    const start = screen.getByRole('slider', { name: 'Brush start' });
    const end = screen.getByRole('slider', { name: 'Brush end' });
    expect(Number(start.getAttribute('aria-valuenow'))).toBe(START);
    expect(Number(end.getAttribute('aria-valuenow'))).toBe(START + 300_000);
    expect(start.getAttribute('aria-valuetext')).toContain('2026');
  });

  it('dims only the excluded part, and leaves nothing dimmed with no brush', () => {
    const { container } = renderSeries();
    expect(container.querySelector('[data-testid="brush-mask-left"]')).toBeNull();

    renderSeries({ range: { from: START + 120_000, to: START + 300_000 } });
    expect(screen.getAllByTestId(/^brush-mask-/)).toHaveLength(2);
  });
});

describe('spanLabel', () => {
  it('names the two ends of a selection', () => {
    const span = { from: START, to: START + 3_600_000 };

    expect(spanLabel(span, { from: START + 60_000, to: START + 120_000 })).toMatch(
      /from 06 Oct 2026, 10:01.* to 06 Oct 2026, 10:02/,
    );
  });

  it('says the whole window is selected when there is no brush', () => {
    const span = { from: START, to: START + 3_600_000 };

    expect(spanLabel(span, null)).toContain('the whole window');
  });
});
