/**
 * Polling hooks shared by more than one screen.
 *
 * They live under `components/` rather than in a feature because they are not
 * about any one screen's data: `design.md` §4.1's "auto-refresh ... pause when the
 * tab is hidden" and §8.1's "stale data shows a last-update age" are properties of
 * *live screens in general*. The features layer sits above this one, so the
 * overview and the triage screen both read them from here; a feature cannot import
 * another feature (R-22's slice rule, checked by `check_frontend_boundaries.py`),
 * and a copy per feature would be two answers to "when does polling stop?".
 *
 * They are not in `lib` because they are React — `lib` is the layer that must stay
 * framework-free.
 */
import { useEffect, useState } from 'react';

/**
 * Whether the tab is visible, for pausing the polls.
 *
 * A dashboard left open in a background tab must not keep hitting the API: the
 * operator cannot see the answer, and the cost is paid by the service everyone
 * shares.
 */
export function useDocumentVisible(): boolean {
  const [visible, setVisible] = useState(() => document.visibilityState !== 'hidden');

  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  return visible;
}

/**
 * A clock that ticks, for ages and other relative times.
 *
 * Without it an age would be computed once and then freeze — the exact failure
 * §8.1's stale state exists to prevent, since a frozen age looks like a live
 * screen that simply has not changed.
 */
export function useNow(intervalMs = 1_000, enabled = true): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!enabled) return undefined;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, enabled]);

  return now;
}
