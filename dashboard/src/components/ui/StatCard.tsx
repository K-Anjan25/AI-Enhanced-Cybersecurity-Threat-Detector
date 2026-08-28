import React from "react";
import { Card } from "./Card";
import { cn } from "./Button";

export interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "success" | "warning" | "critical" | "accent";
  icon?: React.ReactNode;
  className?: string;
}

const TONE_TEXT: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "text-content-primary",
  success: "text-status-success",
  warning: "text-status-warning",
  critical: "text-status-critical",
  accent: "text-accent-primary",
};

const TONE_ICON: Record<NonNullable<StatCardProps["tone"]>, string> = {
  default: "bg-app-subtle text-content-secondary",
  success: "bg-status-success/15 text-status-success",
  warning: "bg-status-warning/15 text-status-warning",
  critical: "bg-status-critical/15 text-status-critical",
  accent: "bg-accent-primary/15 text-accent-primary",
};

/**
 * KPI card for the SOC overview: label + big value + optional hint + icon.
 */
export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  hint,
  tone = "default",
  icon,
  className,
}) => (
  <Card className={cn("p-5 flex flex-col justify-between gap-3", className)}>
    <div className="flex items-start justify-between gap-3">
      <p className="tech-label text-content-tertiary leading-tight">
        {label}
      </p>
      {icon && (
        <span className={cn("w-9 h-9 rounded-sm flex items-center justify-center shrink-0", TONE_ICON[tone])}>
          {icon}
        </span>
      )}
    </div>
    <div>
      <p className={cn("text-3xl font-bold tabular-nums leading-none tracking-tight", TONE_TEXT[tone])}>{value}</p>
      {hint && <p className="text-xs text-content-tertiary mt-2">{hint}</p>}
    </div>
  </Card>
);