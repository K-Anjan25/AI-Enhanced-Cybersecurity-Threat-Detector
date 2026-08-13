import React from "react";
import { cn } from "./Button";

/**
 * Accessible loading spinner with a text label for assistive tech.
 */
export const Spinner: React.FC<{ label?: string; className?: string }> = ({
  label = "Loading",
  className,
}) => (
  <span
    role="status"
    aria-label={label}
    className={cn("inline-block", className)}
  >
    <span className="block w-4 h-4 border-2 border-accent-primary/30 border-t-accent-primary rounded-full animate-spin" />
    <span className="sr-only">{label}…</span>
  </span>
);

/** Centered loading block for page/panel placeholder. */
export const LoadingState: React.FC<{ label?: string }> = ({ label = "Loading" }) => (
  <div className="flex items-center gap-3 justify-center py-12 text-content-secondary text-sm">
    <Spinner />
    <span>{label}…</span>
  </div>
);