import React from "react";
import { BRAND_NAME } from "../constants/brand";

type Props = {
  collapsed?: boolean;
  size?: number;
  withWordmark?: boolean;
  mono?: boolean;
  className?: string;
};

/**
 * NOCTRA mark — "The Night Signal".
 *
 * An N whose right stroke breaks into a rising signal arc with a detached
 * dot: the analyst transmitting a finding into the night. Geometric,
 * ownable, legible at 16px. Construction + clear-space rules live in
 * docs/noctra-redesign-spec.md §12–13.
 */
const BrandLogo: React.FC<Props> = ({
  collapsed = false,
  size = 28,
  withWordmark = true,
  mono = false,
  className,
}) => {
  const stroke = mono ? "currentColor" : "#a8a2ff"; // brand accent
  const dotFill = mono ? "currentColor" : "#c9c4ff"; // the finding

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
        {/* Left stroke of the N */}
        <path d="M8 26 V6" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" />
        {/* Diagonal — top-left to bottom-right */}
        <path d="M8 7 L21.5 24" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" />
        {/* Right stroke, stopping short of the top… */}
        <path d="M22 26 V15.5" stroke={stroke} strokeWidth="2.4" strokeLinecap="round" />
        {/* …where it releases into a signal arc… */}
        <path
          d="M22 15 C22 11.8 24.3 9.8 26.6 9.4"
          stroke={stroke}
          strokeWidth="2.2"
          strokeLinecap="round"
        />
        {/* …and the finding (dot) travels on. */}
        <circle cx="27.2" cy="6" r="2.2" fill={dotFill} />
      </svg>

      {withWordmark && !collapsed && (
        <span className="flex flex-col leading-none">
          <span className="text-[15px] font-extrabold font-display tracking-[0.18em] text-content-primary">
            {BRAND_NAME}
          </span>
          <span className="text-[9px] font-bold tracking-[0.28em] text-accent-primary uppercase mt-0.5">
            Autonomous Analyst
          </span>
        </span>
      )}
    </span>
  );
};

export default BrandLogo;
