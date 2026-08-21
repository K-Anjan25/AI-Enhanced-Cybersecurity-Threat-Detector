import React from "react";
import { cn } from "./Button";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padded?: boolean;
  interactive?: boolean;
}

/**
 * Standard SOC surface card with consistent border, radius and shadow.
 */
export const Card: React.FC<CardProps> = ({
  className,
  padded = true,
  interactive = false,
  children,
  ...props
}) => (
  <div
    className={cn(
      "bg-app-surface border border-line-subtle rounded-xl shadow-card",
      padded && "p-5",
      interactive &&
        "hover:bg-app-surface-raised hover:border-accent-primary/20 hover:shadow-raised transition-all cursor-pointer focus-visible:outline-none",
      className
    )}
    {...props}
  >
    {children}
  </div>
);

export interface CardHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export const CardHeader: React.FC<CardHeaderProps> = ({
  title,
  description,
  action,
  className,
}) => (
  <div className={cn("flex items-start justify-between gap-3", className)}>
    <div>
      <h3 className="text-sm font-semibold text-content-primary tracking-tight">{title}</h3>
      {description && <p className="text-xs text-content-tertiary mt-0.5">{description}</p>}
    </div>
    {action}
  </div>
);