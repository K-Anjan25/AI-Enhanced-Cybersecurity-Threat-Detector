/**
 * PulseWave — Animated SVG pulse/heartbeat wave for system vitals.
 *
 * Renders an animated oscilloscope-style waveform that simulates
 * real-time network activity or system health.
 */
import { useEffect, useRef } from 'react';

interface PulseWaveProps {
  width?: number;
  height?: number;
  color?: string;
  speed?: number;
  amplitude?: number;
  className?: string;
}

export function PulseWave({
  width = 300,
  height = 60,
  color = 'var(--color-accent)',
  speed = 2,
  amplitude = 0.6,
  className = '',
}: PulseWaveProps) {
  const pathRef = useRef<SVGPathElement>(null);
  const offsetRef = useRef(0);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    let animId: number;

    function animate() {
      offsetRef.current += speed * 0.02;
      const path = pathRef.current;
      if (!path) return;

      const points: string[] = [];
      const steps = 60;
      const stepWidth = width / steps;

      for (let i = 0; i <= steps; i++) {
        const x = i * stepWidth;
        const t = (i / steps) * Math.PI * 4 + offsetRef.current;

        // Combine sine waves for a heartbeat-like pattern
        let y = Math.sin(t) * amplitude * 0.3;
        y += Math.sin(t * 2.5) * amplitude * 0.15;
        y += Math.sin(t * 0.5) * amplitude * 0.1;

        // Add sharp spikes
        const spike = Math.pow(Math.max(0, Math.sin(t * 1.5)), 8) * amplitude * 0.4;
        y += spike;

        const py = height / 2 - y * (height / 2);
        points.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${py.toFixed(1)}`);
      }

      path.setAttribute('d', points.join(' '));
      animId = requestAnimationFrame(animate);
    }

    animId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animId);
  }, [width, height, speed, amplitude]);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="pulseGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopOpacity="0" style={{ stopColor: color }} />
          <stop offset="20%" stopOpacity="0.8" style={{ stopColor: color }} />
          <stop offset="80%" stopOpacity="0.8" style={{ stopColor: color }} />
          <stop offset="100%" stopOpacity="0" style={{ stopColor: color }} />
        </linearGradient>
        <filter id="pulseGlow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Grid lines */}
      {Array.from({ length: 5 }, (_, i) => (
        <line
          key={`h-${i}`}
          x1="0"
          y1={(height / 4) * i}
          x2={width}
          y2={(height / 4) * i}

          strokeWidth="0.5"
          style={{ stroke: 'color-mix(in srgb, var(--color-accent) 6%, transparent)' }}
        />
      ))}
      {Array.from({ length: Math.floor(width / 20) + 1 }, (_, i) => (
        <line
          key={`v-${i}`}
          x1={i * 20}
          y1="0"
          x2={i * 20}
          y2={height}

          strokeWidth="0.5"
          style={{ stroke: 'color-mix(in srgb, var(--color-accent) 6%, transparent)' }}
        />
      ))}

      {/* Center line */}
      <line
        x1="0"
        y1={height / 2}
        x2={width}
        y2={height / 2}

        strokeWidth="0.5"
        strokeDasharray="4 4"
        style={{ stroke: 'color-mix(in srgb, var(--color-accent) 15%, transparent)' }}
      />

      {/* Waveform */}
      <path
        ref={pathRef}

        stroke="url(#pulseGrad)"
        strokeWidth="1.5"
        filter="url(#pulseGlow)"
        style={{ fill: 'none' }}
      />
    </svg>
  );
}
