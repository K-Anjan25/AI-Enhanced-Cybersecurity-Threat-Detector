/**
 * DataStream — Scrolling hexadecimal / binary data stream animation.
 *
 * Pure CSS + React component that renders columns of scrolling hex data
 * for that authentic hacker terminal aesthetic.
 */
import { useEffect, useState } from 'react';

interface DataStreamProps {
  columns?: number;
  speed?: 'slow' | 'medium' | 'fast';
  color?: string;
  className?: string;
}

function randomHex(length: number): string {
  return Array.from({ length }, () =>
    Math.floor(Math.random() * 16).toString(16).toUpperCase(),
  ).join(' ');
}

function randomBinary(length: number): string {
  return Array.from({ length }, () => (Math.random() > 0.5 ? '1' : '0')).join(' ');
}

export function DataStream({
  columns = 8,
  speed = 'medium',
  color = 'rgba(0, 240, 255, 0.3)',
  className = '',
}: DataStreamProps) {
  const [data, setData] = useState<string[]>([]);

  useEffect(() => {
    const initial = Array.from({ length: columns }, () =>
      Math.random() > 0.5 ? randomHex(16) : randomBinary(16),
    );
    setData(initial);

    const interval = setInterval(
      () => {
        setData((prev) =>
          prev.map(() =>
            Math.random() > 0.5 ? randomHex(16) : randomBinary(16),
          ),
        );
      },
      speed === 'fast' ? 80 : speed === 'medium' ? 150 : 300,
    );

    return () => clearInterval(interval);
  }, [columns, speed]);

  const animDuration = speed === 'fast' ? '8s' : speed === 'medium' ? '15s' : '25s';

  return (
    <div
      className={`pointer-events-none flex gap-2 overflow-hidden ${className}`}
      aria-hidden="true"
    >
      {data.map((col, i) => (
        <div
          key={i}
          className="font-mono text-caption whitespace-nowrap"
          style={{
            color,
            writingMode: 'vertical-rl',
            animation: `dataStreamScroll ${animDuration} linear infinite`,
            animationDelay: `${i * -1.5}s`,
            opacity: 0.3 + Math.random() * 0.4,
          }}
        >
          {col}
        </div>
      ))}
    </div>
  );
}