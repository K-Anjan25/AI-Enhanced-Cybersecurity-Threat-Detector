/**
 * HexGrid — Animated SVG hexagonal grid background pattern.
 *
 * Renders a tessellating hexagon pattern with random highlight pulses,
 * creating a futuristic circuit-board aesthetic.
 */
import { useEffect, useState } from 'react';

interface HexGridProps {
  width?: number;
  height?: number;
  cellSize?: number;
  className?: string;
}

interface HexHighlight {
  col: number;
  row: number;
  opacity: number;
}

export function HexGrid({
  width = 400,
  height = 300,
  cellSize = 30,
  className = '',
}: HexGridProps) {
  const [highlights, setHighlights] = useState<HexHighlight[]>([]);

  useEffect(() => {
    const interval = setInterval(() => {
      const cols = Math.floor(width / (cellSize * 1.5));
      const rows = Math.floor(height / (cellSize * Math.sqrt(3)));
      const col = Math.floor(Math.random() * cols);
      const row = Math.floor(Math.random() * rows);
      setHighlights((prev) => [...prev.slice(-8), { col, row, opacity: 1 }]);
    }, 600);

    const fadeInterval = setInterval(() => {
      setHighlights((prev) =>
        prev.map((h) => ({ ...h, opacity: h.opacity - 0.05 })).filter((h) => h.opacity > 0),
      );
    }, 100);

    return () => {
      clearInterval(interval);
      clearInterval(fadeInterval);
    };
  }, [width, height, cellSize]);

  const hexPath = (cx: number, cy: number, r: number) => {
    const points = Array.from({ length: 6 }, (_, i) => {
      const angle = (Math.PI / 3) * i - Math.PI / 6;
      return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
    });
    return `M ${points.join(' L ')} Z`;
  };

  const cols = Math.floor(width / (cellSize * 1.5));
  const rows = Math.floor(height / (cellSize * Math.sqrt(3)));

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`pointer-events-none ${className}`}
      aria-hidden="true"
    >
      {Array.from({ length: cols }, (_, col) =>
        Array.from({ length: rows }, (_, row) => {
          const cx = col * cellSize * 1.5 + cellSize;
          const cy =
            row * cellSize * Math.sqrt(3) +
            (col % 2 ? (cellSize * Math.sqrt(3)) / 2 : 0) +
            cellSize;
          const isHighlighted = highlights.find((h) => h.col === col && h.row === row);

          return (
            <path
              key={`${col}-${row}`}
              d={hexPath(cx, cy, cellSize * 0.45)}
              fill={isHighlighted ? `rgba(0, 240, 255, ${isHighlighted.opacity * 0.2})` : 'none'}
              stroke="rgba(0, 240, 255, 0.08)"
              strokeWidth="0.5"
            />
          );
        }),
      )}
    </svg>
  );
}
