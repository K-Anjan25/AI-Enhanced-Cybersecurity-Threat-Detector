/** Lightweight header indicator for the backend alert-stream health and RTT. */
import { useOptionalRealtime } from './RealtimeProvider';

const STATUS: Record<
  'connecting' | 'live' | 'polling' | 'refused',
  { label: string; tone: string; dot: string }
> = {
  connecting: { label: 'Connecting', tone: 'text-muted', dot: 'bg-muted' },
  live: { label: 'Live', tone: 'text-accent', dot: 'bg-accent' },
  polling: {
    label: 'Polling fallback',
    tone: 'text-severityText-medium',
    dot: 'bg-severity-medium',
  },
  refused: {
    label: 'Connection refused',
    tone: 'text-severityText-critical',
    dot: 'bg-severity-critical',
  },
};

function formatRtt(rttMs: number | null): string {
  if (rttMs === null) return '—';
  if (rttMs < 1) return '<1 ms';
  return `${Math.round(rttMs)} ms`;
}

/**
 * Shows actual stream state; the latency is an application-level ping/pong to the
 * backend, not ICMP and not a synthetic estimate. No provider means no indicator.
 */
export function RealtimeStatus() {
  const realtime = useOptionalRealtime();
  if (realtime === null) return null;

  const status = STATUS[realtime.state];
  const rttLabel = formatRtt(realtime.rttMs);
  const description = realtime.detail ?? 'Alert stream health from the backend';
  const rttDescription =
    'Application-level ping/pong round-trip time to the AEGIS backend; not ICMP';

  return (
    <div
      className={`inline-flex shrink-0 items-center gap-2 rounded-pill border border-line bg-surface px-2 py-1 font-mono text-caption ${status.tone}`}
    >
      <span
        role="status"
        aria-live="polite"
        aria-atomic="true"
        title={`${description}. ${rttDescription}.`}
        className="inline-flex items-center gap-2"
      >
        <span aria-hidden="true" className={`size-2 shrink-0 rounded-pill ${status.dot}`} />
        <span className="sr-only">{status.label}</span>
        <span aria-hidden="true" className="hidden md:inline">
          {status.label}
        </span>
        <span aria-hidden="true" className="hidden lg:inline">
          RTT
        </span>
        <span aria-hidden="true" className="hidden md:inline font-mono tabular-nums">
          {rttLabel}
        </span>
        <span className="sr-only">
          Application RTT {rttLabel}. {rttDescription}.
        </span>
      </span>
    </div>
  );
}
