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
  color?: 'accent' | 'critical' | 'benign' | 'medium';
  className?: string;
  animate?: boolean;
  onClick?: () => void;
}

const COLOR_MAP = {
  accent: {
    border: 'var(--color-accent)',
    glow: 'color-mix(in srgb, var(--color-accent) 30%, transparent)',
    glowIntense: 'color-mix(in srgb, var(--color-accent) 60%, transparent)',
    text: 'var(--color-accent)',
  },
  critical: {
    border: 'var(--severity-critical)',
    glow: 'color-mix(in srgb, var(--severity-critical) 30%, transparent)',
    glowIntense: 'color-mix(in srgb, var(--severity-critical) 60%, transparent)',
    text: 'var(--severity-critical)',
  },
  benign: {
    border: 'var(--severity-benign)',
    glow: 'color-mix(in srgb, var(--severity-benign) 30%, transparent)',
    glowIntense: 'color-mix(in srgb, var(--severity-benign) 60%, transparent)',
    text: 'var(--severity-benign)',
  },
  medium: {
    border: 'var(--severity-medium)',
    glow: 'color-mix(in srgb, var(--severity-medium) 30%, transparent)',
    glowIntense: 'color-mix(in srgb, var(--severity-medium) 60%, transparent)',
    text: 'var(--severity-medium)',
  },
};

export function NeonCard({
  children,
  title,
  subtitle,
  color = 'accent',
  className = '',
  animate = false,
  onClick,
}: NeonCardProps) {
  const palette = COLOR_MAP[color];

  return (
    <div
      className={`neon-card ${animate ? 'neon-card-animated' : ''} ${className}`}
      style={
        {
          '--neon-border': palette.border,
          '--neon-glow': palette.glow,
          '--neon-glow-intense': palette.glowIntense,
          '--neon-text': palette.text,
        } as React.CSSProperties
      }
      onClick={onClick}
      onKeyDown={
        onClick
          ? (event) => {
              // A clickable card is a button: Enter and Space activate it, as a native one does.
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {/* Scanline overlay */}
      <div className="neon-card-scanlines" aria-hidden="true" />

      {/* HUD corners */}
      <div className="neon-card-corner neon-card-corner-tl" aria-hidden="true" />
      <div className="neon-card-corner neon-card-corner-tr" aria-hidden="true" />
      <div className="neon-card-corner neon-card-corner-bl" aria-hidden="true" />
      <div className="neon-card-corner neon-card-corner-br" aria-hidden="true" />

      {/* Content */}
      <div className="neon-card-content">
        {title && (
          <div className="mb-3">
            <h3
              className="font-mono text-caption uppercase tracking-widest"
              style={{ color: palette.text }}
            >
              {title}
            </h3>
            {subtitle && <p className="mt-1 text-body-sm text-muted">{subtitle}</p>}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
