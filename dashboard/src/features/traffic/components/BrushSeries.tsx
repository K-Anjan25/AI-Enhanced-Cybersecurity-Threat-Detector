/**
 * The brushable time-series (design.md §4.4, §7).
 *
 * An SVG rather than a canvas, because the brush *is* the interaction: the handles
 * are real focusable elements with slider semantics, so the window can be narrowed
 * from the keyboard (NFR-09 — a control that only works with a pointer is a control
 * half the analysts cannot use), and the region between them is draggable.
 *
 * The drawing follows §7's rules for charts, each of which is a decision:
 *
 *   * **Two series, two axes, both labelled.** Record volume is a count (bars, from
 *     a zero baseline — §7 forbids truncating a count axis), the composite score is
 *     a 0–1 ratio drawn as a line on its own labelled axis. A dual axis with no
 *     labels is what §7 calls out as misleading; here both are named and unit-marked.
 *   * **The score line breaks where there is no data.** An empty bucket has
 *     `score: null`, and the path skips it rather than drawing through zero — a line
 *     at the floor reads as "benign", and the truth is "nothing happened".
 *   * **The brush is visible, not implied.** The unselected region is dimmed and the
 *     selected range is announced in words beside the chart (`spanLabel`, printed
 *     under it and in the group's accessible name), so the current selection is never
 *     only a shading.
 *   * **A table is available for everything drawn** (§9): the same buckets render as
 *     a table behind a toggle, with the counts the bars encode.
 */
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

import { Button } from '../../../components/ui';
import { formatBytes, formatCount, formatInstant, formatStamp } from '../../../lib/format';
import type { BrushRange, TrafficBucket } from '../aggregate';
import type { ChartPalette } from '../../../components/charts/palette';

export interface BrushSeriesProps {
  buckets: readonly TrafficBucket[];
  /** The selected range, or `null` for "all of it". */
  range: BrushRange | null;
  onRange: (range: BrushRange | null) => void;
  palette: ChartPalette;
  /** Accessible name; the caption under the chart repeats it for sighted readers. */
  label: string;
  width?: number;
  height?: number;
}

const PADDING = { top: 12, right: 56, bottom: 24, left: 56 };

/** The window a bucket list covers, as a brush range. */
function spanOf(buckets: readonly TrafficBucket[]): BrushRange {
  const first = buckets[0];
  const last = buckets.at(-1);
  if (first === undefined || last === undefined) return { from: 0, to: 0 };
  return { from: first.start.getTime(), to: last.end.getTime() };
}

