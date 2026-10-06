/**
 * The narrow-viewport banner (T-412, design.md §8.3).
 *
 * §8.3's last row: *"< 768 px | Triage-focused: alert list and alert detail only. A
 * banner states that the full console needs a larger screen."* So the banner has one
 * job, and it is a statement rather than an apology: what this window is showing, and
 * why the rest is absent.
 *
 * Two things about it are deliberate:
 *
 *   * **It is a `role="status"`, not an alert.** Nothing went wrong. An operator on a
 *     phone is in a supported state, and an assertive region would interrupt a screen
 *     reader reading the queue behind it.
 *   * **It names the number, not "mobile".** "At least 768 px" is checkable by the
 *     person holding the device — they can rotate it and watch the banner go — where
 *     "a larger screen" alone would leave them guessing how much larger.
 *
 * The link back to the queue is offered only where it goes somewhere new, which is
 * the caller's decision: the shell knows the current route, this does not.
 */
import { Link } from 'react-router-dom';

// The queue's address from `lib/routes`, not from the triage feature: a shared
// component may not reach up into a feature (rules.md §7), and the path is the same
// string either way.
import { ALERTS_PATH } from '../../lib/routes';
import { VIEWPORT_BREAKPOINTS } from '../../lib/viewport';

export interface NarrowNoticeProps {
  /** The queue link, when the banner is not already standing over the queue. */
  showQueueLink?: boolean;
}

export function NarrowNotice({ showQueueLink = false }: NarrowNoticeProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      // Named, so the region is identifiable when a screen reader lists the page's
      // live regions: the shell already has two more (`ConnectionStatus` in the top bar
      // and the empty states below), and three unnamed status regions are
      // indistinguishable in a rotor menu.
      aria-label="Screen size"
      className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-b border-line bg-surface px-6 py-2 text-body-sm"
    >
      <span className="font-semibold text-ink">
        Only alert triage is offered at this window size.
      </span>
      <span className="text-muted">
        The rest of the console needs a window at least {VIEWPORT_BREAKPOINTS.compact} px wide.
      </span>
      {showQueueLink ? (
        <Link className="underline" to={ALERTS_PATH}>
          Go to the alert queue
        </Link>
      ) : null}
    </div>
  );
}
