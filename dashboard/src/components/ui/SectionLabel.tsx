import React from "react";
import { cn } from "./Button";

/**
 * SectionLabel — the overline eyebrow used across the landing and page heads
 * (SaaS hero pattern: tiny, tracked-out, mono where it labels product moments).
 */
export interface SectionLabelProps extends React.HTMLAttributes<HTMLParagraphElement> {
  children: React.ReactNode;
  /** Use mono styling (product/technical labels) instead of the sans overline. */
  mono?: boolean;
  tone?: "default" | "accent" | "muted";
}

export function SectionLabel({
  children,
  mono = false,
  tone = "accent",
  className,
  ...props
}: SectionLabelProps) {
  return (
    <p
      className={cn(
        "inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.28em]",
        mono && "font-mono tracking-[0.18em] text-[10px]",
        tone === "accent" && "text-accent-secondary",
        tone === "default" && "text-content-primary",
        tone === "muted" && "text-content-tertiary",
        className
      )}
      {...props}
    >
      {children}
    </p>
  );
}

export default SectionLabel;
