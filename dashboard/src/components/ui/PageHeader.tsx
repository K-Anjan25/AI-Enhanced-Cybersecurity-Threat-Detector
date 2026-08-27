import React from "react";
import { BackButton } from "./BackButton";
import { Breadcrumbs, Crumb } from "./Breadcrumbs";

export interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
  /** Route/count to navigate back to when the page is a deep view. */
  backTo?: string | number;
  /** Breadcrumb trail shown above the title. */
  crumbs?: Crumb[];
}

/** Consistent page heading: optional back/breadcrumbs + title + description + actions. */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, description, actions, badge, backTo, crumbs }) => (
  <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
    <div className="min-w-0">
      {(backTo !== undefined || (crumbs && crumbs.length > 0)) && (
        <div className="mb-1.5 flex items-center gap-1">
          {crumbs && crumbs.length > 0 ? (
            <>
              <BackButton to={backTo} label="" className="px-1.5" />
              <Breadcrumbs items={crumbs} />
            </>
          ) : (
            <BackButton to={backTo} />
          )}
        </div>
      )}
      <div className="flex items-center gap-2.5">
        <h1 className="text-2xl sm:text-[1.7rem] font-bold font-display text-neutral-900 tracking-tight">{title}</h1>
        {badge}
      </div>
      {description && <p className="text-sm text-neutral-500 mt-1 max-w-3xl">{description}</p>}
    </div>
    {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
  </div>
);