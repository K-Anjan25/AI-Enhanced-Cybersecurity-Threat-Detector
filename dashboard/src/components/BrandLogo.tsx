import React from "react";
import { BRAND_NAME } from "../constants/brand";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  className?: string;
};

/**
 * NOCTRA Logo Mark — Owl-Eye Radar Diamond in Obsidian Ember palette.
 * Pure SVG, highly scalable from favicon to high-res headers.
 */
const BrandLogo: React.FC<Props> = ({
  collapsed = false,
  size = 28,
  withWordmark = true,
  className,
}) => {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className || ""}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
        className="shrink-0"
      >
        {/* Outer Radar Diamond Shield - Warm Amber */}
        <path
          d="M16 2 L29 16 L16 30 L3 16 Z"
          stroke="#f59e0b"
          strokeWidth="1.8"
          fill="rgba(245, 158, 11, 0.1)"
        />
        {/* Inner Sentinel Eye Diamond - Calm Sage */}
        <path
          d="M16 8 L23 16 L16 24 L9 16 Z"
          stroke="#84a98c"
          strokeWidth="1.5"
          fill="none"
        />
        {/* Central Pupil Core */}
        <circle cx="16" cy="16" r="2.5" fill="#f59e0b" />
      </svg>

      {withWordmark && !collapsed && (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-extrabold font-display tracking-[0.14em] text-content-primary">
            {BRAND_NAME}
          </span>
          <span className="text-[9px] font-bold tracking-[0.18em] text-accent-amber uppercase mt-0.5">
            THREAT OPS ANALYST
          </span>
        </span>
      )}
    </span>
  );
};

export default BrandLogo;
