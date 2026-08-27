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
  <div className={cn("bg-app-surface border border-line-subtle rounded-2xl p-5", className)}>
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

/** Skeleton that matches a StatCard: label bar + big number + hint. */
export const SkeletonStatCard: React.FC<{ className?: string }> = ({ className }) => (
  <div
    className={cn(
      "bg-app-surface border border-line-subtle rounded-2xl p-5 shadow-card",
      className
    )}
  >
    <Skeleton className="h-2.5 w-20" />
    <Skeleton className="h-8 w-16 mt-3" />
    <Skeleton className="h-2.5 w-24 mt-2.5" />
  </div>
);

/** Skeleton that matches a chart / content card: title bar + body block. */
export const SkeletonChart: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cn("bg-app-surface border border-line-subtle rounded-2xl p-6 shadow-card", className)}>
    <Skeleton className="h-3.5 w-36" />
    <div className="mt-6 space-y-3">
      <Skeleton className="h-2 w-full" />
      <Skeleton className="h-2 w-11/12" />
      <Skeleton className="h-2 w-4/5" />
      <Skeleton className="h-2 w-3/5" />
      <Skeleton className="h-2 w-1/2" />
    </div>
  </div>
);

/** Skeleton list rows (sidebars, activity feeds): icon + two lines each. */
export const SkeletonList: React.FC<{ rows?: number; className?: string }> = ({
  rows = 5,
  className,
}) => (
  <div className={cn("bg-app-surface border border-line-subtle rounded-2xl shadow-card divide-y divide-line-subtle overflow-hidden", className)}>
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex items-center gap-3 px-4 py-3.5">
        <Skeleton className="w-8 h-8 rounded-lg shrink-0" />
        <div className="flex-1 min-w-0 space-y-2">
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="h-2.5 w-3/5" />
        </div>
        <Skeleton className="h-4 w-10 shrink-0" />
      </div>
    ))}
  </div>
);

const HEADER_WIDTHS = ["w-24", "w-16", "w-28", "w-20", "w-32", "w-24"];
const ROW_WIDTHS = ["w-32", "w-20", "w-40", "w-28", "w-36", "w-24"];

/** Table skeleton: header + N shimmer rows with a column layout that echoes
 *  the real table (varied widths + optional select-all checkbox column).
 *  Pass `bare` when the skeleton sits inside a Card that already provides the
 *  outer chrome (avoids a nested double-card border). */
export const SkeletonTable: React.FC<{
  rows?: number;
  cols?: number;
  checkbox?: boolean;
  bare?: boolean;
}> = ({ rows = 6, cols = 4, checkbox = false, bare = false }) => (
  <div
    className={cn(
      !bare && "bg-app-surface border border-line-subtle rounded-2xl shadow-card overflow-hidden"
    )}
  >
    <div className="px-5 py-3.5 border-b border-line-subtle bg-app-subtle/60 flex items-center gap-6">
      {checkbox && <Skeleton className="w-4 h-4 rounded shrink-0" />}
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", HEADER_WIDTHS[i % HEADER_WIDTHS.length])} />
      ))}
    </div>
    <div className="divide-y divide-line-subtle">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="px-5 py-4 flex items-center gap-6">
          {checkbox && <Skeleton className="w-4 h-4 rounded shrink-0" />}
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-3", ROW_WIDTHS[c % ROW_WIDTHS.length])} />
          ))}
        </div>
      ))}
    </div>
  </div>
);
