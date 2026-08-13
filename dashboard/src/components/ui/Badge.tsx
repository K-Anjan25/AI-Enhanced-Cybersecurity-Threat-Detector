import React from "react";
import { cn } from "./Button";

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode;
}

/** Generic pill badge, token-driven. */
export const Badge: React.FC<BadgeProps> = ({ children, className, ...props }) => (
  <span
    className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium border whitespace-nowrap",
      className
    )}
    {...props}
  >
    {children}
  </span>
);

const SEVERITY_STYLES: Record<Severity, { badge: string; dot: string }> = {
  CRITICAL: {
    badge: "bg-status-critical/15 text-status-critical border-status-critical/30",
    dot: "bg-status-critical",
  },
  HIGH: {
    badge: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    dot: "bg-orange-400",
  },
  MEDIUM: {
    badge: "bg-status-warning/15 text-status-warning border-status-warning/30",
    dot: "bg-status-warning",
  },
  LOW: {
    badge: "bg-status-success/15 text-status-success border-status-success/30",
    dot: "bg-status-success",
  },
};

export interface SeverityBadgeProps {
  severity: string;
  withDot?: boolean;
  className?: string;
}

/**
 * Severity badge. Colour is paired with a dot and label text, so it never
 * relies on colour alone (WCAG 2.1 AA).
 */
export const SeverityBadge: React.FC<SeverityBadgeProps> = ({
  severity,
  withDot = true,
  className,
}) => {
  const key = (severity || "LOW").trim().toUpperCase() as Severity;
  const styles = SEVERITY_STYLES[key] || SEVERITY_STYLES.LOW;
  return (
    <Badge className={cn(styles.badge, className)}>
      {withDot && <span className={cn("w-1.5 h-1.5 rounded-full", styles.dot)} />}
      <span className="capitalize-first font-semibold capitalize">{key.toLowerCase()}</span>
    </Badge>
  );
};

/** Informational status badge (e.g. "Operational", "Triaging"). */
export const StatusBadge: React.FC<{ tone: "success" | "warning" | "critical" | "neutral"; label: string }> = ({
  tone,
  label,
}) => {
  const map = {
    success: "bg-status-success/15 text-status-success border-status-success/30",
    warning: "bg-status-warning/15 text-status-warning border-status-warning/30",
    critical: "bg-status-critical/15 text-status-critical border-status-critical/30",
    neutral: "bg-app-subtle text-content-secondary border-line-subtle",
  } as const;
  return <Badge className={map[tone]}>{label}</Badge>;
};