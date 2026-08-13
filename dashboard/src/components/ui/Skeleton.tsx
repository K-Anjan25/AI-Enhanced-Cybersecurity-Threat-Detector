import React from "react";
import { cn } from "./Button";

export interface SkeletonProps {
  className?: string;
}

/** Pulsing placeholder used while data loads. */
export const Skeleton: React.FC<SkeletonProps> = ({ className }) => (
  <div className={cn("animate-pulse rounded-lg bg-app-subtle", className)} />
);

export const SkeletonCard: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cn("bg-app-surface border border-line-subtle rounded-xl p-5", className)}>
    <Skeleton className="h-3 w-24 mb-3" />
    <Skeleton className="h-8 w-16" />
  </div>
);

export const SkeletonText: React.FC<{ lines?: number; className?: string }> = ({
  lines = 3,
  className,
}) => (
  <div className="space-y-2">
    {Array.from({ length: lines }).map((_, i) => (
      <Skeleton key={i} className={cn("h-3 w-full", className)} />
    ))}
  </div>
);

/** Table skeleton: header + N shimmer rows with matching column layout. */
export const SkeletonTable: React.FC<{ rows?: number; cols?: number }> = ({
  rows = 6,
  cols = 4,
}) => (
  <div className="bg-app-surface border border-line-subtle rounded-xl shadow-card overflow-hidden">
    <div className="px-5 py-3.5 border-b border-line-subtle bg-app-subtle/50 flex gap-6">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-20" />
      ))}
    </div>
    <div className="divide-y divide-line-subtle">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="px-5 py-4 flex gap-6 items-center">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 w-24" />
          ))}
        </div>
      ))}
    </div>
  </div>
);