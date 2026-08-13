import React from "react";
import { cn } from "./Button";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

/** Friendly empty state for tables/panels that have no data yet. */
export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon,
  action,
  className,
}) => (
  <div
    className={cn(
      "flex flex-col items-center justify-center text-center py-12 px-6",
      className
    )}
  >
    {icon && <div className="mb-3 text-content-tertiary flex items-center justify-center">{icon}</div>}
    <p className="text-sm font-medium text-content-secondary">{title}</p>
    {description && <p className="text-xs text-content-tertiary mt-1 max-w-sm">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);