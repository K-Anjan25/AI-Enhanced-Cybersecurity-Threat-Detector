import React from "react";
import { BRAND_NAME } from "../constants/brand";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  className?: string;
};

/**
 * NOCTRA mark — geometric owl-eye / radar sweep.
 * - Diamond outer (shield) + inner offset eye with sweep negative space.
 * - Works at 16px favicon through to 48px sidebar.
 * - No external assets; pure SVG for crisp scaling.
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
        {/* outer shield/diamond */}
        <path
          d="M16 2 L28 10 V22 L16 30 L4 22 V10 Z"
          stroke="#00e0ff"
          strokeWidth="1.6"
          fill="rgba(0,224,255,0.08)"
        />
        {/* inner eye — offset double arc */}
        <path
          d="M11 16 C11 11.8 13.4 9.2 16 9.2 C18.6 9.2 21 11.8 21 16 C21 20.2 18.6 22.8 16 22.8 C13.4 22.8 11 20.2 11 16Z"
          stroke="#00e0ff"
          strokeWidth="1.5"
          fill="none"
        />
        {/* radar sweep negative */}
        <path d="M16 16 L16 9.2 A6.8 6.8 0 0 1 21 16 Z" fill="#00e0ff" opacity={0.9} />
        {/* pupil */}
        <circle cx={16} cy={16} r={2.1} fill="#0a0f1c" stroke="#00e0ff" strokeWidth={1.2} />
        {/* violet depth accent */}
        <circle cx={16} cy={16} r={6.8} stroke="#7c3aed" strokeWidth={0.9} opacity={0.45} strokeDasharray="2 3" />
      </svg>

      {withWordmark && !collapsed && (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-bold tracking-[0.14em] text-content-primary">
            {BRAND_NAME}
          </span>
          <span className="text-[10px] font-medium tracking-[0.18em] text-content-tertiary -mt-0.5">
            THREAT OPS
          </span>
        </span>
      )}
    </span>
  );
};

export default BrandLogo;