export function BrushSeries({
  buckets,
  range,
  onRange,
  palette,
  label,
  width = 720,
  height = 200,
}: BrushSeriesProps) {
  const [asTable, setAsTable] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragFrom = useRef<number | null>(null);

  const span = spanOf(buckets);
  const spanMs = Math.max(1, span.to - span.from);
  const innerWidth = width - PADDING.left - PADDING.right;
  const innerHeight = height - PADDING.top - PADDING.bottom;

  const peak = buckets.reduce((best, bucket) => Math.max(best, bucket.flows), 0);
  // §7: a count axis starts at zero. The ceiling is at least 1 so an all-empty
  // window draws a baseline rather than dividing by zero.
  const ceiling = Math.max(1, peak);

  const geometry = useMemo(() => {
    const step = innerWidth / Math.max(1, buckets.length);
    const bars = buckets.map((bucket, index) => ({
      bucket,
      x: PADDING.left + index * step,
      width: Math.max(1, step - 1),
      height: (bucket.flows / ceiling) * innerHeight,
    }));

    // One segment per contiguous run of buckets that have a score: a break in the
    // data is a break in the line.
    const segments: { x: number; y: number }[][] = [];
    let current: { x: number; y: number }[] = [];
    buckets.forEach((bucket, index) => {
      if (bucket.score === null) {
        if (current.length > 0) segments.push(current);
        current = [];
        return;
      }
      current.push({
        x: PADDING.left + index * step + step / 2,
        y: PADDING.top + (1 - Math.max(0, Math.min(1, bucket.score))) * innerHeight,
      });
    });
    if (current.length > 0) segments.push(current);

    return { step, bars, segments };
  }, [buckets, ceiling, innerHeight, innerWidth]);

  const toInstant = (x: number): number => {
    const ratio = Math.max(0, Math.min(1, (x - PADDING.left) / innerWidth));
    return span.from + ratio * spanMs;
  };

  const pixelOf = (at: number): number => PADDING.left + ((at - span.from) / spanMs) * innerWidth;

  const active = range ?? span;

  const emitRange = (from: number, to: number): void => {
    const clamped = {
      from: Math.max(span.from, Math.min(from, to)),
      to: Math.min(span.to, Math.max(from, to)),
    };
    // A brush narrower than one bucket is a click, not a selection: it would filter
    // the page to a window the series cannot even draw.
    const minimum = spanMs / Math.max(1, buckets.length);
    onRange(clamped.to - clamped.from < minimum ? null : clamped);
  };

  const nudge = (edge: 'from' | 'to', direction: -1 | 1): void => {
    const stepMs = spanMs / 20;
    const next =
      edge === 'from'
        ? {
            from: Math.max(
              span.from,
              Math.min(active.from + direction * stepMs, active.to - stepMs / 2),
            ),
            to: active.to,
          }
        : {
            from: active.from,
            to: Math.min(
              span.to,
              Math.max(active.to + direction * stepMs, active.from + stepMs / 2),
            ),
          };
    onRange(next);
  };

  const onPointerDown = (event: ReactPointerEvent<SVGRectElement>): void => {
    const box = svgRef.current?.getBoundingClientRect();
    if (box === undefined) return;
    dragFrom.current = event.clientX - box.left;
  };

  const onPointerUp = (event: ReactPointerEvent<SVGRectElement>): void => {
    const box = svgRef.current?.getBoundingClientRect();
    const from = dragFrom.current;
    dragFrom.current = null;
    if (box === undefined || from === null) return;
    const to = event.clientX - box.left;
    if (Math.abs(to - from) < 4) {
      // A click on the plot clears the brush: the only other way out of a narrow
      // selection is to drag back over the whole axis, which is not obvious.
      onRange(null);
      return;
    }
    emitRange(toInstant(from), toInstant(to));
  };

  const handle = (edge: 'from' | 'to') => {
    const at = edge === 'from' ? active.from : active.to;
    const x = pixelOf(at);
    return (
      <g key={edge}>
        <line
          x1={x}
          x2={x}
          y1={PADDING.top}
          y2={PADDING.top + innerHeight}
          stroke={palette.critical}
          strokeWidth={1.5}
        />
        <rect
          role="slider"
          tabIndex={0}
          aria-label={edge === 'from' ? 'Brush start' : 'Brush end'}
          aria-valuemin={span.from}
          aria-valuemax={span.to}
          aria-valuenow={at}
          aria-valuetext={formatStamp(new Date(at).toISOString())}
          x={x - 4}
          y={PADDING.top + innerHeight / 2 - 12}
          width={8}
          height={24}
          fill={palette.critical}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') {
              event.preventDefault();
              nudge(edge, -1);
            }
            if (event.key === 'ArrowRight') {
              event.preventDefault();
              nudge(edge, 1);
            }
          }}
        />
      </g>
    );
  };

  return (
    <div>
      {/* `group`, not `img`: the brush handles are focusable sliders, and an `img`
          role makes its descendants presentational — which would hide the only
          keyboard affordance this chart has from assistive technology. */}
      <svg
        ref={svgRef}
        role="group"
        aria-label={`${label}. Brushed range: ${spanLabel(active, range)}`}
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        className="w-full"
        style={{ maxHeight: `${String(height)}px` }}
        onPointerMove={(event) => {
          if (dragFrom.current === null || event.buttons === 0) return;
          // A live preview while dragging is intentionally absent: the range is
          // committed on release, so a drag does not re-derive three panels per
          // pointer move.
        }}
      >
        {/* Gridlines every quarter, labelled with where they are in the window. */}
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const x = PADDING.left + fraction * innerWidth;
          return (
            <g key={fraction}>
              <line
                x1={x}
                x2={x}
                y1={PADDING.top}
                y2={PADDING.top + innerHeight}
                stroke={palette.grid}
                strokeWidth={1}
              />
              <text
                x={x}
                y={height - 8}
                textAnchor="middle"
                className="fill-current text-caption"
                fill={palette.muted}
              >
                {formatInstant(new Date(span.from + fraction * spanMs).toISOString()).slice(11, 16)}
              </text>
            </g>
          );
        })}

        {/* Count axis, from zero, with its unit named. */}
        <text x={4} y={PADDING.top + 10} fill={palette.muted} className="text-caption">
          flows
        </text>
        <text x={4} y={PADDING.top + innerHeight} fill={palette.muted} className="text-caption">
          0
        </text>
        <text x={4} y={PADDING.top + 22} fill={palette.muted} className="text-caption">
          {ceiling}
        </text>

        {geometry.bars.map((bar) => (
          <rect
            key={bar.bucket.start.getTime()}
            x={bar.x}
            y={PADDING.top + innerHeight - bar.height}
            width={bar.width}
            height={bar.height}
            fill={palette.high}
            data-testid={`bar-${String(bar.bucket.start.getTime())}`}
          >
            <title>
              {`${formatInstant(bar.bucket.start.toISOString())}: ${formatCount(bar.bucket.flows)} flows, ${formatBytes(bar.bucket.bytes)}, ${String(bar.bucket.alerts)} alerts`}
            </title>
          </rect>
        ))}

        {geometry.segments.map((segment, index) => (
          <polyline
            key={index}
            points={segment.map((point) => `${String(point.x)},${String(point.y)}`).join(' ')}
            fill="none"
            stroke={palette.critical}
            strokeWidth={1.5}
            data-testid={`score-segment-${String(index)}`}
          />
        ))}

        {/* Score axis, 0–1, named on the right so the two scales cannot be confused. */}
        <text
          x={width - PADDING.right + 6}
          y={PADDING.top + 10}
          fill={palette.muted}
          className="text-caption"
        >
          score
        </text>
        <text
          x={width - PADDING.right + 6}
          y={PADDING.top + 22}
          fill={palette.muted}
          className="text-caption"
        >
          1.0
        </text>
        <text
          x={width - PADDING.right + 6}
          y={PADDING.top + innerHeight}
          fill={palette.muted}
          className="text-caption"
        >
          0.0
        </text>

        {/* The brush: a dimmed mask over what is excluded, and the handles. */}
        {range === null ? null : (
          <rect
            x={PADDING.left}
            y={PADDING.top}
            width={Math.max(0, pixelOf(range.from) - PADDING.left)}
            height={innerHeight}
            fill={palette.muted}
            opacity={0.15}
            data-testid="brush-mask-left"
          />
        )}
        {range === null ? null : (
          <rect
            x={pixelOf(range.to)}
            y={PADDING.top}
            width={Math.max(0, PADDING.left + innerWidth - pixelOf(range.to))}
            height={innerHeight}
            fill={palette.muted}
            opacity={0.15}
            data-testid="brush-mask-right"
          />
        )}
        <rect
          x={PADDING.left}
          y={PADDING.top}
          width={innerWidth}
          height={innerHeight}
          fill="transparent"
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          data-testid="brush-surface"
        />
        {handle('from')}
        {handle('to')}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-caption text-muted">Brushed range: {spanLabel(active, range)}</p>
        <div className="flex items-center gap-2">
          {range === null ? null : (
            <Button variant="ghost" size="sm" onClick={() => onRange(null)}>
              Clear brush
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={asTable}
            aria-controls="traffic-series-table"
            onClick={() => setAsTable((open) => !open)}
          >
            {asTable ? 'View as chart' : 'View as table'}
          </Button>
        </div>
      </div>

      {asTable ? (
        <table id="traffic-series-table" className="mt-2 w-full border-collapse text-body-sm">
          <caption className="sr-only">{label}, as a table — every bucket the chart draws</caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th scope="col" className="py-2 pr-4 font-semibold">
                Bucket start
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Flows
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Bytes
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Alerts
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Mean score
              </th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket) => (
              <tr key={bucket.start.getTime()} className="border-b border-line/50">
                <th scope="row" className="py-1 pr-4 text-left font-normal text-ink">
                  {formatStamp(bucket.start.toISOString())}
                </th>
                <td className="py-1 pr-4 tabular-nums text-ink">{formatCount(bucket.flows)}</td>
                <td className="py-1 pr-4 tabular-nums text-ink">{formatBytes(bucket.bytes)}</td>
                <td className="py-1 pr-4 tabular-nums text-ink">{bucket.alerts}</td>
                <td className="py-1 pr-4 tabular-nums text-ink">
                  {bucket.score === null ? 'no data' : bucket.score.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}

/**
 * The range in words: "the whole window", or the two instants it selects.
 *
 * A full stamp, not a time of day: a brush can span days, and a window labelled
 * "10:15–10:45" is ambiguous about *which* 10:15 once the range is longer than a day.
 */
export function spanLabel(range: BrushRange, active: BrushRange | null): string {
  if (active === null) {
    return `the whole window (from ${formatStamp(new Date(range.from).toISOString())})`;
  }
  return `from ${formatStamp(new Date(active.from).toISOString())} to ${formatStamp(new Date(active.to).toISOString())}`;
}
