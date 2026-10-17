import { render } from '@testing-library/react';
import type { ChartConfiguration } from 'chart.js';
import { describe, expect, it } from 'vitest';

import { ChartCanvas } from './ChartCanvas';

const config: ChartConfiguration = { type: 'bar', data: { labels: [], datasets: [] } };

describe('ChartCanvas', () => {
  it('takes its height from a fixed box, not from the canvas itself', () => {
    // Regression: a canvas that set its own height inside an unsized card grew on
    // every Chart.js resize pass. The box carries the height; the canvas fills it.
    const { container, getByRole } = render(
      <ChartCanvas config={config} label="Alert volume" height={240} />,
    );
    const box = container.firstElementChild as HTMLElement;
    expect(box.style.height).toBe('240px');
    expect(box.style.position).toBe('');
    expect(box.className).toContain('relative');
    const canvas = getByRole('img', { name: 'Alert volume' });
    expect(canvas.style.height).toBe('');
    expect(canvas.className).toContain('h-full');
  });
});
