/**
 * The viewport, as React state (T-412).
 *
 * One hook, so a screen's layout and the shell's chrome cannot disagree about how
 * wide the window is: `AppShell` hides the rail with the same answer that makes the
 * triage page drop the queue beside the detail.
 *
 * It re-renders on `change` rather than on every resize event: `matchMedia` fires
 * when a query's answer flips, which is exactly when a class changes, and a resize
 * that stays inside a class is not a reason to re-render a screen.
 *
 * The fallback is the *wide* class, deliberately — see `lib/viewport.ts` for why an
 * environment that cannot measure itself gets the full console rather than the
 * triage-only one.
 */
import { useEffect, useState } from 'react';

import {
  VIEWPORT_QUERY,
  viewportClassFrom,
  type ViewportClass,
  type ViewportMatches,
} from '../../lib/viewport';

/** Whether the three queries answer, right now. */
function readMatches(): ViewportMatches {
  if (typeof window.matchMedia !== 'function') {
    return { narrow: false, narrowOrCompact: false, belowWide: false };
  }
  return {
    narrow: window.matchMedia(VIEWPORT_QUERY.narrow).matches,
    narrowOrCompact: window.matchMedia(VIEWPORT_QUERY.narrowOrCompact).matches,
    belowWide: window.matchMedia(VIEWPORT_QUERY.belowWide).matches,
  };
}

/** The current class, read once and not subscribed. */
export function currentViewportClass(): ViewportClass {
  return viewportClassFrom(readMatches());
}

/** The window's class, re-read whenever one of §8.3's boundaries is crossed. */
export function useViewportClass(): ViewportClass {
  const [viewport, setViewport] = useState<ViewportClass>(currentViewportClass);

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const lists = {
      narrow: window.matchMedia(VIEWPORT_QUERY.narrow),
      narrowOrCompact: window.matchMedia(VIEWPORT_QUERY.narrowOrCompact),
      belowWide: window.matchMedia(VIEWPORT_QUERY.belowWide),
    };
    const onChange = () => {
      setViewport(
        viewportClassFrom({
          narrow: lists.narrow.matches,
          narrowOrCompact: lists.narrowOrCompact.matches,
          belowWide: lists.belowWide.matches,
        }),
      );
    };
    // Re-read on mount as well: the window can have been resized between the first
    // render and this effect, and a stale class would be a screen laid out for a
    // window that is no longer there.
    onChange();
    for (const list of Object.values(lists)) list.addEventListener('change', onChange);
    return () => {
      for (const list of Object.values(lists)) list.removeEventListener('change', onChange);
    };
  }, []);

  return viewport;
}
