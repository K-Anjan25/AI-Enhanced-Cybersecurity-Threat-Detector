/**
 * Skeleton — R-29 / design.md §8.1: "Loading: skeletons matching the final layout.
 * Spinners only for actions under 1 s."
 *
 * A skeleton is a *shape*, not a message, so the bars are `aria-hidden` and the
 * accessible fact is carried once: `aria-busy="true"` on a labelled `role="status"`
 * region. Without that, a screen-reader user is told "Loading" once per bar — or,
 * with the bars hidden and nothing else added, is told nothing at all while the
 * page stays empty.
 *
 * `lines` matches the block being replaced, which is what "matching the final
 * layout" means in practice: a three-line paragraph becomes three bars.
 */
export interface SkeletonProps {
  /** How many bars to draw, for the block this stands in for. */
  lines?: number;
  /** What is loading, in the operator's words — "Alert list". */
  label?: string;
}

export function Skeleton({ lines = 1, label = 'Loading' }: SkeletonProps) {
  return (
    // One label, not two: an `aria-label` *and* a visually hidden copy of the same
    // words would be announced twice.
    <div role="status" aria-busy="true">
      <span className="sr-only">{label}</span>
      <div className="flex flex-col gap-2" aria-hidden="true">
        {Array.from({ length: lines }, (_unused, index) => (
          <div
            key={index}
            data-testid="skeleton-bar"
            className="h-2 animate-pulse rounded-input bg-surface"
          />
        ))}
      </div>
    </div>
  );
}
