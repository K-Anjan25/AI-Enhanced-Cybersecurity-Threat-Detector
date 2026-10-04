/**
 * Live connection indicator.
 *
 * design.md principle 5 and §8.1: a quiet screen must never be ambiguous. The
 * analyst has to be able to tell "nothing is happening" from "we stopped
 * hearing from the server", so the state is always rendered explicitly and is
 * encoded by colour AND label AND glyph (never colour alone, NFR-09).
 */
import { useTheme } from '../../theme/ThemeProvider';

export type ConnectionState = 'live' | 'degraded' | 'disconnected';

interface ConnectionStatusProps {
  state: ConnectionState;
  /** Human-readable detail, e.g. "last update 2 m ago". */
  detail?: string | undefined;
}

const LABELS: Record<ConnectionState, string> = {
  live: 'Live',
  degraded: 'Degraded',
  disconnected: 'Disconnected',
};

const GLYPHS: Record<ConnectionState, string> = {
  live: '\u25CF', // filled circle
  degraded: '\u25D0', // half circle
  disconnected: '\u25CB', // hollow circle
};

const TEXT_CLASSES: Record<ConnectionState, string> = {
  live: 'text-severityText-benign',
  degraded: 'text-severityText-medium',
  disconnected: 'text-severityText-critical',
};

const FILL_CLASSES: Record<ConnectionState, string> = {
  live: 'bg-severity-benign',
  degraded: 'bg-severity-medium',
  disconnected: 'bg-severity-critical',
};

export function ConnectionStatus({ state, detail }: ConnectionStatusProps) {
  // Theme is read so the component re-renders on a theme change; the colours
  // themselves come from CSS variables that already switch per theme.
  useTheme();

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 rounded-pill border border-line px-3 py-1"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-pill ${FILL_CLASSES[state]}`} />
      <span className={`text-caption font-semibold ${TEXT_CLASSES[state]}`}>
        <span aria-hidden="true">{GLYPHS[state]} </span>
        {LABELS[state]}
      </span>
      {detail !== undefined ? <span className="text-caption text-muted">{detail}</span> : null}
    </div>
  );
}
