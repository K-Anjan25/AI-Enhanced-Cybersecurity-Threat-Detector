/**
 * SeverityPill — design.md §6.
 *
 * `Badge` and `SeverityPill` encode the same §5.3 palette for two different
 * densities, and the difference matters:
 *
 *   * `Badge` is a **fill** — the base hue with near-black text. It is the loud
 *     form, for a standalone figure or a card header, and the rule that it must
 *     never carry light text lives in that component.
 *   * `SeverityPill` is a **label** — the §5.3 *text* variant of the hue, with the
 *     base hue as a 3 px left rail. In a 44 px alert row a full fill is a block of
 *     colour that competes with the row's own content; the text variant is the one
 *     §5.3 publishes a ratio for against both backgrounds (≥ 4.5:1, asserted by
 *     src/theme/tokens.test.ts), precisely so it can be read on a surface.
 *
 * Both carry the §5.3 glyph, because colour is never the only encoding (NFR-09).
 * Neither lets the caller pass a colour: the severity chooses both the rail and the
 * text.
 */
import { SEVERITY_GLYPHS, SEVERITY_LABELS, type Severity } from './severity';

/** The §5.3 text variant of each hue. These are the AA-safe form on a surface. */
const TEXT: Record<Severity, string> = {
  critical: 'text-severityText-critical',
  high: 'text-severityText-high',
  medium: 'text-severityText-medium',
  low: 'text-severityText-low',
  info: 'text-severityText-info',
  benign: 'text-severityText-benign',
};

/** The base hue, as the rail. Fills and rails use the base hues (§5.3). */
const RAIL: Record<Severity, string> = {
  critical: 'border-severity-critical',
  high: 'border-severity-high',
  medium: 'border-severity-medium',
  low: 'border-severity-low',
  info: 'border-severity-info',
  benign: 'border-severity-benign',
};

export interface SeverityPillProps {
  severity: Severity;
  /**
   * A qualifier in words, e.g. `partial evidence` — §8.1's partial/degraded state,
   * which must be labelled rather than presented as complete.
   */
  detail?: string | undefined;
}

export function SeverityPill({ severity, detail }: SeverityPillProps) {
  return (
    <span
      className={`inline-flex items-baseline gap-2 border-l-rail pl-2 ${RAIL[severity]} ${TEXT[severity]}`}
    >
      <span aria-hidden="true">{SEVERITY_GLYPHS[severity]}</span>
      <span className="text-caption font-semibold">{SEVERITY_LABELS[severity]}</span>
      {detail === undefined ? null : <span className="text-caption text-muted">{detail}</span>}
    </span>
  );
}
