import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

export interface Crumb {
  label: string;
  to?: string;
}

export interface BreadcrumbsProps {
  items: Crumb[];
}

/** Breadcrumb trail for deep views so users never get stranded. */
export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ items }) => (
  <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 flex-wrap text-xs">
    {items.map((item, i) => {
      const last = i === items.length - 1;
      return (
        <React.Fragment key={`${item.label}-${i}`}>
          {i > 0 && (
            <ChevronRight size={12} className="text-content-tertiary" aria-hidden />
          )}
          {!last && item.to ? (
            <Link
              to={item.to}
              className="text-content-secondary hover:text-accent-primary transition font-medium"
            >
              {item.label}
            </Link>
          ) : (
            <span className={last ? "text-content-primary font-semibold" : "text-content-secondary"}>
              {item.label}
            </span>
          )}
        </React.Fragment>
      );
    })}
  </nav>
);

export default Breadcrumbs;