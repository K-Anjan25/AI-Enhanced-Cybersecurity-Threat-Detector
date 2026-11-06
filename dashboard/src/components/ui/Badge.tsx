/**
 * Badge — design.md §6: "severity or neutral; enforces the badge rule in §5.3".
 *
 * Critical and high are a filled badge: `bg-severity-*` with the `onSeverity` text,
 * which is the ground colour. The other four are outlined, so the filled and outlined
 * badges differ by shape as well as by the word.
 *
 * Colour is never the only encoding (NFR-09): the severity is also written out in
 * words as the badge's children, so no symbol is drawn.
 */
import { type ReactNode } from 'react';

import { type Severity } from './severity';

export type BadgeTone = Severity | 'neutral';

const FILLS: Record<BadgeTone, string> = {
  // Two-colour palette (memory.md D-099): critical and high are filled, the other four
  // are outlined with their word. Colour is not the only signal, so the word stays.
  critical: 'bg-severity-critical text-onSeverity',
  high: 'bg-severity-high text-onSeverity',
  medium: 'border border-severity-medium bg-surface text-severityText-medium',
  low: 'border border-severity-low bg-surface text-severityText-low',
  info: 'border border-severity-info bg-surface text-severityText-info',
  benign: 'border border-severity-benign bg-surface text-severityText-benign',
  // Neutral is not a severity: a hairline chip for counts and states that are not
  // on the scale, so it uses the border token with normal text.
  neutral: 'border border-line bg-surface text-ink',
};

export interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-input px-2 py-1 text-caption font-semibold ${FILLS[tone]}`}
    >
      {children}
    </span>
  );
}
