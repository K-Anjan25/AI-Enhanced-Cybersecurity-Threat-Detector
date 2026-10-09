/**
 * ThreatLevelBar — Animated threat level indicator with segmented bar.
 *
 * Shows the current system threat level with color-coded segments,
 * pulsing glow, and a numeric readout.
 */
import { useEffect, useRef, useState } from 'react';

interface ThreatLevelBarProps {
  level: number; // 0-100
  label?: string;
  animated?: boolean;
  className?: string;
}

export function ThreatLevelBar({
  level,
  label = 'THREAT LEVEL',
  animated = true,
  className = '',
}: ThreatLevelBarProps) {
  const [displayLevel, setDisplayLevel] = useState(0);
  // Mirrors displayLevel so the animation can start from the value on screen without
  // making it an effect dependency (which would restart the animation every frame).
  const displayRef = useRef(0);
  displayRef.current = displayLevel;

  useEffect(() => {
    if (!animated) {
      setDisplayLevel(level);
      return;
    }
    const duration = 1500;
    const startTime = Date.now();
    const startLevel = displayRef.current;

    function animate() {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplayLevel(startLevel + (level - startLevel) * eased);
      if (progress < 1) requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  }, [level, animated]);

  const getColor = (pct: number) => {
    if (pct < 25) return '#05ffa1';
    if (pct < 50) return '#fcee0a';
    if (pct < 75) return '#f76808';
    return '#ff2a6d';
  };

  const color = getColor(displayLevel);
  const segments = 20;
  const filledSegments = Math.round((displayLevel / 100) * segments);

  return (
    <div className={`threat-level-bar ${className}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-caption uppercase tracking-widest text-muted">{label}</span>
        <span className="font-mono text-h2 tabular" style={{ color }}>
          {Math.round(displayLevel)}%
        </span>
      </div>

      <div className="flex gap-0.5">
        {Array.from({ length: segments }, (_, i) => (
          <div
            key={i}
            className="threat-level-bar__segment"
            style={{
              backgroundColor: i < filledSegments ? color : 'rgba(255,255,255,0.05)',
              boxShadow: i < filledSegments ? `0 0 6px ${color}40` : 'none',
              transition: 'background-color 0.15s ease, box-shadow 0.15s ease',
            }}
          />
        ))}
      </div>

      <div
        className="mt-1 flex justify-between font-mono text-caption"
        style={{ color: 'rgba(255,255,255,0.3)' }}
      >
        <span>LOW</span>
        <span>MEDIUM</span>
        <span>HIGH</span>
        <span>CRITICAL</span>
      </div>
    </div>
  );
}
