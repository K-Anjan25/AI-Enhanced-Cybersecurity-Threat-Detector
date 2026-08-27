import React from "react";
import { CheckCircle2, ShieldCheck, Lock } from "lucide-react";
import { cn } from "./Button";

/**
 * TrustPill — a trust/proof chip (WooCommerce trust-signal pattern): a small,
 * labeled assurance ("Record-only by design", "Append-only audit", …).
 * Always paired with a lucide mark; never fabricated claims.
 */
export type TrustPillIcon = "check" | "shield" | "lock";

export interface TrustPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  icon?: TrustPillIcon;
}

const ICONS: Record<TrustPillIcon, React.ReactNode> = {
  check: <CheckCircle2 size={13} aria-hidden />,
  shield: <ShieldCheck size={13} aria-hidden />,
  lock: <Lock size={13} aria-hidden />,
};

export function TrustPill({ icon = "shield", children, className, ...props }: TrustPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-line-subtle bg-app-surface px-3 py-1.5 text-xs font-medium text-content-secondary",
        className
      )}
      {...props}
    >
      <span className="text-status-success shrink-0" aria-hidden>
        {ICONS[icon]}
      </span>
      {children}
    </span>
  );
}

export default TrustPill;
