/**
 * NeonCard — A cyberpunk-styled card with neon glow borders, clipped corners,
 * and optional HUD corner decorations.
 *
 * Replaces the standard Card with a futuristic aesthetic: scanlines overlay,
 * neon accent border, and angular clip-paths.
 */
import { type ReactNode } from 'react';

interface NeonCardProps {
  children: ReactNode;
  title?: string;
  subtitle?: string;
  color?: 'cyan' | 'magenta' | 'green' | 'yellow';
  className?: string;
  animate?: boolean;
  onClick?: () => void;
}

const COLOR_MAP = {
  cyan: {
    border: '#00f0ff',
    glow: 'rgba(0, 240, 255, 0.3)',
    glowIntense: 'rgba(0, 240, 255, 0.6)',
    text: '#00f0ff',
  },
  magenta: {
    border: '#ff2a6d',
    glow: 'rgba(255, 42, 109, 0.3)',
    glowIntense: 'rgba(255, 42, 109, 0.6)',
    text: '#ff2a6d',
  },
  green: {
    border: '#05ffa1',
    glow: 'rgba(5, 255, 161, 0.3)',
    glowIntense: 'rgba(5, 255, 161, 0.6)',
    text: '#05ffa1',
  },
  yellow: {
    border: '#fcee0a',
    glow: 'rgba(252, 238, 10, 0.3)',
    glowIntense: 'rgba(252, 238, 10, 0.6)',
    text: '#fcee0a',
  },
};

export function NeonCard({
  children,
  title,
  subtitle,
  color = 'cyan',
  className = '',
  animate = false,
  onClick,
}: NeonCardProps) {
  const palette = COLOR_MAP[color];

  return (
    <div
      className={`neon-card ${animate ? 'neon-card--animated' : ''} ${className}`}
      style={{
        '--neon-border': palette.border,
        '--neon-glow': palette.glow,
        '--neon-glow-intense': palette.glowIntense,
        '--neon-text': palette.text,
      } as React.CSSProperties}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* Scanline overlay */}
      <div className="neon-card__scanlines" aria-hidden="true" />

      {/* HUD corners */}
      <div className="neon-card__corner neon-card__corner--tl" aria-hidden="true" />
      <div className="neon-card__corner neon-card__corner--tr" aria-hidden="true" />
      <div className="neon-card__corner neon-card__corner--bl" aria-hidden="true" />
      <div className="neon-card__corner neon-card__corner--br" aria-hidden="true" />

      {/* Content */}
      <div className="neon-card__content">
        {title && (
          <div className="mb-3">
            <h3
              className="font-mono text-caption uppercase tracking-widest"
              style={{ color: palette.text }}
            >
              {title}
            </h3>
            {subtitle && (
              <p className="mt-1 text-body-sm text-muted">{subtitle}</p>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}