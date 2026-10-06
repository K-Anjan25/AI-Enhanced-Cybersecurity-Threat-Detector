/**
 * The canvas wrapper every Chart.js chart in the overview goes through.
 *
 * It exists for three reasons, each of which is a way a canvas chart goes wrong:
 *
 *   * **Registration is explicit.** `chart.js/auto` would pull in every controller
 *     and scale; naming the pieces keeps the bundle to what the two charts use and
 *     makes the dependency visible in the file that needs it.
 *   * **The canvas has a name.** A `<canvas>` is opaque to assistive technology, so
 *     it carries `role="img"` and the chart's label. That label is the *second*
 *     encoding: the first is the data table the panel toggles open (§9).
 *   * **No context, no crash.** A canvas without a 2D context — jsdom, a hardened
 *     browser, a failed stylesheet — must not take the page down with it. The
 *     chart is simply not drawn, and the data table is still there, which is the
 *     part that carries the information anyway.
 */
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartConfiguration,
} from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';
import { useEffect, useRef } from 'react';

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  ChartDataLabels,
);

export interface ChartCanvasProps {
  /** Built by `charts.ts`, where it is tested as data. */
  config: ChartConfiguration;
  /** The chart's accessible name — what it shows, not what it is. */
  label: string;
  /** Height in pixels; width follows the panel. */
  height?: number;
}

export function ChartCanvas({ config, label, height = 240 }: ChartCanvasProps) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const chart = useRef<Chart | null>(null);

  useEffect(() => {
    const element = canvas.current;
    if (element === null) return undefined;
    const context = element.getContext('2d');
    if (context === null) return undefined;
    chart.current = new Chart(context, config);
    return () => {
      chart.current?.destroy();
      chart.current = null;
    };
  }, [config]);

  return (
    <canvas
      ref={canvas}
      role="img"
      aria-label={label}
      className="w-full"
      style={{ height: `${String(height)}px` }}
    />
  );
}
