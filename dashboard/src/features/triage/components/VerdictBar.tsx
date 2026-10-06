/**
 * The sticky verdict bar — design.md §4.3's first element, and the screen's one
 * write.
 *
 * "The verdict bar is sticky and reachable without scrolling. Keyboard verdicts
 * `1`/`2`/`3`." Both halves are structural here:
 *
 *   * **sticky** — `sticky top-0` on the bar itself, inside the page's scroll
 *     container. The analyst reads zone 3, decides, and the controls are still on
 *     screen; nothing about the decision requires scrolling back.
 *   * **`1`/`2`/`3`** — the keys are read from `VERDICT_SHORTCUTS`, the same table
 *     the buttons render from, so the key and the button cannot come to mean
 *     different things. `useVerdictShortcuts` owns the three ways a shortcut goes
 *     wrong (repeats, modifiers, typing in a field).
 *
 * The current verdict is a live region: a verdict recorded from the keyboard
 * changes text the analyst is looking at, and a change nobody is told about is a
 * change nobody saw. The write's own failure is announced the same way, in the
 * bar where the buttons are.
 */
import { Link } from 'react-router-dom';

import { Button, isSeverity, SeverityPill } from '../../../components/ui';
import { useVerdictShortcuts } from '../hooks';
import type { AlertDetail } from '../types';
import { verdictBarFacts, verdictLine } from '../view';
import { VERDICT_SHORTCUTS, verdictForKey, type VerdictName } from '../verdicts';

export interface VerdictBarProps {
  detail: AlertDetail;
  /** Record a verdict. The page owns the mutation; the bar owns the keys. */
  onVerdict: (verdict: VerdictName) => void;
  /** True while a write is in flight, so the keys cannot queue a second one. */
  pending?: boolean;
  /** What went wrong with the last write, if anything (R-58: no URL, no body). */
  errorMessage?: string | null;
  /** Where the next alert in the queue is, or `null` when this is the last one. */
  next: string | null;
}

export function VerdictBar({
  detail,
  onVerdict,
  pending = false,
  errorMessage = null,
  next,
}: VerdictBarProps) {
  const facts = verdictBarFacts(detail);
  const current = outputLine(verdictLine(detail.verdict.current));

  useVerdictShortcuts(onVerdict, !pending, verdictForKey);

  return (
    <section
      aria-label="Verdict"
      className="sticky top-0 z-10 flex flex-col gap-3 border border-line bg-surface px-4 py-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        {isSeverity(detail.alert.severity) ? (
          <SeverityPill severity={detail.alert.severity} />
        ) : (
          <span className="text-body-sm font-semibold text-ink">{facts.severity}</span>
        )}
        <span className="font-mono text-body-sm text-ink">score {facts.score}</span>
        <span className="text-body-sm text-ink">{facts.family}</span>
        <span className="text-body-sm text-muted">{facts.entity}</span>
        <span className="font-mono text-body-sm text-muted">{facts.at}</span>
        <span className="ml-auto">
          {next === null ? (
            <span className="text-body-sm text-muted">last alert in the queue</span>
          ) : (
            <Link className="text-body-sm underline" to={next}>
              Next alert ▸
            </Link>
          )}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {VERDICT_SHORTCUTS.map((shortcut) => (
          <Button
            key={shortcut.verdict}
            variant="secondary"
            onClick={() => onVerdict(shortcut.verdict)}
            disabled={pending}
            aria-keyshortcuts={shortcut.key}
          >
            <kbd className="mr-2 rounded-input border border-line px-1 font-mono text-caption">
              {shortcut.key}
            </kbd>
            {shortcut.label}
          </Button>
        ))}
        <p aria-live="polite" className="ml-2 text-body-sm text-muted">
          {current ?? 'No verdict recorded yet — press 1, 2 or 3.'}
        </p>
      </div>

      {errorMessage === null ? null : (
        <p role="alert" className="text-body-sm font-semibold text-severityText-critical">
          {errorMessage}
        </p>
      )}
    </section>
  );
}

/** The live region's text for a recorded verdict, or `null` when there is none. */
function outputLine(line: string | null): string | null {
  return line === null ? null : `Current verdict: ${line}`;
}
