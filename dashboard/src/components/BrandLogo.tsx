import React from "react";
import { BRAND_NAME } from "../constants/brand";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  className?: string;
};

/**
 * AXIOM AI Logo Mark — Geometric Axiom Proposition + Security Shield.
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
        {/* Outer Axiom Delta Shield - Cobalt Blue */}
        <path
          d="M16 3 L28 11 V21 L16 29 L4 21 V11 Z"
          stroke="#2563eb"
          strokeWidth="1.8"
          fill="rgba(37, 99, 235, 0.08)"
        />
        {/* Stylized Interlocking Axiom A / Delta */}
        <path
          d="M16 7 L23 21 H9 Z"
          stroke="#2563eb"
          strokeWidth="1.5"
          fill="none"
        />
        <path
          d="M11.5 17 H20.5"
          stroke="#2563eb"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        {/* Central Intelligence Node Dot */}
        <circle cx="16" cy="14" r="2.2" fill="#2563eb" />
        {/* Outer Node Orbit Ring */}
        <circle
          cx="16"
          cy="16"
          r="10"
          stroke="#3b82f6"
          strokeWidth="0.8"
          strokeDasharray="2 2"
          opacity={0.6}
        />
      </svg>

      {withWordmark && !collapsed && (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-extrabold font-display tracking-[0.12em] text-slate-900">
            {BRAND_NAME}
          </span>
          <span className="text-[9px] font-bold tracking-[0.2em] text-blue-600 uppercase mt-0.5">
            AUTONOMOUS ANALYST
          </span>
        </span>
      )}
    </span>
  );
};

export default BrandLogo;
