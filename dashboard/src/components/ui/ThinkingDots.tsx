import React from "react";
import { cn } from "./Button";

/**
 * ThinkingDots — the AI "reasoning" indicator (spec §30 / §40.8).
 *
 * Three dots, staggered, signal green. No glow, no pulse-storm, no scaling —
 * motion here means "work is happening", never "look at me". The dots are
 * `aria-hidden`; the accompanying text carries the meaning for assistive tech,
 * and the whole row is a `role="status"` so it is announced once.
 *
 * Reduced motion: `globals.css` collapses every animation to 0.01ms, which
 * leaves the dots lit and static — still a live status, no movement.
 */
export const ThinkingDots: React.FC<{ className?: string }> = ({ className }) => (
  <span className={cn("inline-flex items-center gap-[3px]", className)} aria-hidden="true">
    {[0, 1, 2].map((i) => (
      <span
        key={i}
        className="h-1 w-1 rounded-full bg-accent-primary animate-thinking-dot"
        style={{ animationDelay: `${i * 0.16}s` }}
      />
    ))}
  </span>
);

/** Full reasoning row: dots + the honest label. Use wherever NOCTRA is working. */
export const ThinkingIndicator: React.FC<{
  label?: string;
  className?: string;
}> = ({ label = "NOCTRA is reasoning", className }) => (
  <div
    role="status"
    className={cn(
      "flex items-center gap-2 text-xs text-content-tertiary",
      className
    )}
  >
    <ThinkingDots />
    <span>{label}…</span>
  </div>
);

export default ThinkingDots;
