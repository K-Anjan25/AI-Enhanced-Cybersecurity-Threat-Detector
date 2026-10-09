/**
 * ThreatRadar — Animated SVG radar sweep for threat monitoring.
 *
 * A pure SVG component that renders a rotating radar sweep with concentric
 * rings, crosshairs, and random threat blips. Zero canvas/WebGL needed.
 */
import { useEffect, useRef, useState, useCallback } from 'react';

interface ThreatBlip {
  id: number;
  angle: number;
  distance: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  opacity: number;
}

const SEVERITY_COLORS = {
  critical: '#e5484d',
  high: '#f76808',
  medium: '#ffc53d',
  low: '#3e8ef7',
};

export function ThreatRadar({ size = 280 }: { size?: number }) {
  const [blips, setBlips] = useState<ThreatBlip[]>([]);
  const [sweepAngle, setSweepAngle] = useState(0);
  const frameRef = useRef<number>();
  const lastBlipRef = useRef(0);
  const center = size / 2;
  const radius = size / 2 - 20;

  const addBlip = useCallback(() => {
    const severities: ThreatBlip['severity'][] = ['critical', 'high', 'medium', 'low'];
    const newBlip: ThreatBlip = {
      id: Date.now() + Math.random(),
      angle: Math.random() * 360,
      distance: 0.2 + Math.random() * 0.75,
      severity: severities[Math.floor(Math.random() * severities.length)] ?? 'low',
      opacity: 1,
    };
    setBlips((prev) => [...prev.slice(-6), newBlip]); // was 12, now 6
  }, []);

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.matches) return;

    let lastTime = 0;
    function animate(time: number) {
      const delta = time - lastTime;
      if (delta > 33) { // ~30fps instead of 60fps
        setSweepAngle((prev) => (prev + 2) % 360);

        // Fade blips
        setBlips((prev) =>
          prev
            .map((b) => ({ ...b, opacity: b.opacity - 0.008 }))
            .filter((b) => b.opacity > 0),
        );

        // Random new blips — less frequent
        if (time - lastBlipRef.current > 1500 + Math.random() * 3000) {
          addBlip();
          lastBlipRef.current = time;
        }

        lastTime = time;
      }
      frameRef.current = requestAnimationFrame(animate);
    }

    frameRef.current = requestAnimationFrame(animate);
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [addBlip]);

  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <div className="threat-radar flex items-center justify-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          {/* Sweep gradient */}
          <linearGradient id="sweepGrad" gradientTransform={`rotate(${sweepAngle}, 0.5, 0.5)`}>
            <stop offset="0%" stopColor="rgba(0, 240, 255, 0.3)" />
            <stop offset="50%" stopColor="rgba(0, 240, 255, 0)" />
            <stop offset="100%" stopColor="rgba(0, 240, 255, 0)" />
          </linearGradient>

          {/* Glow filter */}
          <filter id="blipGlow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background circle */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="rgba(0, 240, 255, 0.02)"
          stroke="rgba(0, 240, 255, 0.2)"
          strokeWidth="1"
        />

        {/* Concentric rings */}
        {rings.map((ring) => (
          <circle
            key={ring}
            cx={center}
            cy={center}
            r={radius * ring}
            fill="none"
            stroke="rgba(0, 240, 255, 0.12)"
            strokeWidth="0.5"
            strokeDasharray="4 4"
          />
        ))}

        {/* Crosshairs */}
        <line
          x1={center - radius}
          y1={center}
          x2={center + radius}
          y2={center}
          stroke="rgba(0, 240, 255, 0.15)"
          strokeWidth="0.5"
        />
        <line
          x1={center}
          y1={center - radius}
          x2={center}
          y2={center + radius}
          stroke="rgba(0, 240, 255, 0.15)"
          strokeWidth="0.5"
        />

        {/* Diagonal crosshairs */}
        <line
          x1={center - radius * 0.707}
          y1={center - radius * 0.707}
          x2={center + radius * 0.707}
          y2={center + radius * 0.707}
          stroke="rgba(0, 240, 255, 0.08)"
          strokeWidth="0.5"
        />
        <line
          x1={center + radius * 0.707}
          y1={center - radius * 0.707}
          x2={center - radius * 0.707}
          y2={center + radius * 0.707}
          stroke="rgba(0, 240, 255, 0.08)"
          strokeWidth="0.5"
        />

        {/* Sweep line */}
        <line
          x1={center}
          y1={center}
          x2={center + radius * Math.cos((sweepAngle * Math.PI) / 180)}
          y2={center + radius * Math.sin((sweepAngle * Math.PI) / 180)}
          stroke="rgba(0, 240, 255, 0.6)"
          strokeWidth="1.5"
        />

        {/* Sweep cone */}
        <path
          d={`M ${center} ${center} L ${
            center + radius * Math.cos(((sweepAngle - 30) * Math.PI) / 180)
          } ${center + radius * Math.sin(((sweepAngle - 30) * Math.PI) / 180)} A ${radius} ${radius} 0 0 1 ${
            center + radius * Math.cos((sweepAngle * Math.PI) / 180)
          } ${center + radius * Math.sin((sweepAngle * Math.PI) / 180)} Z`}
          fill="rgba(0, 240, 255, 0.08)"
        />

        {/* Threat blips */}
        {blips.map((blip) => {
          const bx = center + radius * blip.distance * Math.cos((blip.angle * Math.PI) / 180);
          const by = center + radius * blip.distance * Math.sin((blip.angle * Math.PI) / 180);
          return (
            <g key={blip.id} filter="url(#blipGlow)">
              <circle
                cx={bx}
                cy={by}
                r={blip.severity === 'critical' ? 4 : 3}
                fill={SEVERITY_COLORS[blip.severity]}
                opacity={blip.opacity}
              />
              <circle
                cx={bx}
                cy={by}
                r={8}
                fill="none"
                stroke={SEVERITY_COLORS[blip.severity]}
                strokeWidth="0.5"
                opacity={blip.opacity * 0.5}
              >
                <animate
                  attributeName="r"
                  from="3"
                  to="12"
                  dur="2s"
                  repeatCount="indefinite"
                />
                <animate
                  attributeName="opacity"
                  from={String(blip.opacity * 0.5)}
                  to="0"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </circle>
            </g>
          );
        })}

        {/* Center dot */}
        <circle cx={center} cy={center} r="3" fill="#00f0ff" filter="url(#blipGlow)" />

        {/* Cardinal labels */}
        <text x={center} y={14} textAnchor="middle" fill="rgba(0,240,255,0.4)" fontSize="9" fontFamily="monospace">N</text>
        <text x={center} y={size - 6} textAnchor="middle" fill="rgba(0,240,255,0.4)" fontSize="9" fontFamily="monospace">S</text>
        <text x={8} y={center + 3} textAnchor="start" fill="rgba(0,240,255,0.4)" fontSize="9" fontFamily="monospace">W</text>
        <text x={size - 8} y={center + 3} textAnchor="end" fill="rgba(0,240,255,0.4)" fontSize="9" fontFamily="monospace">E</text>
      </svg>
    </div>
  );
}