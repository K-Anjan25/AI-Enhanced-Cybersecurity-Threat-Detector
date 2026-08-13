import React from "react";

export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}

/** Consistent page heading: title + description + optional actions. */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, description, actions, badge }) => (
  <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
    <div>
      <div className="flex items-center gap-2.5">
        <h1 className="text-2xl font-bold text-content-primary tracking-tight">{title}</h1>
        {badge}
      </div>
      {description && <p className="text-sm text-content-secondary mt-1">{description}</p>}
    </div>
    {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
  </div>
);