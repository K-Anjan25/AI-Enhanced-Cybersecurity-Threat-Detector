/**
 * CyberButton — Cyberpunk-styled button with clipped corners and neon effects.
 */
import { type ReactNode, type ButtonHTMLAttributes } from 'react';

interface CyberButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

export function CyberButton({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  ...props
}: CyberButtonProps) {
  return (
    <button
      className={`cyber-btn cyber-btn--${variant} cyber-btn--${size} ${className}`}
      {...props}
    >
      <span className="cyber-btn__text">{children}</span>
      <span className="cyber-btn__glitch" aria-hidden="true" />
    </button>
  );
}