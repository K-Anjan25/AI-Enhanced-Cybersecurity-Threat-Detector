/**
 * GlitchText — Cyberpunk glitch effect on text.
 *
 * Uses CSS pseudo-elements and clip-path animations to create a chromatic
 * aberration / digital tear effect. Supports both persistent subtle glitch
 * and hover-triggered intense glitch.
 */
import { type ReactNode } from 'react';

interface GlitchTextProps {
  children: ReactNode;
  as?: 'h1' | 'h2' | 'h3' | 'span' | 'p';
  className?: string;
  intensity?: 'subtle' | 'medium' | 'intense';
}

export function GlitchText({
  children,
  as: Tag = 'h1',
  className = '',
  intensity = 'subtle',
}: GlitchTextProps) {
  return (
    <Tag
      className={`glitch-text glitch-text--${intensity} ${className}`}
      data-text={typeof children === 'string' ? children : ''}
    >
      {children}
    </Tag>
  );
}
