/**
 * The global connection banner (design.md §6: `ConnectionStatus` "drives the
 * global banner"; architecture.md §10 and §14: a *visible* `disconnected` banner).
 *
 * It is presentational — the state and the words come from `useConnectionView`,
 * which is the half that knows about the client. That split is what makes the
 * banner testable without a socket and the state machine testable without a DOM.
 *
 * Three rules about what it says:
 *
 *   * **What happened, then what the app is doing about it.** "Live updates are
 *     off — showing the API's data and polling every 15 s" tells an analyst both
 *     that the screen is not live *and* that it is not frozen. A banner that only
 *     said "disconnected" would leave them guessing whether the numbers still
 *     move.
 *   * **No raw error.** R-58: a failed request's message carries a URL, and the
 *     banner renders none of that — only what kind of failure it was.
 *   * **An action, not an apology.** A Retry is offered whenever the state is one
 *     a retry can fix; the backoff continues on its own either way.
 */
import { Button } from '../ui';
import type { ShellConnectionState } from '../../lib/realtime';

export interface ConnectionBannerProps {
  state: ShellConnectionState;
  /** The headline: what is not working. */
  message: string;
  /** The sentence under it: what the dashboard is doing instead. */
  explanation: string;
  /** Called by the Retry control. */
  onRetry?: (() => void) | undefined;
}

export function ConnectionBanner({ state, message, explanation, onRetry }: ConnectionBannerProps) {
  if (state === 'live') return null;

  return (
    <div
      role="status"
      aria-live="polite"
      // The wording is not coloured-only: the message is in words and the tone
      // (critical for a broken stream, medium while connecting) is an accent on
      // top of it (NFR-09).
      className={`flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-6 py-2 ${
        state === 'disconnected' ? 'text-severityText-critical' : 'text-severityText-medium'
      }`}
    >
      <p className="text-body-sm">
        <span className="font-semibold">{message}</span>{' '}
        <span className="text-muted">{explanation}</span>
      </p>
      {onRetry === undefined ? null : (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Reconnect now
        </Button>
      )}
    </div>
  );
}
