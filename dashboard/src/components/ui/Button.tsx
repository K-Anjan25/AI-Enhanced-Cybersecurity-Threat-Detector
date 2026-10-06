/**
 * Button — design.md §6: "variants: primary secondary ghost danger; sizes: sm md;
 * always renders a real `<button>`; `loading` state swaps the label for a spinner
 * and disables".
 *
 * Two properties are structural rather than cosmetic:
 *
 *   * it *is* a `<button>`. A clickable `<div>` is the most common way a control
 *     disappears from the keyboard and from the accessible tree (NFR-09), so the
 *     element is not configurable; and
 *   * a loading button keeps its accessible name. The label is swapped for a
 *     spinner visually, but the name stays in the tree, because a screen reader
 *     that announces "button" with no name cannot tell the operator what is
 *     happening — and every `getByRole('button', { name })` in the suite would
 *     start depending on the loading state.
 */
import { type ButtonHTMLAttributes, type ReactNode } from 'react';

import { Spinner } from './Spinner';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

/** Fill, border and text come from tokens; the base hue pair carries its own text. */
const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-onAccent hover:brightness-110',
  secondary: 'border border-line bg-surface text-ink hover:border-accent',
  ghost: 'text-muted hover:bg-surface hover:text-ink',
  danger: 'bg-severity-critical text-onSeverity hover:brightness-110',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-caption',
  md: 'h-8 px-4 text-body-sm',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Show a spinner and disable the control. The label stays as its name. */
  loading?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  children,
  className = '',
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      className={`inline-flex items-center gap-2 rounded-input font-semibold transition-colors duration-micro disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {loading ? <Spinner /> : null}
      {loading ? <span className="sr-only">{children}</span> : children}
    </button>
  );
}
