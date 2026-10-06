/**
 * Badge — design.md §6: "severity or neutral; enforces the badge rule in §5.3".
 *
 * The rule is explicit that a severity badge is "a base-hue fill with" near-black
 * text, because light text on these fills fails the ratio for critical and fails it
 * badly for medium. So the fill is `bg-severity-*` and the text is the
 * `onSeverity` token — near-black in both themes, and the only colour the closed
 * palette will compile for it.
 *
 * Colour is never the only encoding (NFR-09): every severity badge carries the
 * §5.3 glyph as well, hidden from assistive technology because the label beside it
 * already says the same thing in words.
 */
import { type ReactNode } from 'react';

import { SEVERITY_GLYPHS, type Severity } from './severity';

export type BadgeTone = Severity | 'neutral';

const FILLS: Record<BadgeTone, string> = {
  critical: 'bg-severity-critical text-onSeverity',
  high: 'bg-severity-high text-onSeverity',
  medium: 'bg-severity-medium text-onSeverity',
  low: 'bg-severity-low text-onSeverity',
  info: 'bg-severity-info text-onSeverity',
  benign: 'bg-severity-benign text-onSeverity',
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
      {tone === 'neutral' ? null : <span aria-hidden="true">{SEVERITY_GLYPHS[tone]}</span>}
      {children}
    </span>
  );
}
